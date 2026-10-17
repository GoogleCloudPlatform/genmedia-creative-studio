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

"""Service for trimming prompts."""

import logging
import re
import time

from google.genai.types import GenerateContentConfig

from config.default import Default
from models.domain import TrimResult
from models.prompts import TRIMMER_DECONSTRUCTOR, TRIMMER_REWRITER
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class PromptTrimmer:
    """Service to handle prompt trimming logic."""

    def __init__(self, client: LLMClient = None):
        """Initializes the PromptTrimmer service.

        Args:
            client: An instance of LLMClient. If None, a new one is created.
        """
        self.client = client or LLMClient()
        config = Default()
        self.model_id = config.MODEL_ID
        self.alternative_model_id = config.ALTERNATIVE_MODEL_ID

    def trim_prompt(self, prompt: str) -> TrimResult:
        """Trims a prompt by removing general best practices while keeping task-specific requirements.

        This is a two-step process:
        1. Deconstruct the prompt to identify what is essential vs general.
        2. Rewrite the prompt using only the essential parts.

        Args:
            prompt: The user's original prompt.

        Returns:
            A TrimResult object containing the analysis, trimmed prompt, and duration.
        """
        logger.info(
            f"Trimming prompt (deconstruct={self.alternative_model_id}, "
            f"rewrite={self.model_id})"
        )
        start_time = time.perf_counter()

        # Step 1: Deconstruct (classification/extraction step -> lighter model)
        deconstructor_prompt = TRIMMER_DECONSTRUCTOR.format(prompt)
        response_1 = self.client.generate_content(
            model=self.alternative_model_id,
            contents=deconstructor_prompt,
            config=GenerateContentConfig(
                response_modalities=["TEXT"],
            ),
            log_success_msg="Step 1 (Deconstruction) complete",
        )
        analysis_xml = response_1.text

        # Parse XML to extract requirements and general rules
        tsr_match = re.search(
            r"<TaskSpecificRequirements>(.*?)</TaskSpecificRequirements>",
            analysis_xml,
            re.DOTALL,
        )
        grbp_match = re.search(
            r"<GeneralRulesAndBestPractices>(.*?)</GeneralRulesAndBestPractices>",
            analysis_xml,
            re.DOTALL,
        )

        tsr = tsr_match.group(1).strip() if tsr_match else ""
        grbp = grbp_match.group(1).strip() if grbp_match else ""

        # Step 2: Rewrite
        rewriter_prompt = TRIMMER_REWRITER.format(prompt, tsr, grbp)
        response_2 = self.client.generate_content(
            model=self.model_id,
            contents=rewriter_prompt,
            config=GenerateContentConfig(
                response_modalities=["TEXT"],
            ),
            log_success_msg="Step 2 (Rewriting) complete",
        )
        final_trimmed_prompt = response_2.text

        end_time = time.perf_counter()

        return TrimResult(
            original_prompt=prompt,
            trimmed_prompt=final_trimmed_prompt,
            analysis_xml=analysis_xml,
            duration_seconds=end_time - start_time,
        )
