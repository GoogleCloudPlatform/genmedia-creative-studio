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

from state.imagen_state import PageState


@me.component
def modifier_controls():
    """Image style modifier controls"""
    state = me.state(PageState)
    with me.box(style=_BOX_STYLE):
        with me.box(
            style=me.Style(
                display="flex",
                justify_content="space-between",  # This might crowd if many items
                flex_wrap="wrap",  # Allow wrapping for smaller screens
                gap="8px",  # Use gap for spacing
                width="100%",
            )
        ):
            # Default Modifiers
            me.select(
                label="Aspect Ratio",
                options=[
                    me.SelectOption(label="1:1", value="1:1"),
                    me.SelectOption(label="3:4", value="3:4"),
                    me.SelectOption(label="4:3", value="4:3"),
                    me.SelectOption(label="16:9", value="16:9"),
                    me.SelectOption(label="9:16", value="9:16"),
                ],
                key="image_aspect_ratio",  # Match PageState attribute directly
                on_selection_change=on_selection_change_modifier,
                style=me.Style(min_width="160px", flex_grow=1),
                value=state.image_aspect_ratio,
            )
            me.select(
                label="Content Type",
                options=[
                    me.SelectOption(label="None", value="None"),
                    me.SelectOption(label="Photo", value="Photo"),
                    me.SelectOption(label="Art", value="Art"),
                ],
                key="image_content_type",  # Match PageState attribute
                on_selection_change=on_selection_change_modifier,
                style=me.Style(min_width="160px", flex_grow=1),
                value=state.image_content_type,
            )

            color_and_tone_options = [
                me.SelectOption(label=c, value=c)
                for c in [
                    "None",
                    "Black and white",
                    "Cool tone",
                    "Golden",
                    "Monochromatic",
                    "Muted color",
                    "Pastel color",
                    "Toned image",
                ]
            ]
            me.select(
                label="Color & Tone",
                options=color_and_tone_options,
                key="image_color_tone",  # Match PageState attribute
                on_selection_change=on_selection_change_modifier,
                style=me.Style(min_width="160px", flex_grow=1),
                value=state.image_color_tone,
            )

            lighting_options = [
                me.SelectOption(label=l, value=l)
                for l in [
                    "None",
                    "Backlighting",
                    "Dramatic light",
                    "Golden hour",
                    "Long-time exposure",
                    "Low lighting",
                    "Multiexposure",
                    "Studio light",
                    "Surreal lighting",
                ]
            ]
            me.select(
                label="Lighting",
                options=lighting_options,
                key="image_lighting",  # Match PageState attribute
                on_selection_change=on_selection_change_modifier,
                style=me.Style(min_width="160px", flex_grow=1),
                value=state.image_lighting,
            )

            composition_options = [
                me.SelectOption(label=c, value=c)
                for c in [
                    "None",
                    "Closeup",
                    "Knolling",
                    "Landscape photography",
                    "Photographed through window",
                    "Shallow depth of field",
                    "Shot from above",
                    "Shot from below",
                    "Surface detail",
                    "Wide angle",
                ]
            ]
            me.select(
                label="Composition",
                options=composition_options,
                key="image_composition",  # Match PageState attribute
                on_selection_change=on_selection_change_modifier,
                style=me.Style(min_width="160px", flex_grow=1),
                value=state.image_composition,
            )


from common.analytics import log_ui_click
from state.state import AppState


def on_selection_change_modifier(e: me.SelectSelectionChangeEvent):
    """Handles selection change for image style modifiers."""
    app_state = me.state(AppState)
    log_ui_click(
        element_id=f"imagen_modifier_{e.key}",
        page_name=app_state.current_page,
        session_id=app_state.session_id,
        extras={"value": e.value},
    )
    state = me.state(PageState)
    print(f"Modifier changed: {e.key} = {e.value}")
    if hasattr(state, e.key):  # Ensure the key corresponds to a state attribute
        setattr(state, e.key, e.value)
    else:
        print(f"Warning: No state attribute found for key {e.key}")


_BOX_STYLE = me.Style(
    background=me.theme_var("surface"),  # Use theme variable for background
    border_radius=12,
    box_shadow=me.theme_var("shadow_elevation_2"),  # Use theme variable for shadow
    #padding=me.Padding.all(16),  # Simpler padding
    display="flex",
    flex_direction="column",
    #margin=me.Margin(bottom=28),
)
