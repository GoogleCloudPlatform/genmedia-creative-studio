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

"""Action routes -- the real LLM calls. One route per service method."""

from fastapi import APIRouter, Depends

from api.deps import get_checklist_service
from api.schemas import ChecklistRequest, ChecklistResponse
from services.checklist import PromptChecklist

router = APIRouter(prefix="/api", tags=["actions"])


@router.post("/checklist", response_model=ChecklistResponse)
def checklist(
    req: ChecklistRequest,
    service: PromptChecklist = Depends(get_checklist_service),
) -> ChecklistResponse:
    """Evaluate a prompt against the health checklist.

    Reuses the unchanged `PromptChecklist.evaluate_prompt` (which runs
    `parse_evaluation_markdown` + `ParsedChecklistResponse.from_json_dict`) and
    adapts the result to the typed §3.3 body. On parse failure the service
    returns `(None, raw_text)` and we surface the raw text as a fallback.
    A service/LLM exception propagates to the §3.5 error envelope.
    """
    parsed, raw_text = service.evaluate_prompt(req.prompt)
    return ChecklistResponse.from_parsed(parsed, raw_text)
