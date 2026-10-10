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

"""Shared test fixtures. No real Vertex/Gemini calls -- the LLM client is mocked."""

import os

import pytest

# Config reads PROJECT_ID from env; set a dummy so Default() is well-formed even
# though every test mocks the LLM client (no network).
os.environ.setdefault("PROJECT_ID", "test-project")

# A canned checklist markdown that the UNCHANGED parse pipeline turns into one
# with-issue category (Clarity) and one no-issue category (Typos).
CANNED_CHECKLIST_MD = """# Prompt analysis for Clarity
```json
{"issue_name": "Ambiguous instruction", "location_in_prompt": "the opening line", "rationale": "The phrase 'do the thing' is vague.", "impact_analysis": "The model may produce off-target output.", "severity": "high", "solution": "State the concrete task explicitly."}
```

# Prompt analysis for Typos
Issue not present in the prompt.
"""


@pytest.fixture
def canned_markdown() -> str:
    return CANNED_CHECKLIST_MD


@pytest.fixture
def mock_client(canned_markdown):
    """A mocked LLMClient whose generate_content returns the canned markdown."""
    from unittest.mock import MagicMock

    from google.genai.types import GenerateContentResponse

    client = MagicMock()
    response = MagicMock(spec=GenerateContentResponse)
    response.text = canned_markdown
    client.generate_content.return_value = response
    return client
