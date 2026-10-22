import os
import uuid
import base64
import asyncio
import time
import mimetypes
import io
import requests
import google.auth
import google.auth.transport.requests
from PIL import Image as PILImage
from pathlib import Path
from google import genai
from google.genai import types
from google.cloud import storage

DEFAULT_OMNI_HOST = "https://aiplatform.googleapis.com"

def is_omni_model(model_id: str) -> bool:
    return model_id.startswith("gemini-omni")

def load_image_for_veo(image_path):
    """Loads an image file, ensuring proper JPEG/PNG mime type and format for Veo."""
    try:
        with PILImage.open(image_path) as img:
            fmt = (img.format or "").upper()
            if fmt == "PNG":
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                return buffer.getvalue(), "image/png"
            else:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG")
                return buffer.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"PIL loading failed for {image_path}: {e}, falling back to raw bytes")
        mime_type, _ = mimetypes.guess_type(image_path)
        if mime_type not in ["image/jpeg", "image/png"]:
            mime_type = "image/jpeg"
        with open(image_path, "rb") as f:
            return f.read(), mime_type

def load_image_for_omni(image_path, max_size=(640, 480)):
    """Downscales an image to satisfy the Omni 560_TOKENS visual tokenizer grid limit and encodes as base64 PNG."""
    with PILImage.open(image_path) as img:
        img = img.copy()
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail(max_size)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return {"type": "image", "mime_type": "image/png", "data": b64_data}

def get_veo_client(project_id, location):
    if not project_id:
        raise ValueError("Project ID must be provided.")
    
    return genai.Client(
        vertexai=True,
        project=project_id,
        location=location,
        http_options=types.HttpOptions(
            api_version='v1beta1'
        )
    )

def download_from_gcs(gcs_uri, local_path):
    """Downloads a file from GCS using the Python Storage SDK."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")
    
    parts = gcs_uri[5:].split("/", 1)
    bucket_name = parts[0]
    blob_name = parts[1]
    
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.download_to_filename(local_path)
    return local_path

def _get_auth_headers(project_id):
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
        "x-goog-user-project": project_id,
    }

def _extract_omni_video_bytes(data: dict) -> bytes:
    """Extracts inline base64 MP4 bytes from a completed Interactions API response."""
    for step in data.get("steps", []):
        contents = step.get("content") or step.get("modelOutput", {}).get("content", []) or []
        for c in contents:
            if c.get("type") == "video" or c.get("mime_type") in ("video/mp4", "TYPE_MP4"):
                b64 = c.get("data") or (c.get("video") or {}).get("data")
                if b64:
                    return base64.b64decode(b64)
            elif "video" in c and isinstance(c["video"], dict) and c["video"].get("data"):
                return base64.b64decode(c["video"]["data"])
    for out in data.get("outputs", []):
        if out.get("type") == "video" and out.get("data"):
            return base64.b64decode(out["data"])
    raise RuntimeError("No video data found in completed Omni interaction response")

async def generate_video_omni(prompt, model_id, duration, project_id, output_dir,
                              image_path=None, aspect_ratio="16:9", resolution="360p",
                              api_host=None, poll_interval=3.0):
    """
    Generates a video using Gemini Omni via the Vertex AI Interactions API (v1beta1).
    """
    host = (api_host or os.getenv("OMNI_API_HOST", DEFAULT_OMNI_HOST)).rstrip("/")
    base_url = f"{host}/v1beta1/projects/{project_id}/locations/global/interactions"

    os.makedirs(output_dir, exist_ok=True)
    timestamp = int(time.time())
    uid = uuid.uuid4().hex[:8]

    content_parts = [{"type": "text", "text": prompt}]
    if image_path:
        img_part = await asyncio.to_thread(load_image_for_omni, image_path)
        content_parts.append(img_part)

    rf = {
        "type": "video",
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "duration": f"{duration}s",
    }
    payload = {
        "model": model_id,
        "background": True,
        "response_format": [rf],
        "input": [{"type": "user_input", "content": content_parts}],
    }

    def _create():
        headers = _get_auth_headers(project_id)
        resp = requests.post(base_url, headers=headers, json=payload, timeout=45)
        resp.raise_for_status()
        return resp.json()

    created = await asyncio.to_thread(_create)
    interaction_id = created.get("id")
    if not interaction_id:
        raise RuntimeError(f"Omni interaction did not return an id: {created}")

    def _poll():
        headers = _get_auth_headers(project_id)
        resp = requests.get(f"{base_url}/{interaction_id}", headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    data = created
    while data.get("status") not in ("completed", "failed", "cancelled", "incomplete", "budget_exceeded"):
        await asyncio.sleep(poll_interval)
        data = await asyncio.to_thread(_poll)

    if data.get("status") != "completed":
        errs = data.get("errors") or data.get("error") or data.get("status")
        raise RuntimeError(f"Omni generation failed ({model_id}): {errs}")

    video_bytes = _extract_omni_video_bytes(data)
    local_filename = f"omni-{model_id}-{resolution}-{timestamp}-{uid}.mp4"
    local_path = os.path.join(output_dir, local_filename)
    await asyncio.to_thread(Path(local_path).write_bytes, video_bytes)
    return local_filename

async def generate_video(prompt, model, duration, project_id, location, bucket, output_dir, 
                         image_path=None, aspect_ratio="16:9", resolution=None, api_host=None,
                         poll_interval=3.0):
    """
    Generates a video natively using the google-genai Python SDK (Veo) or Vertex Interactions API (Gemini Omni).
    """
    model_id = model.split('/')[-1]
    if is_omni_model(model_id):
        res = resolution or os.getenv("OMNI_RESOLUTION", "360p")
        return await generate_video_omni(
            prompt=prompt,
            model_id=model_id,
            duration=duration,
            project_id=project_id,
            output_dir=output_dir,
            image_path=image_path,
            aspect_ratio=aspect_ratio,
            resolution=res,
            api_host=api_host,
            poll_interval=poll_interval,
        )

    client = get_veo_client(project_id, location)
    
    os.makedirs(output_dir, exist_ok=True)
    timestamp = int(time.time())
    uid = uuid.uuid4().hex[:8]
    gcs_bucket_name = bucket.replace("gs://", "").rstrip("/")
    gcs_prefix = f"var_{timestamp}_{uid}_{model_id.replace('.', '_')}"
    gcs_output_path = f"gs://{gcs_bucket_name}/{gcs_prefix}/"

    image = None
    if image_path:
        img_bytes, mime_type = await asyncio.to_thread(load_image_for_veo, image_path)
        image = types.Image(image_bytes=img_bytes, mime_type=mime_type)

    try:
        operation = await asyncio.to_thread(
            client.models.generate_videos,
            model=model_id,
            prompt=prompt,
            image=image,
            config=types.GenerateVideosConfig(
                duration_seconds=duration,
                aspect_ratio=aspect_ratio,
                output_gcs_uri=gcs_output_path
            )
        )
        
        while not operation.done:
            await asyncio.sleep(poll_interval)
            operation = await asyncio.to_thread(client.operations.get, operation)
            
        if operation.error:
            raise Exception(f"Generation failed for {model_id}: {operation.error}")
            
        if not operation.result or not operation.result.generated_videos:
            raise Exception(f"No videos found in operation result for {model_id}")
            
        video_uri = operation.result.generated_videos[0].video.uri
        local_filename = f"veo-{model_id}-{timestamp}-{uid}.mp4"
        local_path = os.path.join(output_dir, local_filename)
        
        await asyncio.to_thread(download_from_gcs, video_uri, local_path)
        
        return local_filename

    except Exception as e:
        raise e
