# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the Character Consistency edit path after the Nano Banana port.

The mask-based Imagen edit model ``imagen-3.0-capability-001`` sunsets on
2026-06-30 and has no like-for-like replacement. The Character Consistency edit
steps (subject-customization candidates + 16:9 reframe) were PORTED to the
prompt-based Gemini Image (Nano Banana) adapter
``models.gemini.generate_image_from_prompt_and_images``.

This module previously asserted the removed ``client.models.edit_image`` /
``SubjectReferenceImage`` mask contract. It now:
  * statically guards that the removed Imagen mask-edit contract is gone
    (runs without any third-party deps or Vertex credentials); and
  * unit-tests the two ported helpers with the Gemini adapter mocked (no live
    calls); and
  * keeps an opt-in ``integration`` test for the live Gemini image path.
"""

# ruff: noqa: S101

import re
from pathlib import Path
from unittest import mock

import pytest

_CC_SOURCE_PATH = (
    Path(__file__).resolve().parent.parent / "models" / "character_consistency.py"
)
_CONFIG_SOURCE_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "default.py"
)


# ---------------------------------------------------------------------------
# Static guards — dependency-free; assert the retired mask-edit contract is gone.
# ---------------------------------------------------------------------------


def _strip_docstrings_and_comments(source: str) -> str:
    """Removes triple-quoted strings and ``#`` comments so guards match runtime
    code only (deprecation notes intentionally mention the old identifiers)."""
    source = re.sub(r'"""(?:.|\n)*?"""', "", source)
    source = re.sub(r"'''(?:.|\n)*?'''", "", source)
    source = re.sub(r"#.*", "", source)
    return source


def test_cc_source_has_no_imagen_mask_edit_runtime_refs() -> None:
    """The retired mask-based Imagen edit contract must be gone from runtime code."""
    runtime = _strip_docstrings_and_comments(_CC_SOURCE_PATH.read_text())
    for forbidden in (
        "imagen-3.0-capability-001",
        "CHARACTER_CONSISTENCY_IMAGEN_MODEL",
        "edit_image",
        "SubjectReferenceImage",
        "RawReferenceImage",
        "MaskReferenceImage",
        "EditImageConfig",
    ):
        assert forbidden not in runtime, (
            f"{forbidden!r} still referenced in runtime code of "
            "character_consistency.py after the Nano Banana port"
        )


def test_config_dropped_cc_imagen_model_constant() -> None:
    """``CHARACTER_CONSISTENCY_IMAGEN_MODEL`` must be removed from config."""
    runtime = _strip_docstrings_and_comments(_CONFIG_SOURCE_PATH.read_text())
    assert "CHARACTER_CONSISTENCY_IMAGEN_MODEL" not in runtime


def test_cc_source_uses_gemini_adapter() -> None:
    """The port must route the edit steps through the Gemini (Nano Banana) adapter."""
    runtime = _strip_docstrings_and_comments(_CC_SOURCE_PATH.read_text())
    assert "generate_image_from_prompt_and_images" in runtime


# ---------------------------------------------------------------------------
# Unit tests for the ported helpers (Gemini adapter mocked; no live calls).
# ---------------------------------------------------------------------------


@pytest.fixture
def cc_module():
    """Imports the CC module or skips if third-party deps are unavailable.

    Importing ``models.character_consistency`` pulls in ``google.genai`` and
    constructs (lazily, no network) a Vertex client. In environments without the
    installed dependencies (e.g. this sandbox) the import is skipped; the static
    guards above still run and the live integration test covers the wire path.
    """
    try:
        import models.character_consistency as cc  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"character_consistency import unavailable: {exc}")
    return cc


def _fake_adapter_return(gcs_uris):
    """Mimics generate_image_from_prompt_and_images' 5-tuple return shape."""
    return (gcs_uris, 0.0, ["caption"], None, [])


def test_generate_gemini_candidates_calls_adapter_per_candidate(cc_module) -> None:
    """Candidates come from the Gemini adapter (1 image/call), N calls, with bytes."""
    calls = []

    def fake_adapter(prompt, images, **kwargs):
        calls.append((prompt, images, kwargs))
        return _fake_adapter_return([f"gs://bucket/candidate_{len(calls)}.png"])

    with mock.patch.object(
        cc_module, "generate_image_from_prompt_and_images", side_effect=fake_adapter
    ), mock.patch.object(
        cc_module, "download_from_gcs", side_effect=lambda uri: b"bytes"
    ):
        uris, byts = cc_module._generate_gemini_candidates(
            "a hero on a rooftop",
            ["gs://bucket/ref1.png", "gs://bucket/ref2.png"],
            num_candidates=4,
        )

    assert len(calls) == 4, "one adapter call per requested candidate"
    assert sorted(uris) == [f"gs://bucket/candidate_{i}.png" for i in range(1, 5)]
    assert byts == [b"bytes"] * 4
    # Every call is prompt-based (mask-free) at 1:1 with the reference images.
    for _prompt, images, kwargs in calls:
        assert images == ["gs://bucket/ref1.png", "gs://bucket/ref2.png"]
        assert kwargs["aspect_ratio"] == "1:1"


