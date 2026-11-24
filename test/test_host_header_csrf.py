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

"""Prove-it tests for the Host / X-Forwarded-Host allowlist (b/586647104).

Mesop rejects a cross-site ``/__ui__`` POST by comparing the ``Origin`` hostname
with the request ``Host``. ``main.py`` used to copy the client-controlled
``X-Forwarded-Host`` into ``Host`` unconditionally (with
``TrustedHostMiddleware(["*"])``), so an attacker page could send
``X-Forwarded-Host: evil.com`` with ``Origin: https://evil.com`` and pass that
check. These tests assert the fixed behavior:

* an attacker-chosen ``X-Forwarded-Host`` never reaches the app as ``Host``, so
  the Mesop-style CSRF check still rejects the cross-site POST;
* the deployed public host, forwarded by the load balancer, is still applied
  so legitimate same-site POSTs pass;
* a direct ``Host`` spoof is rejected with a 400; health probes stay reachable;
* with no allowlist (local dev), any ``Host`` is accepted but
  ``X-Forwarded-Host`` is never honored.

Pre-fix, the attack POST returns 200 and ``request.url`` points at evil.com.
"""

# ruff: noqa: ANN001, ANN201, ANN202, D103

import os
import sys
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest

os.environ.setdefault("PROJECT_ID", "test-project")
os.environ.setdefault("LOCATION", "us-central1")
os.environ.setdefault("VEO_PROJECT_ID", "test-project")
os.environ.setdefault("VEO_LOCATION", "us-central1")

for _mod in ("parselmouth", "parselmouth.praat"):
    if _mod not in sys.modules:
        try:  # pragma: no cover - import side effect
            __import__(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from common import http_security as hs  # noqa: E402

APP_HOST = "studio.example.com"


def _build_app(allowed_hosts):
    """Build a minimal app behind the real middleware, with a Mesop-style CSRF check."""
    app = FastAPI()

    @app.post("/__ui__")
    async def ui(request: Request):
        origin_host = urlparse(request.headers.get("origin", "")).hostname
        if origin_host != request.url.hostname:
            return JSONResponse({"error": "cross-site"}, status_code=403)
        return {"status": "handled", "host": request.url.hostname}

    @app.get("/reflect")
    async def reflect(request: Request):
        return {"host": request.headers.get("host"), "url": str(request.url)}

    @app.get("/readyz")
    async def readyz():
        return {"status": "ok"}

    app.add_middleware(main.HostAllowlistMiddleware, allowed_hosts=allowed_hosts)
    return app


@pytest.fixture
def deployed_client():
    allowed = hs.resolve_allowed_hosts((APP_HOST,), "", "prod")
    # Cloud Run / GCLB hands the container an internal Host.
    return TestClient(_build_app(allowed), base_url="http://127.0.0.1:8080")


@pytest.fixture
def local_client():
    return TestClient(_build_app(None), base_url="http://testserver")


def test_attacker_forwarded_host_does_not_bypass_csrf(deployed_client):
    resp = deployed_client.post(
        "/__ui__",
        headers={"Origin": "https://evil.com", "X-Forwarded-Host": "evil.com"},
    )

    assert resp.status_code == 403


def test_attacker_forwarded_host_does_not_poison_request_url(deployed_client):
    resp = deployed_client.get("/reflect", headers={"X-Forwarded-Host": "evil.com"})

    assert resp.status_code == 200
    assert "evil.com" not in resp.text


@pytest.mark.parametrize(
    "forwarded",
    [
        f"evil.com, {APP_HOST}",
        f"{APP_HOST}, evil.com",
        f"{APP_HOST}:443@evil.com",
        f"{APP_HOST}/evil.com",
        f"{APP_HOST}.evil.com",
        f"evil.com#{APP_HOST}",
        f"{APP_HOST}:44x",
        " evil.com",
    ],
)
def test_smuggled_forwarded_host_variants_are_ignored(deployed_client, forwarded):
    resp = deployed_client.get("/reflect", headers={"X-Forwarded-Host": forwarded})

    assert resp.status_code == 200
    assert resp.json()["host"] == "127.0.0.1:8080"


def test_duplicate_forwarded_host_headers_are_ignored(deployed_client):
    resp = deployed_client.get(
        "/reflect",
        headers=[("X-Forwarded-Host", APP_HOST), ("X-Forwarded-Host", "evil.com")],
    )

    assert resp.json()["host"] == "127.0.0.1:8080"


def test_allowlisted_forwarded_host_is_applied(deployed_client):
    resp = deployed_client.post(
        "/__ui__",
        headers={"Origin": f"https://{APP_HOST}", "X-Forwarded-Host": APP_HOST},
    )

    assert resp.status_code == 200
    assert resp.json()["host"] == APP_HOST


def test_allowlisted_forwarded_host_match_is_case_insensitive(deployed_client):
    resp = deployed_client.get(
        "/reflect",
        headers={"X-Forwarded-Host": "Studio.Example.COM:443"},
    )

    assert resp.json()["host"] == "Studio.Example.COM:443"


def test_direct_host_spoof_is_rejected():
    allowed = hs.resolve_allowed_hosts((APP_HOST,), "", "prod")
    client = TestClient(_build_app(allowed), base_url="http://evil.com")

    resp = client.post("/__ui__", headers={"Origin": "https://evil.com"})

    assert resp.status_code == 400


def test_health_probe_with_internal_host_is_served():
    allowed = hs.resolve_allowed_hosts((APP_HOST,), "", "prod")
    client = TestClient(_build_app(allowed), base_url="http://10.1.2.3:8080")

    assert client.get("/readyz").status_code == 200
    assert client.get("/reflect").status_code == 400


def test_local_dev_accepts_any_host_but_ignores_forwarded_host(local_client):
    resp = local_client.post(
        "/__ui__",
        headers={"Origin": "https://evil.com", "X-Forwarded-Host": "evil.com"},
    )

    assert resp.status_code == 403
    assert local_client.get("/reflect").json()["host"] == "testserver"


# --------------------------------------------------------------------------- #
# resolve_allowed_hosts / effective_host
# --------------------------------------------------------------------------- #
def test_configured_hosts_win_and_include_loopback():
    allowed = hs.resolve_allowed_hosts(
        ("Studio.Example.com", " other.example.com "),
        "https://api.example.com",
        "prod",
    )

    assert allowed == {
        "studio.example.com",
        "other.example.com",
        "localhost",
        "127.0.0.1",
        "[::1]",
    }


def test_deployed_env_falls_back_to_api_base_url_host():
    allowed = hs.resolve_allowed_hosts((), "https://studio.example.com", "prod")

    assert "studio.example.com" in allowed


def test_wildcard_entries_never_allow_everything():
    assert hs.resolve_allowed_hosts(("*",), "", "prod") is None
    assert hs.effective_host("x.com", ["evil.com"], None) == "x.com"


def test_local_env_has_no_allowlist_by_default():
    assert hs.resolve_allowed_hosts((), "http://localhost:8080", "local") is None
    assert hs.resolve_allowed_hosts((), "https://studio.example.com", "") is None


def test_effective_host_rejects_unlisted_host():
    allowed = frozenset({APP_HOST})

    assert hs.effective_host("evil.com", [], allowed) is None
    assert hs.effective_host(None, [], allowed) is None
    assert hs.effective_host(f"{APP_HOST}:8080", [], allowed) == f"{APP_HOST}:8080"
