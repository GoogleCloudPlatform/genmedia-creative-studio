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

"""Prove-it tests for the CORS policy (b/585272688).

``main.py`` used to default ``CORS_ORIGIN_REGEX`` to ``https://.*`` with
``allow_credentials=True``, so any HTTPS site could make credentialed
cross-origin calls to the API and read the responses. These tests assert the
fixed behavior:

* by default no origin is granted cross-origin access (no CORS middleware);
* an origin listed in ``CORS_ALLOWED_ORIGINS`` is granted, others are not;
* a literal ``*`` in the list is ignored (it never means "any origin").

``main`` builds its middleware stack at import time, so each case imports it
in a fresh interpreter with its own environment.

Pre-fix, ``https://evil.com`` receives ``Access-Control-Allow-Origin`` and
``Access-Control-Allow-Credentials: true`` by default.
"""

# ruff: noqa: ANN201, D103, S603

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_PROBE = """
import json, sys
from unittest.mock import MagicMock
for _mod in ("parselmouth", "parselmouth.praat"):
    try:
        __import__(_mod)
    except ImportError:
        sys.modules[_mod] = MagicMock()
from fastapi.testclient import TestClient
import main
client = TestClient(main.app)
out = {}
for origin in sys.argv[1:]:
    pre = client.options(
        "/healthz",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    get = client.get("/healthz", headers={"Origin": origin})
    out[origin] = {
        "preflight_allow_origin": pre.headers.get("access-control-allow-origin"),
        "allow_origin": get.headers.get("access-control-allow-origin"),
        "allow_credentials": get.headers.get("access-control-allow-credentials"),
    }
print("CORS_RESULT=" + json.dumps(out))
"""


def _probe(env_overrides: dict[str, str], *origins: str) -> dict:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CORS_ALLOWED_ORIGINS", "CORS_ORIGIN_REGEX", "ALLOWED_HOSTS")
    }
    env.update(
        {
            "PROJECT_ID": "test-project",
            "LOCATION": "us-central1",
            "VEO_PROJECT_ID": "test-project",
            "VEO_LOCATION": "us-central1",
            "APP_ENV": "local",
        },
    )
    env.update(env_overrides)
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE, *origins],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("CORS_RESULT="):
            return json.loads(line.removeprefix("CORS_RESULT="))
    pytest.fail(f"probe failed:\n{proc.stdout}\n{proc.stderr}")


def test_no_cross_origin_access_by_default():
    result = _probe({}, "https://evil.com", "http://localhost:8080")

    for origin, headers in result.items():
        assert headers["allow_origin"] is None, origin
        assert headers["preflight_allow_origin"] is None, origin
        assert headers["allow_credentials"] is None, origin


def test_only_listed_origins_are_granted():
    result = _probe(
        {"CORS_ALLOWED_ORIGINS": "https://studio.example.com"},
        "https://studio.example.com",
        "https://evil.com",
        "https://studio.example.com.evil.com",
    )

    granted = result["https://studio.example.com"]
    assert granted["allow_origin"] == "https://studio.example.com"
    assert granted["preflight_allow_origin"] == "https://studio.example.com"
    assert granted["allow_credentials"] == "true"
    for origin in ("https://evil.com", "https://studio.example.com.evil.com"):
        assert result[origin]["allow_origin"] is None, origin
        assert result[origin]["preflight_allow_origin"] is None, origin


def test_wildcard_entry_is_ignored():
    result = _probe({"CORS_ALLOWED_ORIGINS": "*"}, "https://evil.com")

    assert result["https://evil.com"]["allow_origin"] is None
