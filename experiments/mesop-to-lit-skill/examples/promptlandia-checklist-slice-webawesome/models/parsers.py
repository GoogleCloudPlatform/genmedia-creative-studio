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

import json
import re
from typing import Any, Dict


def parse_evaluation_markdown(markdown_text: str) -> Dict[str, Any]:
    """
    Parses the markdown output from the evaluation prompt into a dict
    that can be used to create a ParsedChecklistResponse object.
    """
    # Split the text by the main category headers
    sections = re.split(r"# Prompt analysis for ", markdown_text)

    parsed_data = {}

    for section in sections:
        if not section.strip():
            continue

        lines = section.strip().split("\n")
        category_name = lines[0].strip()
        content = "\n".join(lines[1:]).strip()

        # Find all json blocks, not just the first one
        json_matches = re.findall(r"```json\n(.*?)\n```", content, re.DOTALL)

        if "Issue not present in the prompt" in content or not json_matches:
            category_data = {
                "items": {"Issue Found": False},
                "details": {"Issue Found": "No issue was found for this category."},
                "explanation": "The model did not find any issues for this category.",
            }
        else:
            # For simplicity, we'll use the first valid JSON block found in the section.
            # A more advanced implementation could handle multiple blocks per section.
            try:
                json_data = json.loads(json_matches[0])
                explanation = (
                    f"**Impact Analysis:**\n{json_data.get('impact_analysis', 'N/A')}\n\n"
                    f"**Suggested Solution:**\n{json_data.get('solution', 'N/A')}"
                )
                details = {
                    "Issue Found": (
                        f"**Location:** {json_data.get('location_in_prompt', 'N/A')}\n\n"
                        f"**Rationale:** {json_data.get('rationale', 'N/A')}"
                    )
                }
                category_data = {
                    "items": {"Issue Found": True},
                    "details": details,
                    "explanation": explanation,
                }
            except (json.JSONDecodeError, IndexError):
                # Fallback if JSON is malformed or not found after all
                category_data = {
                    "items": {"Issue Found": False},
                    "details": {
                        "Issue Found": "Could not parse details for this category."
                    },
                    "explanation": "There was an error parsing the response from the model.",
                }

        parsed_data[category_name] = category_data

    return parsed_data
