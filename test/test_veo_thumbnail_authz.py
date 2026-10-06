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
"""Prove-It test for the write-side IDOR on the veo thumbnail task endpoint.

``routers.veo_router.generate_thumbnail`` is the handler for
``POST /api/veo/thumbnail``. It is a *task* endpoint: Cloud Tasks invokes it with
a Google-signed OIDC token minted for ``SERVICE_ACCOUNT_EMAIL`` (see
``common.tasks.enqueue_thumbnail_task``). The handler calls
``services.veo_service.run_thumbnail_job``, which overwrites a Firestore item's
``thumbnail_uri`` keyed by the client-supplied ``job_id`` with **no owner check**.

Pre-fix, the endpoint ran that write for *any* caller, so an authenticated user
(or anyone who can reach the URL) could POST a victim's ``job_id`` plus an
attacker-controlled ``video_uri`` and overwrite the victim item's thumbnail —
``test_attacker_without_task_identity_cannot_overwrite_thumbnail`` demonstrates
that unauthorized write and FAILS against pre-fix behavior.

The fix (``common.task_auth.authorize_cloud_task_caller``) restricts the endpoint
to the trusted Cloud Tasks OIDC identity and fails closed. The legitimate Cloud
Tasks caller still succeeds (``test_legit_cloud_tasks_caller_can_write_thumbnail``),
and the in-process fallback never traverses this HTTP endpoint.

External boundaries (video frame selection, thumbnail extraction/upload,
Firestore, and OIDC verification) are faked in-process so the test is hermetic.
"""

# ruff: noqa: D101, D102, D103, S101

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common.task_auth as task_auth
import services.veo_service as veo_service
from routers import veo_router

OWNER = "victim@example.com"
JOB_ID = "job_victim_123"
LEGIT_THUMB = "gs://victim-bucket/legit-thumb.png"

TRUSTED_SA = "tasks-sa@proj.iam.gserviceaccount.com"
OTHER_SA = "attacker-sa@evil.iam.gserviceaccount.com"
API_BASE_URL = "https://svc.example.com"
EXPECTED_AUDIENCE = f"{API_BASE_URL}/api/veo/thumbnail"

# Token strings the faked verifier recognizes (production never sees these; the
# verifier itself is the test seam, patched below).
VALID_TASK_TOKEN = "valid-task-token"  # noqa: S105
WRONG_SA_TOKEN = "wrong-sa-token"  # noqa: S105
UNVERIFIED_EMAIL_TOKEN = "unverified-email-token"  # noqa: S105

ATTACKER_VIDEO = "gs://attacker-bucket/evil.mp4"
LEGIT_VIDEO = "gs://victim-bucket/real-render.mp4"


class FakeItem:
    """Minimal stand-in for the Firestore-backed media item."""

    def __init__(self, user_email, thumbnail_uri):
        self.user_email = user_email
        self.thumbnail_uri = thumbnail_uri


def _thumb_for(video_uri):
    """Deterministic 'uploaded thumbnail' uri derived from the source video."""
    return f"{video_uri}::thumb"


@pytest.fixture
def store():
    """In-process item store seeded with a single victim-owned item."""
    return {JOB_ID: FakeItem(user_email=OWNER, thumbnail_uri=LEGIT_THUMB)}


@pytest.fixture
def fake_verifier():
    """Registry-backed replacement for ``common.task_auth.verify_oidc_token``.

    Returns claims for recognized tokens (asserting the audience the router
    computed) and raises for anything else — exactly as the real Google verifier
    would on a bad/absent token.
    """

    def _verify(token, audience):
        assert audience == EXPECTED_AUDIENCE, (
            f"router passed unexpected OIDC audience {audience!r}"
        )
        if token == VALID_TASK_TOKEN:
            return {
                "iss": "https://accounts.google.com",
                "email": TRUSTED_SA,
                "email_verified": True,
                "aud": audience,
            }
        if token == WRONG_SA_TOKEN:
            return {
                "iss": "https://accounts.google.com",
                "email": OTHER_SA,
                "email_verified": True,
                "aud": audience,
            }
        if token == UNVERIFIED_EMAIL_TOKEN:
            return {
                "iss": "https://accounts.google.com",
                "email": TRUSTED_SA,
                "email_verified": False,
                "aud": audience,
            }
        raise ValueError(f"unrecognized/invalid token: {token!r}")

    return _verify


