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

"""Request contract definitions and models for GenMedia Creative Studio API."""

from typing import Optional

from pydantic import BaseModel, Field


class APIReferenceImage(BaseModel):
    """Represents a single reference image for the API request."""

    gcs_uri: str
    mime_type: str


class VideoGenerationRequest(BaseModel):
    """Defines the contract for a video generation request.

    This schema is used by the UI to call the model layer and will be
    the schema for the future FastAPI endpoint.
    """

    prompt: str
    duration_seconds: int = Field(..., gt=0)
    video_count: int
    aspect_ratio: str
    resolution: str
    enhance_prompt: bool
    generate_audio: bool
    model_version_id: str
    person_generation: str
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    rewriter_type: Optional[str] = None

    # For I2V and Interpolation
    reference_image_gcs: Optional[str] = None
    last_reference_image_gcs: Optional[str] = None
    reference_image_mime_type: Optional[str] = None
    last_reference_image_mime_type: Optional[str] = None

    # For R2V
    r2v_references: Optional[list[APIReferenceImage]] = None
    r2v_style_image: Optional[APIReferenceImage] = None

    # For Video Extension
    video_input_gcs: Optional[str] = None
    video_input_mime_type: Optional[str] = None


class OmniVideoGenerationRequest(BaseModel):
    """Defines the contract for a Gemini Omni video generation or editing request."""

    prompt: str
    duration_seconds: int = Field(..., gt=0)
    aspect_ratio: str
    resolution: str
    omni_mode: str  # "t2v", "i2v", "ref2v", "edit", "extend", "upscale"
    model_version_id: str

    # Reference Image GCS URIs
    reference_image_gcs: Optional[str] = None
    reference_image_mime_type: Optional[str] = None

    # Last frame image (first_last mode; reference_image_gcs is the first frame)
    last_reference_image_gcs: Optional[str] = None
    last_reference_image_mime_type: Optional[str] = None

    # Reference Video GCS URIs (for editing)
    reference_video_gcs: Optional[str] = None
    reference_video_mime_type: Optional[str] = None

    # Reference Media List (for ref2v)
    r2v_references: Optional[list[APIReferenceImage]] = None

    # Multi-turn interaction context
    previous_interaction_id: Optional[str] = None
    chat_history_json: Optional[str] = None
