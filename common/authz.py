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

"""Server-side ownership authorization for Firestore mutations.

This module centralizes the *server-side* authorization that every Firestore
mutate/delete path must perform before writing or deleting a document. It closes
the "broken access control" gap where the only ownership gate lived in
client/UI state (for example ``is_editable`` computed in a page render or the
``mode`` of a dialog), which a caller who reaches the mutation can bypass.

Trust model
-----------
The *caller identity* used here is the **server-derived, cryptographically
verified** user email. It is established server-side by
``common.verified_identity.get_verified_user_identity`` (which verifies the IAP
JWT assertion) in the request middleware and stored on
``state.state.AppState.user_email``. It is deliberately **not** re-read from any
client-controllable component state (``PageState``, dialog ``mode``, etc.) nor
from any plaintext identity header.

This ownership check enforces authorization on the server before every mutation;
Vuln #4 makes the identity it consumes unspoofable (the IAP assertion is verified
and plaintext identity headers are never trusted).
"""

from __future__ import annotations

from typing import Any


class OwnershipError(PermissionError):
    """Raised when the server-derived caller does not own the target document.

    Subclasses :class:`PermissionError` so existing ``except PermissionError``
    handlers (and callers that expect a 403-style failure) work unchanged.
    """


def get_current_user_email() -> str | None:
    """Return the server-derived caller identity for the current request.

    Reads ``AppState.user_email`` (populated at request handling from the
    verified identity in ``common.verified_identity``). Returns ``None`` when
    there is no active Mesop request context (for example a background thread or
    a unit test), so callers can supply an explicit identity or a server-derived
    fallback.

    All errors are swallowed intentionally: the inability to resolve an identity
    must never be mistaken for a *valid* identity. Callers decide how to treat a
    ``None`` result (see :func:`resolve_caller_email`).
    """
    try:
        import mesop as me

        from state.state import AppState

        return me.state(AppState).user_email
    except Exception:
        return None


def resolve_caller_email(
    explicit: str | None = None,
    *,
    fallback: str | None = None,
) -> str | None:
    """Resolve the server-derived caller identity to enforce ownership against.

    Priority:
      1. ``explicit`` — an identity the caller already derived server-side
         (for example the ``user_email`` a request-scoped middleware computed).
      2. ``AppState.user_email`` for the active request.
      3. ``fallback`` — a server-derived value captured earlier at request time
         (for example ``item.user_email`` set from ``app_state.user_email``),
         used for create/overwrite paths that may run outside a live request
         context (background threads) where nothing else is available.
    """
    if explicit:
        return explicit
    server = get_current_user_email()
    if server:
        return server
    return fallback


def enforce_ownership(
    existing_owner: Any,
    caller_email: str | None,
    *,
    resource: str = "document",
) -> None:
    """Raise :class:`OwnershipError` unless ``caller_email`` owns the resource.

    Fails closed: a missing caller identity is rejected rather than allowed. An
    ``existing_owner`` of ``None`` (an ownerless/legacy document) is permitted so
    this check does not break access to pre-existing unattributed data.
    """
    if not caller_email:
        raise OwnershipError(
            f"Refusing to modify {resource}: no server-derived caller identity "
            "is available to authorize the request.",
        )
    if existing_owner is not None and existing_owner != caller_email:
        raise OwnershipError(
            f"Caller {caller_email!r} is not the owner of this {resource} "
            f"(owned by {existing_owner!r}).",
        )


def authorize_snapshot(
    snapshot: Any,
    owner_field: str,
    caller_email: str | None,
    *,
    resource: str = "document",
) -> None:
    """Authorize a mutation against an already-loaded Firestore snapshot.

    Use this to avoid a second read when the caller has already fetched the
    document. A non-existent snapshot is treated as ownerless (create).
    """
    existing_owner = None
    if snapshot is not None and getattr(snapshot, "exists", False):
        existing_owner = (snapshot.to_dict() or {}).get(owner_field)
    enforce_ownership(existing_owner, caller_email, resource=resource)


def authorize_existing_document(
    doc_ref: Any,
    owner_field: str,
    caller_email: str | None,
    *,
    resource: str = "document",
) -> None:
    """Load ``doc_ref`` and authorize the caller against its ``owner_field``.

    For update/overwrite/delete paths keyed by a client-supplied document id.
    Loads the existing document, compares its owner field to ``caller_email`` and
    raises :class:`OwnershipError` on mismatch. A document that does not yet
    exist is treated as a create (ownerless) and only requires a valid caller.
    """
    snapshot = doc_ref.get()
    authorize_snapshot(snapshot, owner_field, caller_email, resource=resource)


def authorize_attribution(
    recorded_owner: Any,
    caller_email: str | None,
    *,
    resource: str = "document",
) -> None:
    """Authorize a create: the recorded owner must equal the caller identity.

    Prevents attribution forgery — a caller recording a document as owned by
    someone else. Fails closed when no caller identity is available.
    """
    if not caller_email:
        raise OwnershipError(
            f"Refusing to create {resource}: no server-derived caller identity "
            "is available to authorize the request.",
        )
    if recorded_owner is not None and recorded_owner != caller_email:
        raise OwnershipError(
            f"Refusing to record {resource} attributed to {recorded_owner!r} "
            f"on behalf of caller {caller_email!r}.",
        )


def is_owner(existing_owner: Any, caller_email: str | None) -> bool:
    """Return ``True`` when ``caller_email`` may access ``existing_owner``'s data.

    The read-side counterpart of :func:`enforce_ownership`, sharing the same
    policy but returning a boolean instead of raising:

    * fails closed — a missing caller identity is *never* an owner;
    * tolerates legacy/ownerless documents (``existing_owner is None``) so
      pre-existing unattributed data stays reachable, consistent with #1920.
    """
    if not caller_email:
        return False
    if existing_owner is None:
        return True
    return existing_owner == caller_email


def authorize_read(
    doc_ref: Any,
    owner_field: str,
    caller_email: str | None,
    *,
    resource: str = "document",  # noqa: ARG001 (kept for call-site symmetry)
    allow_shared: bool = False,
) -> dict | None:
    """Owner-scoped single-document read for load-by-client-supplied-id paths.

    Loads ``doc_ref`` and returns its data dict **only** when the caller owns it
    (or it is a legacy ownerless document, per :func:`is_owner`). Returns
    ``None`` when the document does not exist **or** the caller is not
    authorized — the two cases are deliberately indistinguishable so a non-owner
    cannot probe existence or contents (no existence/content leak). Fails closed
    on a missing caller identity.

    Use this for reads keyed by a client-controllable id (for example a
    ``storyboard_id`` / ``object_rotation_id`` URL query param).

    ``allow_shared`` is the opt-in for the shared Library (the ``SHARED_LIBRARY``
    admin setting): when ``True`` any *authenticated* caller (non-empty
    ``caller_email``) may read the document, not just its owner. It is
    read-only by construction and still fails closed on a missing identity. The
    default is ``False`` so existing owner-only callers are unchanged; write
    paths never consult it.
    """
    snapshot = doc_ref.get()
    if snapshot is None or not getattr(snapshot, "exists", False):
        return None
    data = snapshot.to_dict() or {}
    if allow_shared and caller_email:
        return data
    if not is_owner(data.get(owner_field), caller_email):
        return None
    return data
