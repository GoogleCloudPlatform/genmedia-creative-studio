"""Probe Omni reference-to-video task handling (gmcs-csx).

Core ``ref2v`` sends no ``video_config.task``.  gmcs-qw3 showed that two images
without a task are read as first/last frames.  This compares, for 1, 2 and 3
reference images, the inferred task (none) against an explicit
``reference_to_video`` task.  Reference images are synthetic subjects on flat,
distinct backgrounds, so a generated frame that is pixel-close to one of them
(min mean abs diff, lower is closer) means the image was used as a *frame*
(i2v / first-last behaviour); a large diff means it was used as a *reference*.

Usage: omni_ref2v_probe.py OUTDIR [--model M] [--project P]
           [--only none_1,ref_2] [--duration 5]
"""

import argparse
import base64
import io
import json
import os
import subprocess
import time

import google.auth
import google.auth.transport.requests
import requests
from PIL import Image, ImageChops, ImageDraw, ImageStat

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


def make_subject(kind: str, bg: str, fg: str) -> Image.Image:
    img = Image.new("RGB", (640, 360), bg)
    d = ImageDraw.Draw(img)
    if kind == "circle":
        d.ellipse((220, 80, 420, 280), fill=fg)
    elif kind == "triangle":
        d.polygon([(320, 70), (210, 290), (430, 290)], fill=fg)
    else:
        d.rectangle((230, 90, 410, 270), fill=fg)
    return img


REFS = [
    make_subject("circle", "#fff8dc", "#d62828"),  # red ball on cream
    make_subject("triangle", "#d9d9d9", "#2a9d3c"),  # green cone on grey
    make_subject("square", "#b8e0ff", "#1d3fbf"),  # blue cube on sky blue
]
REF_PATHS = []
for i, im in enumerate(REFS):
    p = os.path.join(a.outdir, f"ref{i + 1}.png")
    im.save(p)
    REF_PATHS.append(p)


def image_part(im: Image.Image) -> dict:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return {
        "type": "image",
        "mime_type": "image/png",
        "data": base64.b64encode(buf.getvalue()).decode(),
    }


PROMPTS = {
    1: "A red ball rolls across a wooden table in a sunlit room.",
    2: "A red ball and a green cone sit on a wooden table in a sunlit room.",
    3: "A red ball, a green cone and a blue cube sit on a wooden table in a sunlit room.",
}

CASES = {}
for n in (1, 2, 3):
    parts = [{"type": "text", "text": PROMPTS[n]}] + [image_part(r) for r in REFS[:n]]
    CASES[f"none_{n}"] = dict(parts=parts, n=n)
    CASES[f"ref_{n}"] = dict(parts=parts, n=n, task="reference_to_video")


def frame_diffs(video: str, n: int, which: str) -> list:
    png = video.replace(".mp4", f"_{which}.png")
    seek = ["-sseof", "-0.1"] if which == "last" else []
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *seek, "-i", video, "-frames:v", "1", png],
        check=True,
    )
    frame = Image.open(png).convert("RGB")
    out = []
    for r in REFS[:n]:
        ref = r.resize(frame.size)
        out.append(
            round(sum(ImageStat.Stat(ImageChops.difference(ref, frame)).mean) / 3, 1)
        )
    return out


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
    res = {"case": name, "model": a.model, "task": case.get("task")}
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
                with open(path, "wb") as f:
                    f.write(base64.b64decode(item["data"]))
    if os.path.exists(path):
        res["first_vs_refs"] = frame_diffs(path, case["n"], "first")
        res["last_vs_refs"] = frame_diffs(path, case["n"], "last")
    res["secs"] = round(time.time() - t0)
    return res


if __name__ == "__main__":
    names = a.only.split(",") if a.only else list(CASES)
    out = []
    for n in names:
        r = run(n, CASES[n])
        out.append(r)
        print(json.dumps(r), flush=True)
    with open(os.path.join(a.outdir, "ref2v_results.json"), "a") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
