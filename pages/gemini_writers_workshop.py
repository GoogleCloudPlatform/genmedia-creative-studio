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
"""Gemini Writers Workshop - an experimental page for text generation."""

import json
import time
from dataclasses import field

import mesop as me

from common.analytics import track_click
from common.prompt_template_service import PromptTemplate, prompt_template_service
from common.storage import store_to_gcs
from common.utils import create_display_url
from components.copy_button.copy_button import copy_button
from components.dialog import dialog
from components.header import header
from components.library.events import LibrarySelectionChangeEvent
from components.library.library_chooser_button import library_chooser_button
from components.page_scaffold import page_frame, page_scaffold
from components.prompt_template_form_dialog.prompt_template_form_dialog import (
    prompt_template_form_dialog,
)
from components.svg_icon.svg_icon import svg_icon
from components.video_thumbnail.video_thumbnail import video_thumbnail
from config.default import Default as cfg
from models.gemini import generate_text
from state.state import AppState

MAX_MEDIA_ASSETS = 3


@me.stateclass
class PageState:
    """Gemini Writers Workshop Page State"""

    uploaded_media_gcs_uris: list[str] = field(default_factory=list)  # pylint: disable=E3701:invalid-field-call
    uploaded_media_display_urls: list[str] = field(default_factory=list)  # pylint: disable=E3701:invalid-field-call
    prompt: str = ""
    generated_text: str = ""
    is_generating: bool = False
    generation_complete: bool = False
    generation_time: float = 0.0
    show_snackbar: bool = False
    snackbar_message: str = ""
    previous_media_item_id: str | None = None
    prompt_templates_json: str = "[]"
    selected_model: str = ""

    info_dialog_open: bool = False
    show_error_dialog: bool = False
    error_message: str = ""
    show_save_template_dialog: bool = False


with open("config/about_content.json") as f:
    about_content = json.load(f)
    WRITERS_WORKSHOP_INFO = {
        "title": "Gemini Writers Workshop",
        "description": "A place to generate text content from prompts and optional media assets.\n\nUpload an image or video to get a Gemini description, or upload a PDF to extract or analyze information. Use this information to enhance your understanding and create new prompts.",
    }


def open_info_dialog(e: me.ClickEvent):
    """Open the info dialog."""
    state = me.state(PageState)
    state.info_dialog_open = True
    yield


def close_info_dialog(e: me.ClickEvent):
    """Close the info dialog."""
    state = me.state(PageState)
    state.info_dialog_open = False
    yield


def workshop_model_options() -> list[str]:
    """Return the models offered by the picker, preferred model first.

    The configured default is always included so it can be preselected even if
    an operator left it out of ``GEMINI_WRITERS_WORKSHOP_MODELS``.
    """
    models = list(cfg().GEMINI_WRITERS_WORKSHOP_MODELS)
    default = cfg().GEMINI_WRITERS_WORKSHOP_MODEL_ID
    if default and default not in models:
        models.insert(0, default)
    return models


def default_workshop_model() -> str:
    """Return the model preselected in the picker."""
    options = workshop_model_options()
    default = cfg().GEMINI_WRITERS_WORKSHOP_MODEL_ID
    return default if default in options else options[0]


def on_load(e: me.LoadEvent):
    state = me.state(PageState)
    # Also reset a stale selection (e.g. a model that is no longer offered).
    if state.selected_model not in workshop_model_options():
        state.selected_model = default_workshop_model()
    if state.prompt_templates_json == "[]":
        templates = prompt_template_service.load_templates(
            config_path="config/text_prompt_templates.json",
            template_type="text",
        )
        state.prompt_templates_json = json.dumps(
            [t.model_dump() for t in templates], default=str
        )
    yield


def on_model_selection_change(e: me.SelectSelectionChangeEvent):
    state = me.state(PageState)
    state.selected_model = e.value
    yield


