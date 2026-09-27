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

"""Service wrapper for interacting with EAP Gemini Omni Flash model."""

import base64
import json
import time
import uuid

from google import genai

from common.analytics import get_logger, track_model_call
from common.error_handling import ErrorCategory, GenerationError
from common.storage import download_from_gcs, store_to_gcs
from config.default import Default
from config.omni_models import get_omni_model_config
from models.requests import OmniVideoGenerationRequest

config = Default()
logger = get_logger(__name__)

_clients = {}


class MissingMediaError(GenerationError):
    """Raised when a request omits media that its Omni mode requires.

    This is raised *before* any model call is attempted, so a missing-input
    request is never recorded as a failed model_call and never reaches the
    billable Interactions API (issue #1929).
    """

    def __init__(self, message: str) -> None:
        """Initialize with an INVALID_ARGUMENT category (a client input error)."""
        super().__init__(message, category=ErrorCategory.INVALID_ARGUMENT)


def find_missing_required_media(
    omni_mode: str,
    *,
    has_image: bool,
    has_video: bool,
    reference_count: int,
) -> str | None:
    """Return a message describing missing required media for a mode, else None.

    This is a pure function (no I/O, no state) so it can back both the model
    boundary check and the UI button guard from a single source of truth.

    Per-mode required media (based on the Omni UI contract):
      - ``t2v``:   no media required.
      - ``i2v``:   a reference image is required.
      - ``ref2v``: at least one reference image is required.
      - ``edit``:  a base video to edit is required (image is optional).
    """
    if omni_mode == "i2v" and not has_image:
        return "Image-to-Video requires a reference image."
    if omni_mode == "ref2v" and reference_count < 1:
        return "Reference-to-Video requires at least one reference image."
    if omni_mode == "edit" and not has_video:
        return "Video editing requires a base video to edit."
    return None


def _validate_required_media(request: OmniVideoGenerationRequest) -> None:
    """Fail fast if the request omits media its mode requires.

    Multi-turn refinement operates on an existing interaction (it does not
    append single-turn reference media), so the per-mode media requirements do
    not apply when ``previous_interaction_id`` is set.
    """
    if request.previous_interaction_id:
        return

    missing = find_missing_required_media(
        request.omni_mode,
        has_image=bool(request.reference_image_gcs),
        has_video=bool(request.reference_video_gcs),
        reference_count=len(request.r2v_references or []),
    )
    if missing:
        raise MissingMediaError(missing)


def get_omni_client(location: str) -> genai.Client:
    """Get or create a genai.Client initialized with enterprise=True for Gemini Omni."""
    if location not in _clients:
        logger.info(
            f"Initializing GenAI Client for Omni on project {config.OMNI_PROJECT_ID} in {location}",
        )
        _clients[location] = genai.Client(
            enterprise=True,
            project=config.OMNI_PROJECT_ID,
            location=location,
            http_options={"timeout": config.OMNI_TIMEOUT_MS / 1000.0},
        )
    return _clients[location]


