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

"""Tests for cached V4 signed display URLs (gmcs-oi4.1, .2, .4)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from common import utils

GS = "gs://assets-bucket/images/a.png"
SA = "runtime-sa@project.iam.gserviceaccount.com"


class FakeClock:
    """Controllable replacement for ``utils._now``."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = FakeClock()
    monkeypatch.setattr(utils, "_now", c)
    return c


@pytest.fixture
def signing(monkeypatch, clock):
    """Signed-URL mode (no proxy, SA configured) with all GCP calls mocked."""
    monkeypatch.setattr(
        utils,
        "cfg",
        lambda: SimpleNamespace(USE_MEDIA_PROXY=False, SERVICE_ACCOUNT_EMAIL=SA),
    )
    monkeypatch.setattr(utils, "_display_url_cache", {})
    monkeypatch.setattr(utils, "_signing_resources", {})

    counter = {"n": 0}

    def fake_generate(**_kwargs):
        counter["n"] += 1
        return f"https://storage.googleapis.com/b/o?X-Goog-Signature=sig{counter['n']}"

    blob = MagicMock()
    blob.generate_signed_url.side_effect = fake_generate
    bucket = MagicMock()
    bucket.blob.return_value = blob
    client = MagicMock()
    client.bucket.return_value = bucket
    credentials_cls = MagicMock()
    storage_client_cls = MagicMock(return_value=client)
    default = MagicMock(return_value=(MagicMock(), "project"))

    monkeypatch.setattr(utils.google.auth, "default", default)
    monkeypatch.setattr(utils.impersonated_credentials, "Credentials", credentials_cls)
    monkeypatch.setattr(utils.storage, "Client", storage_client_cls)
    return SimpleNamespace(
        blob=blob,
        bucket=bucket,
        client=client,
        credentials_cls=credentials_cls,
        storage_client_cls=storage_client_cls,
        default=default,
    )


def test_proxy_mode_uses_media_path(monkeypatch, signing):
    monkeypatch.setattr(
        utils,
        "cfg",
        lambda: SimpleNamespace(USE_MEDIA_PROXY=True, SERVICE_ACCOUNT_EMAIL=SA),
    )

    assert utils.create_display_url(GS) == "/media/assets-bucket/images/a.png"
    signing.blob.generate_signed_url.assert_not_called()


def test_no_service_account_keeps_unsigned_link(monkeypatch, signing):
    monkeypatch.setattr(
        utils,
        "cfg",
        lambda: SimpleNamespace(USE_MEDIA_PROXY=False, SERVICE_ACCOUNT_EMAIL=None),
    )

    assert (
        utils.create_display_url(GS)
        == "https://storage.cloud.google.com/assets-bucket/images/a.png"
    )
    signing.blob.generate_signed_url.assert_not_called()


@pytest.mark.parametrize("value", ["", None, "https://x/y.png", "assets/a.png"])
def test_non_gcs_values_return_empty(signing, value):
    assert utils.create_display_url(value) == ""


def test_signed_mode_returns_v4_url_and_requests_get(signing):
    url = utils.create_display_url(GS)

    assert url.startswith("https://storage.googleapis.com/")
    kwargs = signing.blob.generate_signed_url.call_args.kwargs
    assert kwargs["version"] == "v4"
    assert kwargs["method"] == "GET"
    assert kwargs["expiration"].total_seconds() == 60 * 60
    signing.client.bucket.assert_called_with("assets-bucket")
    signing.bucket.blob.assert_called_with("images/a.png")


def test_url_is_cached_until_ttl_then_resigned(signing, clock):
    first = utils.create_display_url(GS)
    clock.t += utils.DISPLAY_URL_CACHE_TTL_SECONDS - 1
    assert utils.create_display_url(GS) == first
    assert signing.blob.generate_signed_url.call_count == 1

    clock.t += 2  # past the 50 minute TTL
    second = utils.create_display_url(GS)
    assert second != first
    assert signing.blob.generate_signed_url.call_count == 2