def on_template_click(e: me.ClickEvent):
    """Handles clicks on prompt template buttons.
    If the user has already entered a prompt, it combines the user's prompt
    with the template's prompt and triggers generation.
    If the user's prompt is empty, it populates the prompt text area
    with the template's content.
    """
    state = me.state(PageState)

    template_prompt = e.key

    # Check if the user has entered their own prompt (and it's not just whitespace)

    if state.prompt and state.prompt.strip():
        # Combine the user's prompt and the template, then generate

        combined_prompt = f"{template_prompt}\n\n{state.prompt}"

        state.prompt = combined_prompt

        # Trigger generation

        yield from _generate_text_and_save(
            base_prompt=combined_prompt,
            input_gcs_uris=state.uploaded_media_gcs_uris,
        )

    else:
        # If there's no user prompt, just apply the template to the text area

        state.prompt = template_prompt

        yield


def on_open_save_dialog_click(e: me.ClickEvent):
    state = me.state(PageState)

    state.show_save_template_dialog = True

    yield


def on_close_save_dialog(e: me.ClickEvent):
    state = me.state(PageState)

    state.show_save_template_dialog = False

    yield


def on_save_template(label: str, key: str, category: str, prompt: str):
    state = me.state(PageState)

    app_state = me.state(AppState)

    new_template = PromptTemplate(
        key=key,
        label=label,
        prompt=prompt,  # Use prompt from dialog
        category=category,
        template_type="text",
        attribution=app_state.user_email,  # or user_id
    )

    try:
        prompt_template_service.add_template(new_template)

        # Reload templates

        templates = prompt_template_service.load_templates(
            config_path="config/text_prompt_templates.json",
            template_type="text",
        )

        state.prompt_templates_json = json.dumps(
            [t.model_dump() for t in templates], default=str
        )

        # Close dialog

        state.show_save_template_dialog = False

        yield from show_snackbar("Template saved successfully!")

    except Exception as e:
        print(f"Error saving template: {e}")

        state.error_message = f"Error saving template: {e}"

        state.show_error_dialog = True

    yield


CHIP_STYLE = me.Style(
    padding=me.Padding(top=4, right=12, bottom=4, left=12),
    border_radius=8,
    font_size=14,
    height=32,
)


@me.component
def _prompt_templates_ui():
    state = me.state(PageState)
    prompt_templates = json.loads(state.prompt_templates_json)

    # Group templates by category (case-insensitive)
    categories = {}
    for t in prompt_templates:
        category_key = t["category"].lower()
        if category_key not in categories:
            categories[category_key] = []
        categories[category_key].append(t)

    if not categories:
        return

    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="column",
            gap=8,
            margin=me.Margin(top=16),
        ),
    ):
        me.text("Prompt Templates", style=me.Style(font_weight="bold"))
        for category_key, templates in categories.items():
            if not templates:
                continue

            me.text(
                f"{category_key.capitalize()}",
                style=me.Style(
                    font_size=14,
                    margin=me.Margin(top=8),
                ),
            )
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="row",
                    align_items="center",
                    gap=8,
                    flex_wrap="wrap",
                ),
            ):
                for template in templates:
                    me.button(
                        template["label"],
                        on_click=on_template_click,
                        type="stroked",
                        key=template["prompt"],
                        style=CHIP_STYLE,
                    )


@me.page(
    path="/gemini-writers-workshop",
    title="Gemini Writers Workshop - GenMedia Creative Studio",
    on_load=on_load,
)
def page():
    """Define the Mesop page route for Gemini Writers Workshop."""
    with page_scaffold(page_name="gemini-writers-workshop"):  # pylint: disable=E1129:not-context-manager
        gemini_writers_workshop_page_content()