def generate_omni_video(request: OmniVideoGenerationRequest) -> tuple[str, str]:
    """Generate or edit a video using the EAP Gemini Omni Flash Interactions API.

    Args:
        request: The video generation or editing request options.

    Returns:
        A tuple containing the GCS URI of the saved video and the interaction ID.

    """
    model_config = get_omni_model_config(request.model_version_id)
    if not model_config:
        raise GenerationError(
            f"Unsupported Gemini Omni model: {request.model_version_id}",
        )

    # Validate required media *before* opening the model-call span, so a
    # missing-input request is never recorded as a failed model_call and never
    # reaches the billable Interactions API (issue #1929).
    _validate_required_media(request)

    billing_units = {
        "video_seconds_generated": request.duration_seconds,
        "sample_count": 1,
        "aspect_ratio": request.aspect_ratio,
        "omni_mode": request.omni_mode,
        "is_multiturn": bool(request.previous_interaction_id),
    }

    with track_model_call(model_config.model_name, billing_units=billing_units) as ctx:
        # 1. Resolve client
        client = get_omni_client(config.OMNI_LOCATION)

        # 2. Build input list
        input_parts = _build_input_parts(request)

        # 3. Call Interactions API
        try:
            call_args = {
                "model": model_config.model_name,
                "input": input_parts,
            }
            # Request the desired output resolution via the Interactions API
            # video response_format. Aspect ratio and duration continue to be
            # conveyed through the prompt text (see _modify_prompt_for_omni).
            if request.resolution:
                call_args["response_format"] = [
                    {"type": "video", "resolution": request.resolution},
                ]
            if request.previous_interaction_id:
                call_args["previous_interaction_id"] = request.previous_interaction_id

            logger.info(
                f"Calling client.interactions.create with model={model_config.model_name}",
            )
            interaction = client.interactions.create(
                **call_args,
                timeout=config.OMNI_TIMEOUT_MS / 1000.0,
            )

            # 4. Extract outputs
            video_data, interaction_id = _extract_video_payload(interaction)

            # 5. Decode and save
            gcs_uri = _save_video_to_gcs(video_data)
            ctx["details"]["interaction_id"] = interaction_id

            return gcs_uri, interaction_id

        except Exception as e:
            logger.exception("Error calling Gemini Omni Interactions API")
            raise GenerationError(f"Omni generation failed: {e}") from e


DEFAULT_OMNI_DURATION = 10


def _modify_prompt_for_omni(prompt: str, aspect_ratio: str, duration: int) -> str:
    """Append aspect ratio and duration to the prompt if they differ from defaults (16:9, 10s)."""
    additions = []
    if aspect_ratio != "16:9":
        additions.append(f"aspect ratio {aspect_ratio}")
    if duration != DEFAULT_OMNI_DURATION:
        additions.append(f"duration {duration}s")

    if additions:
        separator = " " if prompt.endswith(",") else ", "
        return prompt.strip() + separator + ", ".join(additions)
    return prompt


def _resolve_gcs_uris_in_history(input_parts: list) -> list:
    """Iterate input parts history and convert GCS URIs back to base64 data for model outputs."""
    resolved_parts = []
    for step in input_parts:
        if not isinstance(step, dict):
            resolved_parts.append(step)
            continue

        step_type = step.get("type")
        step_content = step.get("content")

        if step_type == "model_output" and isinstance(step_content, list):
            resolved_content = []
            for item in step_content:
                if (
                    isinstance(item, dict)
                    and item.get("type") == "video"
                    and "gcs_uri" in item
                ):
                    try:
                        logger.info(
                            f"Downloading previous video output from GCS: {item['gcs_uri']}",
                        )
                        video_bytes = download_from_gcs(item["gcs_uri"])
                        base64_data = base64.b64encode(video_bytes).decode("utf-8")
                        resolved_content.append(
                            {
                                "type": "video",
                                "data": base64_data,
                                "mime_type": item.get("mime_type", "video/mp4"),
                            },
                        )
                    except Exception:
                        logger.exception(
                            f"Failed to download previous video from {item['gcs_uri']}",
                        )
                        resolved_content.append(item)
                else:
                    resolved_content.append(item)

            resolved_parts.append({"type": "model_output", "content": resolved_content})
        else:
            resolved_parts.append(step)

    return resolved_parts


def _build_input_parts(request: OmniVideoGenerationRequest) -> list:
    """Build the input parts list from the request options."""
    input_parts = []

    modified_prompt = _modify_prompt_for_omni(
        request.prompt,
        request.aspect_ratio,
        request.duration_seconds,
    )

    # Handle multi-turn history if present
    if request.previous_interaction_id and request.chat_history_json:
        try:
            logger.info("Mode: Multi-turn Chat / Editing")
            raw_history = json.loads(request.chat_history_json)
            input_parts = _resolve_gcs_uris_in_history(raw_history)
        except json.JSONDecodeError as je:
            raise GenerationError(f"Failed to decode chat history: {je}") from je

        # Append current user prompt to history list
        input_parts.append(
            {
                "type": "user_input",
                "content": [{"type": "text", "text": modified_prompt}],
            },
        )
    else:
        # Standard single-turn flow
        input_parts.append({"type": "text", "text": modified_prompt})
        _append_single_turn_media(request, input_parts)

    return input_parts