def test_credentials_and_client_are_singletons(signing):
    utils.create_display_url("gs://assets-bucket/one.png")
    utils.create_display_url("gs://assets-bucket/two.png")
    utils.create_display_url("gs://other-bucket/three.png")

    assert signing.default.call_count == 1
    assert signing.credentials_cls.call_count == 1
    assert signing.storage_client_cls.call_count == 1
    assert signing.credentials_cls.call_args.kwargs["target_principal"] == SA
    assert signing.credentials_cls.call_args.kwargs["target_scopes"] == [
        "https://www.googleapis.com/auth/devstorage.read_only"
    ]


def test_signing_failure_falls_back_and_is_negatively_cached(signing, clock):
    signing.blob.generate_signed_url.side_effect = RuntimeError("no iam permission")

    url = utils.create_display_url(GS)
    assert url == "https://storage.cloud.google.com/assets-bucket/images/a.png"
    utils.create_display_url(GS)
    assert signing.blob.generate_signed_url.call_count == 1  # not retried per render

    clock.t += utils.DISPLAY_URL_FAILURE_TTL_SECONDS + 1
    utils.create_display_url(GS)
    assert signing.blob.generate_signed_url.call_count == 2  # retried after expiry


def test_cache_is_bounded(monkeypatch, signing):
    monkeypatch.setattr(utils, "DISPLAY_URL_CACHE_MAX_ENTRIES", 3)

    for i in range(10):
        utils.get_signed_display_url(f"gs://assets-bucket/{i}.png")

    assert len(utils._display_url_cache) <= 3


def test_warm_signs_pending_in_batch_and_skips_cached(signing):
    cached = "gs://assets-bucket/already.png"
    utils.create_display_url(cached)
    signing.blob.generate_signed_url.reset_mock()

    uris = [
        cached,
        "gs://assets-bucket/a.png",
        "gs://assets-bucket/a.png",  # duplicate
        "gs://assets-bucket/b.png",
        None,
        "",
        "not-gcs",
    ]
    utils.warm_display_urls(uris)

    assert signing.blob.generate_signed_url.call_count == 2  # a.png, b.png once each
    # Warmed entries are now cache hits.
    signing.blob.generate_signed_url.reset_mock()
    utils.create_display_url("gs://assets-bucket/a.png")
    utils.create_display_url("gs://assets-bucket/b.png")
    signing.blob.generate_signed_url.assert_not_called()


def test_warm_initializes_credentials_once(signing):
    utils.warm_display_urls([f"gs://assets-bucket/{i}.png" for i in range(20)])

    assert signing.credentials_cls.call_count == 1
    assert signing.storage_client_cls.call_count == 1


def test_warm_is_noop_with_proxy_or_without_service_account(monkeypatch, signing):
    for proxy, email in ((True, SA), (False, None)):
        monkeypatch.setattr(
            utils,
            "cfg",
            lambda proxy=proxy, email=email: SimpleNamespace(
                USE_MEDIA_PROXY=proxy, SERVICE_ACCOUNT_EMAIL=email
            ),
        )
        utils.warm_display_urls([GS])

    signing.blob.generate_signed_url.assert_not_called()


def test_signed_display_url_round_trips_to_gcs_uri(signing):
    signing.blob.generate_signed_url.side_effect = None
    signing.blob.generate_signed_url.return_value = (
        "https://storage.googleapis.com/assets-bucket/images/a.png"
        "?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Signature=abc"
    )

    assert utils.https_url_to_gcs_uri(utils.create_display_url(GS)) == GS


def test_media_tile_guards_empty_source():
    js = (
        Path(__file__).parent.parent / "components/media_tile/media_tile.js"
    ).read_text()

    assert "!this.thumbnailSrc" in js
    assert "broken_image" in js
