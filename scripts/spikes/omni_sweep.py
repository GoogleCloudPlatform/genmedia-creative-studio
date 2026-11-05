"""Capability sweep for an Omni model via the Interactions REST API (prod, global).

Usage: omni_sweep.py OUTDIR [--model M] [--only name,name] [--workers N]
Writes OUTDIR/sweep_results.json (appended per run) and mp4s.
"""
import argparse, base64, json, os, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor
import google.auth, google.auth.transport.requests, requests

ap = argparse.ArgumentParser()
ap.add_argument("outdir")
ap.add_argument("--model", default="gemini-omni-1.2-flash")
ap.add_argument("--project", default=os.environ.get("PROJECT_ID"))
ap.add_argument("--only")
ap.add_argument("--workers", type=int, default=4)
ap.add_argument("--assets", default=os.path.dirname(os.path.abspath(__file__)))
a = ap.parse_args()
os.makedirs(a.outdir, exist_ok=True)

BASE = f"https://aiplatform.googleapis.com/v1beta1/projects/{a.project}/locations/global/interactions"
creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
lock = threading.Lock()

def token():
    with lock:
        if not creds.valid:
            creds.refresh(google.auth.transport.requests.Request())
        return creds.token

def hdr():
    return {"Authorization": f"Bearer {token()}", "x-goog-user-project": a.project, "Content-Type": "application/json"}

def b64(p):
    return base64.b64encode(open(os.path.join(a.assets, p), "rb").read()).decode()

IMG1 = {"type": "image", "mime_type": "image/png", "data": b64("frame1.png")}
IMG2 = {"type": "image", "mime_type": "image/png", "data": b64("frame2.png")}
VID = {"type": "video", "mime_type": "video/mp4", "data": b64("cand12_0.mp4")}
T2V = "a lighthouse on a rocky coast at dusk, waves crashing"

def case(prompt=T2V, parts=(), rf=None, task=None, extra=None):
    return dict(prompt=prompt, parts=list(parts), rf=rf, task=task, extra=extra or {})

def rf(**kw):
    return [dict(type="video", **kw)]

CASES = {
    # resolutions (3s clips where possible)
    "res_default": case(),
    "res_360p": case(rf=rf(resolution="360p")),
    "res_720p": case(rf=rf(resolution="720p")),
    "res_1080p": case(rf=rf(resolution="1080p", duration="3s")),
    "res_4k": case(rf=rf(resolution="4k", duration="3s")),
    "res_bogus": case(rf=rf(resolution="480p")),
    # aspect ratios (360p to be cheap)
    "ar_16_9": case(rf=rf(resolution="360p", aspect_ratio="16:9")),
    "ar_9_16": case(rf=rf(resolution="360p", aspect_ratio="9:16")),
    "ar_1_1": case(rf=rf(resolution="360p", aspect_ratio="1:1")),
    "ar_4_3": case(rf=rf(resolution="360p", aspect_ratio="4:3")),
    "ar_3_4": case(rf=rf(resolution="360p", aspect_ratio="3:4")),
    "ar_21_9": case(rf=rf(resolution="360p", aspect_ratio="21:9")),
    "ar_bogus": case(rf=rf(resolution="360p", aspect_ratio="7:5")),
    # durations (360p)
    **{f"dur_{d}": case(rf=rf(resolution="360p", duration=f"{d}s")) for d in (1, 2, 3, 5, 8, 10, 12, 15, 20, 30)},
    # modes
    "mode_i2v": case("animate this scene: gentle camera push-in", [IMG1], rf(resolution="360p")),
    "mode_ref1": case("a character walking through this environment", [IMG1], rf(resolution="360p")),
    "mode_ref2": case("combine the look of these two images into one scene", [IMG1, IMG2], rf(resolution="360p")),
    "mode_ref4": case("combine these references", [IMG1, IMG2, IMG1, IMG2], rf(resolution="360p")),
    "mode_edit": case("edit this video: make it nighttime with a full moon", [VID], rf(resolution="360p")),
    "mode_extend": case("extend this video by a few more seconds, same scene continuing", [VID], rf(resolution="360p")),
    "mode_vid3": case("make a montage of these clips", [VID, VID, VID], rf(resolution="360p")),
    "mode_vid4": case("make a montage of these clips", [VID, VID, VID, VID], rf(resolution="360p")),
    # explicit generation_config.video_config.task
    "task_t2v": case(task="text_to_video", rf=rf(resolution="360p")),
    "task_i2v": case("animate this scene", [IMG1], rf(resolution="360p"), task="image_to_video"),
    "task_ref2v": case("a character in this environment", [IMG1], rf(resolution="360p"), task="reference_to_video"),
    "task_edit": case("make it night", [VID], rf(resolution="360p"), task="edit"),
    "task_extend": case("continue the scene", [VID], rf(resolution="360p"), task="extend"),
    "task_bogus": case(task="not_a_task", rf=rf(resolution="360p")),
    "task_mismatch": case("make it night", [VID], rf(resolution="360p"), task="text_to_video"),
}

