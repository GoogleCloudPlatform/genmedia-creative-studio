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
"""Canonical, cryptographically-verified caller identity.

This module is the single source of truth for *who the caller is*. It replaces
the previous practice of trusting client-settable plaintext identity headers. In
a deployed environment the only identity source is the IAP-signed assertion
``X-Goog-IAP-JWT-Assertion``, whose signature, issuer, audience and expiry are
verified before any claim is trusted.

Consumed by the request middleware (``main.py:set_request_context``) and, in a
later phase, by the Mesop ``AppState``. Vuln #2's server-side ownership checks
compare stored attribution against the identity produced here.

Design intent, in three rules: a failed or missing verification yields *no*
identity rather than a fallback one; mock identity is accepted only in an
explicitly local app environment; and a local-mode resolution on a managed
platform is a hard refusal to serve, not a warning.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass

from common.identity import LOCAL_APP_ENVS, normalize_user_email

logger = logging.getLogger(__name__)

# The only signed identity credential IAP provides. This is the *only* request
# header this module ever reads as an identity source.
IAP_ASSERTION_HEADER = "X-Goog-IAP-JWT-Assertion"

# Google's IAP public-key endpoint (x509 certs, rotated by Google).
IAP_PUBLIC_KEY_URL = "https://www.gstatic.com/iap/verify/public_key"

# IAP always sets this issuer; google-auth's verify_token does not enforce it,
# so we assert it explicitly after decode.
IAP_ISSUER = "https://cloud.google.com/iap"

IDENTITY_SOURCE_IAP = "iap"
IDENTITY_SOURCE_LOCAL = "local-dev"

AUTH_MODE_IAP = "iap"
AUTH_MODE_LOCAL = "local"

# Environment markers that indicate we are running on a managed serving platform
# (Cloud Run sets K_SERVICE; GKE sets KUBERNETES_SERVICE_HOST). If either is
# present we must never serve with the local mock identity.
MANAGED_PLATFORM_MARKERS = ("K_SERVICE", "KUBERNETES_SERVICE_HOST")


@dataclass(frozen=True)
class VerifiedIdentity:
    """A caller identity derived from a cryptographically verified source.

    Attributes:
        email: The verified, normalized caller email.
        subject: Stable principal id (IAP ``sub`` claim); ``None`` if absent.
        source: Where the identity came from — ``"iap"`` or ``"local-dev"``.
    """

    email: str
    subject: str | None
    source: str


class IdentityConfigError(Exception):
    """Raised at startup when a deployed env is misconfigured.

    Specifically, when ``AUTH_MODE`` resolves to ``"iap"`` but no
    ``IAP_JWT_AUDIENCE`` is configured. Raised at boot (never per request) so a
    missing-audience misconfiguration is caught at deploy time rather than
    silently failing open or 401-ing every request.
    """


def resolve_auth_mode(app_env: str | None) -> str:
    """Derive the identity source mode from ``APP_ENV``.

    Local envs (``""``, ``dev``, ``development``, ``local``, ``test``) use a
    mock identity; everything else verifies the IAP assertion. Verification is
    intrinsic to running in a deployed env — it is not a separately toggleable
    switch — which makes the incoherent "reject-absent but trust-spoofed" state
    unexpressible.
    """
    return AUTH_MODE_LOCAL if (app_env or "") in LOCAL_APP_ENVS else AUTH_MODE_IAP


def auth_mode() -> str:
    """Return the effective ``AUTH_MODE`` resolved from the environment."""
    return resolve_auth_mode(os.environ.get("APP_ENV", ""))


def iap_jwt_audience() -> str:
    """Return the configured IAP JWT audience (opaque, per-env). Empty if unset.

    The audience differs per topology and is owned by infra as a per-env value;
    it is never hardcoded here.
    """
    return os.environ.get("IAP_JWT_AUDIENCE", "") or ""


def _local_dev_user_email() -> str | None:
    """Return the explicit dev-only identity, if configured."""
    return normalize_user_email(os.environ.get("LOCAL_DEV_USER_EMAIL"))


def validate_identity_config() -> None:
    """Startup validation: fail fast on a misconfigured deployed env.

    Must be called once at boot. In ``iap`` mode:
      * an unset/empty ``IAP_JWT_AUDIENCE`` is fatal; and
      * the google-auth requests transport must be importable/usable — a missing
        transport is caught here (fail fast) rather than producing a silent
        per-request 401-storm at runtime.
    In ``local`` mode this is a no-op.
    """
    if auth_mode() != AUTH_MODE_IAP:
        return

    if not iap_jwt_audience():
        raise IdentityConfigError(
            "AUTH_MODE=iap requires IAP_JWT_AUDIENCE to be set "
            "(the per-env IAP JWT audience). Refusing to serve.",
        )

    # Boot-time transport smoke-check (audit LOW-1): confirm the google-auth
    # requests transport can be constructed now, while we can still fail loudly.
    try:
        _request_transport()
    except Exception as exc:
        raise IdentityConfigError(
            "The google-auth requests transport is unavailable; IAP assertion "
            "verification cannot run. Ensure 'google-auth[requests]' (and its "
            "'requests' dependency) is installed. Refusing to serve.",
        ) from exc


def validate_serving_environment() -> None:
    """Serve/boot guard — must be called from the serving path, NOT at module import.

    Refuses to serve (audit LOW-3) when the app has resolved to ``local`` mode
    (mock identity) but a managed-platform marker is present — i.e. a deployment
    that forgot to set a non-local ``APP_ENV`` would otherwise silently accept a
    mock/anonymous identity in production. This is a hard refusal, not a warning,
    with no easy override. In every other case it is a no-op, so plain local dev
    (no platform markers) serves normally.
    """
    if auth_mode() != AUTH_MODE_LOCAL:
        return

    present = [m for m in MANAGED_PLATFORM_MARKERS if os.environ.get(m)]
    if present:
        raise IdentityConfigError(
            "AUTH_MODE resolved to 'local' but a managed-platform marker is set "
            f"({', '.join(present)}). Refusing to serve with a mock identity in a "
            "deployed environment. Set APP_ENV to a non-local value so identity is "
            "verified from the IAP assertion.",
        )


def _request_transport():
    """Return the process-global google-auth HTTP transport.

    Reusing one transport shares google-auth's built-in IAP cert cache across
    requests; on an unknown ``kid`` (post key-rotation) google-auth refetches
    automatically, so no custom key store is needed.
    """
    global _TRANSPORT
    if _TRANSPORT is None:
        # Imported lazily so that merely importing this module (e.g. for the
        # config resolution helpers, or in local mode) does not require the
        # google-auth requests transport.
        from google.auth.transport import requests as google_requests

        _TRANSPORT = google_requests.Request()
    return _TRANSPORT


_TRANSPORT = None


def verify_iap_assertion(assertion: str, audience: str) -> Mapping[str, object]:
    """Verify an IAP JWT assertion and return its claims.

    Pure verifier (no header/config access): validates the ES256 signature,
    ``aud`` and ``exp`` via google-auth, then asserts the IAP ``iss``. Raises on
    any failure (bad signature, wrong audience, expired, wrong issuer, malformed
    token). This is the production verifier and the test seam — tests exercise it
    with self-signed ES256 tokens against a patched certs source; no fake
    verifier is ever wired into a deployed path.

    Args:
        assertion: The raw ``X-Goog-IAP-JWT-Assertion`` value.
        audience: The expected IAP audience for this env (opaque, per-env).

    Returns:
        The verified JWT claims.

    Raises:
        Exception: If the assertion cannot be cryptographically verified or the
            issuer is not IAP.
    """
    # Lazy import keeps module import light and confines the google-auth crypto
    # dependency to the actual verification path.
    from google.oauth2 import id_token

    claims = id_token.verify_token(
        assertion,
        _request_transport(),
        audience=audience,
        certs_url=IAP_PUBLIC_KEY_URL,
    )

    issuer = claims.get("iss")
    if issuer != IAP_ISSUER:
        raise ValueError(f"Unexpected IAP token issuer: {issuer!r}")

    return claims


def _verified_iap_identity(headers: Mapping[str, str]) -> VerifiedIdentity | None:
    """Verify the IAP assertion from ``headers`` and derive identity, or None."""
    assertion = headers.get(IAP_ASSERTION_HEADER) if headers else None
    if not assertion:
        # No signed credential present -> no verified identity. Plaintext
        # identity headers are deliberately never consulted here.
        return None

    audience = iap_jwt_audience()
    if not audience:
        # Should be impossible after startup validation; fail closed defensively.
        logger.error(
            "IAP_JWT_AUDIENCE is unset at request time; rejecting assertion.",
        )
        return None

    try:
        claims = verify_iap_assertion(assertion, audience)
    except Exception as exc:  # noqa: BLE001 - any failure => no verified identity
        # Present-but-invalid assertion is a tamper signal: fail closed, log it.
        logger.warning("IAP assertion verification failed: %s", exc)
        return None

    email = normalize_user_email(claims.get("email"))
    if not email:
        logger.warning("Verified IAP assertion is missing an email claim.")
        return None

    subject = claims.get("sub")
    return VerifiedIdentity(
        email=email,
        subject=str(subject) if subject is not None else None,
        source=IDENTITY_SOURCE_IAP,
    )


def _local_identity() -> VerifiedIdentity | None:
    """Return the mock dev identity (local mode only), or None for anonymous."""
    email = _local_dev_user_email()
    if email:
        return VerifiedIdentity(
            email=email,
            subject=None,
            source=IDENTITY_SOURCE_LOCAL,
        )
    # No explicit dev identity -> None. The middleware maps this to anonymous;
    # in local mode the fail-closed gate is off, preserving the local dev UX.
    return None


def get_verified_user_identity(
    headers: Mapping[str, str],
) -> VerifiedIdentity | None:
    """Return the cryptographically-verified caller identity, or ``None``.

    - ``iap`` mode (deployed): verifies ``X-Goog-IAP-JWT-Assertion`` and derives
      the email from the verified claim. NEVER reads plaintext identity headers.
      Returns ``None`` if the assertion is absent, malformed, expired, or fails
      verification (invalid is logged at WARNING).
    - ``local`` mode: returns a mock identity from ``LOCAL_DEV_USER_EMAIL``, or
      ``None`` (anonymous) if unset. Unreachable in any deployed env because the
      mode is derived from ``APP_ENV``.

    This function does not decide policy — the caller (middleware) decides
    whether ``None`` on a protected path means 401.
    """
    if auth_mode() == AUTH_MODE_LOCAL:
        return _local_identity()
    return _verified_iap_identity(headers)
