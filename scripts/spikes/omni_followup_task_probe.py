"""Probe multi-turn follow-ups with an explicit Omni task (gmcs-csx).

Core sends ``generation_config.video_config.task`` for the active mode on every
turn, including text-only chat follow-ups that use ``previous_interaction_id``.
This checks that a follow-up is accepted (and still produces a video) with no
task versus the same task as the first turn, for first/last frame and
reference-to-video bases.

Usage: omni_followup_task_probe.py OUTDIR [--model M] [--project P]
           [--only fl,ref1,ref3] [--duration 5]
"""

import argparse
import base64
import io
import json
import os
import time

import google.auth
import google.auth.transport.requests
import requests
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument("outdir")
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


def subject(kind: str, bg: str, fg: str) -> dict:
    img = Image.new("RGB", (640, 360), bg)
    d = ImageDraw.Draw(img)
    if kind == "circle":
        d.ellipse((220, 80, 420, 280), fill=fg)
    elif kind == "triangle":
        d.polygon([(320, 70), (210, 290), (430, 290)], fill=fg)
    else:
        d.rectangle((230, 90, 410, 270), fill=fg)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {
        "type": "image",
        "mime_type": "image/png",
        "data": base64.b64encode(buf.getvalue()).decode(),
    }


IMGS = [
    subject("circle", "#fff8dc", "#d62828"),
    subject("triangle", "#d9d9d9", "#2a9d3c"),
    subject("square", "#b8e0ff", "#1d3fbf"),
]
TXT = lambda t: {"type": "text", "text": t}  # noqa: E731

BASES = {
    "fl": dict(
        parts=[TXT("A red ball turns into a green cone on a table."), IMGS[0], IMGS[1]],
        task="image_to_video",
    ),
    "ref1": dict(
        parts=[TXT("A red ball rolls across a wooden table."), IMGS[0]],
        task="reference_to_video",
    ),
    "ref3": dict(
        parts=[
            TXT("A red ball, a green cone and a blue cube on a wooden table."),
            *IMGS,
        ],
        task="reference_to_video",
    ),
}
FOLLOW_UP = "Make the camera slowly orbit around the objects."


def call(parts: list, task: str | None, previous: str | None) -> dict:
    body = {
        "model": a.model,
        "stream": False,
        "background": True,
        "input": [{"type": "user_input", "content": parts}],
        "response_format": [
            {
                "type": "video",
                "resolution": a.resolution,
                "aspect_ratio": "16:9",
                "duration": f"{a.duration}s",
            },
        ],
    }
    if task:
        body["generation_config"] = {"video_config": {"task": task}}
    if previous:
        body["previous_interaction_id"] = previous
    res = {"task": task, "previous": bool(previous)}
    t0 = time.time()
    r = requests.post(BASE, json=body, headers=headers(), timeout=120)
    res["http"] = r.status_code
    if r.status_code != 200:
        res["error"] = r.text[:300]
        return res
    j = r.json()
    while j.get("status") == "in_progress" and time.time() - t0 < 600:
        time.sleep(8)
        j = requests.get(f"{BASE}/{j['id']}", headers=headers(), timeout=120).json()
    res["status"] = j.get("status")
    res["id"] = j.get("id")
    if j.get("errors") or j.get("error"):
        res["error"] = json.dumps(j.get("errors") or j.get("error"))[:300]
    res["has_video"] = any(
        item.get("data") and str(item.get("mime_type", "")).startswith("video")
        for step in j.get("steps", [])
        if step.get("type") != "user_input"
        for item in step.get("content", []) or []
    )
    res["secs"] = round(time.time() - t0)
    return res


if __name__ == "__main__":
    out = []
    for name in a.only.split(",") if a.only else list(BASES):
        b = BASES[name]
        first = call(b["parts"], b["task"], None)
        first["case"] = f"{name}:first"
        print(json.dumps(first), flush=True)
        out.append(first)
        if not first.get("id") or not first.get("has_video"):
            continue
        for follow_task in (None, b["task"]):
            r = call([TXT(FOLLOW_UP)], follow_task, first["id"])
            r["case"] = f"{name}:followup"
            print(json.dumps(r), flush=True)
            out.append(r)
    with open(os.path.join(a.outdir, "followup_results.json"), "a") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
