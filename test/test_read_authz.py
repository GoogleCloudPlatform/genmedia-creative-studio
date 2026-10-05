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
"""Prove-it tests for server-side ownership authorization on media READS (Vuln #3).

The read side is broken access control / IDOR: a chooser/library listing that
returns *every* user's media, and load-by-client-supplied-id paths that return
*any* user's document with no ownership check. These tests assert the fix:

* listings are owner-scoped (only the caller's items) and fail closed to EMPTY
  when no server-derived identity is resolvable (never "everything");
* single-document loads keyed by a client-supplied id return the document only
  to its owner (or a legacy ownerless doc), and are indistinguishable from
  not-found for a non-owner (no existence/content leak).

They FAIL against the pre-fix code (the listing returns all users; the load
returns any user's doc) and PASS once the ``common.authz`` read checks and the
owner-scoped queries are in place.

Firestore is faked in-process so the tests never touch a real backend.
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
# In-process Firestore fake (query-capable)
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


class FakeQuery:
    """Records the filters applied and streams the matching docs in order."""

    def __init__(self, store):
        self._store = store
        self.wheres: list[tuple] = []
        self._order_field = None
        self._descending = False
        self._start_after_id = None
        self._limit = None

    def where(self, field, op, value):
        self.wheres.append((field, op, value))
        return self

    def order_by(self, field, direction=None):
        self._order_field = field
        self._descending = str(direction).endswith("DESCENDING") or direction == "DESCENDING"
        return self

    def start_after(self, snapshot):
        self._start_after_id = getattr(snapshot, "id", None)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self, data):
        for field, op, value in self.wheres:
            if op != "==":  # only equality is exercised by these paths
                raise NotImplementedError(op)
            if data.get(field) != value:
                return False
        return True

    def stream(self):
        rows = [
            FakeSnapshot(doc_id, data)
            for doc_id, data in self._store.items()
            if self._matches(data)
        ]
        if self._order_field is not None:
            rows.sort(
                key=lambda s: s.to_dict().get(self._order_field),
                reverse=self._descending,
            )
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

    # Query builders delegate to a fresh FakeQuery so call chains work in any
    # order (where -> order_by -> limit ..., or limit -> stream).
    def where(self, field, op, value):
        return FakeQuery(self._store).where(field, op, value)

    def order_by(self, field, direction=None):
        return FakeQuery(self._store).order_by(field, direction=direction)

    def limit(self, n):
        return FakeQuery(self._store).limit(n)

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
def fake_db():
    return FakeDB()


def _set_server_identity(monkeypatch, email):
    monkeypatch.setattr(authz, "get_current_user_email", lambda: email)


# --------------------------------------------------------------------------- #
# A. authorize_read helper — load-by-client-supplied-id (spots 3 & 4)
# --------------------------------------------------------------------------- #
def test_authorize_read_denies_non_owner_without_leaking(fake_db):
    fake_db.seed(
        "interior_design_storyboards",
        "sb_alice",
        {"user_email": "alice@example.com", "secret": "alice-plan"},
    )
    doc_ref = fake_db.collection("interior_design_storyboards").document("sb_alice")

    result = authz.authorize_read(doc_ref, "user_email", "attacker@evil.com")

    # Non-owner gets nothing back — no contents, and indistinguishable from
    # not-found (see the missing-doc test below returning the same None).
    assert result is None


def test_authorize_read_allows_owner(fake_db):
    fake_db.seed(
        "object_rotation_projects",
        "proj_alice",
        {"user_email": "alice@example.com", "final_video_uri": "gs://x"},
    )
    doc_ref = fake_db.collection("object_rotation_projects").document("proj_alice")

    result = authz.authorize_read(doc_ref, "user_email", "alice@example.com")

    assert result is not None
    assert result["final_video_uri"] == "gs://x"


def test_authorize_read_allows_legacy_ownerless_doc(fake_db):
    # Pre-existing unattributed data (owner field absent/None) stays reachable,
    # consistent with #1920's enforce_ownership tolerance.
    fake_db.seed("interior_design_storyboards", "sb_legacy", {"secret": "old"})
    doc_ref = fake_db.collection("interior_design_storyboards").document("sb_legacy")

    result = authz.authorize_read(doc_ref, "user_email", "anyone@example.com")

    assert result == {"secret": "old"}


def test_authorize_read_fails_closed_without_identity(fake_db):
    fake_db.seed(
        "interior_design_storyboards",
        "sb_alice",
        {"user_email": "alice@example.com"},
    )
    doc_ref = fake_db.collection("interior_design_storyboards").document("sb_alice")

    # No resolvable caller identity => denied (never returned).
    assert authz.authorize_read(doc_ref, "user_email", None) is None
    assert authz.authorize_read(doc_ref, "user_email", "") is None


def test_authorize_read_missing_doc_returns_none(fake_db):
    doc_ref = fake_db.collection("interior_design_storyboards").document("nope")

    assert authz.authorize_read(doc_ref, "user_email", "alice@example.com") is None


def test_authorize_read_non_owner_and_missing_are_indistinguishable(fake_db):
    """No existence/content oracle: a non-owner load and a not-found load must
    return the identical ``None`` so the two cases render the same at call sites
    (interior_design_v2 / object_rotation on_load) and a caller cannot probe
    whether another user's doc exists."""
    fake_db.seed(
        "interior_design_storyboards",
        "sb_alice",
        {"user_email": "alice@example.com", "secret": "alice-plan"},
    )
    owned_ref = fake_db.collection("interior_design_storyboards").document("sb_alice")
    missing_ref = fake_db.collection("interior_design_storyboards").document("ghost")

    non_owner = authz.authorize_read(owned_ref, "user_email", "attacker@evil.com")
    not_found = authz.authorize_read(missing_ref, "user_email", "attacker@evil.com")

    assert non_owner is None
    assert not_found is None
    assert non_owner == not_found  # indistinguishable outcome, no oracle


