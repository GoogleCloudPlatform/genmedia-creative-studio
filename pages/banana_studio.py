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
"""Banana Studio - an experimental page."""

import json
import time
from dataclasses import dataclass, field

import mesop as me

from common.analytics import log_ui_click
from common.metadata import (
    MediaItem,
    add_media_item_to_firestore,
)
from common.prompt_template_service import prompt_template_service
from common.storage import store_to_gcs
from common.utils import create_display_url, https_url_to_gcs_uri
from components.banana_button.banana_button import banana_button
from components.banana_studio.description_accordion import description_accordion
from components.dialog import dialog
from components.gemini_image.events import (
    get_on_aspect_ratio_change,
    get_on_image_search_change,
    get_on_image_size_change,
    get_on_include_thoughts_change,
    get_on_model_select,
    get_on_num_images_change,
    get_on_prompt_blur,
    get_on_search_change,
    get_on_thinking_level_change,
    get_on_thumbnail_click,
)
from components.gemini_image.upload_ui import gemini_image_upload_ui
from components.header import header
from components.library.events import LibrarySelectionChangeEvent
from components.page_scaffold import page_frame, page_scaffold
from components.pill import pill
from components.snackbar import snackbar
from components.svg_icon.svg_icon import svg_icon
from components.veo_button.veo_button import veo_button
from config.gemini_image_models import get_gemini_image_model_config
from models.gemini import (
    describe_image,
    evaluate_image_with_questions,
    generate_critique_questions,
    generate_image_from_prompt_and_images,
    generate_transformation_prompts,
)
from models.upscale import get_image_resolution
from state.state import AppState

CHIP_STYLE = me.Style(
    padding=me.Padding(top=4, right=12, bottom=4, left=12),
    border_radius=8,
    font_size=14,
    height=32,
)


@me.component
def _generate_images_button():
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
                me.text("Generating Images...")
    else:
        me.button(
            "Generate Images",
            on_click=generate_images,
            type="raised",
        )


@dataclass
class Evaluation:
    score: str
    details: list[dict]


@me.stateclass
class PageState:
    """Gemini Image Generation Page State"""

    selected_model: str = "gemini-nano-banana-2.1"
    uploaded_image_gcs_uris: list[str] = field(default_factory=list)  # pylint: disable=invalid-field-call
    uploaded_image_display_urls: list[str] = field(default_factory=list)  # pylint: disable=invalid-field-call
    image_descriptions: list[str] = field(default_factory=list)  # pylint: disable=invalid-field-call
    prompt: str = ""
    generated_image_urls: list[str] = field(default_factory=list)  # pylint: disable=invalid-field-call
    generated_resolution: str = ""
    is_generating: bool = False
    generation_complete: bool = False
    generation_time: float = 0.0
    selected_image_url: str = ""
    show_snackbar: bool = False
    snackbar_message: str = ""
    previous_media_item_id: str | None = None  # For linking generation sequences
    aspect_ratio: str = "1:1"
    image_size: str = "1K"
    num_images_to_generate: int = 1
    suggested_transformations_json: str = "[]"
    is_suggesting_transformations: bool = False
    critique_questions: list[str] = field(default_factory=list)  # pylint: disable=invalid-field-call
    is_generating_questions: bool = False
    prompt_templates_json: str = "[]"

    use_search: bool = False
    use_image_search: bool = False
    include_thoughts: bool = False
    thinking_level: str = "HIGH"
    thoughts: str = ""
    grounding_info: str = ""

    evaluations_json: str = "{}"
    is_evaluating: bool = False
    description_queue: list[int] = field(default_factory=list)  # pylint: disable=invalid-field-call
    accordion_panels_json: str = "{}"

    info_dialog_open: bool = False
    initial_load_complete: bool = False


on_aspect_ratio_change = get_on_aspect_ratio_change(PageState)
on_image_size_change = get_on_image_size_change(PageState)
on_num_images_change = get_on_num_images_change(PageState)
on_search_change = get_on_search_change(PageState)
on_image_search_change = get_on_image_search_change(PageState)
on_include_thoughts_change = get_on_include_thoughts_change(PageState)
on_thinking_level_change = get_on_thinking_level_change(PageState)
on_model_select = get_on_model_select(PageState)
on_prompt_blur = get_on_prompt_blur(PageState)
on_thumbnail_click = get_on_thumbnail_click(PageState)

NUM_IMAGES_PROMPTS = {
    2: "Give me 2 options.",
    3: "Give me 3 options.",
    4: "Give me 4 options.",
}

with open("config/about_content.json") as f:
    about_content = json.load(f)
    NANO_BANANA_INFO = next(
        (
            s
            for s in about_content["sections"]
            if s.get("id") == "gemini_image_generation"
        ),
        None,
    )