@pytest.fixture
def client(monkeypatch, store, fake_verifier):
    """TestClient mounting the REAL veo_router with external boundaries faked.

    ``run_thumbnail_job`` runs unmodified; only its video/Firestore seams and the
    OIDC verifier are replaced. Deployed (``iap``) auth mode is selected so the
    task-identity check is active (it is a no-op in local mode by design).
    """
    # Deployed auth mode: the Cloud Tasks identity check must run.
    monkeypatch.setenv("APP_ENV", "production")

    # ``config.Default`` is a dataclass whose field defaults are captured at class
    # definition from the (then-empty) env, so patching its attributes would not
    # reach ``cfg()`` instances. Patch the config the router actually calls.
    _trusted_sa = TRUSTED_SA
    _api_base_url = API_BASE_URL

    class _FakeCfg:
        SERVICE_ACCOUNT_EMAIL = _trusted_sa
        API_BASE_URL = _api_base_url

    monkeypatch.setattr(veo_router, "cfg", _FakeCfg)

    # OIDC verification seam.
    monkeypatch.setattr(task_auth, "verify_oidc_token", fake_verifier)

    # Video-processing boundaries (no ffmpeg / GCS / Gemini in the test).
    monkeypatch.setattr(
        veo_service, "get_best_video_frame_timestamp", lambda video_uri: 1.0
    )
    monkeypatch.setattr(
        veo_service,
        "extract_and_upload_thumbnail",
        lambda video_uri, timestamp_s: _thumb_for(video_uri),
    )

    # Firestore boundary: operate on the in-process store. The item object is
    # mutated in place by run_thumbnail_job, so add_media_item_to_firestore just
    # persists the (same) object back.
    monkeypatch.setattr(
        veo_service, "get_media_item_by_id_system", lambda job_id: store.get(job_id)
    )

    def _persist(item):
        for job_id, existing in store.items():
            if existing is item:
                store[job_id] = item
                return

    monkeypatch.setattr(veo_service, "add_media_item_to_firestore", _persist)

    app = FastAPI()
    app.include_router(veo_router.router)
    return TestClient(app)


def _post(client, job_id, video_uri, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/api/veo/thumbnail",
        json={"job_id": job_id, "video_uri": video_uri},
        headers=headers,
    )


def test_attacker_without_task_identity_cannot_overwrite_thumbnail(client, store):
    """THE prove-it: a caller without the trusted OIDC token is rejected and the
    victim item's thumbnail is untouched.

    Against PRE-fix behavior the endpoint overwrote the thumbnail for any caller,
    so this asserts both the 403 AND that the stored thumbnail is unchanged — it
    FAILS pre-fix (overwrite happened, status 200) and PASSES post-fix.
    """
    resp = _post(client, JOB_ID, ATTACKER_VIDEO, token=None)

    assert resp.status_code == 403
    assert store[JOB_ID].thumbnail_uri == LEGIT_THUMB
    assert _thumb_for(ATTACKER_VIDEO) != store[JOB_ID].thumbnail_uri


def test_invalid_bearer_token_rejected(client, store):
    """A present-but-bogus bearer token fails verification -> 403, no write."""
    resp = _post(client, JOB_ID, ATTACKER_VIDEO, token="garbage-token")

    assert resp.status_code == 403
    assert store[JOB_ID].thumbnail_uri == LEGIT_THUMB


def test_token_for_wrong_service_account_rejected(client, store):
    """A valid Google OIDC token minted for a DIFFERENT SA -> 403, no write."""
    resp = _post(client, JOB_ID, ATTACKER_VIDEO, token=WRONG_SA_TOKEN)

    assert resp.status_code == 403
    assert store[JOB_ID].thumbnail_uri == LEGIT_THUMB


def test_unverified_email_claim_rejected(client, store):
    """A token whose ``email_verified`` is false -> 403, no write."""
    resp = _post(client, JOB_ID, ATTACKER_VIDEO, token=UNVERIFIED_EMAIL_TOKEN)

    assert resp.status_code == 403
    assert store[JOB_ID].thumbnail_uri == LEGIT_THUMB


def test_legit_cloud_tasks_caller_can_write_thumbnail(client, store):
    """Positive control: the trusted Cloud Tasks identity still succeeds.

    Proves the fix does not break the legitimate thumbnail flow (and that the
    write path is real, so the negative tests above are not vacuous).
    """
    resp = _post(client, JOB_ID, LEGIT_VIDEO, token=VALID_TASK_TOKEN)

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert store[JOB_ID].thumbnail_uri == _thumb_for(LEGIT_VIDEO)
