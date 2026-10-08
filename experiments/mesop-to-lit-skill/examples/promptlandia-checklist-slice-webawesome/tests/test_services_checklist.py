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

"""Service-layer tests for PromptChecklist (adapted from the carried-over
tests/unit/test_services.py checklist case) + the schema adapter."""

from unittest.mock import MagicMock

from google.genai.types import GenerateContentResponse

from models.checklist_models import ParsedChecklistResponse
from services.checklist import PromptChecklist
from api.schemas import ChecklistResponse


def test_checklist_service_calls_client_once(mock_client):
    checklist = PromptChecklist(client=mock_client)
    structured, raw = checklist.evaluate_prompt("prompt")

    assert isinstance(structured, ParsedChecklistResponse)
    assert raw.startswith("# Prompt analysis for Clarity")
    assert mock_client.generate_content.call_count == 1


def test_checklist_service_parse_fallback_returns_none():
    # A non-string .text makes the parse pipeline raise -> service returns None.
    client = MagicMock()
    response = MagicMock(spec=GenerateContentResponse)
    response.text = None
    client.generate_content.return_value = response

    structured, raw = PromptChecklist(client=client).evaluate_prompt("x")

    assert structured is None


def test_adapter_maps_parsed_to_wire_shape(mock_client):
    structured, raw = PromptChecklist(client=mock_client).evaluate_prompt("x")
    wire = ChecklistResponse.from_parsed(structured, raw)

    names = [c.name for c in wire.categories]
    assert "Clarity" in names and "Typos" in names
    clarity = next(c for c in wire.categories if c.name == "Clarity")
    assert clarity.has_issue is True
    assert len(clarity.items) == 1


def test_adapter_fallback_when_none():
    wire = ChecklistResponse.from_parsed(None, "raw text")
    assert wire.categories == []
    assert wire.raw == "raw text"
