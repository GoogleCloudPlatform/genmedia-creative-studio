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

"""Service for improving prompts."""

import logging

from google.genai.types import GenerateContentConfig

from config.default import Default
from models.domain import ImprovementPlan, ImprovementResult
from models.prompts import (
    PROMPT_IMPROVEMENT_INSTRUCTIONS,
    PROMPT_IMPROVEMENT_PLANNING_INSTRUCTIONS,
)
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class PromptImprover:
    """Service to handle prompt improvement logic."""

    def __init__(self, client: LLMClient = None):
        """Initializes the PromptImprover service.

        Args:
            client: An instance of LLMClient. If None, a new one is created.
        """
        self.client = client or LLMClient()
        config = Default()
        self.model_id = config.MODEL_ID
        self.planning_model_id = config.PLANNING_MODEL_ID or config.MODEL_ID

    def generate_plan(
        self, system_prompt: str, prompt: str, instructions: str
    ) -> ImprovementPlan:
        """Generates a plan for improving a prompt.

        Args:
            system_prompt: An optional system_prompt to guide the model.
            prompt: The prompt to improve.
            instructions: Instructions for the improvement.

        Returns:
            An ImprovementPlan object containing the inputs and the generated plan.
        """
        planning_prompt = PROMPT_IMPROVEMENT_PLANNING_INSTRUCTIONS.format(
            f"{system_prompt} {prompt}",
            instructions,
        )

        response = self.client.generate_content(
            model=self.planning_model_id,
            contents=planning_prompt,
            config=GenerateContentConfig(
                response_modalities=["TEXT"],
            ),
            log_success_msg="Gemini thinking thoughts successful",
        )

        generated_plan_text = response.candidates[0].content.parts[0].text

        return ImprovementPlan(
            original_prompt=prompt,
            system_prompt=system_prompt,
            instructions=instructions,
            generated_plan=generated_plan_text,
        )

    def improve_prompt(self, plan: ImprovementPlan) -> ImprovementResult:
        """Improves a prompt based on a generated plan.

        Args:
            plan: The ImprovementPlan object.

        Returns:
            An ImprovementResult object containing the plan and the improved prompt.
        """
        improvement_prompt = PROMPT_IMPROVEMENT_INSTRUCTIONS.format(
            plan.generated_plan,
            f"{plan.system_prompt} {plan.original_prompt}",
            plan.instructions,
        )

        response = self.client.generate_content(
            model=self.model_id,
            contents=improvement_prompt,
            config=GenerateContentConfig(
                response_modalities=["TEXT"],
            ),
            log_success_msg="Gemini prompt improvement successful",
        )

        return ImprovementResult(plan=plan, improved_prompt=response.text)

    def run(
        self, system_prompt: str, prompt: str, instructions: str
    ) -> ImprovementResult:
        """Orchestrates the full improvement process (Plan -> Improve).

        Args:
            system_prompt: An optional system_prompt to guide the model.
            prompt: The prompt to improve.
            instructions: Instructions for the improvement.

        Returns:
            An ImprovementResult object.
        """
        plan = self.generate_plan(system_prompt, prompt, instructions)
        result = self.improve_prompt(plan)
        return result
