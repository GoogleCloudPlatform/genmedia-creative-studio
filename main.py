# Copyright 2024 Google LLC
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
"""Main Mesop App."""

import datetime
import inspect
import os
import uuid

try:
    import urllib3.contrib.pyopenssl

    urllib3.contrib.pyopenssl.extract_from_urllib3()
except (ImportError, AttributeError):
    pass

try:
    import OpenSSL.SSL

    for _attr_name in dir(OpenSSL.SSL.Context):
        _attr = getattr(OpenSSL.SSL.Context, _attr_name)
        if callable(_attr) and not _attr_name.startswith("__"):

            def _make_wrapper(orig_func):
                def _wrapper(*args, **kwargs):
                    try:
                        return orig_func(*args, **kwargs)
                    except ValueError as e:
                        if "already been used" in str(e):
                            return None
                        raise

                return _wrapper

            setattr(OpenSSL.SSL.Context, _attr_name, _make_wrapper(_attr))
except (ImportError, AttributeError):
    pass

import google.auth
import mesop as me
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from google.auth import impersonated_credentials
from google.cloud import storage
from pydantic import BaseModel

import pages.brand_adherence
import pages.character_sheet
import pages.imagen_upscale
import pages.shop_the_look
import pages.storyboarder
from app_factory import app
from common.identity import (
    ANONYMOUS_USER_EMAIL,
    INTERNAL_SESSION_ID_HEADER,
    INTERNAL_VERIFIED_EMAIL_HEADER,
    LOCAL_APP_ENVS,
    set_internal_scope_headers,
)
from common.prompt_template_service import PromptTemplate
from common.utils import create_display_url
from common.verified_identity import (
    get_verified_user_identity,
    validate_serving_environment,
)
from config import default as config
from models.video_processing import convert_mp4_to_gif
from pages import about as about_page
from pages import banana_studio as banana_studio_page
from pages import character_consistency as character_consistency_page
from pages import chirp_3hd as chirp_3hd_page
from pages import config as config_page
from pages import gemini_image_generation as gemini_image_generation_page
from pages import gemini_tts as gemini_tts_page
from pages import gemini_writers_workshop as gemini_writers_workshop_page
from pages import guideline_analysis as guideline_analysis_page
from pages import home as home_page
from pages import imagen as imagen_page
from pages import interior_design_v2 as interior_design_page
from pages import lyria as lyria_page
from pages import omni as omni_page
from pages import pixie_compositor as pixie_compositor_page
from pages import portraits as motion_portraits
from pages import selfie as selfie_page
from pages import starter_pack as starter_pack_page
from pages import test_proxy_caching as test_proxy_caching_page
from pages import veo
from pages import vto as vto_page
from pages import welcome as welcome_page
from pages.library_v2 import page as library_v2_page
from pages.test_async_veo import page as test_async_veo_page
from pages.test_character_consistency import page as test_character_consistency_page
from pages.test_index import page as test_index_page
from pages.test_infinite_scroll import test_infinite_scroll_page
from pages.test_media_chooser import page as test_media_chooser_page
from pages.test_pixie_compositor import test_pixie_compositor_page
from pages.test_svg import test_svg_page
from pages.test_uploader import test_uploader_page
from pages.test_vto_prompt_generator import page as test_vto_prompt_generator_page
from routers import veo_router
from state.state import AppState
from workflows.retro_games import page as retro_games

# Object Rotation ("Edit Images") is gated behind EDIT_IMAGES_ENABLED and is
# disabled by default (product decision; see config/default.py). Only import the
# page module — which self-registers its @me.page("/object-rotation") route — when
# the feature is enabled, so the page is neither shown in nav nor reachable by URL.
if config.Default.EDIT_IMAGES_ENABLED:
    from pages import object_rotation as object_rotation_page


class UserInfo(BaseModel):
    email: str | None
    agent: str | None


PUBLIC_PATH_PREFIXES = ("/healthz", "/readyz", "/favicon.ico")


def _is_public_path(path: str) -> bool:
    """Return True only for a public prefix or a sub-path of one.

    Matches on a path-segment boundary so a public prefix like ``/healthz`` does
    not match an unrelated path such as ``/healthzXYZ`` (audit LOW-2).
    """
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in PUBLIC_PATH_PREFIXES
    )


# Serve/boot guard: refuse to serve with a mock (local) identity on a managed
# platform (audit LOW-3). Runs when the server process boots (this module is the
# serving entrypoint), not during unit tests, which do not import main.
validate_serving_environment()


# FastAPI server with Mesop
router = APIRouter()
app.include_router(router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("assets/favicon.ico")


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz():
    return {"status": "ok"}


# Define allowed origins for CORS


from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware


class ForwardedHostMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        forwarded_host = request.headers.get("X-Forwarded-Host")
        if forwarded_host:
            # Overwrite the host so that Mesop's CSRF check matches the Origin header
            request.scope["headers"] = [
                (k, v) if k != b"host" else (k, forwarded_host.encode())
                for k, v in request.scope["headers"]
            ]
        return await call_next(request)


app.add_middleware(ForwardedHostMiddleware)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=os.environ.get(
        "CORS_ORIGIN_REGEX",
        r"https://.*|http://localhost:8080",
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/convert_to_gif")
def convert_to_gif(gcs_uri: str, request: Request):
    """Converts an MP4 video to a GIF and saves it to GCS."""
    try:
        uri = convert_mp4_to_gif(gcs_uri, request.scope["MESOP_USER_EMAIL"])

        return {"url": create_display_url(uri)}
    except Exception as e:
        error_message = str(e)
        print(f"Error generating GIF: {error_message}")
        return {"error": error_message}, 500


@app.get("/api/get_signed_url")
def get_signed_url(gcs_uri: str):
    """Generates a signed URL for a GCS object."""
    try:
        credentials, _ = google.auth.default()

        signing_credentials = impersonated_credentials.Credentials(
            source_credentials=credentials,
            target_principal=config.Default.SERVICE_ACCOUNT_EMAIL,
            target_scopes="https://www.googleapis.com/auth/devstorage.read_only",
        )

        storage_client = storage.Client()
        bucket_name, blob_name = gcs_uri.replace("gs://", "").split("/", 1)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=15),
            method="GET",
            credentials=signing_credentials,
        )

        return {"signed_url": signed_url}
    except Exception as e:
        error_message = str(e)
        print(f"Error generating signed url: {error_message}")
        if "private key" in error_message:
            print(
                "This error often occurs in a local development environment. "
                "Please ensure you have authenticated with service account impersonation by running: "
                "gcloud auth application-default login --impersonate-service-account=<YOUR_SERVICE_ACCOUNT_EMAIL>",
            )
        return {"error": error_message}, 500


@app.middleware("http")
async def add_global_csp(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://esm.sh https://cdn.jsdelivr.net; "
        "connect-src 'self' https://esm.sh https://cdn.jsdelivr.net https://storage.cloud.google.com https://storage.googleapis.com https://*.googleusercontent.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com http://fonts.googleapis.com/; "
        "font-src 'self' data: https://fonts.gstatic.com https://fonts.googleapis.com http://fonts.googleapis.com;"
        "img-src 'self' data: blob: https://google-ai-skin-tone-research.imgix.net https://storage.cloud.google.com https://storage.googleapis.com https://*.googleusercontent.com; "
        "media-src 'self' https://deepmind.google https://storage.cloud.google.com https://storage.googleapis.com https://*.googleusercontent.com; "
        "worker-src 'self' blob:;"
    )
    return response


@app.middleware("http")
async def set_request_context(request: Request, call_next):
    # Identity comes ONLY from the cryptographically verified source. In a
    # deployed env this verifies the IAP assertion; plaintext identity headers
    # are never trusted. Verification is CPU-bound (with an occasional cached cert
    # fetch), so run it off the event loop.
    identity = await run_in_threadpool(get_verified_user_identity, request.headers)
    user_email = identity.email if identity else ANONYMOUS_USER_EMAIL

    if (
        config.Default.REQUIRE_AUTHENTICATED_USER
        and identity is None
        and not _is_public_path(request.url.path)
    ):
        return JSONResponse(
            {"detail": "Authentication required"},
            status_code=401,
        )

    # Generate the session id ONCE and use the same value everywhere below (scope
    # key, internal bridge header, and the response cookie) so AppState, the ASGI
    # consumers, and the client cookie never disagree.
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())

    # ASGI scope keys — consumed directly by the ASGI-layer handlers
    # (veo_router, get_media_proxy, convert_to_gif). Left as-is (Phase 4).
    request.scope["MESOP_USER_EMAIL"] = user_email
    request.scope["MESOP_SESSION_ID"] = session_id

    # ASGI->WSGI bridge (Vuln #4 HIGH-2 transport fix + LOW-4 session transport).
    # WSGIMiddleware.build_environ copies ONLY headers into the WSGI environ, not
    # custom scope keys, so the Mesop AppState (WSGI) cannot see the scope values
    # above. Carry the ALREADY-verified email and the server-owned session id
    # across as dedicated internal headers. set_internal_scope_headers strips any
    # client-supplied copy BEFORE setting exactly one server value, so a client
    # can neither inject nor append to them. These headers are never an identity
    # input to the verifier.
    set_internal_scope_headers(
        request.scope,
        {
            INTERNAL_VERIFIED_EMAIL_HEADER: user_email,
            INTERNAL_SESSION_ID_HEADER: session_id,
        },
    )

    # Pass GA ID to Mesop context if it exists
    if config.Default.GA_MEASUREMENT_ID:
        request.scope["MESOP_GA_MEASUREMENT_ID"] = config.Default.GA_MEASUREMENT_ID

    response = await call_next(request)
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        samesite="Lax",
    )
    return response