def gemini_writers_workshop_page_content():
    """Renders the main UI for the Gemini Writers Studio page."""
    state = me.state(PageState)
    # Use the new, unified dialog in 'create' mode
    prompt_template_form_dialog(
        # Pass the prompt text in the 'template' dict
        template={"prompt": state.prompt},
        mode="create",
        is_open=state.show_save_template_dialog,
        on_save=on_save_template,
        on_close=on_close_save_dialog,
        on_update=None,  # Not used on this page
    )

    if state.info_dialog_open:
        with dialog(is_open=state.info_dialog_open):  # pylint: disable=E1129:not-context-manager
            me.text(f"About {WRITERS_WORKSHOP_INFO['title']}", type="headline-6")
            me.markdown(WRITERS_WORKSHOP_INFO["description"])
            me.divider()
            me.button("Close", on_click=close_info_dialog, type="flat")

    with dialog(is_open=state.show_error_dialog):  # pylint: disable=E1129:not-context-manager
        me.text(
            "An Error Occurred",
            type="headline-6",
            style=me.Style(color=me.theme_var("error")),
        )
        me.text(state.error_message, style=me.Style(margin=me.Margin(top=16)))
        with me.box(
            style=me.Style(
                display="flex",
                justify_content="flex-end",
                margin=me.Margin(top=24),
            ),
        ):
            me.button("Close", on_click=on_close_error_dialog, type="flat")

    with page_frame():  # pylint: disable=E1129:not-context-manager
        header(
            "Gemini Writers Workshop",
            "spark",
            show_info_button=True,
            on_info_click=open_info_dialog,
        )
        with me.box(style=me.Style(display="flex", flex_direction="row", gap=16)):
            # Left column (controls)
            with me.box(
                style=me.Style(
                    width=400,
                    background=me.theme_var("surface-container-lowest"),
                    padding=me.Padding.all(16),
                    border_radius=12,
                ),
            ):
                me.text(
                    "Type a prompt and optionally add media assets",
                    style=me.Style(margin=me.Margin(bottom=16)),
                )
                me.textarea(
                    label="Prompt",
                    rows=5,
                    max_rows=20,
                    autosize=True,
                    on_blur=on_prompt_blur,
                    value=me.state(PageState).prompt,
                    style=me.Style(width="100%", margin=me.Margin(bottom=2)),
                    appearance="outline",
                )
                # Media upload
                _media_upload_slots()

                # Model choice: exactly the configured Workshop models.
                me.select(
                    label="Model",
                    options=[
                        me.SelectOption(
                            label=(
                                f"{model_id} (default)"
                                if model_id == default_workshop_model()
                                else model_id
                            ),
                            value=model_id,
                        )
                        for model_id in workshop_model_options()
                    ],
                    on_selection_change=on_model_selection_change,
                    value=state.selected_model or default_workshop_model(),
                    style=me.Style(width="100%"),
                    appearance="outline",
                )

                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="row",
                        align_items="center",
                        gap=16,
                        margin=me.Margin(top=16),
                    ),
                ):
                    _generate_text_button()
                    with me.content_button(on_click=on_clear_click, type="icon"):
                        me.icon("delete_sweep")
                    with me.tooltip(
                        message="Enter a prompt and click outside the text box to enable saving.",
                    ):
                        with me.content_button(
                            on_click=on_open_save_dialog_click,
                            type="icon",
                            disabled=not state.prompt,
                        ):
                            me.icon("save")

                if (
                    me.state(PageState).generation_complete
                    and me.state(PageState).generation_time > 0
                ):
                    me.text(
                        f"{me.state(PageState).generation_time:.2f} seconds",
                        style=me.Style(font_size=12),
                    )

                _prompt_templates_ui()

            # Right column (generated text)
            with me.box(
                style=me.Style(
                    flex_grow=1,
                    border_radius=12,
                    padding=me.Padding.all(16),
                    min_height=400,
                ),
            ):
                if me.state(PageState).generated_text:
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="row",
                            justify_content="space-between",
                            align_items="center",
                        ),
                    ):
                        me.text("Generated Text", type="headline-6")
                        copy_button(text_to_copy=me.state(PageState).generated_text)
                    me.markdown(
                        me.state(PageState).generated_text,
                        style=me.Style(margin=me.Margin(top=16)),
                    )
                else:
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="column",
                            align_items="center",
                            justify_content="center",
                            height="100%",
                        ),
                    ):
                        with me.box(
                            style=me.Style(
                                opacity=0.2,
                                width=128,
                                height=128,
                                color=me.theme_var("on-surface-variant"),
                            ),
                        ):
                            svg_icon(icon_name="spark")


