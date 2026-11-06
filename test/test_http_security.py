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

"""Tests for the gmcs-0lo HTTP security hardening.

Covers: 403 for app-level denials (.1), no made-up identity in the Veo router
(.2), environment-aware HSTS (.3), no internal error leakage via a global
handler (.5) and per-request correlation ids (.6).
"""

# ruff: noqa: D103, S101

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

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

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from common import http_security as hs  # noqa: E402
from common.identity import ANONYMOUS_USER_EMAIL  # noqa: E402
from routers import veo_router  # noqa: E402

VEO_BODY = {
    "prompt": "a cat",
    "duration_seconds": 5,
    "video_count": 1,
    "aspect_ratio": "16:9",
    "resolution": "720p",
    "enhance_prompt": False,
    "generate_audio": False,
    "model_version_id": "veo-3.0-generate-001",
    "person_generation": "allow_adult",
}


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("app_env", "hostname", "expected"),
    [
        ("prod", "app.example.com", True),
        ("staging", "app.example.com", True),
        ("prod", "localhost", False),
        ("prod", "127.0.0.1", False),
        ("local", "app.example.com", False),
        ("dev", "app.example.com", False),
        ("", "app.example.com", False),
        (None, "app.example.com", False),
    ],
)
def test_should_send_hsts(app_env, hostname, expected):
    assert hs.should_send_hsts(app_env, hostname) is expected


def test_resolve_correlation_id_honors_well_formed_value():
    assert hs.resolve_correlation_id("req-123_A.b") == "req-123_A.b"


@pytest.mark.parametrize(
    "bad", [None, "", "has space", "line\r\nbreak", "x" * 65, "semi;colon"]
)
def test_resolve_correlation_id_replaces_malformed_value(bad):
    new = hs.resolve_correlation_id(bad)

    assert new != bad
    assert len(new) == 36  # uuid4


def test_public_error_body_is_generic_when_deployed():
    body = hs.public_error_body(RuntimeError("db password=hunter2"), "prod", "cid-1")

    assert body == {"error": hs.GENERIC_ERROR_MESSAGE, "correlation_id": "cid-1"}


def test_public_error_body_is_detailed_in_local_dev():
    body = hs.public_error_body(RuntimeError("boom"), "local", "cid-1")

    assert "RuntimeError: boom" in body["detail"]
    assert "Traceback" in body["traceback"] or "RuntimeError" in body["traceback"]


# --------------------------------------------------------------------------- #
# Through the real app
# --------------------------------------------------------------------------- #
@pytest.fixture
def client():
    return TestClient(main.app, base_url="http://app.example.com")


@pytest.fixture
def deployed(monkeypatch):
    monkeypatch.setattr(main.config.Default, "APP_ENV", "prod")
    monkeypatch.setattr(main.config.Default, "REQUIRE_AUTHENTICATED_USER", False)


def test_hsts_header_in_deployed_env(client, deployed):
    resp = client.get("/healthz")

    assert resp.headers[hs.HSTS_HEADER] == hs.HSTS_VALUE


def test_no_hsts_in_local_env(client, monkeypatch):
    monkeypatch.setattr(main.config.Default, "APP_ENV", "local")

    resp = client.get("/healthz")

    assert hs.HSTS_HEADER not in resp.headers


def test_no_hsts_on_localhost_even_if_deployed_env(deployed):
    resp = TestClient(main.app, base_url="http://localhost").get("/healthz")

    assert hs.HSTS_HEADER not in resp.headers


def test_correlation_id_is_generated(client):
    resp = client.get("/healthz")

    assert len(resp.headers[hs.CORRELATION_ID_HEADER]) == 36


def test_correlation_id_is_honored_and_sanitized(client):
    ok = client.get("/healthz", headers={hs.CORRELATION_ID_HEADER: "trace-42"})
    bad = client.get("/healthz", headers={hs.CORRELATION_ID_HEADER: "bad value!"})

    assert ok.headers[hs.CORRELATION_ID_HEADER] == "trace-42"
    assert bad.headers[hs.CORRELATION_ID_HEADER] != "bad value!"