def test_is_owner_policy():
    assert authz.is_owner("alice@example.com", "alice@example.com") is True
    assert authz.is_owner("alice@example.com", "attacker@evil.com") is False
    assert authz.is_owner(None, "anyone@example.com") is True  # legacy ownerless
    assert authz.is_owner("alice@example.com", None) is False  # fail closed
    assert authz.is_owner("alice@example.com", "") is False  # fail closed


# --------------------------------------------------------------------------- #
# B. guideline_analysis chooser listing (spot 1)
# --------------------------------------------------------------------------- #
def _seed_two_user_media(fake_db):
    import common.metadata as md

    coll = md.config.GENMEDIA_COLLECTION_NAME
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    fake_db.seed(
        coll,
        "m_alice_1",
        {"user_email": "alice@example.com", "timestamp": now, "mime_type": "image/png"},
    )
    fake_db.seed(
        coll,
        "m_alice_2",
        {
            "user_email": "alice@example.com",
            "timestamp": now - datetime.timedelta(hours=1),
            "mime_type": "image/png",
        },
    )
    fake_db.seed(
        coll,
        "m_bob_1",
        {"user_email": "bob@example.com", "timestamp": now, "mime_type": "image/png"},
    )
    return coll


def test_chooser_lists_only_callers_items(monkeypatch, fake_db):
    import pages.guideline_analysis as page

    coll = _seed_two_user_media(fake_db)
    monkeypatch.setattr(page, "db", fake_db)

    items, _last = page.get_all_media_for_chooser(
        page_size=20, user_email="alice@example.com"
    )

    owners = {i.user_email for i in items}
    assert owners == {"alice@example.com"}
    assert len(items) == 2
    # bob's item is never disclosed to alice
    assert all(i.user_email != "bob@example.com" for i in items)
    # sanity: the collection really did contain another user's data
    assert "m_bob_1" in fake_db.collections[coll]