@me.component
def _media_upload_slots():
    """The media upload UI with 3 slots."""
    state = me.state(PageState)
    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="row",
            gap=10,
            margin=me.Margin(bottom=16),
            justify_content="center",
        ),
    ):
        for i in range(MAX_MEDIA_ASSETS):
            if i < len(state.uploaded_media_display_urls):
                display_url = state.uploaded_media_display_urls[i]
                gcs_uri = state.uploaded_media_gcs_uris[i]

                with me.box(style=me.Style(position="relative", width=100, height=100)):
                    if any(
                        gcs_uri.lower().endswith(ext)
                        for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]
                    ):
                        me.image(
                            src=display_url,
                            style=me.Style(
                                width="100%",
                                height="100%",
                                border_radius=8,
                                object_fit="cover",
                            ),
                        )
                    elif any(
                        gcs_uri.lower().endswith(ext)
                        for ext in [".mp4", ".mov", ".avi", ".webm"]
                    ):
                        video_thumbnail(video_src=display_url)
                    elif gcs_uri.lower().endswith(".pdf"):
                        with me.box(
                            style=me.Style(
                                width=100,
                                height=100,
                                border=me.Border.all(me.BorderSide(style="dashed")),
                                display="flex",
                                align_items="center",
                                justify_content="center",
                            ),
                        ):
                            me.icon("article")
                    else:
                        with me.box(
                            style=me.Style(
                                width=100,
                                height=100,
                                border=me.Border.all(me.BorderSide(style="dashed")),
                                display="flex",
                                align_items="center",
                                justify_content="center",
                            ),
                        ):
                            me.icon("article")

                    with me.box(
                        on_click=on_remove_media,
                        key=str(i),
                        style=me.Style(
                            background="rgba(0, 0, 0, 0.5)",
                            color="white",
                            position="absolute",
                            top=4,
                            right=4,
                            border_radius="50%",
                            cursor="pointer",
                            display="flex",
                            align_items="center",
                            justify_content="center",
                            width=26,
                            height=26,
                        ),
                    ):
                        me.icon("close", style=me.Style(font_size=18))

            elif i == len(state.uploaded_media_gcs_uris):
                _uploader_placeholder(key_prefix=f"media_slot_{i}")
            else:
                _empty_placeholder()


@me.component
def _uploader_placeholder(key_prefix: str):
    """A placeholder box with uploader and library chooser buttons."""
    with me.box(
        style=me.Style(
            height=100,
            width=100,
            border=me.Border.all(
                me.BorderSide(
                    width=1,
                    style="dashed",
                    color=me.theme_var("outline"),
                ),
            ),
            border_radius=8,
            display="flex",
            flex_direction="column",
            align_items="center",
            justify_content="center",
            gap=8,
        ),
    ):
        me.uploader(
            label="Upload Media",
            on_upload=on_upload,
            accepted_file_types=[
                "image/jpeg",
                "image/png",
                "image/webp",
                "video/mp4",
                "application/pdf",
            ],
            key=f"{key_prefix}_uploader",
            multiple=True,
        )
        library_chooser_button(
            on_library_select=on_media_select,
            button_type="icon",
            key=f"{key_prefix}_library_chooser",
            media_type=["all"],
        )


@me.component
def _empty_placeholder():
    """An empty, non-interactive placeholder box."""
    me.box(
        style=me.Style(
            height=100,
            width=100,
            border=me.Border.all(
                me.BorderSide(width=1, style="dashed", color=me.theme_var("outline")),
            ),
            border_radius=8,
            opacity=0.5,
        ),
    )


