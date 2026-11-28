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

import mesop as me

import models.shop_the_look_workflow as shop_the_look_workflow
from components.header import header
from components.page_scaffold import (
    page_frame,
    page_scaffold,
)
from components.shop_the_look.config_panel import config_panel
from components.shop_the_look.look_selection import look_selection
from components.shop_the_look.model_selection import model_selection
from components.shop_the_look.results_display import (
    on_click_clear_reference_image,
    results_display,
)
from components.tab_nav import Tab, tab_group
from models.shop_the_look_handlers import on_click_vto_look
from state.shop_the_look_state import PageState
from state.state import AppState


@me.page(
    path="/shop_the_look",
    title="Shop the Look",
)
def page():
    with page_scaffold(page_name="shop_the_look"): # pylint: disable=E1129:not-context-manager
        with page_frame():  # pylint: disable=E1129:not-context-manager
            header("Shop the Look", icon="apparel", current_status=me.state(PageState).current_status)
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="column",
                    gap=15,
                    width="100%",
                )
            ):
                build_tab_nav()


@me.component
def tab_config():
    state = me.state(PageState)
    state.models = shop_the_look_workflow.load_model_data()
    config_panel()


@me.component
def tab_stl():
    state = me.state(PageState)
    if not state.catalog:
        state.catalog = shop_the_look_workflow.load_look_data()
    if not state.models:
        state.models = shop_the_look_workflow.load_model_data()
        shop_the_look_workflow.load_article_data()
    if state.reference_image_gcs_model is None or not state.reference_image_gcs_model:
        model_selection()
    elif not state.look or state.look == 0:
        look_selection()
    else:
        results_display()


def on_look_button_click(e: me.ClickEvent):
    state = me.state(PageState)
    print(e)
    state.look = int(e.key)


def build_tab_nav():
    state = me.state(PageState)
    app_state = me.state(AppState)

    visible = (
        True
        if app_state.user_email in ["andrewturner@google.com", "rouzbeha@google.com"]
        else True
    )
    tabs = [
        Tab(label="Shop the Look", icon="apparel", content=tab_stl),
        Tab(
            label="Config",
            icon="settings",
            content=tab_config,
            tab_width="100px",
            visible=visible,
        ),
    ]
    for index, tab in enumerate(tabs):
        tab.selected = state.selected_tab_index == index
        tab.disabled = index in state.disabled_tab_indexes
    tab_group(tabs, on_tab_click)


def on_tab_click(e: me.ClickEvent):
    """Click handler that handles updating the tabs when clicked."""
    state = me.state(PageState)
    _, tab_index = e.key.split("-")
    tab_index = int(tab_index)

    if tab_index == state.selected_tab_index:
        return
    if tab_index in state.disabled_tab_indexes:
        return

    next(on_click_clear_reference_image())
    state.selected_tab_index = int(tab_index)



