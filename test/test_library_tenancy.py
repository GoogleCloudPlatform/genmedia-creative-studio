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

"""Prove-it tests for owner-scoped Library listings (b/585273425).

``get_media_for_page``, ``get_media_for_page_optimized`` and
``get_latest_videos`` treated ``filter_by_user_email=None`` as "no filter", and
the video, audio and infinite-scroll choosers (and the library chooser's
default state) called them without one, so any signed-in user could list every
user's media. These tests assert the fixed behavior:

* by default each listing returns only the caller's items;
* "All Users" is returned only when the caller asks for it (``all_users``) AND
  ``SHARED_LIBRARY`` is enabled;
* with no resolvable caller identity the listing is empty and Firestore is not
  queried at all (fail closed);
* the server-derived identity wins over a client-supplied
  ``filter_by_user_email``.

Pre-fix, the default listings return bob's items to alice.
"""

# ruff: noqa: ANN001, ANN003, ANN201, ANN202, ANN204, ARG001, D103, PLC0415, RUF012

import datetime
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import common.metadata as md
from common import authz

ALICE = "alice@example.com"
BOB = "bob@example.com"


class _Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _Query:
    """Minimal Firestore query fake supporting ==, >=, < and ordering."""

    _OPS = {
        "==": lambda a, b: a == b,
        ">=": lambda a, b: a is not None and a >= b,
        "<": lambda a, b: a is not None and a < b,
    }

    def __init__(self, store, wheres=(), order=None, limit=None):
        self._store = store
        self.wheres = list(wheres)
        self._order = order
        self._limit = limit

    def where(self, field, op, value):
        return _Query(
            self._store,
            [*self.wheres, (field, op, value)],
            self._order,
            self._limit,
        )

    def order_by(self, field, direction=None):
        return _Query(self._store, self.wheres, (field, direction), self._limit)

    def start_after(self, _snapshot):
        return self

    def limit(self, n):
        return _Query(self._store, self.wheres, self._order, n)

    def stream(self):
        rows = [
            _Snap(doc_id, data)
            for doc_id, data in self._store.items()
            if all(self._OPS[op](data.get(f), v) for f, op, v in self.wheres)
        ]
        if self._order:
            rows.sort(key=lambda s: s.to_dict().get(self._order[0]), reverse=True)
        return iter(rows[: self._limit] if self._limit else rows)


class _DB:
    def __init__(self, store):
        self.store = store

    def collection(self, _name):
        return _Query(self.store)


@pytest.fixture
def db(monkeypatch):
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    store = {
        "a1": {
            "user_email": ALICE,
            "timestamp": now,
            "mime_type": "image/png",
            "gcsuri": "gs://b/a1.png",
        },
        "a2": {
            "user_email": ALICE,
            "timestamp": now - datetime.timedelta(hours=1),
            "mime_type": "video/mp4",
            "gcsuri": "gs://b/a2.mp4",
        },
        "b1": {
            "user_email": BOB,
            "timestamp": now,
            "mime_type": "image/png",
            "gcsuri": "gs://b/b1.png",
        },
        "b2": {
            "user_email": BOB,
            "timestamp": now,
            "mime_type": "video/mp4",
            "gcsuri": "gs://b/b2.mp4",
        },
    }
    fake = _DB(store)
    monkeypatch.setattr(md, "db", fake)
    return fake


@pytest.fixture
def as_alice(monkeypatch):
    monkeypatch.setattr(authz, "get_current_user_email", lambda: ALICE)


@pytest.fixture
def no_identity(monkeypatch):
    monkeypatch.setattr(authz, "get_current_user_email", lambda: None)


_OWNER_BY_ID = {"a1": ALICE, "a2": ALICE, "b1": BOB, "b2": BOB}


def _owners(items):
    # get_media_for_page_optimized does not copy user_email onto MediaItem, so
    # map each returned document id back to its seeded owner.
    return {_OWNER_BY_ID[i.id] for i in items}


@pytest.mark.parametrize("shared", [True, False])
def test_get_media_for_page_defaults_to_caller_only(db, as_alice, monkeypatch, shared):
    monkeypatch.setattr(md.config, "SHARED_LIBRARY", shared)

    items = md.get_media_for_page(1, 50, ["all"], sort_by_timestamp=True)

    assert _owners(items) == {ALICE}
    assert len(items) == 2


@pytest.mark.parametrize("shared", [True, False])
def test_get_media_for_page_optimized_defaults_to_caller_only(
    db,
    as_alice,
    monkeypatch,
    shared,
):
    monkeypatch.setattr(md.config, "SHARED_LIBRARY", shared)

    images, _ = md.get_media_for_page_optimized(20, ["images"])
    videos, _ = md.get_media_for_page_optimized(20, ["videos"])

    assert _owners(images) == {ALICE}
    assert _owners(videos) == {ALICE}


def test_get_latest_videos_is_caller_only(db, as_alice):
    docs = md.get_latest_videos(10)

    assert {d["user_email"] for d in docs} == {ALICE}


def test_all_users_requires_shared_library(db, as_alice, monkeypatch):
    monkeypatch.setattr(md.config, "SHARED_LIBRARY", False)

    assert _owners(md.get_media_for_page(1, 50, ["all"], all_users=True)) == {ALICE}
    items, _ = md.get_media_for_page_optimized(20, ["images"], all_users=True)
    assert _owners(items) == {ALICE}


def test_all_users_with_shared_library_lists_everyone(db, as_alice, monkeypatch):
    monkeypatch.setattr(md.config, "SHARED_LIBRARY", True)

    assert _owners(md.get_media_for_page(1, 50, ["all"], all_users=True)) == {
        ALICE,
        BOB,
    }
    items, _ = md.get_media_for_page_optimized(20, ["images"], all_users=True)
    assert _owners(items) == {ALICE, BOB}


def test_server_identity_wins_over_client_supplied_filter(db, as_alice):
    items = md.get_media_for_page(1, 50, ["all"], filter_by_user_email=BOB)

    assert _owners(items) == {ALICE}


@pytest.mark.parametrize("shared", [True, False])
def test_no_identity_fails_closed_without_querying(monkeypatch, no_identity, shared):
    monkeypatch.setattr(md.config, "SHARED_LIBRARY", shared)
    mock_db = MagicMock()
    monkeypatch.setattr(md, "db", mock_db)

    assert md.get_media_for_page(1, 50, ["all"], all_users=True) == []
    assert md.get_media_for_page_optimized(20, ["images"], all_users=True) == ([], None)
    assert md.get_latest_videos(10) == []
    mock_db.collection.assert_not_called()


def test_fallback_identity_scopes_background_callers(db, no_identity):
    items = md.get_media_for_page(1, 50, ["all"], filter_by_user_email=BOB)

    assert _owners(items) == {BOB}


def test_library_chooser_passes_all_users_through(monkeypatch):
    import components.library.library_chooser_button as chooser

    calls = []

    def fake_fetch(page_size, media_type, **kwargs):
        calls.append(kwargs)
        return [], None

    monkeypatch.setattr(chooser, "get_media_for_page_optimized", fake_fetch)
    monkeypatch.setattr(chooser, "warm_display_urls", lambda _uris: None)

    chooser.load_chooser_items_json(["images"], ALICE)
    chooser.load_chooser_items_json(["images"], ALICE, all_users=True)

    assert calls == [
        {"filter_by_user_email": ALICE, "all_users": False},
        {"filter_by_user_email": ALICE, "all_users": True},
    ]
