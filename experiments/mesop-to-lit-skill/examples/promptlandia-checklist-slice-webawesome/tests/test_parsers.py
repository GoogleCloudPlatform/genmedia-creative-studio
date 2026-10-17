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

"""Parser tests, carried over from tests/test_rendering_logic.py but exercising
the UNCHANGED models/parsers.py directly (the source test read sample files that
are not vendored; we use an inline fixture instead)."""

from models.parsers import parse_evaluation_markdown
from models.checklist_models import ParsedChecklistResponse


def test_parse_marks_issue_and_no_issue(canned_markdown):
    parsed = parse_evaluation_markdown(canned_markdown)

    assert isinstance(parsed, dict)
    assert parsed["Clarity"]["items"]["Issue Found"] is True
    assert parsed["Typos"]["items"]["Issue Found"] is False
    assert "details" in parsed["Clarity"]
    assert "explanation" in parsed["Clarity"]


def test_from_json_dict_builds_model(canned_markdown):
    parsed = parse_evaluation_markdown(canned_markdown)
    model = ParsedChecklistResponse.from_json_dict(parsed)

    assert set(model.categories) == {"Clarity", "Typos"}
    assert model.categories["Clarity"].items["Issue Found"] is True
