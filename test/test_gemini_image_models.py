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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.gemini_image_models import get_gemini_image_model_config


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
    assert cfg.supported_image_sizes == ["1K"], (
        "NB2Lite must only support 1K image size."
    )
    assert cfg.requires_base_url is True
    assert cfg.supports_search is False, "Grounding is not supported by NB2Lite."
    assert cfg.supports_thinking is True
    assert len(cfg.supported_aspect_ratios) == 14
    assert "video/mp4" in cfg.supported_input_mime_types


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
