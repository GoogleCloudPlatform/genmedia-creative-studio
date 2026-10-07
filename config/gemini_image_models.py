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

"""Configuration and registry for Gemini Image Generation models."""

from dataclasses import dataclass, field


@dataclass
class GeminiImageModelConfig:
    """Configuration for a specific Gemini Image Generation model version."""

    version_id: str  # Short ID for UI/Logic (e.g., "3.0-pro", "3.1-flash")
    model_name: str  # Full API Model ID (e.g., "gemini-3.1-flash-image")
    display_name: str  # Human-readable name (e.g., "Gemini 3.1 Flash")
    button_label: str  # Label for the UI button (e.g., "Flash", "Pro", "2")

    # Capabilities
    max_input_images: int
    max_output_images: int
    requires_base_url: bool = False

    supported_aspect_ratios: list[str] = field(
        default_factory=lambda: [
            "1:1",
            "3:2",
            "2:3",
            "3:4",
            "4:3",
            "4:5",
            "5:4",
            "9:16",
            "16:9",
            "21:9",
        ],
    )
    supported_image_sizes: list[str] = field(
        default_factory=lambda: ["1K", "2K"],
    )
    supported_input_mime_types: list[str] = field(
        default_factory=lambda: [
            "image/jpeg",
            "image/png",
            "image/webp",
            "application/pdf",
        ],
    )

    # Future-proofing
    supports_negative_prompt: bool = False
    supports_person_generation_filter: bool = True
    supports_search: bool = False
    supports_thinking: bool = False


# Single source of truth
GEMINI_IMAGE_MODELS: list[GeminiImageModelConfig] = [
    GeminiImageModelConfig(
        version_id="3.0-pro",
        model_name="gemini-3-pro-image",
        display_name="Gemini 3 Pro",
        button_label="Pro",
        max_input_images=14,
        max_output_images=1,
        requires_base_url=True,
        supported_image_sizes=["1K", "2K", "4K"],
        supports_search=True,
    ),
    GeminiImageModelConfig(
        version_id="3.1-flash",
        model_name="gemini-3.1-flash-image",
        display_name="Gemini 3.1 Flash",
        button_label="2",
        max_input_images=14,
        max_output_images=1,
        requires_base_url=True,
        supported_aspect_ratios=[
            "1:1",
            "3:2",
            "2:3",
            "3:4",
            "4:3",
            "1:4",
            "4:1",
            "4:5",
            "5:4",
            "1:8",
            "8:1",
            "9:16",
            "16:9",
            "21:9",
        ],
        supported_image_sizes=["512", "1K", "2K", "4K"],
        supported_input_mime_types=[
            "image/jpeg",
            "image/png",
            "image/webp",
            "application/pdf",
            "video/mp4",
            "video/quicktime",
            "video/x-matroska",
            "video/webm",
        ],
        supports_search=True,
        supports_thinking=True,
    ),
    GeminiImageModelConfig(
        version_id="3.1-flash-lite",
        model_name="gemini-3.1-flash-lite-image",
        display_name="Gemini 3.1 Flash-Lite",
        button_label="2 Lite",
        max_input_images=14,
        max_output_images=1,
        requires_base_url=True,
        supported_aspect_ratios=[
            "1:1",
            "3:2",
            "2:3",
            "3:4",
            "4:3",
            "1:4",
            "4:1",
            "4:5",
            "5:4",
            "1:8",
            "8:1",
            "9:16",
            "16:9",
            "21:9",
        ],
        supported_image_sizes=["1K"],
        supported_input_mime_types=[
            "image/jpeg",
            "image/png",
            "image/webp",
            "application/pdf",
            "video/mp4",
            "video/quicktime",
            "video/x-matroska",
            "video/webm",
        ],
        supports_search=False,
        supports_thinking=True,
    ),
    GeminiImageModelConfig(
        version_id="nano-banana-2.1",
        model_name="gemini-nano-banana-2.1",
        display_name="Gemini Nano Banana 2.1",
        button_label="2.1",
        max_input_images=14,
        max_output_images=1,
        # Validated live on the default Vertex `global` endpoint (2026-10-06
        # spike): the literal id works without a custom base_url, so the flag
        # stays False. See nanobanana-2.1-spike-2026-10-06.md.
        requires_base_url=False,
        # Doc: 15 aspect ratios, including 9:21. Ordered to match the sibling
        # gemini-3.1-flash-image entry, with the 2.1-only 9:21 appended.
        supported_aspect_ratios=[
            "1:1",
            "3:2",
            "2:3",
            "3:4",
            "4:3",
            "1:4",
            "4:1",
            "4:5",
            "5:4",
            "1:8",
            "8:1",
            "9:16",
            "16:9",
            "21:9",
            "9:21",
        ],
        supported_image_sizes=["1K", "2K", "4K"],
        # Doc input MIME: png/jpeg/webp/heic/heif; video input is supported.
        supported_input_mime_types=[
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/heic",
            "image/heif",
            "video/mp4",
            "video/quicktime",
            "video/x-matroska",
            "video/webm",
        ],
        supports_search=True,
        supports_thinking=True,
    ),
]


def get_gemini_image_model_config(
    model_name_or_version: str,
) -> GeminiImageModelConfig | None:
    """Find config by either full model name or short version ID."""
    for model in GEMINI_IMAGE_MODELS:
        if model_name_or_version in (model.model_name, model.version_id):
            return model
    return None
