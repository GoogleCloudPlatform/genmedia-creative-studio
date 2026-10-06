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
"""Prove-it tests for owner-scoped ``get_media_for_chooser`` (READ-SWEEP-A).

``common.metadata.get_media_for_chooser`` backs the media chooser dialog
(``pages/test_media_chooser.py``). Pre-fix it queried the shared ``genmedia``
collection with **no** owner filter, so the chooser returned *every* user's media
to *any* caller — a cross-user listing / read-side IDOR (information disclosure).

These tests assert the fix, mirroring the merged #1930/#1971 pattern
(``authz.resolve_caller_email`` + ``authz.is_owner``):

* the owner sees their own items;
* a non-owner's items are NEVER disclosed to the caller;
* no resolvable server-derived identity fails closed to EMPTY (never a
  cross-user list) and does not even touch Firestore;
* legacy ownerless documents stay reachable, consistent with the existing
  ``is_owner`` tolerance.

They FAIL against the pre-fix code (the leak test receives another user's item)
and PASS once ``get_media_for_chooser`` is owner-scoped. Firestore is faked
in-process so the tests never touch a real backend.
"""

# ruff: noqa: D101, D102, D103, S101

import datetime
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import authz


# --------------------------------------------------------------------------- #
# In-process Firestore fake (supports the chooser's hybrid query shapes)
# --------------------------------------------------------------------------- #
class FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class FakeQuery:
    """Records filters/ordering and streams matching docs.

    Supports the equality and range (``>=`` / ``<``) ``where`` clauses and the
    chained ``order_by`` calls used by ``get_media_for_chooser``'s two queries.
    """

    def __init__(self, store):
        self._store = store
        self.wheres: list[tuple] = []
        self._orders: list[tuple[str, bool]] = []
        self._start_after_id = None
        self._limit = None

    def where(self, field, op, value):
        self.wheres.append((field, op, value))
        return self

    def order_by(self, field, direction=None):
        descending = str(direction).endswith("DESCENDING") or direction == "DESCENDING"
        self._orders.append((field, descending))
        return self

    def start_after(self, snapshot):
        self._start_after_id = getattr(snapshot, "id", None)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self, data):
        for field, op, value in self.wheres:
            actual = data.get(field)
            if op == "==":
                if actual != value:
                    return False
            elif op == ">=":
                if actual is None or actual < value:
                    return False
            elif op == "<":
                if actual is None or actual >= value:
                    return False
            else:  # pragma: no cover - defensive
                raise NotImplementedError(op)
        return True

    def stream(self):
        rows = [
            FakeSnapshot(doc_id, data)
            for doc_id, data in self._store.items()
            if self._matches(data)
        ]
        for field, descending in reversed(self._orders):
            rows.sort(key=lambda s, f=field: s.to_dict().get(f), reverse=descending)
        if self._start_after_id is not None:
            ids = [s.id for s in rows]
            if self._start_after_id in ids:
                rows = rows[ids.index(self._start_after_id) + 1 :]
        if self._limit is not None:
            rows = rows[: self._limit]
        return iter(rows)


class FakeCollection:
    def __init__(self, store):
        self._store = store

    def where(self, field, op, value):
        return FakeQuery(self._store).where(field, op, value)

    def order_by(self, field, direction=None):
        return FakeQuery(self._store).order_by(field, direction=direction)

    def limit(self, n):
        return FakeQuery(self._store).limit(n)


class FakeDB:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        store = self.collections.setdefault(name, {})
        return FakeCollection(store)

    def seed(self, collection, doc_id, data):
        self.collections.setdefault(collection, {})[doc_id] = dict(data)


@pytest.fixture
def fake_db():
    return FakeDB()


def _set_server_identity(monkeypatch, email):
    monkeypatch.setattr(authz, "get_current_user_email", lambda: email)


def _seed_two_user_images(fake_db):
    """Seed image media for two distinct owners (plus a legacy ownerless doc)."""
    import common.metadata as md

    coll = md.config.GENMEDIA_COLLECTION_NAME
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    fake_db.seed(
        coll,
        "m_alice_1",
        {
            "user_email": "alice@example.com",
            "timestamp": now,
            "mime_type": "image/png",
            "media_type": "image",
            "gcsuri": "gs://private/alice-1.png",
        },
    )
    fake_db.seed(
        coll,
        "m_alice_2",
        {
            "user_email": "alice@example.com",
            "timestamp": now - datetime.timedelta(hours=1),
            "mime_type": "image/png",
            "media_type": "image",
            "gcsuri": "gs://private/alice-2.png",
        },
    )
    fake_db.seed(
        coll,
        "m_bob_secret",
        {
            "user_email": "bob@example.com",
            "timestamp": now - datetime.timedelta(minutes=30),
            "mime_type": "image/png",
            "media_type": "image",
            "gcsuri": "gs://private/bob-secret.png",
        },
    )
    return coll