def test_chooser_without_identity_does_not_query(monkeypatch):
    """Load-bearing fail-closed proof for the chooser.

    The pre-query guard is the only thing that must produce an empty result, so
    we assert Firestore is *never touched* when no identity is resolvable. A
    ``MagicMock`` db is used deliberately: a plain ``raise`` inside the query
    path would be swallowed by ``get_all_media_for_chooser``'s broad ``except``
    (and the test would still pass with the guard removed — the L2 defect). With
    ``assert_not_called`` the test FAILS if the guard is removed, because the
    function would then reach ``db.collection(...)``.
    """
    import pages.guideline_analysis as page

    mock_db = MagicMock()
    monkeypatch.setattr(page, "db", mock_db)

    for missing in (None, ""):
        items, last = page.get_all_media_for_chooser(page_size=20, user_email=missing)
        assert items == []
        assert last is None

    # The guard must short-circuit before any Firestore access.
    mock_db.collection.assert_not_called()


def test_object_rotation_library_returns_empty_without_identity(
    monkeypatch, app_state_factory
):
    """Spot 2 fail-closed proof (L1 fix).

    ``get_media_for_page`` fails OPEN on an empty filter, so the call site must
    not invoke it without an identity. We spy on it and assert it is never
    called and the listing is empty. FAILS if the call-site guard is removed
    (the spy would be called and its rows would populate ``library_items``).
    """
    import common.metadata as md
    import pages.object_rotation as page

    calls = []

    def spy_get_media_for_page(*args, **kwargs):
        calls.append(kwargs)
        return ["LEAKED_ROW"]  # would be exposed if the guard were removed

    monkeypatch.setattr(md, "get_media_for_page", spy_get_media_for_page)

    page_state = page.PageState()
    app_state = app_state_factory(user_email="")  # no resolvable identity

    def fake_state(cls):
        return app_state if cls is page.AppState else page_state

    monkeypatch.setattr(page.me, "state", fake_state)

    # Drive the generator handler to completion.
    list(page.open_library_dialog(None, view_name="front_view"))

    assert calls == []  # get_media_for_page never invoked
    assert page_state.library_items == []


# --------------------------------------------------------------------------- #
# C. object_rotation library listing mechanism (spot 2 — get_media_for_page)
# --------------------------------------------------------------------------- #
def test_get_media_for_page_filters_by_user_email(monkeypatch, fake_db):
    import common.metadata as md

    _seed_two_user_media(fake_db)
    monkeypatch.setattr(md, "db", fake_db)

    items = md.get_media_for_page(
        1, 50, type_filters=["images"], filter_by_user_email="alice@example.com"
    )

    assert {i.user_email for i in items} == {"alice@example.com"}
    assert len(items) == 2


# --------------------------------------------------------------------------- #
# D. get_media_item_by_id — load-by-client-supplied-id (b/565102630 residual)
# --------------------------------------------------------------------------- #
# ``selected_media_item_id`` is set from a client-controlled Mesop ``WebEvent.key``
# (guideline_analysis / library_v2) and the Veo HTTP job id is client-supplied,
# so an unauthorized caller could read ANY user's media item by id. These prove
# the fix: the load is now owner-scoped (mirrors authorize_read / PR #1930), and
# the intentional system bypass stays unscoped for background job processing.
def _seed_alice_media_item(fake_db):
    import common.metadata as md

    coll = md.config.GENMEDIA_COLLECTION_NAME
    fake_db.seed(
        coll,
        "m_alice_secret",
        {
            "user_email": "alice@example.com",
            "timestamp": datetime.datetime(2026, 1, 1, 12, 0, 0),
            "mime_type": "video/mp4",
            "gcsuri": "gs://private/alice.mp4",
            "prompt": "alice-private-prompt",
        },
    )
    return coll


