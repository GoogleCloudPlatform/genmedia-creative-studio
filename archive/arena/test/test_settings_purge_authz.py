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

"""Regression tests for the ELO-ratings purge authorization (S1 b/565103344).

These tests assert on the **effect**: the destructive purge
(``pages.settings._purge_elo_ratings``) must refuse an unauthenticated /
unauthorized caller and delete *nothing* (it must not even construct the
Firestore client), while an authorized admin is allowed to proceed.

The arena app's heavy dependencies (``mesop``, Firebase, GCP config) are stubbed
so the test runs with no credentials, no network, and only the standard library.
A fake async Firestore client records every delete/commit so we can prove no
deletion happens on the unauthorized path. ``common.authz`` is the *real*
module under test.
"""

import os
import sys
import types
import asyncio
import unittest
from unittest import mock

# archive/arena is the app root (where `common`, `pages`, `config` live).
ARENA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ARENA_ROOT not in sys.path:
    sys.path.insert(0, ARENA_ROOT)

# --- Fake async Firestore client that records destructive side effects --------
RECORDER = {"constructed": 0, "deleted": [], "commits": 0}


def _reset_recorder():
    RECORDER["constructed"] = 0
    RECORDER["deleted"] = []
    RECORDER["commits"] = 0


class _FakeDocRef:
    def __init__(self, i):
        self.i = i


class _FakeDoc:
    def __init__(self, i):
        self.reference = _FakeDocRef(i)


class _FakeBatch:
    def delete(self, ref):
        RECORDER["deleted"].append(ref)

    def commit(self, timeout=None):
        async def _c():
            RECORDER["commits"] += 1
            return True

        return _c()


class _FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def where(self, **kwargs):
        return self

    def stream(self):
        docs = self._docs

        async def _gen():
            for d in docs:
                yield d

        return _gen()


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def where(self, **kwargs):
        return _FakeQuery(self._docs)


class _FakeAsyncClient:
    def __init__(self, project=None, database=None):
        RECORDER["constructed"] += 1
        self._docs = [_FakeDoc(0), _FakeDoc(1), _FakeDoc(2)]

    def batch(self):
        return _FakeBatch()

    def collection(self, name):
        return _FakeCollection(self._docs)


class _FakeFieldFilter:
    def __init__(self, *args, **kwargs):
        pass


def _install_stubs():
    """Stub arena's heavy imports so pages.settings imports with no creds."""
    sys.modules["mesop"] = mock.MagicMock(name="mesop")
    for name in (
        "components",
        "components.header",
        "components.page_scaffold",
        "config",
        "config.default",
        "config.firebase_config",
    ):
        sys.modules[name] = mock.MagicMock(name=name)

    sys.modules["google"] = types.ModuleType("google")
    sys.modules["google.cloud"] = types.ModuleType("google.cloud")
    fs = types.ModuleType("google.cloud.firestore")
    fs.AsyncClient = _FakeAsyncClient
    fs.FieldFilter = _FakeFieldFilter
    sys.modules["google.cloud.firestore"] = fs


_install_stubs()

from common import authz  # noqa: E402  (real module under test)
from pages import settings  # noqa: E402  (imports with stubs in place)


class TestAuthzModule(unittest.TestCase):
    """Unit tests for the fail-closed authorization helper."""

    def test_missing_caller_denied(self):
        with mock.patch.dict(os.environ, {"ARENA_ADMIN_EMAILS": "admin@example.com"}):
            self.assertFalse(authz.is_authorized_admin(None))
            self.assertFalse(authz.is_authorized_admin(""))

    def test_empty_allowlist_denies_everyone(self):
        with mock.patch.dict(os.environ, {"ARENA_ADMIN_EMAILS": ""}):
            self.assertFalse(authz.is_authorized_admin("admin@example.com"))

    def test_non_admin_denied(self):
        with mock.patch.dict(os.environ, {"ARENA_ADMIN_EMAILS": "admin@example.com"}):
            self.assertFalse(authz.is_authorized_admin("attacker@example.com"))

    def test_listed_admin_allowed_case_insensitive(self):
        with mock.patch.dict(os.environ, {"ARENA_ADMIN_EMAILS": "admin@example.com"}):
            self.assertTrue(authz.is_authorized_admin("Admin@Example.com"))

    def test_authorize_admin_raises_permissionerror_subclass(self):
        with mock.patch.dict(os.environ, {"ARENA_ADMIN_EMAILS": "admin@example.com"}):
            with self.assertRaises(authz.AuthorizationError) as ctx:
                authz.authorize_admin(None, action="reset the leaderboard")
            self.assertIsInstance(ctx.exception, PermissionError)


class TestPurgeAuthorization(unittest.TestCase):
    """Assert on the EFFECT of the guard on the real purge function."""

    def setUp(self):
        _reset_recorder()

    def test_unauthenticated_caller_deletes_nothing(self):
        with mock.patch.dict(os.environ, {"ARENA_ADMIN_EMAILS": "admin@example.com"}):
            with self.assertRaises(authz.AuthorizationError):
                asyncio.run(settings._purge_elo_ratings(study="study-1", caller_email=None))
        # Fail closed: no client constructed, no deletes, no commits.
        self.assertEqual(RECORDER["constructed"], 0)
        self.assertEqual(RECORDER["deleted"], [])
        self.assertEqual(RECORDER["commits"], 0)

    def test_non_admin_caller_deletes_nothing(self):
        with mock.patch.dict(os.environ, {"ARENA_ADMIN_EMAILS": "admin@example.com"}):
            with self.assertRaises(authz.AuthorizationError):
                asyncio.run(
                    settings._purge_elo_ratings(
                        study="study-1", caller_email="attacker@example.com"
                    )
                )
        self.assertEqual(RECORDER["constructed"], 0)
        self.assertEqual(RECORDER["deleted"], [])

    def test_empty_allowlist_deletes_nothing(self):
        with mock.patch.dict(os.environ, {"ARENA_ADMIN_EMAILS": ""}):
            with self.assertRaises(authz.AuthorizationError):
                asyncio.run(
                    settings._purge_elo_ratings(
                        study="study-1", caller_email="admin@example.com"
                    )
                )
        self.assertEqual(RECORDER["constructed"], 0)
        self.assertEqual(RECORDER["deleted"], [])

    def test_authorized_admin_allowed_to_purge(self):
        with mock.patch.dict(os.environ, {"ARENA_ADMIN_EMAILS": "admin@example.com"}):
            result = asyncio.run(
                settings._purge_elo_ratings(
                    study="study-1", caller_email="Admin@Example.com"
                )
            )
        self.assertTrue(result)
        self.assertEqual(RECORDER["constructed"], 1)
        self.assertEqual(len(RECORDER["deleted"]), 3)  # all matching docs deleted
        self.assertGreaterEqual(RECORDER["commits"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
