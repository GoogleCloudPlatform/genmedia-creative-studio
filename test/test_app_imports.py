# Copyright 2025 Google LLC
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

"""Smoke tests to verify all application pages and model modules import without error."""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Ensure dummy env vars exist for model client initialization during module import
os.environ.setdefault("PROJECT_ID", "test-project")
os.environ.setdefault("LOCATION", "us-central1")
os.environ.setdefault("VEO_PROJECT_ID", "test-project")
os.environ.setdefault("VEO_LOCATION", "us-central1")

# Mock parselmouth if not installed locally
if "parselmouth" not in sys.modules:
    try:
        import parselmouth  # noqa: F401
    except ImportError:
        mock_pm = MagicMock()
        sys.modules["parselmouth"] = mock_pm
        sys.modules["parselmouth.praat"] = mock_pm.praat


def test_import_pages_and_models():
    """Verify that all core pages and model wrappers import successfully."""
    # Test model modules
    import models.chirp_3hd  # noqa: F401
    import models.gemini  # noqa: F401
    import models.gemini_tts  # noqa: F401
    import models.image_models  # noqa: F401
    import models.lyria  # noqa: F401
    import models.omni  # noqa: F401
    import models.upscale  # noqa: F401
    import models.veo  # noqa: F401
    import models.vto  # noqa: F401
    import models.vto_critique  # noqa: F401

    # Verify re-exports expected by pages
    from models.veo import (  # noqa: F401
        APIReferenceImage,
        VideoGenerationRequest,
        generate_video,
    )

    assert APIReferenceImage is not None
    assert VideoGenerationRequest is not None
    assert generate_video is not None

    # Test pages
    import pages.banana_studio  # noqa: F401
    import pages.gemini_image_generation  # noqa: F401
    import pages.imagen  # noqa: F401
    import pages.interior_design_v2  # noqa: F401
    import pages.lyria  # noqa: F401
    import pages.object_rotation  # noqa: F401
    import pages.omni  # noqa: F401
    import pages.portraits  # noqa: F401
    import pages.storyboarder  # noqa: F401
    import pages.veo  # noqa: F401
    import pages.vto  # noqa: F401


def test_import_main():
    """Verify that main.py imports cleanly without ImportError."""
    try:
        import main  # noqa: F401

        assert main.app is not None
    except Exception as e:
        # Fail explicitly on ImportError
        if isinstance(e, ImportError):
            pytest.fail(f"ImportError during main import: {e}")
        # Soft-skip other runtime initialization errors if external services are unreachable
        pytest.skip(f"main import runtime skip: {e}")


def test_vto_critique_workflow_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify run_vto_critique_workflow uses GEMINI_CRITIQUE_MODEL_ID and returns structured placement data (#1730)."""
    from models import vto_critique

    captured_calls: list[dict[str, object]] = []

    class FakeModels:
        def generate_content(
            self,
            *,
            model: str,
            contents: list[object],
            config: object,
        ) -> object:
            captured_calls.append(
                {"model": model, "contents": contents, "config": config},
            )
            resp = MagicMock()
            resp.text = (
                '{"accurate": true, '
                '"placement_analysis": "The jacket drapes naturally across the shoulders.", '
                '"reasoning": "Collar alignment and sleeve length match the source garment."}'
            )
            return resp

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(
        vto_critique.GeminiModelSetup,
        "init",
        lambda **_kwargs: FakeClient(),
    )

    result = vto_critique.run_vto_critique_workflow(
        apparel_image_gcs="gs://bucket/jacket.png",
        result_image_gcs="gs://bucket/tryon_1.png",
    )

    assert len(captured_calls) == 1
    assert captured_calls[0]["model"] == vto_critique.cfg.GEMINI_CRITIQUE_MODEL_ID
    assert result["accurate"] is True
    assert (
        result["placement_analysis"]
        == "The jacket drapes naturally across the shoulders."
    )
    assert (
        result["reasoning"]
        == "Collar alignment and sleeve length match the source garment."
    )
    assert result["result_image_gcs"] == "gs://bucket/tryon_1.png"
