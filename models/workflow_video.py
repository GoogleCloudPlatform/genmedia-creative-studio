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

"""Omni-or-Veo video generation for the Interior Design and Object Rotation workflows.

Both workflows pick their video model from an environment-driven model name
(``INTERIOR_DESIGN_VIDEO_MODEL`` / ``OBJECT_ROTATION_VIDEO_MODEL``). The name can
be a Gemini Omni model (``gemini-omni-*``) or a Veo model (``veo-*``); this
module routes the call and hides the two request shapes.
"""

from common.error_handling import GenerationError
from config.omni_models import clamp_duration, modes_for_model
from config.omni_models import get_version_id_by_model_name as omni_version_id
from config.veo_models import get_veo_model_config
from config.veo_models import get_version_id_by_model_name as veo_version_id
from models.omni import generate_omni_video
from models.requests import (
    APIReferenceImage,
    OmniVideoGenerationRequest,
    VideoGenerationRequest,
)
from models.veo import generate_video

WORKFLOW_RESOLUTION = "720p"
WORKFLOW_ASPECT_RATIO = "16:9"
ROTATION_OMNI_SECONDS = 8

# Fallbacks used when the configured name is not in either registry.
DEFAULT_VEO_I2V_VERSION = "3.1-lite"
DEFAULT_VEO_R2V_VERSION = "3.1"


def is_omni_model_name(model_name: str) -> bool:
    """Return True if a configured model name is a registered Omni model."""
    return omni_version_id(model_name) is not None


def generate_workflow_image_to_video(
    model_name: str,
    image_gcs_uri: str,
    prompt: str,
    duration_seconds: int,
) -> str | None:
    """Animate one image into a 16:9 720p clip with Omni or Veo.

    Args:
        model_name: Configured model name (``gemini-omni-*`` or ``veo-*``).
        image_gcs_uri: GCS URI of the source image (PNG).
        prompt: Camera/motion prompt.
        duration_seconds: Requested clip length (clamped for Omni models).

    Returns:
        The GCS URI of the generated clip, or None if no video was returned.

    Raises:
        GenerationError: If the Omni model cannot do image-to-video.

    """
    omni_version = omni_version_id(model_name)
    if omni_version:
        if "i2v" not in modes_for_model(omni_version):
            raise GenerationError(
                f"{model_name} does not support image-to-video.",
            )
        gcs_uri, _ = generate_omni_video(
            OmniVideoGenerationRequest(
                prompt=prompt,
                duration_seconds=clamp_duration(omni_version, duration_seconds),
                aspect_ratio=WORKFLOW_ASPECT_RATIO,
                resolution=WORKFLOW_RESOLUTION,
                omni_mode="i2v",
                model_version_id=omni_version,
                reference_image_gcs=image_gcs_uri,
                reference_image_mime_type="image/png",
            ),
        )
        return gcs_uri or None

    video_uris, _ = generate_video(
        request=VideoGenerationRequest(
            model_version_id=veo_version_id(model_name) or DEFAULT_VEO_I2V_VERSION,
            reference_image_gcs=image_gcs_uri,
            reference_image_mime_type="image/png",
            duration_seconds=duration_seconds,
            prompt=prompt,
            aspect_ratio=WORKFLOW_ASPECT_RATIO,
            video_count=1,
            enhance_prompt=False,
            generate_audio=False,
            resolution=WORKFLOW_RESOLUTION,
            person_generation="Allow (Adults only)",
        ),
    )
    return video_uris[0] if video_uris else None


def generate_workflow_reference_video(
    model_name: str,
    reference_gcs_uris: list[str],
    prompt: str,
) -> str | None:
    """Generate a 16:9 720p clip conditioned on reference images.

    Args:
        model_name: Configured model name (``gemini-omni-*`` or ``veo-*``).
        reference_gcs_uris: GCS URIs of the reference images (PNG), in order.
        prompt: The video prompt.

    Returns:
        The GCS URI of the generated clip, or None if no video was returned.

    Raises:
        GenerationError: If the model cannot do reference-to-video or is unknown.

    """
    references = [
        APIReferenceImage(gcs_uri=uri, mime_type="image/png")
        for uri in reference_gcs_uris
    ]

    omni_version = omni_version_id(model_name)
    if omni_version:
        if "ref2v" not in modes_for_model(omni_version):
            raise GenerationError(
                f"{model_name} does not support reference-to-video.",
            )
        gcs_uri, _ = generate_omni_video(
            OmniVideoGenerationRequest(
                prompt=prompt,
                duration_seconds=clamp_duration(omni_version, ROTATION_OMNI_SECONDS),
                aspect_ratio=WORKFLOW_ASPECT_RATIO,
                resolution=WORKFLOW_RESOLUTION,
                omni_mode="ref2v",
                model_version_id=omni_version,
                r2v_references=references,
            ),
        )
        return gcs_uri or None

    version = veo_version_id(model_name) or DEFAULT_VEO_R2V_VERSION
    veo_config = get_veo_model_config(version)
    if not veo_config:
        raise GenerationError(f"Unsupported video model: {model_name}")

    video_uris, _ = generate_video(
        VideoGenerationRequest(
            prompt=prompt,
            duration_seconds=veo_config.default_duration,
            video_count=1,
            aspect_ratio=veo_config.supported_aspect_ratios[0],
            resolution=WORKFLOW_RESOLUTION,
            enhance_prompt=True,
            generate_audio=True,
            model_version_id=version,
            person_generation="dont_allow",
            r2v_references=references,
        ),
    )
    return video_uris[0] if video_uris else None
