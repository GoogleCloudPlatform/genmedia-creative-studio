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

"""Tests for Omni-first emphasis on Veo/Omni surfaces."""

import importlib
import inspect
import os
import re
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.mark.parametrize(
    "module_name",
    [
        "pages.banana_studio",
        "pages.gemini_image_generation",
        "pages.vto",
        "components.imagen.image_output",
        "components.interior_design.design_studio",
        "components.library.image_details",
    ],
)
def test_omni_button_is_rendered_before_veo_button(module_name: str) -> None:
    """Omni is listed first wherever both buttons are offered."""
    source = inspect.getsource(importlib.import_module(module_name))
    # Indented calls only: import lines start at column 0.
    omni_call = re.search(r"^\s+omni_button\(", source, re.MULTILINE)
    veo_call = re.search(r"^\s+veo_button\(", source, re.MULTILINE)
    assert omni_call
    assert veo_call
    assert omni_call.start() < veo_call.start()


def test_veo_page_renders_omni_hint() -> None:
    """The Veo page shows the Omni hint right after its header."""
    from pages import veo

    source = inspect.getsource(veo.veo_content)
    assert source.index("header(") < source.index("omni_hint()")


@patch("components.omni_hint.omni_hint.log_ui_click")
@patch("components.omni_hint.omni_hint.me.navigate")
@patch("components.omni_hint.omni_hint.me.state")
def test_omni_hint_navigates_to_omni_page(
    _mock_state: MagicMock,
    mock_navigate: MagicMock,
    mock_log: MagicMock,
) -> None:
    """The hint's button opens the Gemini Omni page and logs the click."""
    from components.omni_hint.omni_hint import on_open_omni_click

    list(on_open_omni_click(MagicMock()))

    mock_navigate.assert_called_once_with(url="/gemini-omni")
    mock_log.assert_called_once()