def on_media_select(e: LibrarySelectionChangeEvent):
    """Handles the selection of an image from the library dialog.
    Adds a placeholder, and queues the description generation.
    """
    state = me.state(PageState)
    current_model_name = state.selected_model
    model_config = get_gemini_image_model_config(current_model_name)
    max_input_images = model_config.max_input_images if model_config else 3

    # Check if there's space for a new image
    if len(state.uploaded_image_gcs_uris) >= max_input_images:
        yield from show_snackbar(
            state,
            f"You can add a maximum of {max_input_images} images.",
        )
        return

    # Add image and placeholder
    state.uploaded_image_gcs_uris.append(e.gcs_uri)
    state.uploaded_image_display_urls.append(create_display_url(e.gcs_uri))
    state.image_descriptions.append("Generating description...")
    new_image_index = len(state.image_descriptions) - 1

    # Queue the description generation
    is_queue_empty = not state.description_queue
    state.description_queue.append(new_image_index)

    # Yield to update UI (show placeholder and hide dialog)
    yield

    # Start the queue processor if it wasn't already running
    if is_queue_empty:
        yield from process_description_queue()


def on_accordion_toggle(e: me.ExpansionPanelToggleEvent):
    """Implements accordion behavior where only one panel can be open at a time."""
    state = me.state(PageState)

    # If the panel is being closed, this will result in all panels being closed.
    if not e.opened:
        state.accordion_panels_json = "{}"
        return

    # If a panel is being opened, create a new state dict with only that panel open.
    # This implicitly closes all other panels.
    state.accordion_panels_json = json.dumps({e.key: True})


@me.component
def _critique_questions_button():
    state = me.state(PageState)
    with me.box(style=me.Style(margin=me.Margin(top=16))):
        if state.is_generating_questions:
            with me.content_button(type="stroked", disabled=True):
                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="row",
                        align_items="center",
                        gap=8,
                    ),
                ):
                    me.progress_spinner(diameter=20, stroke_width=3)
                    me.text("Generating Questions...")
        else:
            me.button(
                "Generate Critique Questions",
                on_click=on_generate_questions_click,
                type="stroked",
                disabled=not state.prompt,
            )


@me.component
def _actions_row():
    state = me.state(PageState)
    with me.box(
        style=me.Style(
            display="flex" if state.generated_image_urls else "none",
            flex_direction="column",
            gap=16,
            margin=me.Margin(top=16),
        ),
    ):
        me.text("Actions", type="headline-5")
        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="row",
                align_items="center",
                gap=16,
            ),
        ):
            me.image(
                src=state.selected_image_url,
                style=me.Style(
                    width=100,
                    height=100,
                    border_radius=8,
                    object_fit="cover",
                ),
            )
            me.button(
                "Continue",
                on_click=on_continue_click,
                type="stroked",
            )
            veo_button(gcs_uri=https_url_to_gcs_uri(state.selected_image_url))


@me.component
def _prompt_templates_ui():
    state = me.state(PageState)
    is_visible = bool(state.generated_image_urls or state.uploaded_image_gcs_uris)

    # Group templates by category
    categories = {}
    if is_visible:
        for t in json.loads(state.prompt_templates_json):
            if t["category"] not in categories:
                categories[t["category"]] = []
            categories[t["category"]].append(t)

    with me.box(
        style=me.Style(
            display="flex" if is_visible and categories else "none",
            flex_direction="column",
            gap=8,
            margin=me.Margin(top=16),
        ),
    ):
        for category_name, templates in categories.items():
            if not templates:
                continue

            me.text(
                f"{category_name.capitalize()} Actions",
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
                        on_click=on_image_action_click,
                        type="stroked",
                        key=template["key"],
                        style=CHIP_STYLE,
                    )


@me.component
def _suggest_transformations_ui():
    state = me.state(PageState)
    # Suggest transformations button
    if (
        state.generation_complete
        and not json.loads(state.suggested_transformations_json)
        and state.generated_image_urls
    ):
        with me.box(style=me.Style(margin=me.Margin(top=16))):
            if state.is_suggesting_transformations:
                with me.content_button(disabled=True, style=CHIP_STYLE):
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="row",
                            align_items="center",
                            gap=8,
                        ),
                    ):
                        me.progress_spinner(diameter=20, stroke_width=3)
                        me.text("Suggesting...")
            else:
                me.button(
                    "Suggest Transformations",
                    on_click=on_suggest_transformations_click,
                    style=CHIP_STYLE,
                )

    # Suggested transformations
    if json.loads(state.suggested_transformations_json):
        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="row",
                gap=16,
                margin=me.Margin(top=16),
            ),
        ):
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="column",
                    align_items="flex-start",
                    gap=8,
                ),
            ):
                for transformation in json.loads(state.suggested_transformations_json):
                    with me.content_button(
                        on_click=on_transformation_click,
                        key=json.dumps(transformation),
                        type="stroked",
                        style=CHIP_STYLE,
                    ):
                        with me.box(
                            style=me.Style(
                                display="flex",
                                flex_direction="row",
                                align_items="center",
                                gap=8,
                            ),
                        ):
                            svg_icon(icon_name="image_edit_auto")
                            me.text(transformation["title"])


