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

"""Orchestrates the Gemini-as-a-judge critique workflow for VTO results."""

from google.genai import types
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from common.analytics import analytics_logger, track_model_call
from common.error_handling import GenerationError
from config.default import Default
from config.rewriters import VTO_PLACEMENT_CRITIQUE_PROMPT
from models.model_setup import GeminiModelSetup

cfg = Default()


class VTOPlacementCritique(BaseModel):
    """Structured Gemini evaluation of a virtual try-on image."""

    accurate: bool = Field(
        ...,
        description="True if the garment is accurately and naturally placed on the model.",
    )
    placement_analysis: str = Field(
        ...,
        description="A concise one-sentence critique of the garment placement on the model.",
    )
    reasoning: str = Field(
        ...,
        description="Supporting observations on garment fit, drape, alignment, and visual fidelity.",
    )


def _infer_image_mime_type(uri: str) -> str:
    """Infers an image MIME type from a GCS URI."""
    lower = uri.lower()
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    return "image/png"


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def evaluate_vto_placement(
    apparel_image_gcs: str,
    result_image_gcs: str,
) -> VTOPlacementCritique:
    """Evaluate garment placement quality in a VTO result image using Gemini."""
    model_name = cfg.GEMINI_CRITIQUE_MODEL_ID
    critique_client = GeminiModelSetup.init(location=cfg.GEMINI_CRITIQUE_LOCATION)

    prompt_parts = [
        VTO_PLACEMENT_CRITIQUE_PROMPT,
        types.Part.from_uri(
            file_uri=apparel_image_gcs,
            mime_type=_infer_image_mime_type(apparel_image_gcs),
        ),
        types.Part.from_uri(
            file_uri=result_image_gcs,
            mime_type=_infer_image_mime_type(result_image_gcs),
        ),
    ]

    gen_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=VTOPlacementCritique.model_json_schema(),
        temperature=cfg.TEMP_BEST_IMAGE_SELECTION,
    )

    with track_model_call(model_name=model_name, task="vto_placement_critique"):
        response = critique_client.models.generate_content(
            model=model_name,
            contents=prompt_parts,
            config=gen_config,
        )

    return VTOPlacementCritique.model_validate_json(response.text)


def run_vto_critique_workflow(
    apparel_image_gcs: str,
    result_image_gcs: str,
) -> dict[str, str | bool]:
    """Run the VTO critique workflow (Stage 1: placement analysis)."""
    try:
        critique = evaluate_vto_placement(
            apparel_image_gcs=apparel_image_gcs,
            result_image_gcs=result_image_gcs,
        )
    except Exception as exc:
        analytics_logger.error(f"Error during VTO placement analysis: {exc}")
        msg = f"Failed to analyze VTO garment placement: {exc}"
        raise GenerationError(msg) from exc
    return {
        "accurate": critique.accurate,
        "placement_analysis": critique.placement_analysis,
        "reasoning": critique.reasoning,
        "result_image_gcs": result_image_gcs,
    }
