# Copyright 2025 Google LLC
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

"""FastAPI TestClient coverage for POST /api/checklist (LLM client mocked)."""

import pytest
from fastapi.testclient import TestClient

from api.deps import get_checklist_service
from main import app
from services.checklist import PromptChecklist


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def _override(service):
    app.dependency_overrides[get_checklist_service] = lambda: service


def teardown_function():
    app.dependency_overrides.clear()


# ---- happy path --------------------------------------------------------------


def test_checklist_happy_path(client, mock_client):
    _override(PromptChecklist(client=mock_client))

    resp = client.post("/api/checklist", json={"prompt": "Write a poem."})

    assert resp.status_code == 200
    body = resp.json()
    assert body["raw"] is None
    cats = {c["name"]: c for c in body["categories"]}
    # Issue category present and flagged, with a nested item.
    assert cats["Clarity"]["has_issue"] is True
    assert len(cats["Clarity"]["items"]) == 1
    assert "vague" in cats["Clarity"]["items"][0]["rationale"]
    # Impact/solution carried on the category explanation (parity with Mesop).
    assert "Impact Analysis" in cats["Clarity"]["explanation"]
    # No-issue category present, not flagged, no items.
    assert cats["Typos"]["has_issue"] is False
    assert cats["Typos"]["items"] == []
    # Issues sorted first.
    assert body["categories"][0]["name"] == "Clarity"
    # Only the ~1 real LLM action is a call; it was mocked.
    assert mock_client.generate_content.call_count == 1


# ---- 422 validation (empty prompt) ------------------------------------------


def test_checklist_empty_prompt_422(client, mock_client):
    _override(PromptChecklist(client=mock_client))

    resp = client.post("/api/checklist", json={"prompt": ""})

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"
    assert "message" in body["error"]
    # the mocked LLM is never called on a rejected request
    assert mock_client.generate_content.call_count == 0


def test_checklist_missing_field_422(client):
    resp = client.post("/api/checklist", json={})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


# ---- error envelope (service/LLM raises) ------------------------------------


def test_checklist_service_error_envelope(client):
    class BoomService:
        def evaluate_prompt(self, prompt):
            raise RuntimeError("Gemini exploded")

    _override(BoomService())

    resp = client.post("/api/checklist", json={"prompt": "hi"})

    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "internal_error"
    # The client gets a GENERIC message -- the raw exception text (which can leak
    # prompt content / internal paths / provider identifiers) must NOT be echoed.
    assert body["error"]["message"] == "Internal server error"
    assert "Gemini exploded" not in body["error"]["message"]


# ---- parse-fallback (unparseable -> raw) ------------------------------------


def test_checklist_parse_fallback(client):
    # The service returns (None, raw) when the markdown cannot be parsed.
    class FallbackService:
        def evaluate_prompt(self, prompt):
            return None, "totally unparseable model output"

    _override(FallbackService())

    resp = client.post("/api/checklist", json={"prompt": "hi"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["categories"] == []
    assert body["raw"] == "totally unparseable model output"


# ---- security headers / CSP --------------------------------------------------


def test_csp_frame_ancestors_header(client):
    resp = client.get("/api/healthz")
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy", "")
    assert "frame-ancestors 'self' https://google.github.io" in csp
    # Hardening (F3): base-uri / object-src locked down, img-src not wildcard-https.
    assert "base-uri 'self'" in csp
    assert "object-src 'none'" in csp
    assert "https:" not in csp.split("img-src", 1)[-1].split(";", 1)[0]


# ---- path-traversal regression (CWE-22) -------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/..%2F..%2Fmain.py",           # encoded ../../main.py (app's own source)
        "/%2e%2e%2f%2e%2e%2fmain.py",   # fully-encoded dot-segments
        # Enough ../ to reach the filesystem root from any WEB_DIST depth, so this
        # genuinely exercises the /etc/passwd escape (containment, not a missing file).
        "/" + "..%2F" * 12 + "etc%2Fpasswd",  # escape to /etc/passwd
    ],
)
def test_spa_fallback_rejects_path_traversal(client, path):
    """A traversal attempt must NEVER return file contents outside WEB_DIST.

    The containment-checked fallback serves index.html (or a 404 envelope),
    never the app source or /etc/passwd. Uses raise_server_exceptions=False.
    """
    resp = client.get(path)

    # Never leak the backend source or system files.
    assert "register_error_handlers" not in resp.text   # from main.py / api
    assert "spa_fallback" not in resp.text               # from main.py
    assert "root:x:0:0" not in resp.text                 # from /etc/passwd
    # Either the SPA index fallback (200) or the uniform 404 envelope.
    if resp.status_code == 200:
        # index.html, not an arbitrary file.
        assert "<app-root>" in resp.text or resp.text.strip().startswith("<!")
    else:
        assert resp.status_code == 404
