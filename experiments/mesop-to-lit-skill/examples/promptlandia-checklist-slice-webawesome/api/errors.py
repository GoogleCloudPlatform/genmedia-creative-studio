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

"""Uniform error envelope (target-architecture §3.5).

Every error the Lit client can hit becomes `{"error": {"code", "message"}}`:
  - FastAPI validation errors (422) are reshaped to the same envelope.
  - HTTPException preserves its status code.
  - Any other uncaught exception (e.g. an LLM/service failure) -> 500 envelope.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def _envelope(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    """Attach the exception handlers to the FastAPI app."""

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        # Reshape FastAPI's default 422 body into the uniform envelope.
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        msg = first.get("msg", "Invalid request")
        message = f"{loc}: {msg}" if loc else msg
        return JSONResponse(
            status_code=422,
            content=_envelope("validation_error", message),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("http_error", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):
        # Log the full detail server-side (stack trace + exception message) but
        # return a GENERIC message to the client: raw exception text can carry
        # prompt content, internal paths, or provider/config identifiers
        # (info disclosure). Design §3.5 only requires a uniform {code, message}.
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content=_envelope("internal_error", "Internal server error"),
        )