def test_get_media_item_by_id_denies_non_owner(monkeypatch, fake_db):
    """Unauthorized (authenticated-but-not-owner) caller gets NO doc back —
    fail-closed, no disclosure of another user's media item."""
    import common.metadata as md

    _seed_alice_media_item(fake_db)
    monkeypatch.setattr(md, "db", fake_db)
    _set_server_identity(monkeypatch, "attacker@evil.com")

    assert md.get_media_item_by_id("m_alice_secret") is None
    # Explicit caller identity path is denied identically.
    assert (
        md.get_media_item_by_id("m_alice_secret", caller_email="attacker@evil.com")
        is None
    )


def test_get_media_item_by_id_denies_unauthenticated(monkeypatch, fake_db):
    """No resolvable server-derived identity => denied (never returned)."""
    import common.metadata as md

    _seed_alice_media_item(fake_db)
    monkeypatch.setattr(md, "db", fake_db)
    _set_server_identity(monkeypatch, None)

    assert md.get_media_item_by_id("m_alice_secret") is None
    assert md.get_media_item_by_id("m_alice_secret", caller_email="") is None


def test_get_media_item_by_id_allows_owner(monkeypatch, fake_db):
    """The legitimate owner still gets their own item."""
    import common.metadata as md

    _seed_alice_media_item(fake_db)
    monkeypatch.setattr(md, "db", fake_db)
    _set_server_identity(monkeypatch, "alice@example.com")

    item = md.get_media_item_by_id("m_alice_secret")
    assert item is not None
    assert item.id == "m_alice_secret"
    assert item.user_email == "alice@example.com"
    assert item.gcsuri == "gs://private/alice.mp4"

    # Explicit server-derived caller identity path also returns the owner's item.
    item2 = md.get_media_item_by_id("m_alice_secret", caller_email="alice@example.com")
    assert item2 is not None
    assert item2.id == "m_alice_secret"


def test_get_media_item_by_id_non_owner_and_missing_indistinguishable(
    monkeypatch, fake_db
):
    """No existence oracle: a non-owner read and a not-found read both return the
    identical ``None`` so an attacker cannot probe whether a victim's id exists."""
    import common.metadata as md

    _seed_alice_media_item(fake_db)
    monkeypatch.setattr(md, "db", fake_db)
    _set_server_identity(monkeypatch, "attacker@evil.com")

    non_owner = md.get_media_item_by_id("m_alice_secret")
    not_found = md.get_media_item_by_id("does_not_exist")
    assert non_owner is None
    assert not_found is None
    assert non_owner == not_found


def test_get_media_item_by_id_allows_legacy_ownerless(monkeypatch, fake_db):
    """Pre-existing unattributed items (no owner field) stay reachable, consistent
    with #1920/#1930 ownerless tolerance."""
    import common.metadata as md

    coll = md.config.GENMEDIA_COLLECTION_NAME
    fake_db.seed(
        coll,
        "m_legacy",
        {"timestamp": datetime.datetime(2026, 1, 1), "mime_type": "image/png"},
    )
    monkeypatch.setattr(md, "db", fake_db)
    _set_server_identity(monkeypatch, "anyone@example.com")

    item = md.get_media_item_by_id("m_legacy")
    assert item is not None
    assert item.id == "m_legacy"


def test_get_media_item_by_id_system_is_unscoped(monkeypatch, fake_db):
    """The explicit system bypass returns the item regardless of caller identity —
    it is the sanctioned path for background job processing (veo_service) and MUST
    remain unscoped. This documents that the scoping lives in get_media_item_by_id,
    not here."""
    import common.metadata as md

    _seed_alice_media_item(fake_db)
    monkeypatch.setattr(md, "db", fake_db)
    # Even with a non-owner / no identity resolvable, the system read returns it.
    _set_server_identity(monkeypatch, None)

    item = md.get_media_item_by_id_system("m_alice_secret")
    assert item is not None
    assert item.id == "m_alice_secret"
    assert item.user_email == "alice@example.com"
    # Missing id still returns None.
    assert md.get_media_item_by_id_system("ghost") is None