CASES2 = {
    "task_upscale": case("upscale this video", [VID], rf(resolution="1080p"), task="upscale"),
    "upscale_notask_1080": case("upscale this video to higher resolution", [VID], rf(resolution="1080p")),
    "img_10": case("combine these references", [IMG1, IMG2] * 5, rf(resolution="360p", duration="3s")),
    "img_11": case("combine these references", [IMG1, IMG2] * 5 + [IMG1], rf(resolution="360p", duration="3s")),
    "img_14": case("combine these references", [IMG1, IMG2] * 7, rf(resolution="360p", duration="3s")),
    "vid_5": case("make a montage of these clips", [VID] * 5, rf(resolution="360p", duration="3s")),
    "vid_task_edit_2": case("blend these two clips", [VID, VID], rf(resolution="360p"), task="edit"),
    "edit_dur_8": case("make it night", [VID], rf(resolution="360p", duration="8s")),
    "i2v_ar_9_16": case("animate this", [IMG1], rf(resolution="360p", aspect_ratio="9:16", duration="3s")),
    "ctl_ar_9_16_d5": case(rf=rf(resolution="360p", aspect_ratio="9:16", duration="5s")),
    "ctl_d12": case(rf=rf(resolution="360p", duration="12s")),
    "ctl_default": case(rf=rf(resolution="360p")),
    "upscale_video_only_1080": case("", [VID], rf(resolution="1080p"), task="upscale"),
    "upscale_video_only_4k": case("", [VID], rf(resolution="4k"), task="upscale"),
}
CASES.update(CASES2)

def run(name, c, store=False, prev=None, model=None):
    body = {
        "model": model or a.model,
        "stream": False, "background": True,
        "input": [{"type": "user_input", "content": ([{"type": "text", "text": c["prompt"]}] if c["prompt"] else []) + c["parts"]}],
    }
    if store:
        body["store"] = True
    if prev:
        body["previous_interaction_id"] = prev
    if c["rf"]:
        body["response_format"] = c["rf"]
    if c["task"]:
        body["generation_config"] = {"video_config": {"task": c["task"]}}
    body.update(c["extra"])
    res = {"case": name, "model": body["model"]}
    t0 = time.time()
    try:
        r = requests.post(BASE, json=body, headers=hdr(), timeout=120)
        res["create_http"] = r.status_code
        if r.status_code != 200:
            res["error"] = r.text[:500]
            return res
        j = r.json()
        iid = j["id"]; res["interaction_id"] = iid
        while j.get("status") == "in_progress" and time.time() - t0 < 600:
            time.sleep(8)
            j = requests.get(f"{BASE}/{iid}", headers=hdr(), timeout=120).json()
        res["status"] = j.get("status")
        if j.get("errors"):
            res["error"] = json.dumps(j["errors"])[:500]
        if j.get("error"):
            res["error"] = json.dumps(j["error"])[:500]
        n = 0
        def walk(o):
            nonlocal n
            if isinstance(o, dict):
                if o.get("data") and str(o.get("mime_type", "")).startswith("video") and o.get("type") != "user_input":
                    path = os.path.join(a.outdir, f"{name}_{n}.mp4")
                    # skip echoed input video
                    open(path, "wb").write(base64.b64decode(o["data"])); n += 1
                for v in o.values(): walk(v)
            elif isinstance(o, list):
                for x in o: walk(x)
        # only walk model output steps
        for s in j.get("steps", []):
            if s.get("type") != "user_input":
                walk(s)
        for s in j.get("outputs", []) or []:
            walk(s)
        res["videos"] = n
        res["usage_out"] = (j.get("usage") or {}).get("output_tokens_by_modality")
        if n:
            p = os.path.join(a.outdir, f"{name}_0.mp4")
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration", "-of", "json", p],
                                 capture_output=True, text=True).stdout
            streams = json.loads(out or "{}").get("streams", [])
            v = next((s for s in streams if s["codec_type"] == "video"), {})
            res["dims"] = f'{v.get("width")}x{v.get("height")}'
            res["dur"] = round(float(v.get("duration", 0)), 2)
            res["audio"] = any(s["codec_type"] == "audio" for s in streams)
        elif j.get("status") == "completed":
            res["note"] = "completed without video"
            res["step_types"] = [s.get("type") for s in j.get("steps", [])]
    except Exception as e:
        res["exception"] = repr(e)[:300]
    res["secs"] = round(time.time() - t0)
    return res

def multiturn():
    first = run("mt_1", case(rf=rf(resolution="360p")), store=True)
    out = [first]
    if first.get("interaction_id") and first.get("videos"):
        out.append(run("mt_2", case("same scene but now at night with heavy rain", rf=rf(resolution="360p")), store=True, prev=first["interaction_id"]))
    return out

if __name__ == "__main__":
    names = a.only.split(",") if a.only else list(CASES)
    results = []
    jobs = [n for n in names if n in CASES]
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(run, n, CASES[n]) for n in jobs]
        mt = ex.submit(multiturn) if (not a.only or "multiturn" in names) else None
        for f in futs:
            r = f.result(); results.append(r); print(json.dumps(r), flush=True)
        if mt:
            for r in mt.result():
                results.append(r); print(json.dumps(r), flush=True)
    with open(os.path.join(a.outdir, "sweep_results.json"), "a") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
