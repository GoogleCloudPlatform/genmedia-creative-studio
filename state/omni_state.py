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

"""Page state definitions for the Gemini Omni workspace."""

import mesop as me

from config.omni_models import DEFAULT_OMNI_VERSION_ID


@me.stateclass
class PageState:
    """Mesop Page State for Gemini Omni."""

    omni_model: str = DEFAULT_OMNI_VERSION_ID
    omni_prompt_input: str = ""
    omni_mode: str = "t2v"  # "t2v", "i2v", "ref2v", "edit", "extend", "upscale"

    prompt: str = (
        "A head-on shot of a neon sign that reads 'Omni' glowing against a brick wall."
    )
    aspect_ratio: str = "16:9"
    resolution: str = "720p"
    video_length: int = 10

    # I2V or Editing base Image
    reference_image_file: me.UploadedFile = None
    reference_image_file_key: int = 0
    reference_image_gcs: str = ""
    reference_image_uri: str = ""
    reference_image_mime_type: str = ""

    # Editing base Video
    reference_video_file: me.UploadedFile = None
    reference_video_file_key: int = 0
    reference_video_gcs: str = ""
    reference_video_uri: str = ""
    reference_video_mime_type: str = ""

    # Video Direct Upload temporary states
    video_upload_signed_url: str = ""
    video_upload_gcs_uri: str = ""
    video_upload_progress: int = 0
    video_upload_error: str = ""

    # Serialized list for Ref2V reference images list.
    # List of dicts specifying GCS URI, mime type, and display URL.
    r2v_references_json: str = "[]"
    r2v_upload_key: int = 0

    # Multi-turn interaction context
    previous_interaction_id: str = ""

    # Raw SDK input list serialized.
    # List of user inputs and model outputs.
    chat_history_json: str = "[]"

    # UI chat representation.
    # List of message objects containing role, text, and media URLs.
    chat_messages_json: str = "[]"

    # UI loading and dialog states
    is_loading: bool = False
    show_error_dialog: bool = False
    info_dialog_open: bool = False
    error_message: str = ""

    # Output results (Single generation fallback)
    result_gcs_uri: str = ""
    result_display_url: str = ""