# --------------------------------------------------------------------------- #
# The leak proof: a non-owner must NEVER receive another user's item.
# --------------------------------------------------------------------------- #
def test_chooser_does_not_leak_other_users_media(monkeypatch, fake_db):
    """FAILS pre-fix: alice's chooser receives bob's item (cross-user listing).

    PASSES post-fix: the owner-scoping excludes bob's media entirely.
    """
    import common.metadata as md

    coll = _seed_two_user_images(fake_db)
    monkeypatch.setattr(md, "db", fake_db)
    _set_server_identity(monkeypatch, "alice@example.com")

    items, _last = md.get_media_for_chooser(media_type="image", page_size=20)

    owners = {i.user_email for i in items}
    # bob's media must never be disclosed to alice.
    assert "bob@example.com" not in owners
    assert all(i.id != "m_bob_secret" for i in items)
    # sanity: the collection really did contain another user's data.
    assert "m_bob_secret" in fake_db.collections[coll]


def test_chooser_returns_only_callers_own_items(monkeypatch, fake_db):
    import common.metadata as md

    _seed_two_user_images(fake_db)
    monkeypatch.setattr(md, "db", fake_db)
    _set_server_identity(monkeypatch, "alice@example.com")

    items, _last = md.get_media_for_chooser(media_type="image", page_size=20)

    assert {i.user_email for i in items} == {"alice@example.com"}
    assert {i.id for i in items} == {"m_alice_1", "m_alice_2"}


def test_chooser_owner_sees_own_via_explicit_caller(monkeypatch, fake_db):
    """The explicit server-derived ``caller_email`` kwarg scopes identically."""
    import common.metadata as md

    _seed_two_user_images(fake_db)
    monkeypatch.setattr(md, "db", fake_db)
    # No ambient request identity: rely solely on the explicit kwarg.
    _set_server_identity(monkeypatch, None)

    items, _last = md.get_media_for_chooser(
        media_type="image", page_size=20, caller_email="bob@example.com"
    )

    assert {i.user_email for i in items} == {"bob@example.com"}
    assert {i.id for i in items} == {"m_bob_secret"}


def test_chooser_fails_closed_without_identity(monkeypatch):
    """No resolvable identity => EMPTY and Firestore is never queried.

    A ``MagicMock`` db is used deliberately: the guard must short-circuit before
    any ``db.collection(...)`` access so the listing can never fall through to a
    cross-user query. FAILS if the fail-closed guard is removed.
    """
    import common.metadata as md

    mock_db = MagicMock()
    monkeypatch.setattr(md, "db", mock_db)
    _set_server_identity(monkeypatch, None)

    for missing in (None, ""):
        items, last = md.get_media_for_chooser(
            media_type="image", page_size=20, caller_email=missing
        )
        assert items == []
        assert last is None

    mock_db.collection.assert_not_called()


def test_chooser_includes_legacy_ownerless_docs(monkeypatch, fake_db):
    """Pre-existing unattributed items (no ``user_email``) stay reachable to an
    authenticated caller, consistent with #1920/#1930 ``is_owner`` tolerance."""
    import common.metadata as md

    coll = md.config.GENMEDIA_COLLECTION_NAME
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    fake_db.seed(
        coll,
        "m_legacy",
        {
            "timestamp": now,
            "mime_type": "image/png",
            "media_type": "image",
            "gcsuri": "gs://legacy/old.png",
        },
    )
    fake_db.seed(
        coll,
        "m_bob_secret",
        {
            "user_email": "bob@example.com",
            "timestamp": now - datetime.timedelta(minutes=1),
            "mime_type": "image/png",
            "media_type": "image",
        },
    )
    monkeypatch.setattr(md, "db", fake_db)
    _set_server_identity(monkeypatch, "alice@example.com")

    items, _last = md.get_media_for_chooser(media_type="image", page_size=20)
    ids = {i.id for i in items}

    # Legacy ownerless doc is reachable; bob's owned doc is still excluded.
    assert "m_legacy" in ids
    assert "m_bob_secret" not in ids
