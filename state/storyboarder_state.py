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

from dataclasses import field

import mesop as me


@me.stateclass
class PageState:
    """Storyboarder Page State."""

    # Input
    prompt: str = ""
    uploaded_image_gcs_uris: list[str] = field(default_factory=list)
    uploaded_image_display_urls: list[str] = field(default_factory=list)

    # Story Sequencer / Narrative State
    story_narrative: str = ""
    scene_narratives: list[str] = field(default_factory=list)
    scene_image_prompts: list[str] = field(default_factory=list)
    scene_video_prompts: list[str] = field(default_factory=list)
    is_generating_story: bool = False

    # Character Asset Sheet State
    character_source_gcs_uri: str = ""
    character_source_display_url: str = ""
    character_sheet_gcs_uri: str = ""
    character_sheet_display_url: str = ""
    is_generating_character_sheet: bool = False

    # Image Generation
    generated_image_urls: list[str] = field(default_factory=list)
    generated_image_gcs_uris: list[str] = field(default_factory=list)
    image_captions: list[str] = field(default_factory=list)
    is_generating_images: bool = False

    # Video Generation
    is_generating_video: bool = False
    video_generation_status: str = ""
    generated_video_clips: list[str] = field(default_factory=list)  # List of GCS URIs
    generated_video_clips_display_urls: list[str] = field(
        default_factory=list,
    )  # List of display URLs for inline players
    final_video_uri: str = ""
    final_video_display_url: str = ""

    # Settings & Models
    aspect_ratio: str = "16:9"
    num_images: int = 4
    selected_image_model: str = "nano-banana-2.1"
    selected_narrative_model: str = "gemini-3.5-flash"
    selected_video_model: str = "3.1-lite"

    # UI
    show_snackbar: bool = False
    snackbar_message: str = ""
    info_dialog_open: bool = False