def gemini_image_gen_page_content():
    """Renders the main UI for the Gemini Image Generation page."""
    state = me.state(PageState)

    current_model_name = state.selected_model
    model_config = get_gemini_image_model_config(current_model_name)

    if state.info_dialog_open:
        with dialog(is_open=state.info_dialog_open):  # pylint: disable=not-context-manager
            me.text(f"About {NANO_BANANA_INFO['title']}", type="headline-6")
            me.markdown(NANO_BANANA_INFO["description"])
            me.divider()
            me.text("Current Settings", type="headline-6")
            me.text(f"Model: {model_config.model_name}")
            with me.box(style=me.Style(margin=me.Margin(top=16))):
                me.button("Close", on_click=close_info_dialog, type="flat")

    with page_frame():  # pylint: disable=E1129:not-context-manager
        header(
            "Gemini Image Generation",
            "banana",
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
                    "Type a prompt or add images and a prompt",
                    style=me.Style(
                        margin=me.Margin(bottom=16),
                    ),
                )
                from config.gemini_image_models import GEMINI_IMAGE_MODELS

                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="row",
                        gap=16,
                        margin=me.Margin(bottom=16),
                        justify_content="center",
                    ),
                ):
                    for model in GEMINI_IMAGE_MODELS:
                        is_selected = state.selected_model == model.model_name
                        banana_button(
                            selected=is_selected,
                            badge=model.button_label,
                            label=model.display_name,
                            model_name=model.model_name,
                            on_click=on_model_select,
                        )

                me.textarea(
                    label="Prompt",
                    rows=3,
                    max_rows=14,
                    autosize=True,
                    on_blur=on_prompt_blur,
                    value=state.prompt,
                    style=me.Style(width="100%", margin=me.Margin(bottom=2)),
                )
                gemini_image_upload_ui(
                    state=state,
                    model_config=model_config,
                    on_upload=on_upload,
                    on_media_select=on_media_select,
                    on_remove_image=on_remove_image,
                )

                # Display descriptions and questions
                if state.image_descriptions or state.critique_questions:
                    with me.box(style=me.Style(margin=me.Margin(top=16))):
                        description_accordion(
                            image_descriptions=state.image_descriptions,
                            critique_questions=state.critique_questions,
                            expanded_panels=json.loads(state.accordion_panels_json),
                            on_toggle=on_accordion_toggle,
                        )

                me.box(style=me.Style(height=8))

                with me.box(
                    style=me.Style(display="flex", flex_direction="row", gap=16),
                ):
                    me.select(
                        label="Aspect Ratio",
                        options=[
                            me.SelectOption(label="1:1", value="1:1"),
                            me.SelectOption(label="3:2", value="3:2"),
                            me.SelectOption(label="2:3", value="2:3"),
                            me.SelectOption(label="3:4", value="3:4"),
                            me.SelectOption(label="4:3", value="4:3"),
                            me.SelectOption(label="4:5", value="4:5"),
                            me.SelectOption(label="9:16", value="9:16"),
                            me.SelectOption(label="16:9", value="16:9"),
                            me.SelectOption(label="21:9", value="21:9"),
                        ],
                        on_selection_change=on_aspect_ratio_change,
                        value=str(state.aspect_ratio),
                        style=me.Style(flex_grow=1),
                    )

                    if model_config and model_config.supported_image_sizes:
                        me.select(
                            label="Image Size",
                            options=[
                                me.SelectOption(label=size, value=size)
                                for size in model_config.supported_image_sizes
                            ],
                            on_selection_change=on_image_size_change,
                            value=str(state.image_size),
                            style=me.Style(flex_grow=1, width="65%"),
                        )

                me.box(style=me.Style(height=16))

                # Generate images button
                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="row",
                        align_items="center",
                        gap=16,
                    ),
                ):
                    _generate_images_button()

                    with me.content_button(on_click=on_clear_click, type="icon"):
                        me.icon("delete_sweep")

                # Generation time duration

                if state.generation_complete and state.generation_time > 0:
                    me.text(
                        f"{state.generation_time:.2f} seconds",
                        style=me.Style(font_size=12),
                    )

                # --- STABLE COMPONENT SECTION ---

                # These components are now always rendered. Their internal logic

                # handles whether they are visible or not.

                _critique_questions_button()

                _actions_row()

                _prompt_templates_ui()

                _suggest_transformations_ui()  # New component for suggestions

            # Right column (generated images)

            with me.box(
                style=me.Style(
                    flex_grow=1,
                    display="flex",
                    flex_direction="column",
                    align_items="center",
                    justify_content="center",
                    border_radius=12,
                    padding=me.Padding.all(16),
                    min_height=400,
                ),
            ):
                if state.generation_complete and not state.generated_image_urls:
                    me.text("No images returned.")

                elif state.generated_image_urls:
                    # This box is to override the parent's centering styles

                    with me.box(
                        style=me.Style(
                            width="100%",
                            height="100%",
                            display="flex",
                            flex_direction="column",
                        ),
                    ):
                        if len(state.generated_image_urls) == 1:
                            # Display single, maximized image

                            image_url = state.generated_image_urls[0]

                            me.image(
                                src=image_url,
                                style=me.Style(
                                    width="100%",
                                    max_height="85vh",
                                    object_fit="contain",
                                    border_radius=8,
                                ),
                            )

                            if state.generated_resolution:
                                with me.box(style=me.Style(margin=me.Margin(top=8))):
                                    pill(
                                        label=f"Resolution: {state.generated_resolution}",
                                        pill_type="resolution",
                                    )

                            # Evaluation display

                            with me.box(
                                style=me.Style(width="100%", margin=me.Margin(top=16)),
                            ):
                                if state.is_evaluating:
                                    with me.box(
                                        style=me.Style(
                                            display="flex",
                                            align_items="center",
                                            gap=8,
                                        ),
                                    ):
                                        me.progress_spinner(diameter=20)

                                        me.text("Evaluating generation...")

                                elif image_url in json.loads(state.evaluations_json):
                                    evaluation = json.loads(state.evaluations_json)[
                                        image_url
                                    ]

                                    score = (
                                        evaluation["score"]
                                        if isinstance(evaluation, dict)
                                        else evaluation.score
                                    )

                                    details = (
                                        evaluation["details"]
                                        if isinstance(evaluation, dict)
                                        else evaluation.details
                                    )

                                    with me.expansion_panel(
                                        title=f"Critique Score: {score}",
                                        icon="rule",
                                    ):
                                        for item in details:
                                            with me.box(
                                                style=me.Style(
                                                    display="flex",
                                                    flex_direction="row",
                                                    align_items="center",
                                                    gap=8,
                                                    margin=me.Margin(bottom=8),
                                                ),
                                            ):
                                                if item["answer"]:
                                                    me.icon(
                                                        "check_circle",
                                                        style=me.Style(
                                                            color=me.theme_var(
                                                                "success",
                                                            ),
                                                        ),
                                                    )

                                                else:
                                                    me.icon(
                                                        "cancel",
                                                        style=me.Style(
                                                            color=me.theme_var("error"),
                                                        ),
                                                    )

                                                me.text(item["question"])

                        else:
                            # Display multiple images in a gallery view

                            with me.box(
                                style=me.Style(
                                    display="flex",
                                    flex_direction="column",
                                    gap=16,
                                ),
                            ):
                                # Main image

                                me.image(
                                    src=state.selected_image_url,
                                    style=me.Style(
                                        width="100%",
                                        max_height="75vh",
                                        object_fit="contain",
                                        border_radius=8,
                                    ),
                                )

                                if state.generated_resolution:
                                    with me.box(
                                        style=me.Style(margin=me.Margin(top=8)),
                                    ):
                                        pill(
                                            label=f"Resolution: {state.generated_resolution}",
                                            pill_type="resolution",
                                        )

                                # Evaluation display
                                with me.box(
                                    style=me.Style(
                                        width="100%",
                                        margin=me.Margin(top=16),
                                    ),
                                ):
                                    if state.is_evaluating:
                                        with me.box(
                                            style=me.Style(
                                                display="flex",
                                                align_items="center",
                                                gap=8,
                                            ),
                                        ):
                                            me.progress_spinner(diameter=20)

                                            me.text("Evaluating generation...")

                                    elif state.selected_image_url in json.loads(
                                        state.evaluations_json,
                                    ):
                                        evaluation = json.loads(state.evaluations_json)[
                                            state.selected_image_url
                                        ]

                                        score = (
                                            evaluation["score"]
                                            if isinstance(evaluation, dict)
                                            else evaluation.score
                                        )

                                        details = (
                                            evaluation["details"]
                                            if isinstance(evaluation, dict)
                                            else evaluation.details
                                        )

                                        with me.expansion_panel(
                                            title=f"Critique Score: {score}",
                                            icon="rule",
                                        ):
                                            for item in details:
                                                with me.box(
                                                    style=me.Style(
                                                        display="flex",
                                                        flex_direction="row",
                                                        align_items="center",
                                                        gap=8,
                                                        margin=me.Margin(bottom=8),
                                                    ),
                                                ):
                                                    if item["answer"]:
                                                        me.icon(
                                                            "check_circle",
                                                            style=me.Style(
                                                                color=me.theme_var(
                                                                    "success",
                                                                ),
                                                            ),
                                                        )

                                                    else:
                                                        me.icon(
                                                            "cancel",
                                                            style=me.Style(
                                                                color=me.theme_var(
                                                                    "error",
                                                                ),
                                                            ),
                                                        )

                                                    me.text(item["question"])

                                # Thumbnail strip

                                with me.box(
                                    style=me.Style(
                                        display="flex",
                                        flex_direction="row",
                                        gap=16,
                                        justify_content="center",
                                    ),
                                ):
                                    for url in state.generated_image_urls:
                                        is_selected = url == state.selected_image_url

                                        with me.box(
                                            key=url,
                                            on_click=on_thumbnail_click,
                                            style=me.Style(
                                                padding=me.Padding.all(4),
                                                border=me.Border.all(
                                                    me.BorderSide(
                                                        width=4,
                                                        style="solid",
                                                        color=(
                                                            me.theme_var("secondary")
                                                            if is_selected
                                                            else "transparent"
                                                        ),
                                                    ),
                                                ),
                                                border_radius=12,
                                                cursor="pointer",
                                            ),
                                        ):
                                            me.image(
                                                src=url,
                                                style=me.Style(
                                                    width=100,
                                                    height=100,
                                                    object_fit="cover",
                                                    border_radius=6,
                                                ),
                                            )

                else:
                    # Placeholder

                    with me.box(
                        style=me.Style(
                            opacity=0.2,
                            width=128,
                            height=128,
                            color=me.theme_var("on-surface-variant"),
                        ),
                    ):
                        svg_icon(icon_name="banana")

        snackbar(is_visible=state.show_snackbar, label=state.snackbar_message)


