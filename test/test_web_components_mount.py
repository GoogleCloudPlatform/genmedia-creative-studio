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

"""Regression tests for /__web-components-module__ routing (#1874).

Mounting ``StaticFiles(directory=".")`` at ``/__web-components-module__`` ahead
of the Mesop WSGI mount bypassed Mesop's ``serve_web_components`` handler:

1. Web component ``.js`` modules were served without ``Cache-Control: no-cache``
   or Mesop's security headers.
2. Any file under the working directory (e.g. ``main.py``, ``config/default.py``)
   was served with HTTP 200 because ``StaticFiles`` applies no extension allowlist,
   whereas Mesop restricts ``/__web-components-module__`` to ``.js`` and ``.css``.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("PROJECT_ID", "test-project")
os.environ.setdefault("LOCATION", "us-central1")
os.environ.setdefault("VEO_PROJECT_ID", "test-project")
os.environ.setdefault("VEO_LOCATION", "us-central1")

for _mod in ("parselmouth", "parselmouth.praat"):
    if _mod not in sys.modules:
        try:  # pragma: no cover
            __import__(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient configured against main.app."""
    return TestClient(main.app, raise_server_exceptions=False)


def test_web_component_js_served_by_mesop_with_cache_control(
    client: TestClient,
) -> None:
    """Legitimate .js web component modules are served by Mesop with Cache-Control."""
    resp = client.get(
        "/__web-components-module__/components/scroll_sentinel/scroll_sentinel.js",
    )

    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("content-type", "")
    assert "no-cache" in resp.headers.get("cache-control", "")


@pytest.mark.parametrize(
    "disallowed_path",
    [
        "/__web-components-module__/main.py",
        "/__web-components-module__/config/default.py",
        "/__web-components-module__/pyproject.toml",
    ],
)
def test_non_js_css_files_in_app_root_are_not_served(
    client: TestClient,
    disallowed_path: str,
) -> None:
    """Non-.js/.css files in the application root must not be served over HTTP."""
    resp = client.get(disallowed_path)

    assert resp.status_code != 200
