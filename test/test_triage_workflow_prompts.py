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
import os
import pytest
from google import genai
from google.genai import types

# Define the prompt template used in the GitHub Action workflow
PROMPT_TEMPLATE = """You are an expert Issue Triage Engineer. Your task is to analyze a list of GitHub issues and assign the most relevant labels.

**Instructions:**

1.  **Retrieve Data**: Immediately run `printenv ISSUES_TO_TRIAGE` and `printenv AVAILABLE_LABELS` to get the input data.
2.  **Batch Analysis**: Analyze all issues in the list internally. Do not output analysis for individual issues.
3.  **Generate Output**: Produce a single, minified JSON array containing the triage results.
4.  **Format**: The output must be a valid JSON array of objects with keys: `issue_number`, `labels_to_set`, `explanation`.
5.  **Constraints**:
    - Perform the analysis yourself. Do NOT write a script (Python, Bash, etc.) to do it.
    - Only use labels from `AVAILABLE_LABELS`.
    - Exclude issues with no matching labels.
    - Do not use `jq` or other tools to parse the input; read the variables directly.
    - Your final output to STDOUT must only be the JSON array.
    - IMPORTANT: Do not format the output as markdown. Do not use backticks (```). Just output the raw JSON string.
    - Do not include any other text or explanations.

**Example Output:**
[
  {
    "issue_number": 123,
    "labels_to_set": ["kind/bug", "priority/p2"],
    "explanation": "The issue describes a critical error in the login functionality."
  }
]
"""

# Mock Data
MOCK_ISSUES = [
    {
        "number": 101,
        "title": "Bug: Application crashes on startup",
        "body": "When I launch the app, it crashes immediately with a NullPointerException."
    },
    {
        "number": 102,
        "title": "Feature Request: Add dark mode",
        "body": "It would be great to have a dark mode for better visibility at night."
    },
    {
        "number": 103,
        "title": "Docs: Fix typo in README",
        "body": "There is a typo in the installation instructions."
    }
]

MOCK_LABELS = [
    "kind/bug",
    "kind/feature",
    "kind/docs",
    "priority/p0",
    "priority/p1",
    "priority/p2",
    "status/needs-triage"
]

@pytest.fixture(scope="module")
def gemini_client():
    """Initializes the Gemini client for testing."""
    project_id = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("LOCATION", "global")
    
    if not project_id:
        pytest.skip("PROJECT_ID or GOOGLE_CLOUD_PROJECT environment variable not set.")
    
    return genai.Client(
        vertexai=True,
        project=project_id,
        location=location,
    )

@pytest.mark.parametrize("iteration", range(5))
def test_triage_prompt_no_markdown(gemini_client, iteration):
    """
    Tests that the triage prompt produces valid JSON without markdown formatting.
    Running multiple iterations to ensure consistency.
    """
    model_id = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    
    # Construct the full prompt with simulated environment variables
    full_prompt = PROMPT_TEMPLATE + f"\n\n[SIMULATED ENV VARS]\nISSUES_TO_TRIAGE={json.dumps(MOCK_ISSUES)}\nAVAILABLE_LABELS={','.join(MOCK_LABELS)}\n"
    
    try:
        response = gemini_client.models.generate_content(
            model=model_id,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.1
            )
        )
        output = response.text
        
        # Assertion 1: Check for markdown code blocks
        assert "```" not in output, f"Output contained markdown code blocks (Iteration {iteration}):\n{output}"
        
        # Assertion 2: Check for valid JSON
        try:
            parsed_json = json.loads(output)
            assert isinstance(parsed_json, list), "Output JSON should be a list"
            if parsed_json:
                assert "issue_number" in parsed_json[0], "JSON objects should have 'issue_number'"
                assert "labels_to_set" in parsed_json[0], "JSON objects should have 'labels_to_set'"
        except json.JSONDecodeError as e:
            pytest.fail(f"Output was not valid JSON (Iteration {iteration}): {e}\nOutput:\n{output}")
            
    except Exception as e:
        pytest.fail(f"Gemini API call failed: {e}")