def on_upload(e: me.UploadEvent):
    """Handles file uploads, stores them in GCS, updates the UI with placeholders,
    and then generates descriptions asynchronously.
    """
    state = me.state(PageState)
    current_model_name = state.selected_model
    model_config = get_gemini_image_model_config(current_model_name)
    max_input_images = model_config.max_input_images if model_config else 3

    # Determine how many new images can be uploaded
    upload_slots_available = max_input_images - len(state.uploaded_image_gcs_uris)
    files_to_upload = e.files[:upload_slots_available]

    if not files_to_upload:
        yield from show_snackbar(
            state,
            f"You can upload a maximum of {max_input_images} images.",
        )
        return

    if len(e.files) > len(files_to_upload):
        yield from show_snackbar(
            state,
            f"You can upload a maximum of {max_input_images} images. Some files were not uploaded.",
        )

    # --- Step 1: Upload files and add placeholders ---
    new_upload_indices = []
    for file in files_to_upload:
        gcs_url = store_to_gcs(
            "gemini_image_gen_references",
            file.name,
            file.mime_type,
            file.getvalue(),
        )
        state.uploaded_image_gcs_uris.append(gcs_url)
        state.image_descriptions.append("Generating description...")
        state.uploaded_image_display_urls.append(create_display_url(gcs_url))
        new_upload_indices.append(len(state.uploaded_image_gcs_uris) - 1)

    # --- Step 2: Yield immediately to update UI with placeholders ---
    yield

    # --- Step 3: Generate descriptions for the new images ---
    for index in new_upload_indices:
        gcs_url = state.uploaded_image_gcs_uris[index]
        try:
            description = describe_image(gcs_url)
            state.image_descriptions[index] = description
        except Exception as ex:
            print(f"ERROR: Failed to describe image {gcs_url}. Details: {ex}")
            state.image_descriptions[index] = "Failed to generate description."

        # Yield after each description is generated to update the UI incrementally
        yield

    # --- Step 4: Final state update to fix rendering bug ---
    state.is_generating = False
    yield


