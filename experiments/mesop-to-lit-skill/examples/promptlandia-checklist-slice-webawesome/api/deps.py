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

"""Dependency injection for the API layer.

The checklist service is constructed behind a FastAPI dependency so tests can
override it with a mocked `LLMClient` (no real Vertex/Gemini calls) via
`app.dependency_overrides[get_checklist_service]`.
"""

from services.checklist import PromptChecklist


def get_checklist_service() -> PromptChecklist:
    """Provide a PromptChecklist. Overridden in tests with a mocked client."""
    return PromptChecklist()
