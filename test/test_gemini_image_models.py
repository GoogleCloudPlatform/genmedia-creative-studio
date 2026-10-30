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

"""Unit tests for Gemini Image Generation model registry and configuration."""

import os
import sys
from pathlib import Path
from typing import NoReturn
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("PROJECT_ID", "test-project")
os.environ.setdefault("LOCATION", "us-central1")
os.environ.setdefault("VEO_PROJECT_ID", "test-project")
os.environ.setdefault("VEO_LOCATION", "us-central1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.gemini_image_models import (
    GEMINI_IMAGE_MODELS,
    get_gemini_image_model_config,
)


def test_gemini_31_flash_lite_config_lookup() -> None:
    """Test lookup of gemini-3.1-flash-lite-image by short ID and full model name."""
    by_short = get_gemini_image_model_config("3.1-flash-lite")
    assert by_short is not None
    assert by_short.model_name == "gemini-3.1-flash-lite-image"
    assert by_short.display_name == "Gemini 3.1 Flash-Lite"

    by_full = get_gemini_image_model_config("gemini-3.1-flash-lite-image")
    assert by_full is not None
    assert by_full == by_short


def test_gemini_31_flash_lite_capabilities() -> None:
    """Test capability restrictions for Nano Banana 2 Lite."""
    cfg = get_gemini_image_model_config("3.1-flash-lite")
    assert cfg is not None
    assert cfg.supported_image_sizes == [
        "1K",
    ], "NB2Lite must only support 1K image size."
    assert cfg.requires_base_url is True
    assert cfg.supports_search is False, "Grounding is not supported by NB2Lite."
    assert cfg.supports_thinking is True
    assert len(cfg.supported_aspect_ratios) == 14
    assert "video/mp4" in cfg.supported_input_mime_types


def test_gemini_25_flash_image_removed() -> None:
    """Regression: gemini-2.5-flash-image must not be a selectable option.

    The 2.5-flash entry was removed as deprecation hygiene while the surviving
    models (nano-banana-2.1 default and the 3.1 series) remain selectable.
    """
    model_names = {m.model_name for m in GEMINI_IMAGE_MODELS}
    version_ids = {m.version_id for m in GEMINI_IMAGE_MODELS}

    # Removed model is gone by both full name and short version ID.
    assert "gemini-2.5-flash-image" not in model_names
    assert "2.5-flash" not in version_ids
    assert get_gemini_image_model_config("gemini-2.5-flash-image") is None
    assert get_gemini_image_model_config("2.5-flash") is None

    # Surviving models remain present.
    assert "gemini-nano-banana-2.1" in model_names
    assert "gemini-3.1-flash-image" in model_names
    assert "gemini-3.1-flash-lite-image" in model_names


def test_gemini_nano_banana_21_config_lookup() -> None:
    """Test lookup of gemini-nano-banana-2.1 by short ID and full model name."""
    by_short = get_gemini_image_model_config("nano-banana-2.1")
    assert by_short is not None
    assert by_short.model_name == "gemini-nano-banana-2.1"
    assert by_short.display_name == "Gemini Nano Banana 2.1"

    by_full = get_gemini_image_model_config("gemini-nano-banana-2.1")
    assert by_full is not None
    assert by_full == by_short


def test_gemini_nano_banana_21_capabilities() -> None:
    """Pin the doc-accurate capabilities for Nano Banana 2.1."""
    cfg = get_gemini_image_model_config("gemini-nano-banana-2.1")
    assert cfg is not None
    assert cfg.max_input_images == 14
    # Validated on the default Vertex endpoint (spike 2026-10-06): no base_url.
    assert cfg.requires_base_url is False
    assert cfg.supports_search is True, "NB2.1 supports Google/image search grounding."
    assert cfg.supports_thinking is True
    # Doc: 15 aspect ratios, including the portrait 9:21 ratio.
    assert len(cfg.supported_aspect_ratios) == 15
    assert "9:21" in cfg.supported_aspect_ratios
    # Doc resolutions: 1K/2K/4K.
    assert cfg.supported_image_sizes == ["1K", "2K", "4K"]
    # Doc input MIME adds HEIC/HEIF; video input is supported.
    assert "image/heic" in cfg.supported_input_mime_types
    assert "image/heif" in cfg.supported_input_mime_types
    assert "video/mp4" in cfg.supported_input_mime_types


def test_generate_and_save_persists_exception_media_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify _generate_and_save persists a reviewable MediaItem on exception (#1729)."""
    import pages.gemini_image_generation as page_mod

    fake_state = page_mod.PageState(
        selected_model="gemini-nano-banana-2.1",
        aspect_ratio="16:9",
        num_images_to_generate=1,
        previous_media_item_id="prev-123",
    )
    fake_app_state = MagicMock()
    fake_app_state.user_email = "tester@example.com"

    def fake_me_state(cls: type) -> object:
        if cls is page_mod.PageState:
            return fake_state
        return fake_app_state

    persisted_items: list[page_mod.MediaItem] = []

    def fake_add_to_firestore(item: page_mod.MediaItem) -> None:
        item.id = "failed-item-456"
        persisted_items.append(item)

    def fake_generate(**_kwargs: object) -> NoReturn:
        msg = "Vertex quota exceeded"
        raise RuntimeError(msg)

    def fake_snackbar(state: page_mod.PageState, message: str) -> object:
        state.snackbar_message = message
        state.show_snackbar = True
        yield

    monkeypatch.setattr(page_mod.me, "state", fake_me_state)
    monkeypatch.setattr(page_mod, "add_media_item_to_firestore", fake_add_to_firestore)
    monkeypatch.setattr(
        page_mod,
        "generate_image_from_prompt_and_images",
        fake_generate,
    )
    monkeypatch.setattr(page_mod, "show_snackbar", fake_snackbar)

    gen = page_mod._generate_and_save(
        base_prompt="A futuristic city",
        input_gcs_uris=["gs://bucket/ref.png"],
    )
    list(gen)

    assert len(persisted_items) == 1
    item = persisted_items[0]
    assert item.prompt == "A futuristic city"
    assert item.model == "gemini-nano-banana-2.1"
    assert item.aspect == "16:9"
    assert item.user_email == "tester@example.com"
    assert item.source_images_gcs == ["gs://bucket/ref.png"]
    assert item.related_media_item_id == "prev-123"
    assert item.error_message == "Vertex quota exceeded"
    assert item.generation_time is not None
    assert item.generation_time >= 0
    assert fake_state.previous_media_item_id == "failed-item-456"
    assert fake_state.is_generating is False
    assert fake_state.generation_complete is True
    assert "Vertex quota exceeded" in fake_state.snackbar_message