def test_middleware_denial_is_403_and_still_tagged(client, monkeypatch):
    monkeypatch.setattr(main.config.Default, "APP_ENV", "prod")
    monkeypatch.setattr(main.config.Default, "REQUIRE_AUTHENTICATED_USER", True)
    monkeypatch.setattr(main, "get_verified_user_identity", lambda headers: None)

    resp = client.get("/api/get_signed_url", params={"gcs_uri": "gs://b/o"})

    assert resp.status_code == 403
    assert resp.json() == {"detail": "Forbidden"}
    assert hs.CORRELATION_ID_HEADER in resp.headers


def test_media_proxy_denies_anonymous_with_403(client, deployed):
    resp = client.get("/media/some-bucket/o.png")

    assert resp.status_code == 403


def test_unhandled_error_is_generic_in_deployed_env(client, deployed, monkeypatch):
    def boom(headers):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(main, "get_verified_user_identity", boom)

    resp = TestClient(
        main.app, base_url="http://app.example.com", raise_server_exceptions=False
    ).get("/healthz", headers={hs.CORRELATION_ID_HEADER: "trace-7"})

    assert resp.status_code == 500
    assert resp.json() == {
        "error": hs.GENERIC_ERROR_MESSAGE,
        "correlation_id": "trace-7",
    }
    assert "secret" not in resp.text
    assert resp.headers[hs.CORRELATION_ID_HEADER] == "trace-7"


def test_unhandled_error_is_detailed_in_local_dev(monkeypatch):
    monkeypatch.setattr(main.config.Default, "APP_ENV", "local")

    def boom(headers):
        raise RuntimeError("visible in dev")

    monkeypatch.setattr(main, "get_verified_user_identity", boom)

    resp = TestClient(main.app, raise_server_exceptions=False).get("/healthz")

    assert resp.status_code == 500
    assert "visible in dev" in resp.json()["detail"]


def test_convert_to_gif_does_not_leak_errors(client, monkeypatch):
    monkeypatch.setattr(main.config.Default, "APP_ENV", "local")

    def boom(*_args, **_kwargs):
        raise RuntimeError("ffmpeg at /srv/internal/path failed")

    monkeypatch.setattr(main, "convert_mp4_to_gif", boom)

    resp = client.get("/api/convert_to_gif", params={"gcs_uri": "gs://b/o.mp4"})

    assert resp.status_code == 500
    assert resp.json() == {"error": "Failed to generate GIF"}


# --------------------------------------------------------------------------- #
# Veo router: no invented identity (gmcs-0lo.2)
# --------------------------------------------------------------------------- #
def _set_env(monkeypatch, app_env):
    # ``cfg()`` builds a fresh instance whose field defaults were captured at class
    # creation, so patching the class would not change the instance's APP_ENV.
    monkeypatch.setattr(
        veo_router, "cfg", lambda: SimpleNamespace(APP_ENV=app_env, SERVICE_ACCOUNT_EMAIL="")
    )


@pytest.fixture
def veo_client(monkeypatch):
    calls = []
    monkeypatch.setattr(
        veo_router, "create_initial_job", lambda req, email: calls.append(email) or "j1"
    )
    monkeypatch.setattr(veo_router, "process_veo_generation_task", lambda **_kw: None)
    app = FastAPI()
    app.include_router(veo_router.router)
    return TestClient(app), calls


def test_veo_async_forbidden_without_identity_when_deployed(veo_client, monkeypatch):
    client, calls = veo_client
    _set_env(monkeypatch, "prod")

    resp = client.post("/api/veo/generate_async", json=VEO_BODY)

    assert resp.status_code == 403
    assert calls == []


def test_veo_async_uses_shared_anonymous_identity_in_local_dev(
    veo_client, monkeypatch
):
    client, calls = veo_client
    _set_env(monkeypatch, "local")

    resp = client.post("/api/veo/generate_async", json=VEO_BODY)

    assert resp.status_code == 200
    assert calls == [ANONYMOUS_USER_EMAIL]


def test_veo_job_not_found_is_a_real_404(veo_client, monkeypatch):
    client, _ = veo_client
    monkeypatch.setattr(veo_router, "get_media_item_by_id", lambda *_a, **_k: None)

    resp = client.get("/api/veo/job/nope")

    assert resp.status_code == 404
    assert resp.json() == {"error": "Job not found"}
