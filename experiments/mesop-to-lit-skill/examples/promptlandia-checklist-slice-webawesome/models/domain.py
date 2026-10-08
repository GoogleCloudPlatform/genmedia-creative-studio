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

"""Domain models for the Promptlandia application."""

from pydantic import BaseModel, Field


class TrimResult(BaseModel):
    """Result of a prompt trimming operation."""

    original_prompt: str = Field(..., description="The original prompt provided by the user.")
    trimmed_prompt: str = Field(..., description="The trimmed version of the prompt.")
    analysis_xml: str = Field(..., description="The XML analysis generated during the trimming process.")
    duration_seconds: float = Field(..., description="Time taken to perform the trim operation in seconds.")


class ImprovementPlan(BaseModel):
    """Plan generated for improving a prompt."""

    original_prompt: str = Field(..., description="The original prompt provided by the user.")
    system_prompt: str = Field(default="", description="The system prompt context.")
    instructions: str = Field(..., description="User instructions for improvement.")
    generated_plan: str = Field(..., description="The thinking/planning output from the model.")


class ImprovementResult(BaseModel):
    """Result of a prompt improvement operation."""

    plan: ImprovementPlan = Field(..., description="The plan used to generate the improvement.")
    improved_prompt: str = Field(..., description="The final improved prompt.")
