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

"""Prove-it tests for the GIF conversion guards (b/585273860).

``/api/convert_to_gif`` passed the client-supplied ``gcs_uri`` straight to
``convert_mp4_to_gif``, which downloaded it with the app's service account and
decoded it with no size or duration limit. A caller could make the service
account read objects from any bucket it can access, and exhaust memory and CPU
with a large video. These tests assert the fixed behavior:

* outside local dev an unauthenticated caller gets a 403;
* a URI outside the app's own buckets gets a generic 404 and nothing is
  downloaded;
* a source larger than ``GIF_MAX_SOURCE_MB`` is rejected (413) before download;
* a source longer than ``GIF_MAX_DURATION_S`` is rejected before conversion;
* an in-limit source in an allowed bucket is still converted.

Pre-fix, the foreign-bucket request reaches ``download_from_gcs``.
"""

# ruff: noqa: ANN001, ANN201, ANN202, ARG001, ARG005, COM812, D103

import os
import sys
from pathlib import Path
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

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from models import video_processing as vp  # noqa: E402

APP_BUCKET = "app-bucket"
SOURCE = f"gs://{APP_BUCKET}/videos/clip.mp4"


@pytest.fixture(autouse=True)
def app_buckets(monkeypatch):
    for name in ("VIDEO_BUCKET", "IMAGE_BUCKET", "GCS_ASSETS_BUCKET", "MEDIA_BUCKET"):
        monkeypatch.setattr(main.config.Default, name, "")
    monkeypatch.setattr(main.config.Default, "GENMEDIA_BUCKET", APP_BUCKET)
    monkeypatch.setattr(vp.config, "GIF_MAX_SOURCE_MB", 200)
    monkeypatch.setattr(vp.config, "GIF_MAX_DURATION_S", 60)


@pytest.fixture
def blob_size(monkeypatch):
    """Fake GCS metadata lookups; returns a setter for the reported blob size."""
    state = {"size": 5 * 1024 * 1024}
    client = MagicMock()
    client.bucket.return_value.get_blob.side_effect = lambda name: SimpleNamespace(
        size=state["size"]
    )
    monkeypatch.setattr(vp, "get_storage_client", lambda: client)
    return lambda size: state.update(size=size)


@pytest.fixture
def downloads(monkeypatch):
    calls = []

    def fake_download(gcs_uri):
        calls.append(gcs_uri)
        return b"fake-mp4"

    monkeypatch.setattr(vp, "download_from_gcs", fake_download)
    return calls


@pytest.fixture
def fake_clip(monkeypatch):
    clip = MagicMock()
    clip.duration = 5.0
    clip.fps = 24
    clip.size = (64, 64)
    clip.resized.return_value.write_gif.side_effect = lambda path, fps: Path(
        path,
    ).write_bytes(b"GIF89a")
    monkeypatch.setattr(vp, "VideoFileClip", lambda _path: clip)
    monkeypatch.setattr(vp, "_calculate_motion_score", lambda _clip: 10.0)
    monkeypatch.setattr(vp, "_upload_to_gcs", lambda *_a: f"gs://{APP_BUCKET}/out.gif")
    monkeypatch.setattr(vp, "add_media_item_to_firestore", lambda _item: None)
    return clip


@pytest.fixture
def client():
    return TestClient(main.app)


def test_foreign_bucket_is_rejected_before_download(client, downloads, blob_size):
    resp = client.get(
        "/api/convert_to_gif", params={"gcs_uri": "gs://victim-bucket/secret.mp4"}
    )

    assert resp.status_code == 404
    assert resp.json() == {"error": "Object not found"}
    assert downloads == []


@pytest.mark.parametrize("bad", ["", "videos/clip.mp4", f"gs://{APP_BUCKET}", "gs://"])
def test_malformed_uri_is_rejected(client, downloads, bad):
    resp = client.get("/api/convert_to_gif", params={"gcs_uri": bad})

    assert resp.status_code == 400
    assert downloads == []


def test_unauthenticated_caller_is_rejected_when_deployed(
    client, downloads, monkeypatch
):
    monkeypatch.setattr(main.config.Default, "APP_ENV", "prod")
    monkeypatch.setattr(main.config.Default, "REQUIRE_AUTHENTICATED_USER", False)

    resp = client.get("/api/convert_to_gif", params={"gcs_uri": SOURCE})

    assert resp.status_code == 403
    assert downloads == []


def test_oversized_source_is_rejected_before_download(client, downloads, blob_size):
    blob_size(201 * 1024 * 1024)

    resp = client.get("/api/convert_to_gif", params={"gcs_uri": SOURCE})

    assert resp.status_code == 413
    assert "200 MB" in resp.json()["error"]
    assert downloads == []


def test_overlong_source_is_rejected(client, downloads, blob_size, fake_clip):
    fake_clip.duration = 61.0

    resp = client.get("/api/convert_to_gif", params={"gcs_uri": SOURCE})

    assert resp.status_code == 413
    assert "60 second" in resp.json()["error"]
    fake_clip.resized.assert_not_called()


def test_in_limit_source_is_converted(
    client, downloads, blob_size, fake_clip, monkeypatch
):
    monkeypatch.setattr(main, "create_display_url", lambda uri: f"/media/{uri[5:]}")

    resp = client.get("/api/convert_to_gif", params={"gcs_uri": SOURCE})

    assert resp.status_code == 200
    assert resp.json() == {"url": f"/media/{APP_BUCKET}/out.gif"}
    assert downloads == [SOURCE]


def test_direct_callers_are_guarded_too(downloads, blob_size):
    """The Mesop pages call convert_mp4_to_gif directly with URIs from state."""
    with pytest.raises(vp.GifSourceRejectedError):
        vp.convert_mp4_to_gif("gs://victim-bucket/secret.mp4", "alice@example.com")
    assert downloads == []
