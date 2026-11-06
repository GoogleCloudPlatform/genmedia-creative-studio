"""Probe how Gemini Omni handles first/last frame conditioning (gmcs-qw3).

The Interactions API task enum has no first/last frame task, so this probes
whether two images plus a prompt behave as a first and a last frame, and which
input shapes honour that.  For each case the first and last frames of the
returned video are extracted with ffmpeg and compared against both input
images (mean absolute pixel difference; lower is closer).

Usage: omni_first_last_probe.py OUTDIR FIRST_IMAGE LAST_IMAGE
           [--model M] [--project P] [--only a,b] [--duration 5]
"""

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import time

import google.auth
import google.auth.transport.requests
import requests
from PIL import Image, ImageChops, ImageStat

ap = argparse.ArgumentParser()
ap.add_argument("outdir")
ap.add_argument("first_image")
ap.add_argument("last_image")
ap.add_argument("--model", default="gemini-omni-1.2-flash")
ap.add_argument("--project", default=os.environ.get("PROJECT_ID"))
ap.add_argument("--only")
ap.add_argument("--duration", type=int, default=5)
ap.add_argument("--resolution", default="360p")
a = ap.parse_args()
os.makedirs(a.outdir, exist_ok=True)

BASE = (
    "https://aiplatform.googleapis.com/v1beta1/projects/"
    f"{a.project}/locations/global/interactions"
)
creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)


def headers() -> dict:
    if not creds.valid:
        creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {creds.token}",
        "x-goog-user-project": a.project,
        "Content-Type": "application/json",
    }


def image_part(path: str) -> dict:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    data = base64.b64encode(open(path, "rb").read()).decode()
    return {"type": "image", "mime_type": mime, "data": data}


def text(t: str) -> dict:
    return {"type": "text", "text": t}


FIRST, LAST = image_part(a.first_image), image_part(a.last_image)
STORY = "A quiet forest path as the day turns to night."

CASES = {
    # Two images, instruction in the prompt only.
    "prompt_only": dict(
        parts=[
            text(
                f"{STORY} Use the first image as the first frame and the "
                "second image as the last frame of the video.",
            ),
            FIRST,
            LAST,
        ],
    ),
    # Interleaved labels directly before each image.
    "labelled": dict(
        parts=[
            text(STORY),
            text("First frame:"),
            FIRST,
            text("Last frame:"),
            LAST,
        ],
    ),
    # Images in order, but no frame wording at all (does order alone matter?).
    "order_only": dict(parts=[text(STORY), FIRST, LAST]),
    # Reversed order with the same wording: proves the order is honoured.
    "reversed": dict(
        parts=[
            text(
                f"{STORY} Use the first image as the first frame and the "
                "second image as the last frame of the video.",
            ),
            LAST,
            FIRST,
        ],
    ),
    # Explicit tasks.
    "task_first_last": dict(
        parts=[text(STORY), FIRST, LAST],
        task="first_last_frame",
    ),
    "task_i2v_two": dict(
        parts=[text(STORY), FIRST, LAST],
        task="image_to_video",
    ),
    "task_ref2v_two": dict(
        parts=[
            text(
                f"{STORY} Use the first image as the first frame and the "
                "second image as the last frame of the video.",
            ),
            FIRST,
            LAST,
        ],
        task="reference_to_video",
    ),
    # Control: a single starting image.
    "ctl_i2v": dict(parts=[text(STORY), FIRST]),
}


def frame_diff(video: str, image: str, which: str) -> float:
    png = video.replace(".mp4", f"_{which}.png")
    seek = ["-sseof", "-0.1"] if which == "last" else []
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *seek, "-i", video, "-frames:v", "1", png],
        check=True,
    )
    ref = Image.open(image).convert("RGB")
    frame = Image.open(png).convert("RGB").resize(ref.size)
    return round(sum(ImageStat.Stat(ImageChops.difference(ref, frame)).mean) / 3, 1)


def run(name: str, case: dict) -> dict:
    body = {
        "model": a.model,
        "stream": False,
        "background": True,
        "input": [{"type": "user_input", "content": case["parts"]}],
        "response_format": [
            {
                "type": "video",
                "resolution": a.resolution,
                "aspect_ratio": "16:9",
                "duration": f"{a.duration}s",
            },
        ],
    }
    if case.get("task"):
        body["generation_config"] = {"video_config": {"task": case["task"]}}
    res = {"case": name, "task": case.get("task")}
    t0 = time.time()
    r = requests.post(BASE, json=body, headers=headers(), timeout=120)
    res["http"] = r.status_code
    if r.status_code != 200:
        res["error"] = r.text[:400]
        return res
    j = r.json()
    while j.get("status") == "in_progress" and time.time() - t0 < 600:
        time.sleep(8)
        j = requests.get(f"{BASE}/{j['id']}", headers=headers(), timeout=120).json()
    res["status"] = j.get("status")
    if j.get("errors") or j.get("error"):
        res["error"] = json.dumps(j.get("errors") or j.get("error"))[:400]
    path = os.path.join(a.outdir, f"{name}.mp4")
    for step in j.get("steps", []):
        if step.get("type") == "user_input":
            continue
        for item in step.get("content", []) or []:
            if item.get("data") and str(item.get("mime_type", "")).startswith("video"):
                open(path, "wb").write(base64.b64decode(item["data"]))
    if os.path.exists(path):
        res["first_vs_FIRST"] = frame_diff(path, a.first_image, "first")
        res["first_vs_LAST"] = frame_diff(path, a.last_image, "first")
        res["last_vs_FIRST"] = frame_diff(path, a.first_image, "last")
        res["last_vs_LAST"] = frame_diff(path, a.last_image, "last")
    res["secs"] = round(time.time() - t0)
    return res


if __name__ == "__main__":
    names = a.only.split(",") if a.only else list(CASES)
    out = []
    for n in names:
        r = run(n, CASES[n])
        out.append(r)
        print(json.dumps(r), flush=True)
    with open(os.path.join(a.outdir, "first_last_results.json"), "a") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
