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
"""Gemini 2.5 Flash Image Generation - nano-banana."""

import json
import time
from dataclasses import field

import mesop as me

from common.analytics import analytics_logger, log_ui_click
from common.metadata import MediaItem, add_media_item_to_firestore
from common.prompt_template_service import prompt_template_service
from common.storage import store_to_gcs
from common.utils import create_display_url, https_url_to_gcs_uri
from components.banana_button.banana_button import banana_button
from components.content_credentials.content_credentials import (
    content_credentials_viewer,
)
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
from components.header import header
from components.image_thumbnail import image_thumbnail
from components.library.events import LibrarySelectionChangeEvent
from components.library.library_chooser_button import library_chooser_button
from components.page_scaffold import page_frame, page_scaffold
from components.pill import pill
from components.search_entry_point.search_entry_point import search_entry_point
from components.snackbar import snackbar
from components.svg_icon.svg_icon import svg_icon
from config.banana_presets import IMAGE_ACTION_PRESETS
from config.gemini_image_models import get_gemini_image_model_config
from models.gemini import (
    generate_image_from_prompt_and_images,
    generate_transformation_prompts,
)
from models.upscale import get_image_resolution
from services.c2pa_service import c2pa_service
from state.state import AppState

CHIP_STYLE = me.Style(
    padding=me.Padding(top=4, right=12, bottom=4, left=12),
    border_radius=8,
    font_size=14,
    height=32,
)


def get_all_image_presets():
    """Loads dynamic templates and merges them with static presets."""
    # Start with a deep copy of the hardcoded presets
    # to ensure backward compatibility and avoid mutating the original
    all_presets = {k: [p.copy() for p in v] for k, v in IMAGE_ACTION_PRESETS.items()}

    try:
        # Load dynamic templates of type 'image'
        dynamic_templates = prompt_template_service.load_templates(
            config_path="config/image_prompt_templates.json",
            template_type="image",
        )

        for template in dynamic_templates:
            t_dict = template.model_dump()
            # Normalize category to lowercase to match keys in IMAGE_ACTION_PRESETS
            category = t_dict.get("category", "custom").lower()

            if category not in all_presets:
                all_presets[category] = []

            # Check for duplicates by key to avoid showing the same action twice
            existing_keys = {p["key"] for p in all_presets[category]}
            if t_dict["key"] not in existing_keys:
                all_presets[category].append(t_dict)

    except Exception as e:
        analytics_logger.error(f"Error loading dynamic prompt templates: {e}")

    return all_presets


@me.stateclass
class PageState:
    """Gemini Image Generation Page State"""

    selected_model: str = "gemini-nano-banana-2.1"
    uploaded_image_gcs_uris: list[str] = field(default_factory=list)  # pylint: disable=invalid-field-call
    uploaded_image_display_urls: list[str] = field(default_factory=list)  # pylint: disable=invalid-field-call
    prompt: str = ""
    generated_image_urls: list[str] = field(default_factory=list)  # pylint: disable=invalid-field-call
    generated_image_captions: list[str] = field(default_factory=list)  # pylint: disable=invalid-field-call
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
    num_images_to_generate: int = 0
    suggested_transformations: list[dict] = field(default_factory=list)  # pylint: disable=invalid-field-call
    is_suggesting_transformations: bool = False
    use_search: bool = False
    use_image_search: bool = False
    include_thoughts: bool = False
    thinking_level: str = "HIGH"
    thoughts: str = ""
    grounding_info: str = ""
    c2pa_manifests: dict[str, str] = field(
        default_factory=dict,
    )  # Store as dict of strings (url -> json_str)

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


def _render_grounding_info(grounding_info_str: str, theme_mode: str):
    """Renders the grounding information (search entry point and sources)."""
    if not grounding_info_str:
        return

    try:
        info = json.loads(grounding_info_str)
        if not info:
            return

        # Render Search Entry Point
        if (
            info.get("search_entry_point")
            and "rendered_content" in info["search_entry_point"]
        ):
            search_entry_point(
                html_content=info["search_entry_point"]["rendered_content"],
                theme_mode=theme_mode,
            )

        # Render Grounding Chunks as Links
        if "grounding_chunks" in info and isinstance(info["grounding_chunks"], list):
            me.text(
                "Sources",
                style=me.Style(font_weight="bold", margin=me.Margin(bottom=8)),
            )
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="column",
                    gap=4,
                    margin=me.Margin(bottom=16),
                ),
            ):
                for chunk in info["grounding_chunks"]:
                    if "web" in chunk:
                        web = chunk["web"]
                        title = web.get("title", "Source")
                        uri = web.get("uri", "#")
                        me.link(
                            text=title,
                            url=uri,
                            # target="_blank", # Removed due to error
                            style=me.Style(
                                color=me.theme_var("primary"),
                                text_decoration="underline",
                                font_size=14,
                            ),
                        )

    except Exception as e:
        me.text(f"Error parsing grounding info: {e}")
        me.text(grounding_info_str)