def process_description_queue():
    """Processes one item from the description queue asynchronously.
    This is a generator function that will be called after the initial UI update.
    """
    # This initial yield is crucial. It forces the event handler to return
    # control to the browser, allowing the dialog to close *before* the
    # potentially slow network request in this function begins.
    yield

    state = me.state(PageState)
    if not state.description_queue:
        return  # Nothing to do

    # Process one item from the queue
    index_to_process = state.description_queue.pop(0)

    # Ensure the index is still valid (e.g., user didn't delete the image)
    if index_to_process >= len(state.uploaded_image_gcs_uris):
        # If more items are in the queue, continue processing them
        if state.description_queue:
            yield from process_description_queue()
        return

    gcs_uri = state.uploaded_image_gcs_uris[index_to_process]

    try:
        description = describe_image(gcs_uri)
        state.image_descriptions[index_to_process] = description
    except Exception as ex:
        print(f"ERROR: Failed to describe image {gcs_uri}. Details: {ex}")
        state.image_descriptions[index_to_process] = "Failed to generate description."

    # Yield to update the UI with the new description
    yield

    # If there are more items, continue processing
    if state.description_queue:
        yield from process_description_queue()


def on_remove_image(e: me.ClickEvent):
    """Removes an image and its description from the state."""
    state = me.state(PageState)
    index_to_remove = int(e.key)
    if 0 <= index_to_remove < len(state.uploaded_image_gcs_uris):
        del state.uploaded_image_gcs_uris[index_to_remove]
        del state.uploaded_image_display_urls[index_to_remove]
        if index_to_remove < len(state.image_descriptions):
            del state.image_descriptions[index_to_remove]

    yield


