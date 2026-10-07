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

"""Service for the prompt health checklist."""

import logging
from typing import Optional, Tuple

from google.genai.types import GenerateContentConfig

from config.default import Default
from models.checklist_models import ParsedChecklistResponse
from models.parsers import parse_evaluation_markdown
from models.prompts import PROMPT_HEALTH_CHECKLIST
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class PromptChecklist:
    """Service to handle prompt health checklist evaluation."""

    def __init__(self, client: LLMClient = None):
        """Initializes the PromptChecklist service.

        Args:
            client: An instance of LLMClient. If None, a new one is created.
        """
        self.client = client or LLMClient()
        self.model_id = Default().MODEL_ID

    def evaluate_prompt(self, prompt: str) -> Tuple[Optional[ParsedChecklistResponse], str]:
        """
        Evaluates a prompt against the health checklist.

        Args:
            prompt: The prompt to evaluate.

        Returns:
            A tuple containing:
            - The ParsedChecklistResponse object if parsing was successful, else None.
            - The raw text response from the model (for fallback or logging).
        """
        logger.info("Starting prompt evaluation...")
        try:
            response = self.client.generate_content(
                model=self.model_id,
                contents=f"# Prompt for Analysis\n<PROMPT>\n{prompt}\n</PROMPT>\n",
                config=GenerateContentConfig(
                    system_instruction=PROMPT_HEALTH_CHECKLIST,
                    response_modalities=["TEXT"],
                ),
                log_success_msg="Gemini content generation for checklist successful",
            )
            response_text = response.text
        except Exception as e:
            logger.error(f"Error during Gemini generation for checklist: {e}")
            raise

        try:
            # Parse the raw markdown into a dictionary
            parsed_dict = parse_evaluation_markdown(response_text)

            # Convert the dictionary to our Pydantic model
            structured_response = ParsedChecklistResponse.from_json_dict(parsed_dict)

            return structured_response, response_text

        except Exception as e:
            logger.error(f"Error parsing checklist response: {e}")
            # Return None for the structured response but keep the raw text
            return None, response_text
