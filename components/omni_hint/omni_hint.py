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

"""A small banner that points Veo page users to Gemini Omni."""

from collections.abc import Generator

import mesop as me

from common.analytics import log_ui_click
from components.omni_button.omni_button import OMNI_PAGE_PATH
from state.state import AppState

OMNI_HINT_TEXT = (
    "Gemini Omni is our newest video model: it adds editing, extension, "
    "upscaling and longer clips on top of text and image prompts."
)


def on_open_omni_click(e: me.ClickEvent) -> Generator[None]:  # noqa: ARG001
    """Navigates from the Veo page to the Gemini Omni page."""
    app_state = me.state(AppState)
    log_ui_click(
        element_id="omni_hint",
        page_name=app_state.current_page,
        session_id=app_state.session_id,
    )
    me.navigate(url=OMNI_PAGE_PATH)
    yield


@me.component
def omni_hint() -> None:
    """Render a one-line banner with a button that opens Gemini Omni."""
    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="row",
            align_items="center",
            gap=12,
            padding=me.Padding.symmetric(vertical=8, horizontal=16),
            margin=me.Margin(top=8, bottom=24),
            border_radius=12,
            background=me.theme_var("surface-container-low"),
        ),
    ):
        me.icon("spark")
        me.text(
            OMNI_HINT_TEXT,
            style=me.Style(
                flex_grow=1,
                font_size=13,
                color=me.theme_var("on-surface-variant"),
            ),
        )
        me.button("Try Gemini Omni", on_click=on_open_omni_click, type="stroked")