def gemini_image_gen_page_content():
    """Renders the main UI for the Gemini Image Generation page."""
    state = me.state(PageState)
    app_state = me.state(AppState)
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

    with page_frame():  # pylint: disable=E1129
        header(
            "Gemini Image Generation",
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

                me.text(
                    "Type a prompt or add images and a prompt",
                    style=me.Style(
                        margin=me.Margin(bottom=16),
                    ),
                )
                max_input_images = model_config.max_input_images if model_config else 3
                upload_disabled = len(state.uploaded_image_gcs_uris) >= max_input_images

                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="row",
                        gap=16,
                        margin=me.Margin(bottom=16),
                        justify_content="center",
                    ),
                ):
                    me.uploader(
                        label="Upload Media",
                        on_upload=on_upload,
                        multiple=True,
                        accepted_file_types=model_config.supported_input_mime_types
                        if model_config
                        else [
                            "image/jpeg",
                            "image/png",
                            "image/webp",
                            "application/pdf",
                        ],
                        style=me.Style(width="100%"),
                        disabled=upload_disabled,
                    )
                    library_chooser_button(
                        on_library_select=on_library_select,
                        button_label="Choose from Library",
                        disabled=upload_disabled,
                    )
                if state.uploaded_image_gcs_uris:
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_wrap="wrap",
                            gap=10,
                            justify_content="center",
                            margin=me.Margin(bottom=16),
                        ),
                    ):
                        for i, uri in enumerate(state.uploaded_image_display_urls):
                            image_thumbnail(
                                image_uri=uri,
                                index=i,
                                on_remove=on_remove_image,
                                icon_size=18,
                            )
                me.textarea(
                    label="Prompt",
                    rows=3,
                    max_rows=14,
                    autosize=True,
                    on_blur=on_prompt_blur,
                    value=state.prompt,
                    style=me.Style(width="100%", margin=me.Margin(bottom=16)),
                )

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

                max_output_images = (
                    model_config.max_output_images if model_config else 1
                )

                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="row",
                        gap=16,
                        align_items="center",
                        margin=me.Margin(bottom=16),
                    ),
                ):
                    if max_output_images > 1:
                        me.select(
                            label="Number of Images",
                            options=[me.SelectOption(label="Auto", value="0")]
                            + [
                                me.SelectOption(label=str(i), value=str(i))
                                for i in range(1, max_output_images + 1)
                            ],
                            on_selection_change=on_num_images_change,
                            value=str(state.num_images_to_generate),
                            style=me.Style(flex_grow=1),
                        )

                    if model_config and model_config.supports_search:
                        me.checkbox(
                            label="Use Search",
                            checked=state.use_search,
                            on_change=on_search_change,
                        )

                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="row",
                        align_items="center",
                        gap=16,
                    ),
                ):
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
                        with me.content_button(on_click=on_clear_click, type="icon"):
                            me.icon("delete_sweep")

                    if state.generation_complete and state.generation_time > 0:
                        me.text(
                            f"{state.generation_time:.2f} seconds",
                            style=me.Style(font_size=12),
                        )

                # Actions row
                if state.generated_image_urls:
                    with me.box(
                        style=me.Style(
                            display="flex",
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
                            veo_button(
                                gcs_uri=https_url_to_gcs_uri(state.selected_image_url),
                            )

                # Image presets
                if state.generated_image_urls or state.uploaded_image_gcs_uris:
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="column",
                            gap=8,  # Reduced gap for tighter category spacing
                            margin=me.Margin(top=16),
                        ),
                    ):
                        # me.text("Image Presets", style=me.Style(font_weight="bold"))

                        all_presets = get_all_image_presets()

                        for category_name, presets in all_presets.items():
                            if not presets:
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
                                    gap=8,  # Reduced gap
                                    flex_wrap="wrap",
                                ),
                            ):
                                for preset in presets:
                                    label = preset.get("label") or preset["key"]
                                    me.button(
                                        label,
                                        on_click=on_image_action_click,
                                        type="stroked",
                                        key=preset["key"],
                                        style=CHIP_STYLE,
                                    )

                # Suggest transformations button
                if (
                    state.generation_complete
                    and not state.suggested_transformations
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
                                # type="stroked",
                                style=CHIP_STYLE,
                            )

                # Suggested transformations
                if state.suggested_transformations:
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="row",
                            gap=16,
                            margin=me.Margin(top=16),
                        ),
                    ):
                        # me.text("Suggested Transformations", style=me.Style(font_weight="bold"))
                        with me.box(
                            style=me.Style(
                                display="flex",
                                flex_direction="column",
                                align_items="flex-start",
                                gap=8,
                            ),
                        ):
                            for transformation in state.suggested_transformations:
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
                            overflow_y="auto",
                        ),
                    ):
                        if len(state.generated_image_urls) == 1:
                            # Display single, maximized image
                            with me.box(
                                style=me.Style(
                                    position="relative",
                                    width="100%",
                                    height="100%",
                                    display="flex",
                                    justify_content="center",
                                ),
                            ):
                                me.image(
                                    src=state.generated_image_urls[0],
                                    alt=state.generated_image_captions[0]
                                    if state.generated_image_captions
                                    else "",
                                    style=me.Style(
                                        width="100%",
                                        max_height="85vh",
                                        object_fit="contain",
                                        border_radius=8,
                                    ),
                                )
                                # Content Credentials (C2PA) Viewer
                                with me.box(
                                    style=me.Style(
                                        position="absolute",
                                        top=16,
                                        right=16,
                                    ),
                                ):
                                    manifest_json = state.c2pa_manifests.get(
                                        state.generated_image_urls[0],
                                    )
                                    if manifest_json:
                                        content_credentials_viewer(
                                            manifest=manifest_json,
                                        )

                            if state.generated_resolution:
                                with me.box(style=me.Style(margin=me.Margin(top=8))):
                                    pill(
                                        label=f"Resolution: {state.generated_resolution}",
                                        pill_type="resolution",
                                    )

                            if state.grounding_info:
                                with me.box(
                                    style=me.Style(
                                        margin=me.Margin(top=16),
                                        width="100%",
                                    ),
                                ):
                                    _render_grounding_info(
                                        state.grounding_info,
                                        app_state.theme_mode,
                                    )

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
                                selected_index = (
                                    state.generated_image_urls.index(
                                        state.selected_image_url,
                                    )
                                    if state.selected_image_url
                                    in state.generated_image_urls
                                    else 0
                                )
                                caption = (
                                    state.generated_image_captions[selected_index]
                                    if selected_index
                                    < len(state.generated_image_captions)
                                    else ""
                                )

                                with me.box(
                                    style=me.Style(
                                        position="relative",
                                        width="100%",
                                        display="flex",
                                        justify_content="center",
                                    ),
                                ):
                                    me.image(
                                        src=state.selected_image_url,
                                        alt=caption,
                                        style=me.Style(
                                            width="100%",
                                            max_height="75vh",
                                            object_fit="contain",
                                            border_radius=8,
                                        ),
                                    )
                                    # Content Credentials (C2PA) Viewer
                                    with me.box(
                                        style=me.Style(
                                            position="absolute",
                                            top=16,
                                            right=16,
                                        ),
                                    ):
                                        manifest_json = state.c2pa_manifests.get(
                                            state.selected_image_url,
                                        )
                                        if manifest_json:
                                            content_credentials_viewer(
                                                manifest=manifest_json,
                                            )

                                if state.generated_resolution:
                                    with me.box(
                                        style=me.Style(margin=me.Margin(top=8)),
                                    ):
                                        pill(
                                            label=f"Resolution: {state.generated_resolution}",
                                            pill_type="resolution",
                                        )

                                # Thumbnail strip
                                with me.box(
                                    style=me.Style(
                                        display="flex",
                                        flex_direction="row",
                                        gap=16,
                                        justify_content="center",
                                    ),
                                ):
                                    for i, url in enumerate(state.generated_image_urls):
                                        is_selected = url == state.selected_image_url
                                        caption = (
                                            state.generated_image_captions[i]
                                            if i < len(state.generated_image_captions)
                                            else ""
                                        )
                                        with me.box(
                                            key=url,
                                            on_click=on_thumbnail_click,
                                            style=me.Style(
                                                padding=me.Padding.all(4),
                                                border=me.Border.all(
                                                    me.BorderSide(
                                                        width=4,
                                                        style="solid",
                                                        color=me.theme_var("secondary")
                                                        if is_selected
                                                        else "transparent",
                                                    ),
                                                ),
                                                border_radius=12,
                                                cursor="pointer",
                                            ),
                                        ):
                                            me.image(
                                                src=url,
                                                alt=caption,
                                                style=me.Style(
                                                    width=100,
                                                    height=100,
                                                    object_fit="cover",
                                                    border_radius=6,
                                                ),
                                            )

                                if state.grounding_info:
                                    with me.box(
                                        style=me.Style(
                                            margin=me.Margin(top=16),
                                            width="100%",
                                        ),
                                    ):
                                        _render_grounding_info(
                                            state.grounding_info,
                                            app_state.theme_mode,
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
    """Handles file uploads, stores them in GCS, and updates the state."""
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

    for file in files_to_upload:
        gcs_url = store_to_gcs(
            "gemini_image_gen_references",
            file.name,
            file.mime_type,
            file.getvalue(),
        )
        state.uploaded_image_gcs_uris.append(gcs_url)
        state.uploaded_image_display_urls.append(create_display_url(gcs_url))
    yield


def on_library_select(e: LibrarySelectionChangeEvent):
    """Appends a selected library image's GCS URI to the list of uploaded images."""
    state = me.state(PageState)
    current_model_name = state.selected_model
    model_config = get_gemini_image_model_config(current_model_name)
    max_input_images = model_config.max_input_images if model_config else 3

    if len(state.uploaded_image_gcs_uris) >= max_input_images:
        yield from show_snackbar(
            state,
            f"You can upload a maximum of {max_input_images} images.",
        )
        return

    state.uploaded_image_gcs_uris.append(e.gcs_uri)
    state.uploaded_image_display_urls.append(create_display_url(e.gcs_uri))
    yield


def on_remove_image(e: me.ClickEvent):
    """Removes an image from the `uploaded_image_gcs_uris` list based on its index."""
    state = me.state(PageState)
    del state.uploaded_image_gcs_uris[int(e.key)]
    del state.uploaded_image_display_urls[int(e.key)]
    yield


def on_clear_click(e: me.ClickEvent):
    """Resets the entire page state to its initial values, clearing all inputs and outputs."""
    state = me.state(PageState)
    state.generated_image_urls = []
    state.generated_image_captions = []
    state.generated_resolution = ""
    state.prompt = ""
    state.uploaded_image_gcs_uris = []
    state.uploaded_image_display_urls = []
    state.selected_image_url = ""
    state.generation_time = 0.0
    state.generation_complete = False
    state.previous_media_item_id = None  # Reset the chain
    state.num_images_to_generate = 0
    state.suggested_transformations = []
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
        gcs_uri = f"gs://{state.generated_image_urls[0].replace('/media/', '')}"
        raw_transformations = generate_transformation_prompts(image_uris=[gcs_uri])
        # Convert Pydantic objects to dicts for state
        state.suggested_transformations = [t.model_dump() for t in raw_transformations]
    except Exception as ex:
        analytics_logger.error(f"Could not generate transformation prompts: {ex}")
        state.suggested_transformations = []
        yield from show_snackbar(state, f"Failed to get suggestions: {ex}")
    finally:
        state.is_suggesting_transformations = False
        yield


def on_image_action_click(e: me.ClickEvent):
    """Handles clicks on image action buttons, triggering a new generation."""
    state = me.state(PageState)
    app_state = me.state(AppState)

    # Find the preset that was clicked
    preset = None
    all_presets = get_all_image_presets()
    for category in all_presets.values():
        found = next((p for p in category if p["key"] == e.key), None)
        if found:
            preset = found
            break

    if not preset:
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

    # Add reference images from the preset, if they exist
    preset_references = preset.get("references", [])
    if preset_references:
        input_gcs_uris.extend(preset_references)

    # If there are no images at all (neither from user nor preset), show an error
    if not input_gcs_uris:
        yield from show_snackbar(state, "Please upload or select an image first.")
        return

    # Log the click event for analytics
    log_ui_click(
        element_id=f"preset_action_{preset['key']}",
        page_name=app_state.current_page,
        session_id=app_state.session_id,
    )

    # The action now uses the combined list of images
    yield from _generate_and_save(
        base_prompt=preset["prompt"],
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
    state.uploaded_image_display_urls = [
        create_display_url(gcs_uri),
    ]  # This line is the fix
    state.generated_image_urls = []
    state.generated_image_captions = []
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
    if num_images <= 1:
        return base_prompt

    suffix = f"Give me {num_images} images."

    if not base_prompt:
        return suffix

    # Avoid double punctuation
    if base_prompt.endswith((".", "!", "?")):
        return f"{base_prompt} {suffix}"
    return f"{base_prompt}. {suffix}"


def _generate_and_save(base_prompt: str, input_gcs_uris: list[str]):
    """Core logic to generate images and save results to Firestore."""
    state = me.state(PageState)
    app_state = me.state(AppState)

    # Clear previous suggestions before generating new ones
    state.suggested_transformations = []

    final_prompt = _get_appended_prompt(base_prompt, state.num_images_to_generate)
    # final_prompt = base_prompt

    state.is_generating = True
    state.generation_complete = False
    yield

    try:
        gcs_uris, execution_time, captions, grounding_info, all_thoughts = (
            generate_image_from_prompt_and_images(
                prompt=final_prompt,
                images=input_gcs_uris,
                aspect_ratio=state.aspect_ratio,
                gcs_folder="gemini_image_generations",
                file_prefix="gemini_image",
                candidate_count=1,
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

        if grounding_info:
            analytics_logger.info(
                f"Grounding Metadata Keys: {list(grounding_info.keys())}",
            )

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
                grounding_info=state.grounding_info,
            )
            add_media_item_to_firestore(item)
            state.previous_media_item_id = item.id
            yield from show_snackbar(
                state,
                "No images were generated, but the attempt was logged to the library.",
            )
        else:
            state.generated_image_urls = [create_display_url(uri) for uri in gcs_uris]
            state.generated_image_captions = captions
            # Measure the actual resolution of the first generated image
            state.generated_resolution = get_image_resolution(gcs_uris[0])

            # Read C2PA Manifests for all images
            state.c2pa_manifests = {}
            for i, uri in enumerate(gcs_uris):
                manifest = c2pa_service.read_manifest(uri)
                display_url = state.generated_image_urls[i]
                if manifest:
                    state.c2pa_manifests[display_url] = json.dumps(manifest)
                    if i == 0:
                        analytics_logger.info(
                            "C2PA manifest found and loaded for image 0.",
                        )

            if state.generated_image_urls:
                state.selected_image_url = state.generated_image_urls[0]

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
                grounding_info=state.grounding_info,
            )
            add_media_item_to_firestore(item)
            state.previous_media_item_id = item.id
            yield from show_snackbar(state, "Automatically saved to library.")

    except Exception as ex:
        analytics_logger.error(f"Failed to generate images. Details: {ex}")
        yield from show_snackbar(state, f"An error occurred: {ex}")

    finally:
        state.is_generating = False
        state.generation_complete = True
        yield


def generate_images(e: me.ClickEvent):
    """Event handler for the main 'Generate Images' button."""
    state = me.state(PageState)
    yield from _generate_and_save(
        base_prompt=state.prompt,
        input_gcs_uris=state.uploaded_image_gcs_uris,
    )


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


from components.veo_button.veo_button import veo_button


def on_load(e: me.LoadEvent):
    """Handles the initial load of the page, checking for an image URI in the query parameters."""
    state = me.state(PageState)
    # This flag ensures the logic runs only once on initial page load,
    # not on subsequent yields or interactions.
    image_uri = me.query_params.get("image_uri")
    if image_uri:
        final_gcs_uri = image_uri
        # If a signed URL is passed, convert it back to a GCS URI.
        if image_uri.startswith("https://"):
            # Strip the query parameters from the signed URL.
            base_url = image_uri.split("?")[0]
            final_gcs_uri = https_url_to_gcs_uri(base_url)

        if final_gcs_uri and final_gcs_uri not in state.uploaded_image_gcs_uris:
            state.uploaded_image_gcs_uris.append(final_gcs_uri)
            state.uploaded_image_display_urls.append(
                create_display_url(final_gcs_uri),
            )
    yield


@me.page(
    path="/gemini_image_generation",
    title="Gemini Image Generation - GenMedia Creative Studio",
    on_load=on_load,
)
@me.page(
    path="/nano-banana",
    title="Gemini Image Generation - GenMedia Creative Studio",
    on_load=on_load,
)
def page():
    """Define the Mesop page route for Gemini Image Generation."""
    with page_scaffold(page_name="gemini_image_generation"):  # pylint: disable=E1129
        gemini_image_gen_page_content()
