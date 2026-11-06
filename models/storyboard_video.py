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

"""Video-model routing for the Storyboarder workflow.

Storyboarder animates each keyframe with an image-to-video call. This module
lets the page offer Gemini Omni and Veo models side by side and hides the
differences between the two request shapes.
"""

from common.error_handling import GenerationError
from config.omni_models import get_models_by_mode, get_omni_model_config
from config.veo_models import VEO_MODELS, get_veo_model_config
from models.omni import generate_omni_video
from models.requests import OmniVideoGenerationRequest
from models.veo import VideoGenerationRequest, generate_video

# Every storyboard clip is the same length and resolution so clips from
# different models stitch together cleanly.
STORYBOARD_CLIP_SECONDS = 4
STORYBOARD_CLIP_RESOLUTION = "720p"

# Aspect ratios the Storyboarder page offers when the model has no limits of
# its own (Veo).
STORYBOARD_ASPECT_RATIOS = ["16:9", "9:16", "1:1"]


def is_omni_model(version_id: str) -> bool:
    """Return True if the id belongs to a registered Gemini Omni model."""
    return get_omni_model_config(version_id) is not None


def video_model_options() -> list[tuple[str, str]]:
    """Return ``(label, version_id)`` pairs for the video model dropdown.

    Omni models that can animate an image come first, followed by Veo.
    """
    omni = [(m.display_name, m.version_id) for m in get_models_by_mode("i2v")]
    veo = [(m.display_name, m.version_id) for m in VEO_MODELS]
    return omni + veo


def supported_aspect_ratios(version_id: str) -> list[str]:
    """Return the storyboard aspect ratios a video model can animate."""
    omni = get_omni_model_config(version_id)
    if omni:
        return list(omni.supported_aspect_ratios)
    return list(STORYBOARD_ASPECT_RATIOS)


def generate_storyboard_clip(
    version_id: str,
    image_gcs_uri: str,
    prompt: str,
    aspect_ratio: str,
) -> str | None:
    """Animates one storyboard keyframe into a clip.

    Args:
        version_id: Omni or Veo model version id.
        image_gcs_uri: GCS URI of the keyframe image.
        prompt: The scene's video prompt.
        aspect_ratio: The storyboard aspect ratio.

    Returns:
        The GCS URI of the generated clip, or None if no video was returned.

    Raises:
        GenerationError: If the model is unknown or cannot produce the aspect.

    """
    omni = get_omni_model_config(version_id)
    if omni:
        if aspect_ratio not in omni.supported_aspect_ratios:
            supported = ", ".join(omni.supported_aspect_ratios)
            raise GenerationError(
                f"{omni.display_name} supports {supported} only; "
                f"choose one of those aspect ratios (got {aspect_ratio}).",
            )
        gcs_uri, _ = generate_omni_video(
            OmniVideoGenerationRequest(
                prompt=prompt,
                duration_seconds=STORYBOARD_CLIP_SECONDS,
                aspect_ratio=aspect_ratio,
                resolution=STORYBOARD_CLIP_RESOLUTION,
                omni_mode="i2v",
                model_version_id=omni.version_id,
                reference_image_gcs=image_gcs_uri,
                reference_image_mime_type="image/png",
            ),
        )
        return gcs_uri or None

    if not get_veo_model_config(version_id):
        raise GenerationError(f"Unsupported storyboard video model: {version_id}")

    video_uris, _ = generate_video(
        VideoGenerationRequest(
            model_version_id=version_id,
            reference_image_gcs=image_gcs_uri,
            reference_image_mime_type="image/png",
            duration_seconds=STORYBOARD_CLIP_SECONDS,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            video_count=1,
            resolution=STORYBOARD_CLIP_RESOLUTION,
            enhance_prompt=True,
            generate_audio=True,
            person_generation="Allow (Adults only)",
        ),
    )
    return video_uris[0] if video_uris else None
