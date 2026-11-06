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
"""Prove-it tests for the verified-identity trust boundary (Vuln #4, Phase 1).

These tests drive the REAL google-auth verification path. Self-signed ES256
tokens are minted with a throwaway EC key, and google-auth's cert fetch is
patched to return the matching self-signed certificate — so ``verify_iap_assertion``
exercises production signature/aud/exp/iss checks against known-good and
known-bad tokens. No fake verifier is wired into any production path.
"""

# ruff: noqa: D103, S101

import datetime
import sys
import time
from pathlib import Path

import jwt as pyjwt  # PyJWT (test-only token minting)
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.identity import (
    ANONYMOUS_USER_EMAIL,
    INTERNAL_SESSION_ID_ENVIRON,
    INTERNAL_SESSION_ID_HEADER,
    INTERNAL_VERIFIED_EMAIL_ENVIRON,
    INTERNAL_VERIFIED_EMAIL_HEADER,
    require_authenticated_user,
    set_internal_scope_headers,
)
from common.verified_identity import (
    IAP_ASSERTION_HEADER,
    IAP_ISSUER,
    MANAGED_PLATFORM_MARKERS,
    IdentityConfigError,
    get_verified_user_identity,
    validate_identity_config,
    validate_serving_environment,
    verify_iap_assertion,
)

TEST_AUDIENCE = "/projects/12345/global/backendServices/67890"
TEST_KID = "test-iap-key-1"
REAL_USER = "real@example.com"
SPOOFED_USER = "admin@google.com"


# --------------------------------------------------------------------------- #
# Self-signed ES256 signing material + a patched certs source (the test seam). #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def _signing_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="module")
def _private_pem(_signing_key):
    return _signing_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.fixture(scope="module")