def on_prompt_blur(e: me.InputEvent):
    """Updates the prompt in the page state when the input field loses focus."""
    me.state(PageState).prompt = e.value


def on_aspect_ratio_change(e: me.SelectSelectionChangeEvent):
    """Changes the aspect ratio on page state."""
    me.state(PageState).aspect_ratio = e.value


def on_image_size_change(e: me.SelectSelectionChangeEvent):
    """Changes the image size on page state."""
    me.state(PageState).image_size = e.value


def on_num_images_change(e: me.SelectSelectionChangeEvent):
    """Updates the number of images to generate in the page state."""
    me.state(PageState).num_images_to_generate = int(e.value)


def on_thumbnail_click(e: me.ClickEvent):
    """Sets the clicked thumbnail as the main selected image."""
    state = me.state(PageState)
    state.selected_image_url = e.key
    yield


def on_clear_click(e: me.ClickEvent):
    """Resets the entire page state to its initial values, clearing all inputs and outputs."""
    state = me.state(PageState)
    state.generated_image_urls = []
    state.generated_resolution = ""
    state.prompt = ""
    state.uploaded_image_gcs_uris = []
    state.uploaded_image_display_urls = []
    state.image_descriptions = []
    state.selected_image_url = ""
    state.generation_time = 0.0
    state.generation_complete = False
    state.previous_media_item_id = None  # Reset the chain
    state.num_images_to_generate = 1
    state.suggested_transformations_json = "[]"
    state.critique_questions = []
    state.evaluations_json = "{}"

    yield


def on_generate_questions_click(e: me.ClickEvent):
    """Generates critique questions based on the prompt and image descriptions."""
    state = me.state(PageState)
    state.is_generating_questions = True
    state.critique_questions = []
    yield

    try:
        questions = generate_critique_questions(
            prompt=state.prompt,
            image_descriptions=state.image_descriptions,
        )
        state.critique_questions = questions
    except Exception as ex:
        print(f"ERROR: Failed to generate critique questions. Details: {ex}")
        yield from show_snackbar(state, f"An error occurred: {ex}")
    finally:
        state.is_generating_questions = False
        yield


def on_transformation_click(e: me.ClickEvent):
    """Handles clicks on suggested transformation buttons."""
    state = me.state(PageState)
    app_state = me.state(AppState)

    if not state.selected_image_url:
        yield from show_snackbar(state, "Please select an image to transform.")
        return

    try:
        transformation = json.loads(e.key)
        title = transformation["title"]
        prompt = transformation["prompt"]
    except (json.JSONDecodeError, KeyError):
        yield from show_snackbar(state, "Invalid transformation data.")
        return

    # Log the click event for analytics
    element_id = f"suggested_transformation_{title.replace(' ', '_').lower()}"
    log_ui_click(
        element_id=element_id,
        page_name=app_state.current_page,
        session_id=app_state.session_id,
    )

    input_gcs_uri = https_url_to_gcs_uri(state.selected_image_url)

    # The transformation uses the selected image as the sole input
    # and the button's key as the prompt.
    state.prompt = prompt  # Update the main prompt box for clarity
    yield from _generate_and_save(base_prompt=prompt, input_gcs_uris=[input_gcs_uri])


def on_suggest_transformations_click(e: me.ClickEvent):
    """Generates and displays suggested transformations for the primary generated image."""
    state = me.state(PageState)

    if not state.generated_image_urls:
        yield from show_snackbar(
            state,
            "No image available to suggest transformations for.",
        )
        return

    state.is_suggesting_transformations = True
    yield

    try:
        # Use the first generated image to get suggestions
        gcs_uri = https_url_to_gcs_uri(state.generated_image_urls[0])
        raw_transformations = generate_transformation_prompts(image_uris=[gcs_uri])
        # Convert Pydantic objects to dicts for state
        state.suggested_transformations_json = json.dumps(
            [t.model_dump() for t in raw_transformations],
        )
    except Exception as ex:
        print(f"Could not generate transformation prompts: {ex}")
        state.suggested_transformations_json = "[]"
        yield from show_snackbar(state, f"Failed to get suggestions: {ex}")
    finally:
        state.is_suggesting_transformations = False
        yield


