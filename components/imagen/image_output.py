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

from common.utils import create_display_url
from components.edit_button.edit_button import edit_button
from components.imagen.generation_controls import on_click_retry_critique
from components.omni_button.omni_button import omni_button
from components.styles import _BOX_STYLE
from components.svg_icon.svg_icon import svg_icon
from components.veo_button.veo_button import veo_button
from state.imagen_state import PageState


@me.component
def image_output():
    """Image output display"""
    state = me.state(PageState)
    print(f"Rendering image_output, commentary: {state.image_commentary}")
    with me.box(style=_BOX_STYLE):
        # me.text("Output", style=me.Style(font_weight=500))
        me.box(style=me.Style(height=10))

        if state.is_loading:
            with me.box(
                style=me.Style(
                    display="flex",
                    justify_content="center",
                    align_items="center",
                    flex_direction="column",
                    min_height="200px",
                ),
            ):
                me.progress_spinner()
                me.text(
                    "Generating, please wait...",
                    style=me.Style(margin=me.Margin(top=10)),
                )

        elif state.image_gcs_uris:
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="column",
                    align_items="center",
                ),
            ):
                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_wrap="wrap",
                        gap="15px",
                        justify_content="center",
                    ),
                ):
                    for img_uri in state.image_gcs_uris:
                        if img_uri:
                            with me.box(
                                style=me.Style(
                                    display="flex", flex_direction="column", gap=8,
                                ),
                            ):
                                me.image(
                                    src=create_display_url(img_uri),
                                    style=me.Style(
                                        width="300px",
                                        height="300px",
                                        object_fit="contain",
                                        border_radius="12px",
                                        box_shadow="0 2px 4px rgba(0,0,0,0.1)",
                                    ),
                                )
                                with me.box(
                                    style=me.Style(
                                        display="flex",
                                        flex_direction="row",
                                        gap=8,
                                        justify_content="center",
                                    ),
                                ):
                                    edit_button(gcs_uri=img_uri)
                                    omni_button(gcs_uri=img_uri)
                                    veo_button(gcs_uri=img_uri)
                if state.imagen_watermark:
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="row",
                            align_items="center",
                            margin=me.Margin(top=15),
                        ),
                    ):
                        svg_icon(icon_name="digitalWatermarkIcon")
                        me.text(
                            text="Images watermarked by SynthID (Google)",
                            style=me.Style(
                                padding=me.Padding.all(10),
                                font_size="0.9em",
                                color="#5f6368",
                            ),
                        )
                if state.image_commentary:
                    with me.box(style=_BOX_STYLE):
                        with me.box(
                            style=me.Style(
                                display="flex",
                                align_items="center",
                                gap="8px",
                                margin=me.Margin(bottom=10),
                            ),
                        ):
                            me.icon("assistant")
                            me.text(
                                "Magazine Editor's Critique",
                                style=me.Style(font_weight=500),
                            )
                        me.markdown(
                            text=state.image_commentary,
                            style=me.Style(
                                padding=me.Padding(left=15, right=15, bottom=15),
                            ),
                        )
                        if (
                            "unavailable" in state.image_commentary
                            or "failed" in state.image_commentary
                        ):
                            me.button(
                                "Retry Critique",
                                on_click=on_click_retry_critique,
                                type="stroked",
                                style=me.Style(margin=me.Margin(left=15, bottom=15)),
                            )
        else:
            me.text(
                text="Generate some images to see them here!",
                style=me.Style(
                    display="flex",
                    justify_content="center",
                    padding=me.Padding.all(20),
                    color=me.theme_var("outline"),
                    min_height="100px",
                    align_items="center",
                ),
            )
