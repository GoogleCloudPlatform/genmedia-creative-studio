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
"""Server-side authorization for Cloud Tasks-triggered task endpoints.

Some FastAPI endpoints are *task* endpoints, not *user* endpoints: they are
invoked only by Cloud Tasks, which attaches a Google-signed OIDC token minted for
the service account configured on the queue (see
``common.tasks.enqueue_thumbnail_task``, which sets ``oidc_token`` with
``SERVICE_ACCOUNT_EMAIL``). The OIDC token's audience defaults to the task's
target URL.

Without a server-side check on *who* called them, such an endpoint is reachable
by any authenticated user. For the veo thumbnail path that is a write-side IDOR:
``run_thumbnail_job`` overwrites a Firestore item's ``thumbnail_uri`` keyed by a
client-supplied ``job_id`` with no owner check, so a user POSTing a victim's
``job_id`` plus an attacker-controlled ``video_uri`` can overwrite the victim
item's thumbnail. The correct boundary for a task endpoint is the trusted Cloud
Tasks identity, verified here.

Trust model
-----------
The caller identity is the **Google-signed, cryptographically verified** OIDC
token email. It is never read from a plaintext header. This mirrors
``common.verified_identity`` (the IAP-assertion verifier for *user* identity) and
reuses its cached google-auth transport.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from common.verified_identity import (
    AUTH_MODE_LOCAL,
    _request_transport,
    auth_mode,
)

logger = logging.getLogger(__name__)

# Google mints Cloud Tasks OIDC tokens from the standard Google OAuth2 issuer.
# google-auth's ``verify_oauth2_token`` already enforces this; we re-assert it
# defensively, matching the explicit issuer check in ``verified_identity``.
GOOGLE_OIDC_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

_BEARER_PREFIX = "Bearer "


class TaskAuthError(PermissionError):
    """Raised when a task-endpoint caller is not the trusted Cloud Tasks identity.

    Subclasses :class:`PermissionError` so existing ``except PermissionError``
    handlers (and callers that expect a 403-style failure) work unchanged.
    """


def _extract_bearer_token(headers: Mapping[str, str]) -> str | None:
    """Return the bearer token from the ``Authorization`` header, or ``None``.

    Starlette ``Headers`` is case-insensitive; a plain ``Mapping`` may not be, so
    both spellings are tried for robustness.
    """
    if not headers:
        return None
    authorization = headers.get("Authorization") or headers.get("authorization")
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        return None
    token = authorization[len(_BEARER_PREFIX) :].strip()
    return token or None


def verify_oidc_token(token: str, audience: str) -> Mapping[str, object]:
    """Verify a Google-signed OIDC token and return its claims.

    Pure verifier (no header/config access): validates the signature, ``aud`` and
    ``exp`` via google-auth against Google's OAuth2 certs, then asserts the Google
    issuer. Raises on any failure. This is the production verifier and the test
    seam — tests patch it rather than wiring a fake verifier into a deployed path.

    Args:
        token: The raw OIDC bearer token Cloud Tasks presented.
        audience: The expected audience (the task's target URL).

    Returns:
        The verified token claims.

    Raises:
        Exception: If the token cannot be cryptographically verified or the
            issuer is not Google.
    """
    # Lazy import keeps module import light and confines the google-auth crypto
    # dependency to the actual verification path (matches verified_identity).
    from google.oauth2 import id_token

    claims = id_token.verify_oauth2_token(
        token,
        _request_transport(),
        audience=audience,
    )

    issuer = claims.get("iss")
    if issuer not in GOOGLE_OIDC_ISSUERS:
        raise ValueError(f"Unexpected OIDC token issuer: {issuer!r}")

    return claims


def authorize_cloud_task_caller(
    headers: Mapping[str, str],
    *,
    expected_service_account: str | None,
    audience: str,
) -> None:
    """Fail closed unless the caller is the trusted Cloud Tasks service account.

    Verifies the ``Authorization: Bearer`` OIDC token Cloud Tasks attaches and
    requires that its verified ``email`` claim equals ``expected_service_account``
    (and ``email_verified`` is true). Raises :class:`TaskAuthError` otherwise.

    In ``local`` auth mode Cloud Tasks is not used (the thumbnail flow runs in an
    in-process background thread, never through this HTTP endpoint), so there is
    no OIDC token to verify and this is a no-op — consistent with how
    ``verified_identity`` treats local mode. ``validate_serving_environment``
    already refuses to serve in local mode on a managed platform, so this cannot
    silently fail open in a deployed environment.

    Args:
        headers: The inbound request headers.
        expected_service_account: The service account Cloud Tasks mints the OIDC
            token for (``config.Default.SERVICE_ACCOUNT_EMAIL``).
        audience: The expected OIDC audience (the task's target URL).

    Raises:
        TaskAuthError: If the token is absent, invalid, unverified, or minted for
            a different identity, or if no trusted service account is configured.
    """
    if auth_mode() == AUTH_MODE_LOCAL:
        return

    if not expected_service_account:
        # A deployed task endpoint with no configured trusted identity must not
        # accept anyone. Fail closed rather than silently allowing all callers.
        raise TaskAuthError(
            "No trusted task service account is configured "
            "(SERVICE_ACCOUNT_EMAIL); refusing the task request.",
        )

    token = _extract_bearer_token(headers)
    if not token:
        raise TaskAuthError("Missing Cloud Tasks OIDC bearer token.")

    try:
        claims = verify_oidc_token(token, audience)
    except Exception as exc:
        # Any verification failure => unauthorized. Re-raised as TaskAuthError.
        raise TaskAuthError(f"OIDC token verification failed: {exc}") from exc

    if not claims.get("email_verified"):
        raise TaskAuthError("OIDC token email claim is not verified.")

    email = claims.get("email")
    if email != expected_service_account:
        raise TaskAuthError(
            f"OIDC token caller {email!r} is not the trusted task identity "
            f"{expected_service_account!r}.",
        )
