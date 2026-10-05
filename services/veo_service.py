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

import datetime
import logging
import threading

from common.metadata import (
    MediaItem,
    add_media_item_to_firestore,
    get_media_item_by_id_system,
)
from common.tasks import enqueue_thumbnail_task
from models.gemini import get_best_video_frame_timestamp
from models.requests import VideoGenerationRequest
from models.veo import generate_video
from config.veo_models import get_veo_model_config
from models.video_processing import extract_and_upload_thumbnail, get_video_duration

logger = logging.getLogger(__name__)


def run_thumbnail_job(job_id: str, video_uri: str) -> None:
    """Extracts a thumbnail and updates Firestore.

    Synchronous function called by Cloud Tasks or a background thread.
    """
    logger.info(f"Starting thumbnail extraction for job {job_id}")
    try:
        timestamp_s = get_best_video_frame_timestamp(video_uri)
        thumbnail_uri = extract_and_upload_thumbnail(video_uri, timestamp_s)

        if thumbnail_uri:
            item = get_media_item_by_id_system(job_id)
            if item:
                item.thumbnail_uri = thumbnail_uri
                add_media_item_to_firestore(item)
                logger.info(f"Successfully added thumbnail URI to job {job_id}")
    except Exception:
        logger.exception(f"Thumbnail extraction failed for job {job_id}")


def process_veo_generation_task(
    job_id: str, request_data: VideoGenerationRequest, user_email: str
):
    """
    Background task to process Veo video generation.
    Updates Firestore with status changes.
    """
    logger.info(f"Starting background task for job {job_id}")

    try:
        # 1. Update status to 'processing'
        _update_job_status(job_id, "processing")

        # 2. Perform the actual heavy lifting (synchronous call)
        video_uris, resolution = generate_video(request_data)

        # 3. Success! Update Firestore with results.
        # Check if this was an extension request to correct the duration
        actual_duration = None
        if request_data.video_input_gcs and video_uris:
            try:
                # For extensions, the resulting video is longer than the requested 'duration_seconds' (which is just the extension amount)
                # So we inspect the actual generated file to get the true total duration.
                actual_duration = get_video_duration(video_uris[0])
                logger.info(f"Corrected duration for extended video: {actual_duration}s")
            except Exception as e:
                logger.warning(f"Could not verify duration of extended video: {e}")

        _complete_job(job_id, video_uris, resolution, duration=actual_duration)
        logger.info(f"Background task for job {job_id} completed successfully.")

        # 4. Trigger thumbnail generation (Cloud Tasks with thread fallback)
        if video_uris:
            enqueued = enqueue_thumbnail_task(job_id, video_uris[0])
            if not enqueued:
                logger.info(
                    f"Falling back to background thread for thumbnail job {job_id}"
                )
                threading.Thread(
                    target=run_thumbnail_job,
                    args=(job_id, video_uris[0]),
                    daemon=True,
                ).start()

    except Exception as e:
        logger.error(f"Background task for job {job_id} failed: {e}")
        _fail_job(job_id, str(e))


def _update_job_status(job_id: str, status: str):
    """Helper to update just the status of a job."""
    item = get_media_item_by_id_system(job_id)
    if item:
        item.status = status
        add_media_item_to_firestore(item)


def _complete_job(job_id: str, video_uris: list[str], resolution: str, duration: float = None):
    """Helper to mark a job as complete with results."""
    item = get_media_item_by_id_system(job_id)
    if item:
        item.status = "complete"
        item.gcs_uris = video_uris
        item.gcsuri = video_uris[0] if video_uris else None
        item.resolution = resolution
        
        if duration is not None:
            item.duration = duration
            
        # Calculate generation time if possible, or just use now - timestamp
        if item.timestamp:
             # Ensure both are offset-aware or both are offset-naive.
             # Firestore timestamps are usually UTC.
             now = datetime.datetime.now(datetime.timezone.utc)
             # Handle potential string timestamp from legacy data if not fully parsed
             start_time = item.timestamp
             if isinstance(start_time, str):
                 try:
                     start_time = datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                 except ValueError:
                     start_time = now # Fallback

             item.generation_time = (now - start_time).total_seconds()

        add_media_item_to_firestore(item)


def _fail_job(job_id: str, error_message: str):
    """Helper to mark a job as failed."""
    item = get_media_item_by_id_system(job_id)
    if item:
        item.status = "failed"
        item.error_message = error_message
        add_media_item_to_firestore(item)


def create_initial_job(request: VideoGenerationRequest, user_email: str) -> str:
    """Creates the initial 'pending' MediaItem in Firestore and returns its ID."""
    model_config = get_veo_model_config(request.model_version_id)
    model_name = model_config.model_name if model_config else request.model_version_id

    # Infer mode
    mode = "t2v"
    source_uris = []
    
    if request.video_input_gcs:
        mode = "video_extension"
        source_uris.append(request.video_input_gcs)
    elif request.r2v_references or request.r2v_style_image:
        mode = "r2v"
    elif request.reference_image_gcs and request.last_reference_image_gcs:
        mode = "interpolation"
    elif request.reference_image_gcs:
        mode = "i2v"

    item = MediaItem(
        user_email=user_email,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
        status="pending",
        prompt=request.prompt,
        model=model_name,
        mime_type="video/mp4",
        mode=mode,
        aspect=request.aspect_ratio,
        duration=float(request.duration_seconds),
        reference_image=request.reference_image_gcs,
        last_reference_image=request.last_reference_image_gcs,
        source_uris=source_uris,
        r2v_reference_images=[ref.gcs_uri for ref in request.r2v_references]
        if request.r2v_references
        else [],
        r2v_style_image=request.r2v_style_image.gcs_uri
        if request.r2v_style_image
        else None,
        negative_prompt=request.negative_prompt,
        enhanced_prompt_used=request.enhance_prompt,
    )
    add_media_item_to_firestore(item)
    return item.id
