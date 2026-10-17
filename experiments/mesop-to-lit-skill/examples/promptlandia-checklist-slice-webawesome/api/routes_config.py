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

"""Config / health routes (read-only)."""

from fastapi import APIRouter

from api.schemas import ConfigResponse
from config.default import Default

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/healthz")
def healthz() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/config", response_model=ConfigResponse)
def config() -> ConfigResponse:
    """Read-only config subset (secrets stay server-side)."""
    cfg = Default()
    return ConfigResponse(
        model_id=cfg.MODEL_ID,
        alternative_model_id=cfg.ALTERNATIVE_MODEL_ID,
        gemini_location=cfg.GEMINI_LOCATION,
    )
