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
"""Endpoint-level prove-it test for the veo job-status read (b/565102630 residual).

``routers.veo_router.get_veo_job_status`` is the handler for
``GET /api/veo/job/<job_id>``. The ``job_id`` is client-supplied, so the handler
is the actual HTTP attack surface for the read-side IDOR fixed in
``common.metadata.get_media_item_by_id``. The router *glue* is the only untested
part of that fix: it reads the server-derived verified identity the middleware
placed on the ASGI scope (``req.scope.get("MESOP_USER_EMAIL")``, set at
``main.py:306``) and forwards it as ``caller_email=`` to the owner-scoped read.

These tests exercise that glue end-to-end against a FastAPI ``TestClient``,
driving identity through the request scope exactly the way the production
middleware does. They guard against a future refactor silently reopening the
IDOR — e.g. renaming the scope key, dropping the ``caller_email=`` kwarg, or
swapping in the unscoped ``get_media_item_by_id_system`` reader. See
``test_read_authz.py`` section D for the unit-level coverage of the read itself;
this file is its endpoint-level counterpart.

Firestore is faked in-process so the test never touches a real backend.
"""

# ruff: noqa: D101, D102, D103, S101

import datetime
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common.metadata as md
from routers import veo_router

OWNER = "alice@example.com"
ATTACKER = "attacker@evil.com"
JOB_ID = "job_alice_secret"
PRIVATE_URI = "gs://private/alice-secret.mp4"

# Header the test middleware maps onto the ASGI scope. It is NOT a production
# identity input (production derives the verified identity server-side); it only
# lets the test populate ``req.scope["MESOP_USER_EMAIL"]`` the same way the
# real middleware does at main.py:306.
IDENTITY_HEADER = "X-Test-Verified-Email"


# --------------------------------------------------------------------------- #
# In-process Firestore fake (single-document read is all this path needs)
# --------------------------------------------------------------------------- #
class FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id

    def get(self):
        return FakeSnapshot(self.id, self._store.get(self.id))


class FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, doc_id):
        return FakeDocRef(self._store, doc_id)


class FakeDB:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        store = self.collections.setdefault(name, {})
        return FakeCollection(store)

    def seed(self, collection, doc_id, data):
        self.collections.setdefault(collection, {})[doc_id] = dict(data)


@pytest.fixture
def client(monkeypatch):
    """A TestClient for an app that mirrors the production scope-identity wiring.

    A middleware copies ``IDENTITY_HEADER`` onto ``request.scope`` under
    ``MESOP_USER_EMAIL`` — the exact key/mechanism of ``main.py:306`` — and
    nothing else. The real ``veo_router`` is mounted, so the router glue under
    test (scope read -> ``caller_email`` forward -> owner-scoped read) runs
    unmodified. Firestore is faked and seeded with a single job owned by OWNER.
    """
    fake_db = FakeDB()
    fake_db.seed(
        md.config.GENMEDIA_COLLECTION_NAME,
        JOB_ID,
        {
            "user_email": OWNER,
            "status": "complete",
            "gcsuri": PRIVATE_URI,
            "gcs_uris": [PRIVATE_URI],
            "timestamp": datetime.datetime(2026, 1, 1, 12, 0, 0),
            "mime_type": "video/mp4",
        },
    )
    # The real get_media_item_by_id reads ``md.db`` from its own module globals
    # at call time, so patching it here routes the owner-scoped read through the
    # fake while the router glue stays real.
    monkeypatch.setattr(md, "db", fake_db)

    app = FastAPI()

    @app.middleware("http")
    async def _set_scope_identity(request: Request, call_next):
        email = request.headers.get(IDENTITY_HEADER)
        if email:
            request.scope["MESOP_USER_EMAIL"] = email
        return await call_next(request)

    app.include_router(veo_router.router)
    return TestClient(app)


def _get_job(client, identity):
    headers = {IDENTITY_HEADER: identity} if identity is not None else {}
    return client.get(f"/api/veo/job/{JOB_ID}", headers=headers)


def test_owner_receives_their_job(client):
    """Positive control: the verified owner gets their job back (not vacuous)."""
    resp = _get_job(client, OWNER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == JOB_ID
    assert body["status"] == "complete"
    assert body["video_uri"] == PRIVATE_URI


def test_non_owner_cannot_read_victim_job(client):
    """A DIFFERENT verified identity gets the generic not-found, never the data.

    FAILS if the router stops forwarding the per-request scope identity as
    ``caller_email`` (scope-key rename, dropped kwarg, or an unscoped read):
    the non-owner would then receive the victim's job.
    """
    resp = _get_job(client, ATTACKER)

    assert "Job not found" in resp.text
    assert PRIVATE_URI not in resp.text
    assert "complete" not in resp.text


def test_unauthenticated_cannot_read_job(client):
    """No identity on the request scope => not-found, never the job data."""
    resp = _get_job(client, None)

    assert "Job not found" in resp.text
    assert PRIVATE_URI not in resp.text
    assert "complete" not in resp.text


def test_non_owner_and_missing_are_indistinguishable(client):
    """No existence oracle: a non-owner read and a genuinely missing id render
    identically, so a caller cannot probe whether a victim's job exists."""
    non_owner = _get_job(client, ATTACKER)
    missing = client.get(
        "/api/veo/job/does_not_exist", headers={IDENTITY_HEADER: ATTACKER}
    )

    assert "Job not found" in non_owner.text
    assert "Job not found" in missing.text
    assert non_owner.json() == missing.json()
