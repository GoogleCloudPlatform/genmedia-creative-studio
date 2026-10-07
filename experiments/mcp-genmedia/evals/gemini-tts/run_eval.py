#!/usr/bin/env python3
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
"""Live eval for mcp-gemini-go's gemini_audio_tts / list_gemini_voices.

Drives the server binary over MCP stdio (real initialize handshake), checks the
tool contract deterministically (errors, advisories, file type, duration), and
optionally sends each audio file to a Gemini "listener" that reports what was
actually heard (transcript, spoken directions, speaker count).

Stdlib only. Auth: gcloud (`gcloud auth print-access-token`) for the judge;
the server itself uses ADC.

    python3 run_eval.py --server ../../mcp-genmedia-go/mcp-gemini-go/mcp-gemini-go \
        --project my-project [--groups 38,31] [--no-judge] [--location us-central1]

Exit code is 1 if any HARD check fails. Judge findings are SOFT (reported as
WARN) because an LLM listener is noisy; use --hard-judge to make them fail.
"""
import argparse
import base64
import json
import os
import re
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

JUDGE_PROMPT = """You are auditing a text-to-speech output. Listen carefully and report what you HEAR.
Return JSON with keys:
- "transcript": strict verbatim transcript of every spoken word, including words that sound like stage directions, tag names, speaker names or instructions.
- "spoken_directions": list of words that appear to be instructions/tags/markup/speaker labels read aloud. Empty if none.
- "nonspeech": list of non-speech vocal events in order (sigh, laugh, gasp, pause ...).
- "speakers": number of distinct voices.
- "delivery": one short sentence on tone, pace, accent.
Intended words (reference only): %s"""


def wav_seconds(path):
    with open(path, "rb") as f:
        b = f.read()
    if b[:4] == b"RIFF" and len(b) >= 44:
        rate = struct.unpack("<I", b[24:28])[0]
        ch = struct.unpack("<H", b[22:24])[0]
        bits = struct.unpack("<H", b[34:36])[0]
        return (len(b) - 44) / (rate * ch * bits / 8), b
    return None, b


