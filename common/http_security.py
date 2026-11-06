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

"""HTTP-layer security helpers shared by the ASGI app (gmcs-0lo).

Pure, framework-light helpers so the behavior can be unit-tested without
booting the whole Mesop app:

- HSTS: emitted only for deployed (non-local) environments over a real host.
- Correlation IDs: one identifier per HTTP request for log traceability.
- Public error bodies: generic in deployed environments, detailed only in
  local development.
"""

import re
import traceback
import uuid
from contextvars import ContextVar

from common.identity import LOCAL_APP_ENVS

HSTS_HEADER = "Strict-Transport-Security"
HSTS_VALUE = "max-age=31536000; includeSubDomains"

# Browsers cache HSTS per host; sending it for localhost would force HTTPS on
# local HTTP testing for a year.
_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "[::1]"}

CORRELATION_ID_HEADER = "X-Correlation-ID"
GENERIC_ERROR_MESSAGE = "An unexpected error occurred"

# Accept only a conservative token for a client-supplied correlation id. The id
# is echoed in a response header and written to logs, so anything else (CR/LF,
# spaces, very long values) is discarded and replaced with a fresh UUID.
_CORRELATION_ID_RE = re.compile(r"[A-Za-z0-9._\-]{1,64}")

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


def should_send_hsts(app_env: str | None, hostname: str | None) -> bool:
    """Return True when the HSTS header should be added to a response."""
    if (app_env or "") in LOCAL_APP_ENVS:
        return False
    return (hostname or "").lower() not in _LOCAL_HOSTNAMES


def resolve_correlation_id(incoming: str | None) -> str:
    """Return the incoming correlation id if well-formed, else a new UUID4."""
    if incoming and _CORRELATION_ID_RE.fullmatch(incoming):
        return incoming
    return str(uuid.uuid4())


def get_correlation_id() -> str:
    """Return the correlation id of the request being handled ("-" if none)."""
    return correlation_id_var.get()


def public_error_body(
    exc: BaseException, app_env: str | None, correlation_id: str,
) -> dict[str, str]:
    """Build the JSON body for an unhandled server error.

    Deployed environments get a generic message plus the correlation id (so the
    user can quote it and an operator can find the log line). Local development
    additionally gets the exception text and stack trace.
    """
    body = {"error": GENERIC_ERROR_MESSAGE, "correlation_id": correlation_id}
    if (app_env or "") in LOCAL_APP_ENVS:
        body["detail"] = f"{type(exc).__name__}: {exc}"
        body["traceback"] = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__),
        )
    return body