@me.component
def _generate_text_button():
    """Renders the main generate button and its loading state."""
    state = me.state(PageState)
    if state.is_generating:
        with me.content_button(type="raised", disabled=True):
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="row",
                    align_items="center",
                    gap=8,
                ),
            ):
                me.progress_spinner(diameter=20, stroke_width=3)
                me.text("Generating Text...")
    else:
        me.button(
            "Generate Text",
            on_click=on_generate_text_click,
            type="raised",
        )


def on_media_select(e: LibrarySelectionChangeEvent):
    """Handles media selection from the library chooser."""
    state = me.state(PageState)
    gcs_uri = e.gcs_uri
    if len(state.uploaded_media_gcs_uris) < MAX_MEDIA_ASSETS:
        state.uploaded_media_gcs_uris.append(gcs_uri)
        state.uploaded_media_display_urls.append(create_display_url(gcs_uri))
    else:
        yield from show_snackbar(
            f"You can add a maximum of {MAX_MEDIA_ASSETS} media assets."
        )
    yield


# Other event handlers
def on_upload(e: me.UploadEvent):
    state = me.state(PageState)
    if len(state.uploaded_media_gcs_uris) < MAX_MEDIA_ASSETS:
        file = e.files[0]
        gcs_url = store_to_gcs(
            "gemini_writers_studio_references",
            file.name,
            file.mime_type,
            file.getvalue(),
        )
        state.uploaded_media_gcs_uris.append(gcs_url)
        state.uploaded_media_display_urls.append(create_display_url(gcs_url))
    else:
        show_snackbar(f"You can add a maximum of {MAX_MEDIA_ASSETS} media assets.")
    yield


def on_remove_media(e: me.ClickEvent):
    state = me.state(PageState)
    index_to_remove = int(e.key)
    if 0 <= index_to_remove < len(state.uploaded_media_gcs_uris):
        del state.uploaded_media_gcs_uris[index_to_remove]
        del state.uploaded_media_display_urls[index_to_remove]
    yield


def on_prompt_blur(e: me.InputEvent):
    me.state(PageState).prompt = e.value


@track_click(element_id="writers_workshop_clear_button")
def on_clear_click(e: me.ClickEvent):
    state = me.state(PageState)
    state.generated_text = ""
    state.prompt = ""
    state.uploaded_media_gcs_uris = []
    state.uploaded_media_display_urls = []
    state.generation_time = 0.0
    state.generation_complete = False
    state.previous_media_item_id = None
    yield


def show_snackbar(message: str):
    state = me.state(PageState)
    state.snackbar_message = message
    state.show_snackbar = True
    yield
    time.sleep(3)
    state.show_snackbar = False
    yield


@track_click(element_id="writers_workshop_generate_button")
def on_generate_text_click(e: me.ClickEvent):
    state = me.state(PageState)
    if not state.prompt:
        yield from show_snackbar("Please enter a prompt.")
        return
    yield from _generate_text_and_save(
        base_prompt=state.prompt,
        input_gcs_uris=state.uploaded_media_gcs_uris,
    )


def on_close_error_dialog(e: me.ClickEvent):
    state = me.state(PageState)
    state.show_error_dialog = False
    yield


def _generate_text_and_save(base_prompt: str, input_gcs_uris: list[str]):
    state = me.state(PageState)
    app_state = me.state(AppState)
    state.is_generating = True
    state.generation_complete = False
    yield

    model_id = state.selected_model or default_workshop_model()

    try:
        text_result, execution_time = generate_text(
            prompt=base_prompt,
            images=input_gcs_uris,
            model_name=model_id,
        )
        state.generation_time = execution_time
        state.generated_text = text_result
    except Exception as ex:
        print(f"ERROR: Failed to generate text. Details: {ex}")
        state.error_message = f"An error occurred: {ex}"
        state.show_error_dialog = True
    finally:
        state.is_generating = False
        state.generation_complete = True
        yield
