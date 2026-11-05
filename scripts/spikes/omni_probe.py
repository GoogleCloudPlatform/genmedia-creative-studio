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

"""Spike: is an Omni model version reachable from this project, and does it work?

Probe A (free): GET publisher-model metadata for a control and a candidate.
Probe B (one billable call, opt-in via --generate): Interactions API at 360p.

Interpretation of Probe A status codes:
  200 -> model exists and is visible to this project
  403 -> model exists but this project is not allowlisted
  404 -> model is not served (yet)

Usage:
  python scripts/spikes/omni_probe.py --project PROJECT [--generate] [--out DIR]
"""

import argparse
import base64
import json
import os
import sys
import time

import google.auth
import google.auth.transport.requests
import requests
from google import genai

CONTROL = "gemini-omni-1.1-flash-preview"
CANDIDATE = "gemini-omni-1.2-flash"
HOST = "https://aiplatform.googleapis.com"


def _token() -> str:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def probe_metadata(model: str, project: str, token: str) -> dict:
    """Probe A: read-only publisher model metadata."""
    out = {"model": model}
    for api in ("v1beta1", "v1"):
        url = f"{HOST}/{api}/publishers/google/models/{model}"
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "x-goog-user-project": project},
            timeout=30,
        )
        try:
            body = r.json()
        except ValueError:
            body = {"raw": r.text[:300]}
        out[api] = {
            "status": r.status_code,
            "error": (body.get("error", {}) or {}).get("status"),
            "message": ((body.get("error", {}) or {}).get("message") or "")[:200],
            "name": body.get("name"),
            "versionId": body.get("versionId"),
            "launchStage": body.get("launchStage"),
        }
    return out


def probe_generate(model: str, project: str, location: str, out_dir: str | None) -> dict:
    """Probe B: one Interactions API call at the cheapest settings."""
    started = time.time()
    result: dict = {"model": model}
    try:
        client = genai.Client(
            enterprise=True,
            project=project,
            location=location,
            http_options={"timeout": 600.0},
        )
        interaction = client.interactions.create(
            model=model,
            input=[
                {
                    "type": "text",
                    "text": "A red balloon rising slowly into a blue sky, 3 seconds",
                }
            ],
            response_format=[{"type": "video", "resolution": "360p"}],
            timeout=600.0,
        )
        result["ok"] = True
        result["interaction_id"] = getattr(interaction, "id", None)
        steps = getattr(interaction, "steps", None) or getattr(
            interaction, "outputs", None
        )
        shape = []
        for step in steps or []:
            stype = getattr(step, "type", None)
            entry = {"type": stype}
            content = getattr(step, "content", None)
            if isinstance(content, list):
                entry["content_types"] = [getattr(c, "type", None) for c in content]
                for c in content:
                    if getattr(c, "type", None) == "video" and out_dir:
                        data = getattr(c, "data", None)
                        if data:
                            os.makedirs(out_dir, exist_ok=True)
                            path = f"{out_dir}/{model}-probe.mp4"
                            with open(path, "wb") as f:
                                f.write(base64.b64decode(data))
                            entry["saved"] = path
                            entry["mime_type"] = getattr(c, "mime_type", None)
            shape.append(entry)
        result["response_shape"] = shape
    except Exception as e:  # noqa: BLE001 - spike: report any failure verbatim
        result["ok"] = False
        result["error_type"] = type(e).__name__
        result["error"] = str(e)[:600]
    result["seconds"] = round(time.time() - started, 1)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--location", default="global")
    ap.add_argument("--candidate", default=CANDIDATE)
    ap.add_argument("--control", default=CONTROL)
    ap.add_argument("--generate", action="store_true", help="make ONE billable call")
    ap.add_argument(
        "--generate-control",
        action="store_true",
        help="also make one call against the control model",
    )
    ap.add_argument("--out", default=None, help="directory for any saved video")
    args = ap.parse_args()

    token = _token()
    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project": args.project,
        "probe_a": [
            probe_metadata(args.control, args.project, token),
            probe_metadata(args.candidate, args.project, token),
        ],
    }
    if args.generate:
        report["probe_b_candidate"] = probe_generate(
            args.candidate, args.project, args.location, args.out
        )
    if args.generate_control:
        report["probe_b_control"] = probe_generate(
            args.control, args.project, args.location, args.out
        )
    json.dump(report, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
