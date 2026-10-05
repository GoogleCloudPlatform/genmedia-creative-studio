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

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel

from common.metadata import get_media_item_by_id
from models.requests import VideoGenerationRequest
from services.veo_service import (
    create_initial_job,
    process_veo_generation_task,
    run_thumbnail_job,
)

router = APIRouter(prefix="/api/veo", tags=["veo"])


class ThumbnailRequest(BaseModel):
    """Request schema for thumbnail generation."""

    job_id: str
    video_uri: str


@router.post("/thumbnail")
async def generate_thumbnail(request: ThumbnailRequest):
    """FastAPI endpoint triggered by Cloud Tasks to extract a thumbnail."""
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
