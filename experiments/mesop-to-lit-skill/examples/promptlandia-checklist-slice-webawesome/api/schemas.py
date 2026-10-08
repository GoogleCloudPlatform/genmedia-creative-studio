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

"""Pydantic request/response schemas for the API layer.

Shapes are taken verbatim from target-architecture §3.3. The checklist response
is the *typed* body that replaces the Mesop JSON-in-state workaround: the
frontend receives a normal typed JSON object, not a JSON string stuffed into
state.

ADAPTER NOTE (skill finding, see RESULTS.md):
  §3.3 `ChecklistItem` mirrors the *raw per-issue JSON block* the model emits
  (issue_name/location_in_prompt/rationale/impact_analysis/severity/solution).
  The reused parse pipeline (`parse_evaluation_markdown` -> `from_json_dict`)
  is lossy: it reshapes those keys into markdown strings on `CategoryData`
  (location+rationale -> a `details` string; impact+solution -> `explanation`)
  and drops `issue_name`/`severity`. `ChecklistResponse.from_parsed` therefore
  maps what survives and leaves the dropped fields empty; the category
  `explanation` still carries impact/solution so the rendered output stays
  equivalent to the Mesop page.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from models.checklist_models import IssueDetail, ParsedChecklistResponse


# ---- checklist (POST /api/checklist) -- target-architecture §3.3 -------------


class ChecklistRequest(BaseModel):
    """Request body for a checklist evaluation."""

    prompt: str = Field(min_length=1)


class ChecklistItem(BaseModel):
    """One identified issue. == models.checklist_models.ChecklistItemDetail shape
    (the raw per-issue JSON block the model emits)."""

    issue_name: str = ""
    location_in_prompt: str = ""
    rationale: str = ""
    impact_analysis: str = ""
    severity: str = ""
    solution: str = ""


class ChecklistCategory(BaseModel):
    """One checklist category (== CategoryData, flattened for transport)."""

    name: str
    has_issue: bool
    explanation: str = ""
    items: List[ChecklistItem] = Field(default_factory=list)


class ChecklistResponse(BaseModel):
    """Typed checklist body (== ParsedChecklistResponse, no JSON-in-state hack)."""

    categories: List[ChecklistCategory] = Field(default_factory=list)
    raw: Optional[str] = None  # fallback text when parse fails (§3.3)

    @classmethod
    def from_parsed(
        cls,
        parsed: Optional[ParsedChecklistResponse],
        raw: str,
    ) -> "ChecklistResponse":
        """Adapt the internal `ParsedChecklistResponse` to the §3.3 wire shape.

        When `parsed` is None the markdown could not be parsed -> return only the
        raw text (parse-fallback path). Categories are sorted so the ones with
        issues come first, mirroring the Mesop page's ordering.
        """
        if parsed is None:
            return cls(categories=[], raw=raw)

        categories: List[ChecklistCategory] = []
        for name, cat in parsed.categories.items():
            has_issue = any(bool(score) for score in cat.items.values())
            items: List[ChecklistItem] = []
            details = cat.details or {}
            for item_name, score in cat.items.items():
                if not score:
                    continue  # passed check -> not an issue item
                detail = details.get(item_name)
                if isinstance(detail, IssueDetail):
                    items.append(
                        ChecklistItem(
                            issue_name=detail.issue_name,
                            location_in_prompt=detail.location_in_prompt,
                            rationale=detail.rationale,
                        )
                    )
                else:
                    # Lossy path: the markdown parser stored a formatted string.
                    items.append(
                        ChecklistItem(
                            issue_name=item_name,
                            rationale=str(detail) if detail else "",
                        )
                    )
            categories.append(
                ChecklistCategory(
                    name=name,
                    has_issue=has_issue,
                    explanation=cat.explanation or "",
                    items=items,
                )
            )

        categories.sort(key=lambda c: not c.has_issue)  # issues first
        return cls(categories=categories, raw=None)


# ---- config (GET /api/config) -- optional for the slice, §3.3 ----------------


class ConfigResponse(BaseModel):
    """Read-only config subset for a Settings display (not required by the slice)."""

    model_id: str
    alternative_model_id: str
    gemini_location: str


# ---- error envelope (§3.5) ---------------------------------------------------


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody
