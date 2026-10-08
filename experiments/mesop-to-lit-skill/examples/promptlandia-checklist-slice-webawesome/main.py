# Copyright 2025 Google LLC
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

"""ASGI entrypoint. Replaces the deleted Mesop WSGI `app.py` (`app:me`).

Single-service model (target-architecture §7): FastAPI serves `/api/*` and the
Vite-built SPA. Order matters -- API routers and health first, then the static
mount + SPA deep-link fallback last.
"""

import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.errors import register_error_handlers
from api.routes_actions import router as actions_router
from api.routes_config import router as config_router

# Built frontend lives in web/dist (vite build output, §4.1). Absolute so it
# resolves regardless of the process CWD.
_HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIST = os.path.join(_HERE, "web", "dist")

# CSP preserves the Mesop iframe-embed hook (§8): frame-ancestors self +
# google.github.io. Trusted-Types disable flags are NOT carried (Mesop-only
# workaround); we sanitize markdown with DOMPurify client-side instead.
# Hardened (security follow-up F3): base-uri/object-src/form-action locked down,
# img-src narrowed to 'self' data: (no wildcard https: beacon surface for
# attacker-influenced markdown image URLs). `style-src 'unsafe-inline'` is kept
# for now -- Lit/MWC inject constructable styles and DOMPurify may leave inline
# `style` attributes on sanitized markdown; dropping it needs a browser/e2e pass
# we do not have here (tracked tradeoff, see RESULTS.md).
_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "form-action 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'self' https://google.github.io"
)

app = FastAPI(title="Promptlandia (FastAPI + Lit)", version="0.1.0")

register_error_handlers(app)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # HSTS (security follow-up F4): only meaningful over HTTPS (Cloud Run
    # terminates TLS and forwards x-forwarded-proto). Emit only on HTTPS so we
    # never pin HSTS on a plain-http dev/test request.
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    if forwarded_proto == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
    return response


# ---- API first ---------------------------------------------------------------
app.include_router(config_router)
app.include_router(actions_router)


# ---- Static + SPA fallback last ----------------------------------------------
if os.path.isdir(WEB_DIST):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(WEB_DIST, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """Serve a built static file if it exists, else index.html (deep links).

        Containment check (CWE-22): `full_path` is attacker-controlled and
        Starlette's `:path` convertor does NOT collapse `..` dot-segments
        (uvicorn percent-decodes before routing), so a naive
        `os.path.join(WEB_DIST, full_path)` + FileResponse is an arbitrary
        file read. Resolve the candidate with realpath and confirm it stays
        inside WEB_DIST before serving; otherwise fall through to index.html.
        """
        real_dist = os.path.realpath(WEB_DIST)
        if full_path:
            candidate = os.path.realpath(os.path.join(real_dist, full_path))
            contained = candidate == real_dist or candidate.startswith(
                real_dist + os.sep
            )
            if contained and os.path.isfile(candidate):
                return FileResponse(candidate)
        index = os.path.join(real_dist, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "Not found"}},
        )