def _append_single_turn_media(
    request: OmniVideoGenerationRequest,
    input_parts: list,
) -> None:
    """Append media inputs to the parts list for single turn generation."""
    # Append reference media depending on mode
    if request.omni_mode == "i2v":
        if not request.reference_image_gcs:
            raise GenerationError(
                "Reference image GCS URI is required for Image-to-Video.",
            )
        logger.info(
            f"Mode: Image-to-Video. Reference Image: {request.reference_image_gcs}",
        )
        input_parts.append(
            {
                "type": "image",
                "mime_type": request.reference_image_mime_type or "image/png",
                "uri": request.reference_image_gcs,
            },
        )

    elif request.omni_mode == "ref2v":
        if not request.r2v_references:
            raise GenerationError(
                "Reference images are required for Reference-to-Video.",
            )
        logger.info(
            f"Mode: Reference-to-Video. References count: {len(request.r2v_references)}",
        )
        input_parts.extend(
            [
                {
                    "type": "image",
                    "mime_type": ref.mime_type or "image/jpeg",
                    "uri": ref.gcs_uri,
                }
                for ref in request.r2v_references
            ],
        )

    elif request.omni_mode == "edit":
        logger.info("Mode: Video Editing")
        if request.reference_image_gcs:
            logger.info(f"Adding edit base image: {request.reference_image_gcs}")
            input_parts.append(
                {
                    "type": "image",
                    "mime_type": request.reference_image_mime_type or "image/png",
                    "uri": request.reference_image_gcs,
                },
            )
        if request.reference_video_gcs:
            logger.info(f"Adding edit base video: {request.reference_video_gcs}")
            input_parts.append(
                {
                    "type": "video",
                    "mime_type": request.reference_video_mime_type or "video/mp4",
                    "uri": request.reference_video_gcs,
                },
            )

    return input_parts


def _extract_video_payload(interaction: object) -> tuple[str, str]:
    """Extract raw video base64 payload and interaction ID from response."""
    contents = []

    # Safely get steps from interaction
    steps = (
        interaction.steps
        if hasattr(interaction, "steps")
        else (interaction.get("steps") if isinstance(interaction, dict) else [])
    )

    for step in steps:
        step_type = (
            step.type
            if hasattr(step, "type")
            else (step.get("type") if isinstance(step, dict) else None)
        )
        step_content = (
            step.content
            if hasattr(step, "content")
            else (step.get("content") if isinstance(step, dict) else [])
        )
        if step_type == "model_output":
            contents.extend(step_content)

    if not contents:
        raise GenerationError("No outputs returned from the Gemini Omni model.")

    # Find the video step in content
    video_content = None
    for c in contents:
        if (hasattr(c, "type") and c.type == "video") or (
            isinstance(c, dict) and c.get("type") == "video"
        ):
            video_content = c
            break
        if hasattr(c, "data") and c.data:
            video_content = c
            break

    if not video_content:
        raise GenerationError("No video content payload found in model output.")

    # Get raw base64 data
    video_data = (
        video_content.data
        if hasattr(video_content, "data")
        else video_content.get("data")
    )
    return video_data, interaction.id


def _save_video_to_gcs(video_data: str) -> str:
    """Save the decoded base64 video payload to the GCS bucket."""
    folder = (
        config.VIDEO_BUCKET.split("/")[-1] if "/" in config.VIDEO_BUCKET else "videos"
    )
    filename = f"omni_{int(time.time())}_{uuid.uuid4().hex[:6]}.mp4"

    logger.info(
        f"Saving generated Omni video to GCS bucket folder '{folder}' as '{filename}'...",
    )
    gcs_uri = store_to_gcs(
        folder=folder,
        file_name=filename,
        mime_type="video/mp4",
        contents=video_data,
        decode=True,
    )
    logger.info(f"Saved generated video to: {gcs_uri}")
    return gcs_uri
