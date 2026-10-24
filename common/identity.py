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
"""Identity helpers: email normalization and the fail-closed auth policy.

Caller identity is derived exclusively from the cryptographically verified source
in :mod:`common.verified_identity`. This module intentionally no longer reads any
plaintext identity header: the prior header-fallback reader (the Vuln #4 spoofing
vector) has been removed. What remains is provider-agnostic email normalization,
shared constants, and the ``REQUIRE_AUTHENTICATED_USER`` policy resolution.
"""

import os

ANONYMOUS_USER_EMAIL = "anonymous@google.com"

# MIRRORED by local.local_app_envs in deploy/terraform/gke/main.tf, the HCL list
# the fail-closed APP_ENV plan-time precondition (terraform_data.gke_app_env_guard)
# reads via contains() to decide whether a GKE Stage-2 apply may PROCEED -- a
# plan-time apply gate, NOT the serving-time refusal (that is
# validate_serving_environment in common/verified_identity.py). The two sets are a
# fail-open-relevant pair with no automated detector: do NOT edit LOCAL_APP_ENVS
# alone; mirror any add, removal, or rename to local.local_app_envs. An env this app
# treats as local but missing there can pass the apply gate and derive
# AUTH_MODE='local' (mock identity) on a managed platform.
LOCAL_APP_ENVS = {"", "dev", "development", "local", "test"}
TRUE_VALUES = {"1", "true", "yes", "on"}

# --- Internal ASGI->WSGI identity transport (Vuln #4) ---------------------- #
# The verified caller identity is resolved in the ASGI request middleware, but
# the Mesop ``AppState`` runs in the WSGI app mounted behind ``WSGIMiddleware``.
# ``build_environ`` copies ONLY request headers (not custom ASGI scope keys) into
# the WSGI environ, so the middleware transports the ALREADY-verified values
# across the boundary as dedicated *internal* request headers. It sets them only
# after UNCONDITIONALLY stripping any client-supplied copy, so a client can never
# inject or append to them. These headers are NEVER an identity *input* to the
# verifier (see ``common.verified_identity``); they only carry a server-decided
# value from the middleware to ``AppState``.
INTERNAL_VERIFIED_EMAIL_HEADER = "X-Internal-Verified-User-Email"
INTERNAL_SESSION_ID_HEADER = "X-Internal-Session-Id"


def _wsgi_environ_key(header_name: str) -> str:
    """Return the WSGI environ key ``build_environ`` produces for a header."""
    return "HTTP_" + header_name.upper().replace("-", "_")


# Keys ``AppState`` reads from the WSGI environ (derived so they never drift from
# the header names the middleware sets).
INTERNAL_VERIFIED_EMAIL_ENVIRON = _wsgi_environ_key(INTERNAL_VERIFIED_EMAIL_HEADER)
INTERNAL_SESSION_ID_ENVIRON = _wsgi_environ_key(INTERNAL_SESSION_ID_HEADER)


def set_internal_scope_headers(scope: dict, values: dict[str, str]) -> None:
    """Strip client-supplied copies of the given internal headers, then set one.

    ASGI ``scope["headers"]`` is a list of ``(name, value)`` byte tuples. For each
    header in ``values`` this removes EVERY existing copy (case-insensitive)
    BEFORE appending exactly one server-controlled copy. Stripping first is
    security-critical: ``build_environ`` comma-joins duplicate headers, so a
    surviving client copy would be prepended to the server value in the WSGI
    environ (an internal-channel injection / identity-spoofing vector). This is
    the transport for the verified identity across the ASGI->WSGI boundary; the
    values here are already server-resolved and are never re-derived from the
    request.
    """
    strip = {name.lower().encode("latin1") for name in values}
    headers = [
        (name, value)
        for (name, value) in scope.get("headers", [])
        if name.lower() not in strip
    ]
    for name, value in values.items():
        headers.append((name.lower().encode("latin1"), value.encode("latin1")))
    scope["headers"] = headers


def normalize_user_email(value: str | None) -> str | None:
    """Normalize identity-provider email header formats."""
    if not value:
        return None

    user_email = value.split(",", maxsplit=1)[0].strip()
    if not user_email:
        return None

    for prefix in ("accounts.google.com:", "mailto:", "email:"):
        if user_email.lower().startswith(prefix):
            user_email = user_email[len(prefix) :].strip()
            break

    return user_email or None


def require_authenticated_user(app_env: str | None) -> bool:
    """Return whether requests without upstream identity should be rejected."""
    configured_value = os.environ.get("REQUIRE_AUTHENTICATED_USER")
    if configured_value is not None:
        return configured_value.strip().lower() in TRUE_VALUES

    return (app_env or "") not in LOCAL_APP_ENVS