def on_image_action_click(e: me.ClickEvent):
    """Handles clicks on image action buttons, triggering a new generation."""
    state = me.state(PageState)
    app_state = me.state(AppState)

    # Find the template that was clicked
    template = next(
        (t for t in json.loads(state.prompt_templates_json) if t["key"] == e.key),
        None,
    )

    if not template:
        yield from show_snackbar(state, f"Unknown action: {e.key}")
        return

    # Assemble the list of input URIs, starting with the user's image
    input_gcs_uris = []
    user_image_uri = ""

    # Prioritize the selected generated image
    if state.selected_image_url:
        user_image_uri = https_url_to_gcs_uri(state.selected_image_url)
    # Fallback to the first uploaded image
    elif state.uploaded_image_gcs_uris:
        user_image_uri = state.uploaded_image_gcs_uris[0]

    if user_image_uri:
        input_gcs_uris.append(user_image_uri)

    # Add reference images from the template, if they exist
    if template["references"]:
        input_gcs_uris.extend(template["references"])

    # If there are no images at all (neither from user nor template), show an error
    if not input_gcs_uris:
        yield from show_snackbar(state, "Please upload or select an image first.")
        return

    # Log the click event for analytics
    log_ui_click(
        element_id=f"preset_action_{template['key']}",
        page_name=app_state.current_page,
        session_id=app_state.session_id,
    )

    # The action now uses the combined list of images
    yield from _generate_and_save(
        base_prompt=template["prompt"],
        input_gcs_uris=input_gcs_uris,
    )


def on_continue_click(e: me.ClickEvent):
    """Uses the currently selected generated image as the input for a subsequent generation."""
    state = me.state(PageState)
    if not state.selected_image_url:
        yield from show_snackbar(state, "Please select an image to continue with.")
        return

    gcs_uri = https_url_to_gcs_uri(state.selected_image_url)
    state.uploaded_image_gcs_uris = [gcs_uri]
    state.uploaded_image_display_urls = [create_display_url(gcs_uri)]
    state.generated_image_urls = []
    state.generated_resolution = ""
    state.selected_image_url = ""
    state.generation_time = 0.0
    state.generation_complete = False
    # Keep state.previous_media_item_id to maintain the chain
    yield


def show_snackbar(state: PageState, message: str):
    """Displays a snackbar message at the bottom of the page."""
    state.snackbar_message = message
    state.show_snackbar = True
    yield
    time.sleep(3)
    state.show_snackbar = False
    yield
    # The snackbar will be hidden on the next interaction.


def _get_appended_prompt(base_prompt: str, num_images: int) -> str:
    """Appends the number of images prompt to the base prompt."""
    suffix = NUM_IMAGES_PROMPTS.get(num_images)
    if not suffix:
        return base_prompt

    if not base_prompt:
        return suffix

    # Avoid double punctuation
    if base_prompt.endswith((".", "!", "?")):
        return f"{base_prompt} {suffix}"
    return f"{base_prompt}. {suffix}"


def generate_images(e: me.ClickEvent):
    """Event handler for the main 'Generate Images' button."""
    state = me.state(PageState)
    yield from _generate_and_save(
        base_prompt=state.prompt,
        input_gcs_uris=state.uploaded_image_gcs_uris,
    )


