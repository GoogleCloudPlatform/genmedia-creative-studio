# Copyright 2026 Google LLC
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

import os

# Disable mTLS client certificate fetching which can cause segfaults (status code -11) in some local environments
os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"

import uuid
import glob
import asyncio
import json
import time
from typing import List, Optional, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Import core logic
from core.generator import generate_video
from core.variations import generate_concept_variations
from core.metrics import evaluate_technical_quality
from core.c2pa import summarize_c2pa

# Load environment variables
load_dotenv()

app = FastAPI(title="Veo Variations Studio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths for static assets
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_DIR = os.getenv("VIDEO_DIR", os.path.join(BASE_DIR, "videos"))
os.makedirs(VIDEO_DIR, exist_ok=True)
UI_DIST_DIR = os.path.join(BASE_DIR, "ui/dist")

# Mount video directory
app.mount("/static/videos", StaticFiles(directory=VIDEO_DIR), name="videos")

# In-memory storage for jobs
jobs = {}

class JobStatus(BaseModel):
    job_id: str
    status: str
    results: Optional[dict] = None
    error: Optional[str] = None

async def run_variation_benchmark(job_id: str, prompt: str, count: int, duration: int, aspect_ratio: str, image_path: Optional[str], video_model: Optional[str] = None):
    """Orchestrates variation generation, video generation, and analysis."""
    try:
        project_id = os.getenv("VEO_PROJECT_ID")
        location = os.getenv("VEO_LOCATION", "us-central1")
        bucket = os.getenv("VEO_BUCKET")
        eval_project = os.getenv("GOOGLE_CLOUD_PROJECT")
        eval_location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        eval_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        target_video_model = video_model or os.getenv("VEO_MODEL", "gemini-omni-1.1-flash-preview")
        
        # 1. Generate Prompt Variations
        jobs[job_id]["status"] = "brainstorming_variations"
        try:
            variation_prompts = await generate_concept_variations(
                prompt, count, eval_project, eval_location, model_name=eval_model
            )
        except Exception as e:
            print(f"Brainstorming failed: {e}")
            raise Exception(f"Failed to generate variations: {str(e)}")
        
        # Pre-initialize the results list with the prompts
        jobs[job_id]["results"] = {
            "model": target_video_model,
            "variations": [
                {"id": i, "prompt": p, "status": "generating", "filename": None}
                for i, p in enumerate(variation_prompts)
            ]
        }
        
        # 2. Concurrent Video Generation
        jobs[job_id]["status"] = "generating_videos"
        
        async def process_one_variation(idx, v_prompt):
            try:
                print(f"Variation {idx}: Generating video with {target_video_model}...")
                start_time = time.time()
                filename = await generate_video(
                    v_prompt, target_video_model, duration, 
                    project_id, location, bucket, VIDEO_DIR, 
                    image_path=image_path, aspect_ratio=aspect_ratio
                )
                end_time = time.time()
                gen_time = round(end_time - start_time, 2)
                
                # Update status
                print(f"Variation {idx}: Video generated: {filename} in {gen_time}s. Analyzing...")
                
                full_path = os.path.join(VIDEO_DIR, filename)
                file_size = os.path.getsize(full_path) if os.path.exists(full_path) else 0
                file_size_mb = round(file_size / (1024 * 1024), 2)

                for item in jobs[job_id]["results"]["variations"]:
                    if item["id"] == idx:
                        item["status"] = "analyzing"
                        item["filename"] = filename
                        item["gen_time_sec"] = gen_time
                        item["file_size_mb"] = file_size_mb
                
                # 3. Quick analysis (NIQE + C2PA)
                metrics = await asyncio.to_thread(evaluate_technical_quality, full_path, "niqe")
                c2pa = await asyncio.to_thread(summarize_c2pa, full_path)
                
                print(f"Variation {idx}: Analysis complete.")
                for item in jobs[job_id]["results"]["variations"]:
                    if item["id"] == idx:
                        item["status"] = "completed"
                        item["metrics"] = metrics
                        item["c2pa"] = c2pa
            except Exception as e:
                import traceback
                print(f"Error in Variation {idx}: {e}")
                traceback.print_exc()
                for item in jobs[job_id]["results"]["variations"]:
                    if item["id"] == idx:
                        item["status"] = "failed"
                        item["error"] = str(e)

        # Launch all variations concurrently
        tasks = [process_one_variation(i, p) for i, p in enumerate(variation_prompts)]
        await asyncio.gather(*tasks)
        
        jobs[job_id]["status"] = "completed"
        
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)

@app.post("/variations", response_model=JobStatus)
async def create_variations(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    count: int = Form(4),
    duration: int = Form(4),
    aspect_ratio: str = Form("16:9"),
    model: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None)
):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"job_id": job_id, "status": "queued", "results": None}
    
    image_path = None
    if image:
        temp_img_dir = os.path.join(VIDEO_DIR, "uploads")
        os.makedirs(temp_img_dir, exist_ok=True)
        image_path = os.path.join(temp_img_dir, f"{job_id}_{image.filename}")
        with open(image_path, "wb") as f:
            f.write(await image.read())
            
    background_tasks.add_task(run_variation_benchmark, job_id, prompt, count, duration, aspect_ratio, image_path, model)
    return jobs[job_id]

@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]

# UI Serving
@app.get("/")
async def serve_ui():
    index_path = os.path.join(UI_DIST_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Veo Variations Studio is running (UI build not found)."}

if os.path.exists(UI_DIST_DIR):
    app.mount("/", StaticFiles(directory=UI_DIST_DIR), name="ui")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
