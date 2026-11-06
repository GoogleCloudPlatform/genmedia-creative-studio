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

"""Tests for the hardened ``/api/get_signed_url`` endpoint (gmcs-oi4.3).

The endpoint signs a GCS object URL as the runtime service account. It must
mirror the ``/media`` proxy's guards: authentication outside local dev and a
fail-closed bucket allowlist (so it cannot be used to read arbitrary buckets),
and it must pass ``target_scopes`` as a list.
"""

import os
import sys
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

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

LEGIT_BUCKET = "legit-app-bucket"
FOREIGN_BUCKET = "some-other-victim-bucket"
SIGNED = "https://storage.googleapis.com/legit-app-bucket/a/b.png?X-Goog-Signature=x"


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def gcs(monkeypatch):
    """Pin the allowlist to LEGIT_BUCKET and mock all signing dependencies."""
    for name in ("VIDEO_BUCKET", "IMAGE_BUCKET", "GCS_ASSETS_BUCKET"):
        monkeypatch.setattr(main.config.Default, name, "")
    monkeypatch.setattr(main.config.Default, "GENMEDIA_BUCKET", LEGIT_BUCKET)
    if hasattr(main.config.Default, "MEDIA_BUCKET"):
        monkeypatch.setattr(main.config.Default, "MEDIA_BUCKET", "")
    monkeypatch.setattr(main.config.Default, "SERVICE_ACCOUNT_EMAIL", "sa@p.iam")

    blob = MagicMock()
    blob.generate_signed_url.return_value = SIGNED
    bucket = MagicMock()
    bucket.blob.return_value = blob
    storage_client = MagicMock()
    storage_client.bucket.return_value = bucket
    impersonated = MagicMock()

    monkeypatch.setattr(main.google.auth, "default", lambda: (MagicMock(), "p"))
    monkeypatch.setattr(main.impersonated_credentials, "Credentials", impersonated)
    monkeypatch.setattr(main.storage, "Client", lambda: storage_client)
    return MagicMock(
        blob=blob,
        bucket=bucket,
        storage_client=storage_client,
        impersonated=impersonated,
    )


def test_allowed_bucket_gets_signed_url(client, gcs):
    resp = client.get(
        "/api/get_signed_url", params={"gcs_uri": f"gs://{LEGIT_BUCKET}/a/b.png"}
    )

    assert resp.status_code == 200
    assert resp.json() == {"signed_url": SIGNED}
    gcs.storage_client.bucket.assert_called_once_with(LEGIT_BUCKET)
    gcs.bucket.blob.assert_called_once_with("a/b.png")


def test_target_scopes_is_a_list(client, gcs):
    client.get(
        "/api/get_signed_url", params={"gcs_uri": f"gs://{LEGIT_BUCKET}/a/b.png"}
    )

    scopes = gcs.impersonated.call_args.kwargs["target_scopes"]
    assert scopes == ["https://www.googleapis.com/auth/devstorage.read_only"]


def test_foreign_bucket_is_rejected_before_any_gcs_access(client, gcs):
    resp = client.get(
        "/api/get_signed_url",
        params={"gcs_uri": f"gs://{FOREIGN_BUCKET}/secrets/private.key"},
    )

    assert resp.status_code == 404
    assert resp.json() == {"error": "Object not found"}
    gcs.storage_client.bucket.assert_not_called()
    gcs.impersonated.assert_not_called()


def test_proxy_url_is_normalized_and_allowlisted(client, gcs):
    resp = client.get(
        "/api/get_signed_url", params={"gcs_uri": f"/media/{LEGIT_BUCKET}/a/b.png"}
    )

    assert resp.status_code == 200
    gcs.bucket.blob.assert_called_once_with("a/b.png")


@pytest.mark.parametrize(
    "bad_uri",
    ["", "not-a-gcs-uri", f"gs://{LEGIT_BUCKET}", f"gs://{LEGIT_BUCKET}/"],
)
def test_malformed_uri_is_a_400(client, gcs, bad_uri):
    resp = client.get("/api/get_signed_url", params={"gcs_uri": bad_uri})

    assert resp.status_code == 400
    assert resp.json() == {"error": "Invalid gcs_uri"}
    gcs.storage_client.bucket.assert_not_called()


def test_empty_allowlist_fails_closed(client, gcs, monkeypatch):
    monkeypatch.setattr(main.config.Default, "GENMEDIA_BUCKET", "")

    resp = client.get(
        "/api/get_signed_url", params={"gcs_uri": f"gs://{LEGIT_BUCKET}/a/b.png"}
    )

    assert resp.status_code == 404
    gcs.storage_client.bucket.assert_not_called()


def test_requires_authentication_outside_local_dev(client, gcs, monkeypatch):
    monkeypatch.setattr(main.config.Default, "APP_ENV", "prod")
    monkeypatch.setattr(main.config.Default, "REQUIRE_AUTHENTICATED_USER", False)

    resp = client.get(
        "/api/get_signed_url", params={"gcs_uri": f"gs://{LEGIT_BUCKET}/a/b.png"}
    )

    assert resp.status_code == 403
    gcs.storage_client.bucket.assert_not_called()


def test_signing_failure_returns_500_without_internal_detail(client, gcs):
    gcs.blob.generate_signed_url.side_effect = RuntimeError("secret internal detail")

    resp = client.get(
        "/api/get_signed_url", params={"gcs_uri": f"gs://{LEGIT_BUCKET}/a/b.png"}
    )

    assert resp.status_code == 500
    assert resp.json() == {"error": "Failed to generate signed URL"}
    assert "secret" not in resp.text