# Test page routes are left as is, they don't need the scaffold
me.page(path="/test_character_consistency", title="Test Character Consistency")(
    test_character_consistency_page,
)
me.page(path="/test_index", title="Test Index")(test_index_page)
me.page(path="/test_infinite_scroll", title="Test Infinite Scroll")(
    test_infinite_scroll_page,
)
me.page(path="/test_pixie_compositor", title="Test Pixie Compositor")(
    test_pixie_compositor_page,
)
me.page(path="/test_uploader", title="Test Uploader")(test_uploader_page)
me.page(path="/test_vto_prompt_generator", title="Test VTO Prompt Generator")(
    test_vto_prompt_generator_page,
)
me.page(path="/test_svg", title="Test SVG")(test_svg_page)
me.page(path="/test_media_chooser", title="Test Media Chooser")(test_media_chooser_page)
me.page(path="/test_async_veo", title="Test Async Veo")(test_async_veo_page)

# Global storage client instance to reuse connections
_proxy_storage_client = None


def get_proxy_storage_client():
    global _proxy_storage_client
    if _proxy_storage_client is None:
        _proxy_storage_client = storage.Client()
    return _proxy_storage_client


def _allowed_proxy_buckets() -> set[str]:
    """Return the set of GCS bucket NAMES the media proxy is permitted to serve.

    The allowlist is sourced exclusively from the application's own storage
    configuration (the buckets this app writes its generated media to). Several
    of those config values embed a path prefix (e.g. ``"my-bucket/videos"``) or
    a ``gs://`` scheme; only the leading bucket component is used for the
    allowlist comparison.

    An empty result means "allow nothing": callers MUST fail closed so that a
    missing/unconfigured allowlist can never degrade into "allow all".
    """
    candidates = (
        config.Default.GENMEDIA_BUCKET,
        config.Default.VIDEO_BUCKET,
        config.Default.IMAGE_BUCKET,
        config.Default.GCS_ASSETS_BUCKET,
        getattr(config.Default, "MEDIA_BUCKET", None),
    )
    allowed: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        # Normalize: drop any gs:// scheme, then keep only the bucket component
        # preceding the first path separator.
        name = candidate.replace("gs://", "", 1).split("/", 1)[0].strip()
        if name:
            allowed.add(name)
    return allowed


def _is_proxy_bucket_allowed(bucket_name: str) -> bool:
    """Return True only if ``bucket_name`` is one of the app's own buckets.

    Fails closed: any empty/unknown bucket, or an empty allowlist, returns False.
    """
    if not bucket_name:
        return False
    return bucket_name in _allowed_proxy_buckets()


# Add a new endpoint to proxy GCS media for better caching.
@app.get("/media/{bucket_name}/{object_path:path}")
def get_media_proxy(request: Request, bucket_name: str, object_path: str):
    """Securely proxies a GCS object, checking for IAP authentication."""
    # Consume the verified identity the middleware placed on the request; no
    # bespoke identity derivation here (Vuln #4, Phase 4).
    user_email = request.scope.get("MESOP_USER_EMAIL")

    # Enforce authentication in any environment that is not a canonical local dev
    # environment (aligned with common.identity.LOCAL_APP_ENVS).
    if config.Default.APP_ENV not in LOCAL_APP_ENVS and (
        not user_email or user_email == ANONYMOUS_USER_EMAIL
    ):
        raise HTTPException(status_code=401, detail="Authentication required")

    # Bucket allowlist enforcement (READ-SWEEP-B, defense-in-depth): the bucket
    # name arrives from the request path, so without this check an authenticated
    # caller could proxy objects from ANY bucket the app's service account can
    # read, not just the app's own media buckets. Restrict to the configured
    # allowlist and fail closed. Reject with the SAME generic 404 used for a
    # missing object so this does not become an oracle that distinguishes
    # "bucket not allowed" from "object does not exist".
    if not _is_proxy_bucket_allowed(bucket_name):
        raise HTTPException(status_code=404, detail="Object not found")

    try:
        storage_client = get_proxy_storage_client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_path)

        if not blob.exists():
            raise HTTPException(status_code=404, detail="Object not found")

        blob.reload()
        content_type = blob.content_type

        # Set a cache header to instruct browsers and CDNs to cache for 1 hour.
        headers = {"Cache-Control": "public, max-age=3600"}

        # Stream the file content directly from GCS to the user.
        stream = blob.open("rb")
        return StreamingResponse(stream, media_type=content_type, headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error proxying GCS object: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/home")


# Use this to mount the static files for the Mesop app
app.mount(
    "/__web-components-module__",
    StaticFiles(directory="."),
    name="web_components",
)
app.mount(
    "/static",
    StaticFiles(
        directory=os.path.join(
            os.path.dirname(inspect.getfile(me)),
            "web",
            "src",
            "app",
            "prod",
            "web_package",
        ),
    ),
    name="static",
)

app.include_router(veo_router.router)


app.mount(
    "/",
    WSGIMiddleware(
        me.create_wsgi_app(debug_mode=os.environ.get("DEBUG_MODE", "") == "true"),
    ),
)


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        reload_includes=["*.py", "*.js"],
        timeout_graceful_shutdown=0,
        proxy_headers=True,
    )