def _generate_and_save(base_prompt: str, input_gcs_uris: list[str]):
    """Core logic to generate images and save results to Firestore."""
    state = me.state(PageState)
    app_state = me.state(AppState)

    # --- FIX: Clear previous results to prevent duplication on re-generation ---
    state.generated_image_urls = []
    state.selected_image_url = ""
    state.suggested_transformations_json = "[]"
    state.generation_complete = False
    state.is_generating = True
    yield

    try:
        final_prompt = base_prompt
        gcs_uris, execution_time, captions, grounding_info, all_thoughts = (
            generate_image_from_prompt_and_images(
                prompt=final_prompt,
                images=input_gcs_uris,
                aspect_ratio=state.aspect_ratio,
                gcs_folder="gemini_image_generations",
                file_prefix="gemini_image",
                image_size=state.image_size,
                use_search=state.use_search,
                use_image_search=state.use_image_search,
                thinking_level=state.thinking_level,
                include_thoughts=state.include_thoughts,
                model_name=state.selected_model,
            )
        )

        state.generation_time = execution_time
        state.grounding_info = json.dumps(grounding_info) if grounding_info else ""
        state.thoughts = all_thoughts[0] if all_thoughts else ""

        if not gcs_uris:
            item = MediaItem(
                prompt=final_prompt,
                mime_type="image/png",
                aspect=state.aspect_ratio,
                user_email=app_state.user_email,
                source_images_gcs=input_gcs_uris,
                comment="generated by gemini image generation",
                model=state.selected_model,
                related_media_item_id=state.previous_media_item_id,
                error_message="No images returned.",
                generation_time=execution_time,
            )
            add_media_item_to_firestore(item)
            state.previous_media_item_id = item.id
            yield from show_snackbar(
                state,
                "No images were generated, but the attempt was logged to the library.",
            )
        else:
            state.generated_image_urls = [create_display_url(uri) for uri in gcs_uris]
            # Measure the actual resolution of the first generated image
            state.generated_resolution = get_image_resolution(gcs_uris[0])
            if state.generated_image_urls:
                state.selected_image_url = state.generated_image_urls[0]

            # Create and save the main media item
            item = MediaItem(
                gcs_uris=gcs_uris,
                captions=captions,
                prompt=final_prompt,
                mime_type="image/png",
                aspect=state.aspect_ratio,
                resolution=state.generated_resolution,
                image_size=state.image_size,
                user_email=app_state.user_email,
                source_images_gcs=input_gcs_uris,
                comment="generated by gemini image generation",
                model=state.selected_model,
                related_media_item_id=state.previous_media_item_id,
                generation_time=execution_time,
            )
            add_media_item_to_firestore(item)
            state.previous_media_item_id = item.id
            yield from show_snackbar(state, "Automatically saved to library.")

            # Phase 2: Evaluate the generated images if critique questions exist
            if state.critique_questions:
                state.is_evaluating = True
                yield

                for uri in gcs_uris:
                    try:
                        evaluation_result = evaluate_image_with_questions(
                            image_uri=uri,
                            questions=state.critique_questions,
                        )

                        # Process results
                        yes_answers = sum(
                            1 for answer in evaluation_result.answers if answer.answer
                        )
                        score_str = f"{yes_answers}/{len(state.critique_questions)}"

                        # Store evaluation
                        # The signed URL was already generated and is in state.generated_image_urls
                        # Find the corresponding signed URL for the current GCS URI.
                        try:
                            uri_index = gcs_uris.index(uri)
                            https_url = state.generated_image_urls[uri_index]
                        except ValueError:
                            # Fallback in case the URI isn't found, though it should be.
                            https_url = create_display_url(uri)

                        evals = json.loads(state.evaluations_json)
                        evals[https_url] = {
                            "score": score_str,
                            "details": [
                                ans.model_dump() for ans in evaluation_result.answers
                            ],
                        }
                        state.evaluations_json = json.dumps(evals)

                    except Exception as eval_ex:
                        print(
                            f"ERROR: Failed to evaluate image {uri}. Details: {eval_ex}",
                        )
                        # Optionally, store an error state for this evaluation

                state.is_evaluating = False
                yield

        # Always turn off the main generating spinner after the core process is done.
        state.is_generating = False
        yield

    except Exception as ex:
        print(f"ERROR: Failed to generate images. Details: {ex}")
        yield from show_snackbar(state, f"An error occurred: {ex}")
        # Ensure loading state is turned off on error
        state.is_generating = False
        state.generation_complete = True  # Mark as complete to stop spinners

    # NOTE: The final state update (is_generating=False, generation_complete=True)
    # happens inside the try/except block to ensure UI updates correctly on success or error.


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


def on_load(e: me.LoadEvent):
    """Handles the initial load of the page, checking for an image URI in the query parameters."""
    state = me.state(PageState)

    # Load templates once on initial load.
    if not json.loads(state.prompt_templates_json):
        templates = prompt_template_service.load_templates(
            config_path="config/image_prompt_templates.json",
            template_type="image",
        )
        state.prompt_templates_json = json.dumps(
            [t.model_dump() for t in templates],
            default=str,
        )
        print(
            f"Loaded {len(json.loads(state.prompt_templates_json))} image prompt templates.",
        )

    if not state.initial_load_complete:
        image_uri = me.query_params.get("image_uri")
        if image_uri and image_uri not in state.uploaded_image_gcs_uris:
            state.uploaded_image_gcs_uris.append(image_uri)
        state.initial_load_complete = True

    yield


@me.page(
    path="/banana-studio",
    title="Banana Studio - GenMedia Creative Studio",
    on_load=on_load,
)
def page():
    """Define the Mesop page route for Gemini Image Generation."""
    with page_scaffold(page_name="banana-studio"):  # pylint: disable=E1129
        gemini_image_gen_page_content()