def test_generate_gemini_candidates_folds_negative_prompt(cc_module) -> None:
    """The negative prompt is folded into the prompt text (adapter has no such input)."""
    seen_prompts = []

    def fake_adapter(prompt, images, **kwargs):
        seen_prompts.append(prompt)
        return _fake_adapter_return(["gs://bucket/candidate.png"])

    with mock.patch.object(
        cc_module, "generate_image_from_prompt_and_images", side_effect=fake_adapter
    ), mock.patch.object(cc_module, "download_from_gcs", side_effect=lambda uri: b"b"):
        cc_module._generate_gemini_candidates(
            "a hero on a rooftop",
            ["gs://bucket/ref1.png"],
            negative_prompt="blurry, deformed hands",
            num_candidates=2,
        )

    assert seen_prompts, "adapter should have been called"
    for prompt in seen_prompts:
        assert "a hero on a rooftop" in prompt
        assert "blurry, deformed hands" in prompt
        assert "Avoid" in prompt


def test_generate_gemini_candidates_raises_when_all_empty(cc_module) -> None:
    """If every candidate call returns no image, raise instead of feeding an empty set."""
    with mock.patch.object(
        cc_module,
        "generate_image_from_prompt_and_images",
        side_effect=lambda *a, **k: _fake_adapter_return([]),
    ), mock.patch.object(cc_module, "download_from_gcs", side_effect=lambda uri: b""):
        with pytest.raises(RuntimeError):
            cc_module._generate_gemini_candidates(
                "prompt", ["gs://bucket/ref1.png"], num_candidates=4
            )


def test_fold_negative_prompt_noop_when_absent(cc_module) -> None:
    """No negative prompt (None / blank) leaves the prompt unchanged."""
    assert cc_module._fold_negative_prompt("p", None) == "p"
    assert cc_module._fold_negative_prompt("p", "   ") == "p"
    assert "Avoid" in cc_module._fold_negative_prompt("p", "ugly")


def test_reframe_image_to_16_9_uses_gemini_adapter(cc_module) -> None:
    """The reframe (old outpaint) step is a prompt-based 16:9 Gemini edit."""
    captured = {}

    def fake_adapter(prompt, images, **kwargs):
        captured["prompt"] = prompt
        captured["images"] = images
        captured["kwargs"] = kwargs
        return _fake_adapter_return(["gs://bucket/outpainted_0.png"])

    with mock.patch.object(
        cc_module, "generate_image_from_prompt_and_images", side_effect=fake_adapter
    ), mock.patch.object(
        cc_module, "download_from_gcs", side_effect=lambda uri: b"reframed"
    ):
        uri, byts = cc_module._reframe_image_to_16_9(
            "gs://bucket/best.png", "a hero on a rooftop"
        )

    assert uri == "gs://bucket/outpainted_0.png"
    assert byts == b"reframed"
    assert captured["images"] == ["gs://bucket/best.png"]
    assert captured["kwargs"]["aspect_ratio"] == "16:9"
    assert "16:9" in captured["prompt"]


def test_reframe_image_raises_when_adapter_returns_nothing(cc_module) -> None:
    """A failed (empty) reframe must raise, not silently return a bad image."""
    with mock.patch.object(
        cc_module,
        "generate_image_from_prompt_and_images",
        side_effect=lambda *a, **k: _fake_adapter_return([]),
    ), mock.patch.object(cc_module, "download_from_gcs", side_effect=lambda uri: b""):
        with pytest.raises(RuntimeError):
            cc_module._reframe_image_to_16_9("gs://bucket/best.png", "prompt")


# ---------------------------------------------------------------------------
# Live integration test (opt-in): exercises the Gemini image wire path.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_gemini_nano_banana_image_edit_live() -> None:
    """Live smoke test of the prompt-based Gemini (Nano Banana) image edit path.

    Requires Vertex credentials + network (run post-merge as the CC edit-path
    credentialed smoke test). Uploads a dummy reference image to GCS and asks the
    adapter to produce an image from a prompt + that reference.
    """
    import io
    import uuid

    from PIL import Image

    from common.storage import store_to_gcs
    from models.gemini import generate_image_from_prompt_and_images

    img = Image.new("RGB", (1024, 1024), color="blue")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    ref_gcs_uri = store_to_gcs(
        folder="character_consistency_test",
        file_name=f"ref_{uuid.uuid4()}.png",
        mime_type="image/png",
        contents=buf.getvalue(),
    )

    gcs_uris, _, _, _, _ = generate_image_from_prompt_and_images(
        "A cinematic portrait of the subject on a neon rooftop at night.",
        [ref_gcs_uri],
        aspect_ratio="1:1",
        gcs_folder="character_consistency_test",
        file_prefix="candidate",
    )

    assert gcs_uris, "Gemini image edit returned no image"
    assert gcs_uris[0].startswith("gs://")


if __name__ == "__main__":
    test_cc_source_has_no_imagen_mask_edit_runtime_refs()
    test_config_dropped_cc_imagen_model_constant()
    test_cc_source_uses_gemini_adapter()
    print("Static guards passed.")
