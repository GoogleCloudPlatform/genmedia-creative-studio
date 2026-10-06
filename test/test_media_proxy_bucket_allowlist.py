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

"""Prove-It tests for the media-proxy bucket allowlist (READ-SWEEP-B).

The ``/media/{bucket_name}/{object_path:path}`` route takes the bucket name
straight from the request path. Without an allowlist, an authenticated caller
can make the app's service account stream objects out of ANY bucket it can read
-- not just the app's own media buckets.

These tests assert the fixed behaviour:

* a request for the app's own configured bucket is still served, and
* a request for a bucket OUTSIDE the configured allowlist is rejected with a
  generic 404 BEFORE any GCS access happens (fail-closed), and
* an empty/unconfigured allowlist rejects everything (does not degrade to
  "allow all").

Pre-fix, the out-of-allowlist case returns 200 and streams the foreign bucket;
that is the regression these tests lock down.
"""

import io
import os
import sys
from unittest.mock import MagicMock

import pytest

# Ensure dummy env vars exist for model client initialization during module
# import (mirrors test/conftest.py so the module is importable without GCP).
os.environ.setdefault("PROJECT_ID", "test-project")
os.environ.setdefault("LOCATION", "us-central1")
os.environ.setdefault("VEO_PROJECT_ID", "test-project")
os.environ.setdefault("VEO_LOCATION", "us-central1")

# Mock parselmouth if not installed in the testing environment.
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
OBJECT_PATH = "images/example.png"


def _fake_storage_client_factory():
    """Return a storage-client factory whose blobs always 'exist'.

    Also exposes the created mock client so tests can assert whether the GCS
    client was touched at all (it must NOT be for a rejected bucket).
    """
    blob = MagicMock()
    blob.exists.return_value = True
    blob.content_type = "image/png"
    blob.open.return_value = io.BytesIO(b"fake-object-bytes")

    bucket = MagicMock()
    bucket.blob.return_value = blob

    client = MagicMock()
    client.bucket.return_value = bucket

    def factory():
        return client

    factory.client = client
    return factory


@pytest.fixture
def storage_factory(monkeypatch):
    factory = _fake_storage_client_factory()
    monkeypatch.setattr(main, "get_proxy_storage_client", factory)
    return factory


@pytest.fixture
def configured_allowlist(monkeypatch):
    """Pin the app config so the allowlist is exactly {LEGIT_BUCKET}."""
    monkeypatch.setattr(main.config.Default, "GENMEDIA_BUCKET", LEGIT_BUCKET)
    monkeypatch.setattr(main.config.Default, "VIDEO_BUCKET", "")
    monkeypatch.setattr(main.config.Default, "IMAGE_BUCKET", "")
    monkeypatch.setattr(main.config.Default, "GCS_ASSETS_BUCKET", "")
    if hasattr(main.config.Default, "MEDIA_BUCKET"):
        monkeypatch.setattr(main.config.Default, "MEDIA_BUCKET", "")


@pytest.fixture
def client():
    return TestClient(main.app)


def test_legitimate_bucket_is_still_served(
    client, storage_factory, configured_allowlist
):
    """A request for the app's own configured bucket is proxied normally."""
    resp = client.get(f"/media/{LEGIT_BUCKET}/{OBJECT_PATH}")

    assert resp.status_code == 200
    assert resp.content == b"fake-object-bytes"
    # The legit bucket actually reached GCS.
    storage_factory.client.bucket.assert_called_once_with(LEGIT_BUCKET)


def test_out_of_allowlist_bucket_is_rejected(
    client, storage_factory, configured_allowlist
):
    """A bucket outside the allowlist is rejected with a generic 404.

    Pre-fix this returned 200 and streamed the foreign bucket. The GCS client
    must not be touched at all (fail-closed before any storage access).
    """
    resp = client.get(f"/media/{FOREIGN_BUCKET}/secrets/private.key")

    assert resp.status_code == 404
    # Generic not-found, identical to a missing object -> no oracle.
    assert resp.json() == {"detail": "Object not found"}
    # Critically: we never reached out to GCS for the foreign bucket.
    storage_factory.client.bucket.assert_not_called()


def test_empty_allowlist_fails_closed(client, storage_factory, monkeypatch):
    """An unconfigured allowlist must reject everything, not allow all."""
    monkeypatch.setattr(main.config.Default, "GENMEDIA_BUCKET", "")
    monkeypatch.setattr(main.config.Default, "VIDEO_BUCKET", "")
    monkeypatch.setattr(main.config.Default, "IMAGE_BUCKET", "")
    monkeypatch.setattr(main.config.Default, "GCS_ASSETS_BUCKET", "")
    if hasattr(main.config.Default, "MEDIA_BUCKET"):
        monkeypatch.setattr(main.config.Default, "MEDIA_BUCKET", "")

    assert main._allowed_proxy_buckets() == set()

    resp = client.get(f"/media/{LEGIT_BUCKET}/{OBJECT_PATH}")

    assert resp.status_code == 404
    storage_factory.client.bucket.assert_not_called()


def test_allowlist_ignores_config_path_prefix(monkeypatch):
    """Config values may embed a path prefix / gs:// scheme; only the bucket
    component is used for the allowlist comparison."""
    monkeypatch.setattr(main.config.Default, "GENMEDIA_BUCKET", "app-bucket")
    monkeypatch.setattr(main.config.Default, "VIDEO_BUCKET", "app-bucket/videos")
    monkeypatch.setattr(main.config.Default, "IMAGE_BUCKET", "gs://image-bucket/images")
    monkeypatch.setattr(main.config.Default, "GCS_ASSETS_BUCKET", "")
    if hasattr(main.config.Default, "MEDIA_BUCKET"):
        monkeypatch.setattr(main.config.Default, "MEDIA_BUCKET", "")

    allowed = main._allowed_proxy_buckets()

    assert allowed == {"app-bucket", "image-bucket"}
    assert main._is_proxy_bucket_allowed("app-bucket") is True
    assert main._is_proxy_bucket_allowed("image-bucket") is True
    assert main._is_proxy_bucket_allowed("videos") is False
    assert main._is_proxy_bucket_allowed("") is False
