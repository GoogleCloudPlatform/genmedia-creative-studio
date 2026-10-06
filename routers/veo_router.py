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

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from common.metadata import get_media_item_by_id
from common.task_auth import TaskAuthError, authorize_cloud_task_caller
from config.default import Default as cfg
from models.requests import VideoGenerationRequest
from services.veo_service import (
    create_initial_job,
    process_veo_generation_task,
    run_thumbnail_job,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/veo", tags=["veo"])

# Path of the thumbnail task endpoint. The Cloud Tasks OIDC token's audience
# defaults to the task's full target URL, which common.tasks builds as
# ``{API_BASE_URL}{THUMBNAIL_TASK_PATH}`` — keep the two in sync.
THUMBNAIL_TASK_PATH = "/api/veo/thumbnail"


class ThumbnailRequest(BaseModel):
    """Request schema for thumbnail generation."""

    job_id: str
    video_uri: str


@router.post("/thumbnail")
async def generate_thumbnail(request: ThumbnailRequest, req: Request):
    """FastAPI endpoint triggered by Cloud Tasks to extract a thumbnail.

    This is a *task* endpoint, not a user endpoint: it is invoked only by Cloud
    Tasks with a Google-signed OIDC token minted for ``SERVICE_ACCOUNT_EMAIL``
    (see ``common.tasks.enqueue_thumbnail_task``). Authorize that trusted
    identity server-side and fail closed.

    Without this check any authenticated *user* could POST a victim's ``job_id``
    with an attacker-controlled ``video_uri``: ``run_thumbnail_job`` writes the
    resulting ``thumbnail_uri`` onto the item keyed by ``job_id`` with no owner
    check, overwriting the victim item's thumbnail (write-side IDOR). The
    legitimate in-process fallback (``process_veo_generation_task`` -> background
    thread) calls ``run_thumbnail_job`` directly and never traverses this HTTP
    endpoint, so restricting the endpoint does not break it.
    """
    try:
        authorize_cloud_task_caller(
            req.headers,
            expected_service_account=cfg().SERVICE_ACCOUNT_EMAIL,
            audience=f"{cfg().API_BASE_URL}{THUMBNAIL_TASK_PATH}",
        )
    except TaskAuthError as exc:
        logger.warning("Rejected unauthorized thumbnail task request: %s", exc)
        raise HTTPException(status_code=403, detail="Forbidden") from exc

    run_thumbnail_job(request.job_id, request.video_uri)
    return {"status": "ok"}


@router.post("/generate_async")
async def generate_veo_async(
    request: VideoGenerationRequest,
    background_tasks: BackgroundTasks,
    req: Request,
):
    """
    Initiates an asynchronous Veo video generation task.
    Returns a job ID immediately.
    """
    # Extract user email from the request scope, set by middleware
    user_email = req.scope.get("MESOP_USER_EMAIL")
    if not user_email:
        # Fallback or error if auth is strictly required.
        # For now, we'll use a placeholder if missing to avoid hard crashes during dev,
        # but in prod this should likely be a 401.
        user_email = "unknown_user@example.com"

    # 1. Create the "Tracking Record" immediately
    job_id = create_initial_job(request, user_email)

    # 2. Schedule the background work
    background_tasks.add_task(
        process_veo_generation_task,
        job_id=job_id,
        request_data=request,
        user_email=user_email,
    )

    # 3. Return the tracking number immediately
    return {"job_id": job_id, "status": "pending"}

@router.get("/job/{job_id}")
async def get_veo_job_status(job_id: str, req: Request):
    """
    Checks the status of a Veo generation job.
    """
    # Owner-scoped read: the job id is client-supplied, so authorize it against
    # the server-derived verified identity the middleware placed on the request
    # scope (see main.py). Without this a caller could poll ANY user's job by id
    # (read-side IDOR / information disclosure). A non-owner / unauthenticated
    # caller is indistinguishable from "not found" (no existence oracle).
    user_email = req.scope.get("MESOP_USER_EMAIL")
    item = get_media_item_by_id(job_id, caller_email=user_email)
    if not item:
        return {"error": "Job not found"}, 404

    response = {"job_id": job_id, "status": item.status}
    if item.status == "complete":
        response["video_uri"] = item.gcsuri
        response["video_uris"] = item.gcs_uris
    elif item.status == "failed":
        response["error_message"] = item.error_message

    return response