class MCP:
    def __init__(self, server, env):
        self.p = subprocess.Popen([server, "-t", "stdio"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=open(os.path.join(env["MCP_OUTPUT_ROOT"], "server.log"), "w"), env=env, text=True)
        self.n = 0
        self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "tts-eval", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _send(self, m):
        self.p.stdin.write(json.dumps(m) + "\n")
        self.p.stdin.flush()

    def rpc(self, method, params):
        self.n += 1
        self._send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("server exited; see server.log")
            m = json.loads(line)
            if m.get("id") == self.n:
                return m

    def call(self, tool, args):
        return self.rpc("tools/call", {"name": tool, "arguments": args})

    def close(self):
        self.p.terminate()


def judge(project, token, wav_bytes, intended, model):
    url = f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/publishers/google/models/{model}:generateContent"
    body = {"contents": [{"role": "user", "parts": [
        {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(wav_bytes).decode()}},
        {"text": JUDGE_PROMPT % intended}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read())
        return json.loads(out["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as e:  # noqa: BLE001
        return {"judge_error": str(e)[:200]}


def norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower())


def intended_text(args):
    if args.get("turns"):
        return " ".join(t["text"] for t in args["turns"])
    return args.get("text", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True, help="path to the built mcp-gemini-go binary")
    ap.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    ap.add_argument("--location", default="us-central1",
                    help="LOCATION passed to the server; non-global on purpose to prove 3.8 pins global")
    ap.add_argument("--groups", default="", help="comma-separated case groups (default: all)")
    ap.add_argument("--cases", default=os.path.join(HERE, "cases.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--hard-judge", action="store_true")
    ap.add_argument("--judge-model", default="gemini-3.5-flash")
    a = ap.parse_args()
    if not a.project:
        sys.exit("set --project or GOOGLE_CLOUD_PROJECT")

    run_dir = os.path.join(a.out, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(run_dir, exist_ok=True)
    env = dict(os.environ, GOOGLE_CLOUD_PROJECT=a.project, LOCATION=a.location, MCP_OUTPUT_ROOT=run_dir)
    token = None if a.no_judge else subprocess.check_output(["gcloud", "auth", "print-access-token"]).decode().strip()

    cases = json.load(open(a.cases))["cases"]
    groups = {g for g in a.groups.split(",") if g}
    if groups:
        cases = [c for c in cases if c["group"] in groups]

    mcp = MCP(os.path.abspath(a.server), env)
    results, hard_fail = [], 0
    for c in cases:
        args, exp = dict(c["args"]), c["expect"]
        if c["tool"] == "gemini_audio_tts":
            args.setdefault("output_directory", "audio")
            args.setdefault("output_filename", c["id"])
        t0 = time.time()
        r = mcp.call(c["tool"], args)
        dt = round(time.time() - t0, 2)
        res = r.get("result") or {}
        text = "\n".join(x.get("text", "") for x in res.get("content", []) if x.get("type") == "text")
        is_err = bool(res.get("isError")) or "error" in r
        checks = []  # (level, ok, message)

        def hard(ok, msg):
            checks.append(("HARD", bool(ok), msg))

        def soft(ok, msg):
            checks.append(("HARD" if a.hard_judge else "SOFT", bool(ok), msg))

        hard(is_err == bool(exp.get("error")), f"error={is_err} expected={bool(exp.get('error'))}")
        for s in exp.get("result_has", []):
            hard(s in text, f"result has {s!r}")
        adv = text.split("Prompt advisories:", 1)[1] if "Prompt advisories:" in text else ""
        for s in exp.get("advisories", []):
            hard(s in adv, f"advisory {s!r}")
        if exp.get("no_advisories"):
            hard(not adv, "no advisories" + (f" (got: {adv.strip()[:160]})" if adv else ""))

        m = re.search(r"Audio saved to: (\S+) \((\d+) bytes\)", text)
        path = m.group(1) if m else None
        rec = {"id": c["id"], "group": c["group"], "tool": c["tool"], "secs": dt, "is_error": is_err, "path": path}
        if "ext" in exp:
            hard(path and path.endswith(exp["ext"]), f"extension {exp['ext']} (got {path})")
        if path and path.endswith(".wav"):
            secs, wav = wav_seconds(path)
            rec["audio_seconds"] = round(secs, 2) if secs else None
            hard(secs is not None, "valid single RIFF header")
            if secs is not None and wav.count(b"RIFF") > 1:
                hard(False, "double WAV header")
            if "min_seconds" in exp:
                hard(secs and secs >= exp["min_seconds"], f"duration >= {exp['min_seconds']}s ({secs})")
            if exp.get("judge") and token:
                j = judge(a.project, token, wav, intended_text(c["args"]), a.judge_model)
                rec["judge"] = j
                if "judge_error" in j:
                    soft(False, "judge error " + j["judge_error"])
                else:
                    heard = norm(j.get("transcript", "") + " " + " ".join(j.get("spoken_directions", [])))
                    for w in exp.get("not_spoken", []):
                        soft(f" {norm(w).strip()} " not in f" {heard} ", f"not spoken: {w!r}")
                    for w in exp.get("transcript_has", []):
                        soft(norm(w).strip() in heard, f"heard: {w!r}")
                    if "speakers" in exp:
                        soft(j.get("speakers") == exp["speakers"], f"speakers={j.get('speakers')} expected {exp['speakers']}")
        if exp.get("control") and rec.get("judge") and "judge_error" not in rec["judge"]:
            # Control case: the defect is expected; pass only if the listener caught it.
            jc = [x for x in checks if x[0] == "SOFT" or (a.hard_judge and x[2].startswith(("not spoken", "heard", "speakers")))]
            caught = any(not ok for _, ok, _ in jc)
            checks = [x for x in checks if x not in jc] + [("SOFT", caught, "control: listener detected the spoken directions")]
        rec["checks"] = [{"level": l, "ok": ok, "msg": msg} for l, ok, msg in checks]
        rec["tool_text"] = text[:1500]
        failed_hard = [x for x in checks if x[0] == "HARD" and not x[1]]
        failed_soft = [x for x in checks if x[0] == "SOFT" and not x[1]]
        hard_fail += bool(failed_hard)
        status = "FAIL" if failed_hard else ("WARN" if failed_soft else "PASS")
        rec["status"] = status
        results.append(rec)
        print(f"{status:4} {c['id']:32} {dt:6.1f}s " + "; ".join(m for _, ok, m in checks if not ok), flush=True)
    mcp.close()

    json.dump(results, open(os.path.join(run_dir, "results.json"), "w"), indent=2, ensure_ascii=False)
    counts = {s: sum(r["status"] == s for r in results) for s in ("PASS", "WARN", "FAIL")}
    with open(os.path.join(run_dir, "report.md"), "w") as f:
        f.write(f"# gemini_audio_tts eval {os.path.basename(run_dir)}\n\nserver LOCATION={a.location}, project={a.project}, judge={'off' if a.no_judge else a.judge_model}\n\n")
        f.write(f"**{counts['PASS']} pass, {counts['WARN']} warn (soft judge), {counts['FAIL']} fail**\n\n| case | status | time | heard | failed checks |\n|---|---|---|---|---|\n")
        for r in results:
            heard = (r.get("judge") or {}).get("transcript", "")
            bad = "; ".join(x["msg"] for x in r["checks"] if not x["ok"])
            f.write(f"| {r['id']} | {r['status']} | {r['secs']}s | {heard[:90]} | {bad} |\n")
    print(f"\n{counts}  ->  {run_dir}/report.md")
    sys.exit(1 if hard_fail else 0)


if __name__ == "__main__":
    main()
