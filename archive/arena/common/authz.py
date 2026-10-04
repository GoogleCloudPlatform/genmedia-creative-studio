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

"""Fail-closed authorization for destructive arena operations.

Background
----------
The arena experiment (``archive/arena``) was built with **no identity or
authorization layer**: ``state.state.AppState`` carries no authenticated user,
there is no login, and no IAP assertion is verified. Yet
``pages/settings.py`` exposes a "Reset Leaderboard" button that batch-deletes
*every* ``arena_elo`` rating document for a study using the Firebase Admin SDK
(which bypasses Firestore Security Rules). Any caller who could reach the
Settings page could irrecoverably delete all ELO ratings for a study
(S1 b/565103344 -- unauthenticated destructive data loss).

This module adds the minimal, **fail-closed** authorization control that the
destructive purge path must pass. It mirrors the main application's merged
authorization pattern (``common/authz.py``, PRs #1920 / #1930): deny by
default, require a *server-derived* caller identity, and never trust a
client-supplied / plaintext identity header.

Trust model
-----------
``caller_email`` MUST be a server-derived, verified identity. The arena app
does not yet verify identities (it has no equivalent of the main app's
``common.verified_identity``, which verifies the IAP JWT assertion), so no
verified identity is currently available to the UI handler -> the purge is
denied (fail closed) until such a pipeline is wired. Plaintext identity headers
(e.g. ``X-Goog-Authenticated-User-Email``) are deliberately **not** trusted
here, matching the main app's decision.

Authorization is granted only to principals explicitly listed in the
``ARENA_ADMIN_EMAILS`` configuration (comma-separated). It is **empty by
default**, so out of the box nobody is authorized and the purge cannot run.
"""

from __future__ import annotations

import os

ADMIN_EMAILS_ENV_VAR = "ARENA_ADMIN_EMAILS"


class AuthorizationError(PermissionError):
    """Raised when a caller is not authorized for a destructive operation.

    Subclasses :class:`PermissionError` so existing ``except PermissionError``
    handlers (and any caller expecting a 403-style failure) treat it correctly.
    """


def _configured_admins() -> set[str]:
    """Return the set of authorized admin emails from configuration (lowercased).

    Read from the ``ARENA_ADMIN_EMAILS`` environment variable (comma-separated).
    **Empty by default**: with no configured admins, every caller is denied.
    """
    raw = os.environ.get(ADMIN_EMAILS_ENV_VAR, "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def is_authorized_admin(caller_email: str | None) -> bool:
    """Return ``True`` only for a present, server-derived, allowlisted admin.

    Fails closed: returns ``False`` on a missing/empty caller identity and when
    the allowlist is empty (the default).
    """
    if not caller_email:
        return False
    return caller_email.strip().lower() in _configured_admins()


def authorize_admin(caller_email: str | None, *, action: str = "operation") -> str:
    """Fail-closed gate guarding a destructive ``action``.

    Returns the normalized caller email when authorized; otherwise raises
    :class:`AuthorizationError` **before any side effect is performed**. The
    error message never reveals whether the target data exists (no existence
    oracle).
    """
    if not is_authorized_admin(caller_email):
        raise AuthorizationError(
            f"Not authorized to {action}: a verified, allowlisted admin identity "
            "is required.",
        )
    return caller_email.strip().lower()


def get_verified_caller_email() -> str | None:
    """Return the server-*verified* caller identity, or ``None`` if unavailable.

    The arena app does not yet verify identities, so this returns ``None`` and
    any guarded operation fails closed. When a verified-identity pipeline is
    added (mirroring the main app's ``common.verified_identity``), populate
    ``state.state.AppState.user_email`` from the *verified* assertion and this
    will pick it up. A plaintext identity header is never consulted.

    All errors are swallowed intentionally: an inability to resolve an identity
    must never be mistaken for a *valid* identity.
    """
    try:
        import mesop as me

        from state.state import AppState

        return getattr(me.state(AppState), "user_email", None) or None
    except Exception:
        return None