def _cert_pem(_signing_key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-iap")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(_signing_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .sign(_signing_key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture
def patch_certs(monkeypatch, _cert_pem):
    """Patch google-auth's cert fetch to serve our self-signed certificate."""
    from google.oauth2 import id_token

    monkeypatch.setattr(
        id_token,
        "_fetch_certs",
        lambda request, certs_url: {TEST_KID: _cert_pem},
    )


@pytest.fixture
def mint_token(_private_pem):
    """Return a factory that mints signed ES256 tokens for tests."""

    def _mint(
        *,
        email=REAL_USER,
        audience=TEST_AUDIENCE,
        issuer=IAP_ISSUER,
        sub="accounts:1234567890",
        exp_delta=3600,
        key=_private_pem,
        kid=TEST_KID,
    ):
        now = int(time.time())
        claims = {
            "iss": issuer,
            "aud": audience,
            "email": email,
            "sub": sub,
            "iat": now - 5,
            "exp": now + exp_delta,
        }
        return pyjwt.encode(claims, key, algorithm="ES256", headers={"kid": kid})

    return _mint


@pytest.fixture
def deployed_env(monkeypatch):
    """Configure a deployed (iap) environment with a test audience."""
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("IAP_JWT_AUDIENCE", TEST_AUDIENCE)


# --------------------------------------------------------------------------- #
# verify_iap_assertion — the pure verifier (real google-auth crypto).         #
# --------------------------------------------------------------------------- #


def test_verify_iap_assertion_accepts_valid_token(patch_certs, mint_token) -> None:
    claims = verify_iap_assertion(mint_token(), TEST_AUDIENCE)

    assert claims["email"] == REAL_USER
    assert claims["iss"] == IAP_ISSUER


def test_verify_iap_assertion_rejects_wrong_audience(patch_certs, mint_token) -> None:
    with pytest.raises(Exception):  # noqa: B017, PT011
        verify_iap_assertion(mint_token(audience="wrong-audience"), TEST_AUDIENCE)


def test_verify_iap_assertion_rejects_expired(patch_certs, mint_token) -> None:
    with pytest.raises(Exception):  # noqa: B017, PT011
        verify_iap_assertion(mint_token(exp_delta=-60), TEST_AUDIENCE)


def test_verify_iap_assertion_rejects_wrong_issuer(patch_certs, mint_token) -> None:
    with pytest.raises(Exception):  # noqa: B017, PT011
        verify_iap_assertion(mint_token(issuer="https://evil.example.com"), TEST_AUDIENCE)


def test_verify_iap_assertion_rejects_bad_signature(patch_certs, mint_token) -> None:
    other_key = ec.generate_private_key(ec.SECP256R1())
    other_pem = other_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with pytest.raises(Exception):  # noqa: B017, PT011
        verify_iap_assertion(mint_token(key=other_pem), TEST_AUDIENCE)


# --------------------------------------------------------------------------- #
# get_verified_user_identity — the contract (prove-it scenarios a, b, c, e).   #
# --------------------------------------------------------------------------- #


def test_a_spoofed_header_no_assertion_yields_no_identity(deployed_env) -> None:
    """(a) Spoofed X-Email and every plaintext header, no assertion -> None."""
    headers = {
        "X-Email": SPOOFED_USER,
        "X-Authenticated-User": SPOOFED_USER,
        "X-Auth-Request-Email": SPOOFED_USER,
        "X-Forwarded-Email": SPOOFED_USER,
        "X-Goog-Authenticated-User-Email": SPOOFED_USER,
    }

    assert get_verified_user_identity(headers) is None


def test_b_invalid_assertion_yields_no_identity(
    deployed_env, patch_certs, mint_token, caplog
) -> None:
    """(b) Tampered/expired/wrong-aud/wrong-iss assertions -> None + WARNING."""
    other_key = ec.generate_private_key(ec.SECP256R1())
    other_pem = other_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    bad_tokens = {
        "tampered": mint_token(key=other_pem),
        "expired": mint_token(exp_delta=-60),
        "wrong_aud": mint_token(audience="wrong-audience"),
        "wrong_iss": mint_token(issuer="https://evil.example.com"),
    }
    for label, token in bad_tokens.items():
        caplog.clear()
        with caplog.at_level("WARNING"):
            identity = get_verified_user_identity({IAP_ASSERTION_HEADER: token})
        assert identity is None, label
        assert any(
            "verification failed" in r.getMessage() for r in caplog.records
        ), f"expected WARNING for {label}"


def test_c_verified_claim_wins_over_spoofed_header(
    deployed_env, patch_certs, mint_token
) -> None:
    """(c) Valid assertion for real@ + spoofed X-Email:admin@ -> real@."""
    headers = {
        IAP_ASSERTION_HEADER: mint_token(email=REAL_USER),
        "X-Email": SPOOFED_USER,
        "X-Goog-Authenticated-User-Email": SPOOFED_USER,
    }

    identity = get_verified_user_identity(headers)

    assert identity is not None
    assert identity.email == REAL_USER
    assert identity.source == "iap"
    assert identity.subject == "accounts:1234567890"


def test_e_local_mode_attributes_dev_identity(monkeypatch) -> None:
    """(e) local mode + LOCAL_DEV_USER_EMAIL attributes that identity; no
    assertion needed, plaintext headers still ignored."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("LOCAL_DEV_USER_EMAIL", "dev@example.com")

    identity = get_verified_user_identity({"X-Email": SPOOFED_USER})

    assert identity is not None
    assert identity.email == "dev@example.com"
    assert identity.source == "local-dev"


def test_e_local_mode_without_dev_email_is_anonymous(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("LOCAL_DEV_USER_EMAIL", raising=False)

    assert get_verified_user_identity({"X-Email": SPOOFED_USER}) is None


# --------------------------------------------------------------------------- #
# validate_identity_config — startup fail-fast (prove-it scenario d).          #
# --------------------------------------------------------------------------- #


def test_d_deployed_startup_without_audience_raises(monkeypatch) -> None:
    """(d) Deployed-mode startup with IAP_JWT_AUDIENCE unset -> IdentityConfigError."""
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("IAP_JWT_AUDIENCE", raising=False)

    with pytest.raises(IdentityConfigError):
        validate_identity_config()


def test_d_deployed_startup_with_audience_ok(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("IAP_JWT_AUDIENCE", TEST_AUDIENCE)

    validate_identity_config()  # must not raise


def test_d_local_startup_without_audience_ok(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("IAP_JWT_AUDIENCE", raising=False)

    validate_identity_config()  # local mode: no-op


# --------------------------------------------------------------------------- #
# Middleware gate — end-to-end 401 / attribution (mirrors main.py).           #
# --------------------------------------------------------------------------- #

PUBLIC_PATH_PREFIXES = ("/healthz", "/readyz", "/favicon.ico")


def _is_public_path(path: str) -> bool:
    """Mirror of ``main.py:_is_public_path`` (audit LOW-2 boundary).

    A public prefix like ``/healthz`` matches only itself or a sub-path
    (``/healthz/live``), never an unrelated path such as ``/healthzXYZ``.
    """
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in PUBLIC_PATH_PREFIXES
    )


def _build_app():
    """A minimal Starlette app whose middleware mirrors main.py:set_request_context
    (the Vuln #4 gate), wired to the real get_verified_user_identity."""
    import os

    from starlette.applications import Starlette
    from starlette.concurrency import run_in_threadpool
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse, PlainTextResponse
    from starlette.routing import Route

    async def endpoint(request):
        return PlainTextResponse(request.scope.get("MESOP_USER_EMAIL", ""))

    async def set_request_context(request, call_next):
        identity = await run_in_threadpool(get_verified_user_identity, request.headers)
        user_email = identity.email if identity else ANONYMOUS_USER_EMAIL
        if (
            require_authenticated_user(os.environ.get("APP_ENV", ""))
            and identity is None
            and not _is_public_path(request.url.path)
        ):
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
        request.scope["MESOP_USER_EMAIL"] = user_email
        return await call_next(request)

    return Starlette(
        routes=[
            Route("/protected", endpoint),
            Route("/healthz", endpoint),
            Route("/healthz/live", endpoint),
            Route("/healthzXYZ", endpoint),
        ],
        middleware=[Middleware(BaseHTTPMiddleware, dispatch=set_request_context)],
    )


def _client(app):
    from starlette.testclient import TestClient

    return TestClient(app)


def test_middleware_403_on_spoofed_header_without_assertion(deployed_env) -> None:
    with _client(_build_app()) as client:
        resp = client.get("/protected", headers={"X-Email": SPOOFED_USER})

    assert resp.status_code == 403


def test_middleware_403_on_invalid_assertion(
    deployed_env, patch_certs, mint_token
) -> None:
    with _client(_build_app()) as client:
        resp = client.get(
            "/protected",
            headers={IAP_ASSERTION_HEADER: mint_token(exp_delta=-60)},
        )

    assert resp.status_code == 403


def test_middleware_attributes_verified_email_over_spoof(
    deployed_env, patch_certs, mint_token
) -> None:
    with _client(_build_app()) as client:
        resp = client.get(
            "/protected",
            headers={
                IAP_ASSERTION_HEADER: mint_token(email=REAL_USER),
                "X-Email": SPOOFED_USER,
            },
        )

    assert resp.status_code == 200
    assert resp.text == REAL_USER


def test_middleware_public_path_allows_anonymous(deployed_env) -> None:
    with _client(_build_app()) as client:
        resp = client.get("/healthz", headers={"X-Email": SPOOFED_USER})

    assert resp.status_code == 200
    assert resp.text == ANONYMOUS_USER_EMAIL


# --------------------------------------------------------------------------- #
# LOW-2: public-path boundary — a prefix must match on a segment boundary.     #
# --------------------------------------------------------------------------- #


def test_public_path_boundary_exact_and_subpath() -> None:
    assert _is_public_path("/healthz") is True
    assert _is_public_path("/healthz/live") is True
    assert _is_public_path("/readyz") is True
    assert _is_public_path("/favicon.ico") is True


def test_public_path_boundary_rejects_lookalike() -> None:
    # The whole point of LOW-2: a lookalike must NOT be treated as public.
    assert _is_public_path("/healthzXYZ") is False
    assert _is_public_path("/healthz-admin") is False
    assert _is_public_path("/readyzzz") is False
    assert _is_public_path("/") is False
    assert _is_public_path("/admin") is False


def test_middleware_lookalike_public_path_still_403s(deployed_env) -> None:
    """A path that only *looks* like a public one is gated (LOW-2), not bypassed."""
    with _client(_build_app()) as client:
        resp = client.get("/healthzXYZ", headers={"X-Email": SPOOFED_USER})

    assert resp.status_code == 403


def test_middleware_public_subpath_allows_anonymous(deployed_env) -> None:
    with _client(_build_app()) as client:
        resp = client.get("/healthz/live", headers={"X-Email": SPOOFED_USER})

    assert resp.status_code == 200
    assert resp.text == ANONYMOUS_USER_EMAIL


# --------------------------------------------------------------------------- #
# LOW-1: boot-time transport smoke-check inside validate_identity_config.      #
# --------------------------------------------------------------------------- #


def test_low1_transport_smoke_check_passes_when_available(monkeypatch) -> None:
    """In iap mode with a real transport importable, startup validation passes."""
    import common.verified_identity as vi

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("IAP_JWT_AUDIENCE", TEST_AUDIENCE)
    # Ensure a clean lazy-global so the smoke-check actually constructs one.
    monkeypatch.setattr(vi, "_TRANSPORT", None)

    validate_identity_config()  # must not raise

    # The smoke-check must have actually constructed the transport at boot.
    assert vi._TRANSPORT is not None


def test_low1_missing_transport_fails_fast_at_boot(monkeypatch) -> None:
    """If the requests transport cannot be constructed, boot fails loudly (not a
    silent per-request 401-storm)."""
    import common.verified_identity as vi

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("IAP_JWT_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setattr(vi, "_TRANSPORT", None)

    def _boom():
        raise ImportError("google-auth[requests] transport unavailable")

    monkeypatch.setattr(vi, "_request_transport", _boom)

    with pytest.raises(IdentityConfigError) as excinfo:
        validate_identity_config()

    assert "transport is unavailable" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# LOW-3: app-side backstop — refuse to serve mock identity on a managed        #
# platform. Exercises validate_serving_environment (the serve/boot guard).     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("marker", MANAGED_PLATFORM_MARKERS)
def test_low3_managed_platform_marker_plus_local_refuses(monkeypatch, marker) -> None:
    """Marker present + AUTH_MODE resolved to local -> hard refusal to serve."""
    monkeypatch.setenv("APP_ENV", "local")
    for m in MANAGED_PLATFORM_MARKERS:
        monkeypatch.delenv(m, raising=False)
    monkeypatch.setenv(marker, "some-value")

    with pytest.raises(IdentityConfigError) as excinfo:
        validate_serving_environment()

    assert marker in str(excinfo.value)


def test_low3_plain_local_dev_serves(monkeypatch) -> None:
    """No platform markers + local mode -> serves normally (no-op)."""
    monkeypatch.setenv("APP_ENV", "local")
    for m in MANAGED_PLATFORM_MARKERS:
        monkeypatch.delenv(m, raising=False)

    validate_serving_environment()  # must not raise


def test_low3_managed_platform_with_iap_mode_ok(monkeypatch) -> None:
    """Marker present but AUTH_MODE is iap (correct deploy) -> no refusal."""
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("K_SERVICE", "gmcs")

    validate_serving_environment()  # must not raise


# --------------------------------------------------------------------------- #
# Phase 2 (taint site B) + HIGH-2/LOW-4: the REAL ASGI->WSGI identity bridge.  #
#                                                                              #
# AppState runs in a WSGI app mounted behind WSGIMiddleware; build_environ     #
# copies ONLY headers into the WSGI environ, so custom ASGI scope keys never   #
# reach AppState. These tests drive the REAL bridge end-to-end: the production #
# strip-then-set helper + real WSGIMiddleware.build_environ + a WSGI app that  #
# reads the environ EXACTLY as state.state.AppState.__init__ does. No          #
# fabricated environ is used (closes MED-1).                                   #
# --------------------------------------------------------------------------- #


def _appstate_read_from_environ(environ) -> tuple[str, str]:
    """Mirror of state.state.AppState.__init__ reads, against the WSGI environ.

    Flask's ``request.environ`` (what AppState reads) IS the WSGI environ that
    ``build_environ`` produces, so reading this dict is faithful to AppState.
    """
    user_email = environ.get(INTERNAL_VERIFIED_EMAIL_ENVIRON, ANONYMOUS_USER_EMAIL)
    session_id = environ.get(INTERNAL_SESSION_ID_ENVIRON, "")
    return user_email, session_id


def _build_bridge_app(captured: dict):
    """A Starlette app whose middleware mirrors main.py:set_request_context and
    mounts a WSGI app (standing in for the Mesop/Flask AppState app) behind the
    REAL WSGIMiddleware, so the ASGI->WSGI header bridge is exercised for real."""
    import uuid

    from starlette.applications import Starlette
    from starlette.concurrency import run_in_threadpool
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.middleware.wsgi import WSGIMiddleware
    from starlette.routing import Mount

    def mesop_like_wsgi_app(environ, start_response):
        # This is the WSGI boundary AppState lives behind. Read exactly as
        # AppState.__init__ does.
        user_email, session_id = _appstate_read_from_environ(environ)
        captured["user_email"] = user_email
        captured["session_id"] = session_id
        # Prove the original HIGH bug: a custom ASGI scope key must NOT be here.
        captured["environ_has_scope_key"] = "MESOP_USER_EMAIL" in environ
        captured["raw_internal_email"] = environ.get(INTERNAL_VERIFIED_EMAIL_ENVIRON)
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [user_email.encode()]

    async def set_request_context(request, call_next):
        identity = await run_in_threadpool(get_verified_user_identity, request.headers)
        user_email = identity.email if identity else ANONYMOUS_USER_EMAIL

        # Generate session id once; use the SAME value for scope, bridge header,
        # and response cookie (mirrors main.py).
        session_id = request.cookies.get("session_id") or str(uuid.uuid4())

        request.scope["MESOP_USER_EMAIL"] = user_email
        request.scope["MESOP_SESSION_ID"] = session_id
        set_internal_scope_headers(
            request.scope,
            {
                INTERNAL_VERIFIED_EMAIL_HEADER: user_email,
                INTERNAL_SESSION_ID_HEADER: session_id,
            },
        )
        captured["server_session_id"] = session_id
        response = await call_next(request)
        response.set_cookie("session_id", session_id, httponly=True, samesite="Lax")
        return response

    return Starlette(
        routes=[Mount("/", app=WSGIMiddleware(mesop_like_wsgi_app))],
        middleware=[Middleware(BaseHTTPMiddleware, dispatch=set_request_context)],
    )


def test_bridge_carries_verified_identity_to_appstate(
    deployed_env, patch_certs, mint_token
) -> None:
    """Valid assertion -> AppState.user_email == the verified email, across the
    REAL WSGI bridge (the scenario the old fabricated-environ test never ran)."""
    captured: dict = {}
    with _client(_build_bridge_app(captured)) as client:
        resp = client.get(
            "/anything",
            headers={IAP_ASSERTION_HEADER: mint_token(email=REAL_USER)},
        )

    assert resp.status_code == 200
    assert captured["user_email"] == REAL_USER
    assert resp.text == REAL_USER


def test_bridge_strips_client_injected_identity_header(
    deployed_env, patch_certs, mint_token
) -> None:
    """A client that supplies the internal transport header cannot influence
    AppState: the copy is stripped before build_environ, server value wins, and
    there is no comma-join with the spoofed value."""
    captured: dict = {}
    with _client(_build_bridge_app(captured)) as client:
        resp = client.get(
            "/anything",
            headers={
                IAP_ASSERTION_HEADER: mint_token(email=REAL_USER),
                INTERNAL_VERIFIED_EMAIL_HEADER: SPOOFED_USER,
                INTERNAL_SESSION_ID_HEADER: "attacker-supplied-session",
            },
        )

    assert resp.status_code == 200
    assert captured["user_email"] == REAL_USER
    assert captured["raw_internal_email"] == REAL_USER  # exactly one server copy
    assert SPOOFED_USER not in (captured["raw_internal_email"] or "")
    assert captured["session_id"] != "attacker-supplied-session"


def test_bridge_anonymous_when_no_assertion(deployed_env) -> None:
    """Deployed mode, no assertion + a spoofed internal header -> AppState is
    anonymous (never the spoof); the internal header is server-set to anonymous."""
    captured: dict = {}
    with _client(_build_bridge_app(captured)) as client:
        resp = client.get(
            "/anything",
            headers={INTERNAL_VERIFIED_EMAIL_HEADER: SPOOFED_USER},
        )

    assert resp.status_code == 200
    assert captured["user_email"] == ANONYMOUS_USER_EMAIL
    assert captured["user_email"] != SPOOFED_USER


def test_bridge_session_id_consistent_first_request_no_cookie(
    deployed_env, patch_certs, mint_token
) -> None:
    """FIX 2 consistency: on a FIRST request (no session cookie) the session id
    AppState reads must equal the uuid the response Set-Cookie carries, and be
    non-empty. Proves AppState is not desynced by reading the cookie directly."""
    captured: dict = {}
    with _client(_build_bridge_app(captured)) as client:
        resp = client.get(
            "/anything",
            headers={IAP_ASSERTION_HEADER: mint_token(email=REAL_USER)},
        )

    assert resp.status_code == 200
    assert captured["session_id"]  # non-empty
    assert captured["session_id"] == captured["server_session_id"]
    assert resp.cookies.get("session_id") == captured["session_id"]


def test_bridge_regression_custom_scope_key_absent_from_wsgi_environ(
    deployed_env, patch_certs, mint_token
) -> None:
    """Regression pin for the original HIGH bug: a custom ASGI scope key
    (MESOP_USER_EMAIL) does NOT reach the WSGI environ. This is exactly why
    setting identity on scope alone left AppState anonymous for everyone."""
    captured: dict = {}
    with _client(_build_bridge_app(captured)) as client:
        client.get(
            "/anything",
            headers={IAP_ASSERTION_HEADER: mint_token(email=REAL_USER)},
        )

    assert captured["environ_has_scope_key"] is False


def test_set_internal_scope_headers_strips_all_client_copies() -> None:
    """Unit test for the production strip-then-set helper: every client copy
    (any case) is removed before exactly one server copy is appended."""
    scope = {
        "headers": [
            (b"host", b"example.com"),
            (b"x-internal-verified-user-email", b"client-a@evil"),
            (b"X-Internal-Verified-User-Email", b"client-b@evil"),
            (b"x-internal-session-id", b"client-session"),
        ],
    }

    set_internal_scope_headers(
        scope,
        {
            INTERNAL_VERIFIED_EMAIL_HEADER: REAL_USER,
            INTERNAL_SESSION_ID_HEADER: "server-session",
        },
    )

    email_copies = [
        v for (k, v) in scope["headers"]
        if k.lower() == INTERNAL_VERIFIED_EMAIL_HEADER.lower().encode()
    ]
    assert email_copies == [REAL_USER.encode()]  # exactly one, server value
    # Unrelated headers preserved.
    assert (b"host", b"example.com") in scope["headers"]


def test_phase2_appstate_source_reads_only_bridged_identity() -> None:
    """Source-level guarantee: state.py derives identity ONLY from the internal
    bridge environ key and never re-introduces a raw-header identity read
    (taint site B closed)."""
    source = (Path(__file__).resolve().parents[1] / "state" / "state.py").read_text()

    assert "INTERNAL_VERIFIED_EMAIL_ENVIRON" in source
    assert "INTERNAL_SESSION_ID_ENVIRON" in source
    assert "get_authenticated_user_email" not in source
    for banned in (
        "X-Email",
        "X-Goog-Authenticated-User-Email",
        "X-Forwarded-Email",
        "X-Authenticated-User",
        "HTTP_COOKIE",
    ):
        assert banned not in source, f"state.py must not read {banned!r}"
