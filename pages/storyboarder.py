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
"""Storyboarder Workflow Page."""

import time
import uuid
import datetime
import mesop as me

from common.analytics import log_ui_click
from common.storage import store_to_gcs
from common.utils import create_display_url, https_url_to_gcs_uri
from common.metadata import MediaItem, add_media_item_to_firestore
from components.header import header
from components.page_scaffold import page_frame, page_scaffold
from components.snackbar import snackbar
from components.dialog import dialog
from components.library.library_chooser_button import library_chooser_button
from components.library.events import LibrarySelectionChangeEvent
from config.default import Default as cfg
from config.gemini_image_models import (
    GEMINI_IMAGE_MODELS,
    get_gemini_image_model_config,
)
from config.veo_models import VEO_MODELS, get_veo_model_config, DEFAULT_VEO_VERSION_ID
from models.gemini import (
    generate_image_from_prompt_and_images,
    describe_image,
    generate_storyboard_narrative,
)
from models.veo import generate_video, VideoGenerationRequest
from models.video_processing import process_videos
from state.storyboarder_state import PageState
from state.state import AppState


@me.page(
    path="/storyboarder",
    title="Storyboarder - GenMedia Creative Studio",
)
def page():
    with page_scaffold(page_name="storyboarder"):
        with page_frame():
            header("Storyboarder", "movie_filter")
            storyboarder_content()


def storyboarder_content():
    state = me.state(PageState)
    snackbar(is_visible=state.show_snackbar, label=state.snackbar_message)

    with me.box(
        style=me.Style(
            display="flex", flex_direction="column", gap=24, padding=me.Padding.all(24)
        )
    ):
        # --- TOP ROW: PROMPT & CHARACTER SETUP ---
        with me.box(
            style=me.Style(
                display="flex", flex_direction="row", gap=24, flex_wrap="wrap"
            )
        ):
            # Left Column: Narrative Prompter (60% basis)
            with me.box(
                style=me.Style(
                    flex_basis="max(480px, calc(60% - 12px))",
                    flex_grow=1,
                    display="flex",
                    flex_direction="column",
                    gap=16,
                )
            ):
                me.text("1. Describe your Story Concept", type="headline-6")

                me.textarea(
                    label="Enter Story Concept or Prompt",
                    value=state.prompt,
                    on_blur=on_prompt_blur,
                    rows=3,
                    style=me.Style(width="100%"),
                )

                with me.box(
                    style=me.Style(display="flex", gap=16, align_items="center")
                ):
                    me.button(
                        "Generate Narrative Arc",
                        on_click=on_generate_story_click,
                        type="raised",
                        disabled=state.is_generating_story or not state.prompt,
                    )
                    if state.is_generating_story:
                        me.progress_spinner(diameter=24)

            # Right Column: Character Consistency (40% basis)
            with me.box(
                style=me.Style(
                    flex_basis="max(320px, calc(40% - 12px))",
                    flex_grow=1,
                    background=me.theme_var("surface-container-low"),
                    padding=me.Padding.all(16),
                    border_radius=12,
                    display="flex",
                    flex_direction="column",
                    gap=12,
                )
            ):
                me.text(
                    "Character Consistency (Optional)",
                    style=me.Style(font_weight="bold", font_size=14),
                )
                me.text(
                    "Upload a character photo to generate a multi-view sheet, guaranteeing consistent looks across all scenes.",
                    style=me.Style(font_size=12, color="#666"),
                )

                if not state.character_source_display_url:
                    me.uploader(
                        label="Upload Character Photo",
                        on_upload=on_upload_character_source,
                        accepted_file_types=["image/jpeg", "image/png", "image/webp"],
                    )
                else:
                    with me.box(
                        style=me.Style(
                            display="flex",
                            gap=12,
                            align_items="center",
                            flex_wrap="wrap",
                        )
                    ):
                        me.image(
                            src=state.character_source_display_url,
                            style=me.Style(
                                width="70px",
                                height="70px",
                                border_radius=8,
                                object_fit="cover",
                            ),
                        )
                        me.button(
                            "Remove",
                            on_click=on_remove_character,
                            type="stroked",
                            style=me.Style(font_size=11),
                        )

                        me.button(
                            "Generate Sheet",
                            on_click=on_generate_character_sheet_click,
                            type="raised",
                            disabled=state.is_generating_character_sheet
                            or bool(state.character_sheet_gcs_uri),
                            style=me.Style(font_size=11),
                        )
                        if state.is_generating_character_sheet:
                            me.progress_spinner(diameter=20)

                if state.character_sheet_display_url:
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="column",
                            gap=4,
                            margin=me.Margin(top=8),
                        )
                    ):
                        me.text(
                            "Active Consistency Sheet:",
                            style=me.Style(font_weight="bold", font_size=11),
                        )
                        me.image(
                            src=state.character_sheet_display_url,
                            style=me.Style(
                                height="90px",
                                border_radius=6,
                                object_fit="cover",
                                border=me.Border.all(
                                    me.BorderSide(width=1, color="#ccc")
                                ),
                            ),
                        )

        # --- CONFIGURATIONS PANEL (ACCORDION style below top row) ---
        with me.box(
            style=me.Style(
                background=me.theme_var("surface-container"),
                padding=me.Padding.all(12),
                border_radius=12,
                border=me.Border.all(me.BorderSide(width=1, color="#e0e0e0")),
            )
        ):
            with me.box(
                style=me.Style(
                    display="flex",
                    justify_content="space-between",
                    align_items="center",
                    cursor="pointer",
                ),
                on_click=on_toggle_settings,
            ):
                with me.box(
                    style=me.Style(display="flex", align_items="center", gap=8)
                ):
                    me.icon("settings")
                    me.text(
                        "Model Settings & Advanced Configurations",
                        style=me.Style(font_weight="500"),
                    )
                me.icon("expand_more" if not state.info_dialog_open else "expand_less")

            if state.info_dialog_open:
                with me.box(style=me.Style(margin=me.Margin(top=8, bottom=16))):
                    me.divider()

                with me.box(style=me.Style(display="flex", gap=16, flex_wrap="wrap")):
                    # Narrative Model Select
                    me.select(
                        label="Narrative Writer Model",
                        value=state.selected_narrative_model,
                        options=[
                            me.SelectOption(
                                label="Gemini 3.5 Flash (Default)",
                                value="gemini-3.5-flash",
                            ),
                            me.SelectOption(
                                label="Gemini 3.0 Pro", value="gemini-3.0-pro"
                            ),
                            me.SelectOption(
                                label="Gemini 3.8 Flash", value="gemini-3.8-flash"
                            ),
                        ],
                        on_selection_change=on_narrative_model_change,
                    )

                    # Image Gen Model Select
                    image_options = [
                        me.SelectOption(label=m.display_name, value=m.version_id)
                        for m in GEMINI_IMAGE_MODELS
                    ]
                    me.select(
                        label="Image Generation Model",
                        value=state.selected_image_model,
                        options=image_options,
                        on_selection_change=on_image_model_change,
                    )

                    # Video Gen Model Select
                    video_options = [
                        me.SelectOption(label=v.display_name, value=v.version_id)
                        for v in VEO_MODELS
                    ]
                    me.select(
                        label="Video Model",
                        value=state.selected_video_model,
                        options=video_options,
                        on_selection_change=on_video_model_change,
                    )

                    me.select(
                        label="Storyboard Aspect Ratio",
                        value=state.aspect_ratio,
                        options=[
                            me.SelectOption(label="16:9", value="16:9"),
                            me.SelectOption(label="9:16", value="9:16"),
                            me.SelectOption(label="1:1", value="1:1"),
                        ],
                        on_selection_change=on_aspect_ratio_change,
                    )

        # --- STORY SEQUENCER & NARRATIVE BREAKDOWN ---
        if state.story_narrative:
            with me.box(
                style=me.Style(
                    background=me.theme_var("surface-container-highest"),
                    padding=me.Padding.all(20),
                    border_radius=12,
                )
            ):
                me.text("Coherent Narrative Story Arc", type="headline-6")
                me.textarea(
                    label="Overall Narrative Story Summary",
                    value=state.story_narrative,
                    on_blur=on_overall_narrative_blur,
                    rows=4,
                    style=me.Style(width="100%", margin=me.Margin(bottom=16)),
                )

                me.text(
                    "Scene Breakdowns & Descriptions",
                    type="subtitle-1",
                    style=me.Style(margin=me.Margin(bottom=12)),
                )
                with me.box(
                    style=me.Style(display="flex", flex_direction="column", gap=16)
                ):
                    for idx in range(4):
                        scene_num = idx + 1
                        narrative_val = (
                            state.scene_narratives[idx]
                            if idx < len(state.scene_narratives)
                            else ""
                        )
                        img_prompt_val = (
                            state.scene_image_prompts[idx]
                            if idx < len(state.scene_image_prompts)
                            else ""
                        )
                        vid_prompt_val = (
                            state.scene_video_prompts[idx]
                            if idx < len(state.scene_video_prompts)
                            else ""
                        )

                        with me.box(
                            style=me.Style(
                                background=me.theme_var("surface"),
                                padding=me.Padding.all(16),
                                border_radius=8,
                                border=me.Border.all(
                                    me.BorderSide(width=1, color="#ddd")
                                ),
                            )
                        ):
                            me.text(
                                f"Scene {scene_num}",
                                style=me.Style(
                                    font_weight="bold", margin=me.Margin(bottom=8)
                                ),
                            )

                            # Horizontal layout of the three textareas side-by-side
                            with me.box(
                                style=me.Style(display="flex", gap=16, flex_wrap="wrap")
                            ):
                                me.textarea(
                                    label="Narrative Line",
                                    value=narrative_val,
                                    on_blur=lambda e, i=idx: on_scene_narrative_blur(
                                        e, i
                                    ),
                                    rows=3,
                                    style=me.Style(
                                        flex_grow=1, flex_basis="calc(33.33% - 11px)"
                                    ),
                                )
                                me.textarea(
                                    label="Scene Image prompt",
                                    value=img_prompt_val,
                                    on_blur=lambda e, i=idx: on_scene_image_prompt_blur(
                                        e, i
                                    ),
                                    rows=3,
                                    style=me.Style(
                                        flex_grow=1, flex_basis="calc(33.33% - 11px)"
                                    ),
                                )
                                me.textarea(
                                    label="Scene Video prompt",
                                    value=vid_prompt_val,
                                    on_blur=lambda e, i=idx: on_scene_video_prompt_blur(
                                        e, i
                                    ),
                                    rows=3,
                                    style=me.Style(
                                        flex_grow=1, flex_basis="calc(33.33% - 11px)"
                                    ),
                                )

                with me.box(
                    style=me.Style(
                        display="flex",
                        gap=16,
                        margin=me.Margin(top=20),
                        justify_content="flex-end",
                    )
                ):
                    me.button(
                        "Generate Scene Images",
                        on_click=on_generate_images_click,
                        type="raised",
                        disabled=state.is_generating_images,
                    )
                    if state.is_generating_images:
                        me.progress_spinner(diameter=24)

        # --- REFERENCE IMAGES INPUT ---
        if state.story_narrative:
            with me.box(
                style=me.Style(
                    background=me.theme_var("surface-container-low"),
                    padding=me.Padding.all(16),
                    border_radius=12,
                )
            ):
                me.text(
                    "Additional Reference Inputs",
                    style=me.Style(
                        font_weight="bold", font_size=14, margin=me.Margin(bottom=8)
                    ),
                )
                with me.box(
                    style=me.Style(display="flex", gap=16, align_items="center")
                ):
                    me.uploader(
                        label="Upload Reference Media",
                        on_upload=on_upload_reference,
                        accepted_file_types=["image/jpeg", "image/png", "image/webp"],
                    )
                    library_chooser_button(
                        on_library_select=on_library_reference_select,
                        button_label="Choose Reference from Library",
                    )

                if state.uploaded_image_gcs_uris:
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_wrap="wrap",
                            gap=10,
                            margin=me.Margin(top=12),
                        )
                    ):
                        for idx, uri in enumerate(state.uploaded_image_display_urls):
                            with me.box(
                                style=me.Style(
                                    position="relative", width="80px", height="80px"
                                )
                            ):
                                me.image(
                                    src=uri,
                                    style=me.Style(
                                        width="100%",
                                        height="100%",
                                        border_radius=4,
                                        object_fit="cover",
                                    ),
                                )
                                with me.box(
                                    style=me.Style(
                                        position="absolute",
                                        top=2,
                                        right=2,
                                        background="rgba(0,0,0,0.6)",
                                        border_radius="50%",
                                        cursor="pointer",
                                        padding=me.Padding.all(2),
                                    ),
                                    on_click=lambda e, i=idx: on_remove_reference(e, i),
                                ):
                                    me.icon(
                                        "close",
                                        style=me.Style(color="white", font_size=14),
                                    )

        # --- VISUAL FRAME CARDS ---
        if state.generated_image_urls or state.generated_video_clips_display_urls:
            me.divider()
            me.text("Storyboard Scenes Preview", type="headline-6")

            with me.box(
                style=me.Style(
                    display="flex", flex_wrap="wrap", gap=24, justify_content="center"
                )
            ):
                for idx in range(4):
                    scene_num = idx + 1
                    img_url = (
                        state.generated_image_urls[idx]
                        if idx < len(state.generated_image_urls)
                        else ""
                    )
                    vid_url = (
                        state.generated_video_clips_display_urls[idx]
                        if idx < len(state.generated_video_clips_display_urls)
                        else ""
                    )
                    scene_narrative = (
                        state.scene_narratives[idx]
                        if idx < len(state.scene_narratives)
                        else ""
                    )

                    with me.box(
                        style=me.Style(
                            width="300px",
                            background=me.theme_var("surface"),
                            border_radius=12,
                            border=me.Border.all(
                                me.BorderSide(width=1, color="#e0e0e0")
                            ),
                            overflow="hidden",
                            display="flex",
                            flex_direction="column",
                        )
                    ):
                        # Top media frame: Play video inline if available, otherwise display image
                        if vid_url:
                            me.video(
                                src=vid_url,
                                style=me.Style(
                                    width="100%", height="170px", object_fit="cover"
                                ),
                            )
                        elif img_url:
                            me.image(
                                src=img_url,
                                style=me.Style(
                                    width="100%", height="170px", object_fit="cover"
                                ),
                            )
                        else:
                            with me.box(
                                style=me.Style(
                                    width="100%",
                                    height="170px",
                                    background="#f5f5f5",
                                    display="flex",
                                    align_items="center",
                                    justify_content="center",
                                )
                            ):
                                me.text(
                                    "No Image Generated", style=me.Style(color="#888")
                                )

                        # Scene metadata & controls
                        with me.box(
                            style=me.Style(
                                padding=me.Padding.all(12),
                                display="flex",
                                flex_direction="column",
                                gap=8,
                                flex_grow=1,
                            )
                        ):
                            me.text(
                                f"Scene {scene_num}",
                                style=me.Style(font_weight="bold", font_size=14),
                            )
                            me.text(
                                scene_narrative,
                                style=me.Style(
                                    font_size=12,
                                    color="#555",
                                    max_height="60px",
                                    overflow="hidden",
                                ),
                            )

                            with me.box(
                                style=me.Style(
                                    display="flex",
                                    gap=8,
                                    justify_content="flex-end",
                                    margin=me.Margin(top="auto"),
                                )
                            ):
                                me.button(
                                    "Regen Image",
                                    on_click=lambda e, i=idx: (
                                        on_regenerate_single_frame(e, i)
                                    ),
                                    type="stroked",
                                    style=me.Style(font_size=11),
                                )
                                me.button(
                                    "Animate",
                                    on_click=lambda e, i=idx: on_animate_single_frame(
                                        e, i
                                    ),
                                    type="stroked",
                                    style=me.Style(font_size=11),
                                )

            # --- Video Sequence Generation Controls ---
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="column",
                    align_items="center",
                    gap=16,
                    margin=me.Margin(top=32),
                )
            ):
                me.button(
                    "Generate Complete Video Sequence",
                    on_click=on_generate_video_click,
                    type="raised",
                    disabled=state.is_generating_video,
                )

                if state.is_generating_video:
                    with me.box(
                        style=me.Style(display="flex", align_items="center", gap=8)
                    ):
                        me.progress_spinner(diameter=24)
                        me.text(state.video_generation_status)

        # --- Final Video Sequence Section ---
        if state.final_video_display_url:
            me.divider()
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="column",
                    align_items="center",
                    gap=16,
                )
            ):
                me.text("Final Storyboard Video Sequence", type="headline-5")
                me.video(
                    src=state.final_video_display_url,
                    style=me.Style(width="100%", max_width="800px", border_radius=12),
                )


# --- UI Snackbar Helper Function ---


def show_snackbar(state: PageState, message: str):
    """Displays a snackbar message and auto-dismisses it after 3 seconds."""
    state.snackbar_message = message
    state.show_snackbar = True
    yield
    time.sleep(3)
    state.show_snackbar = False
    yield


# --- Event Handlers ---


def on_toggle_settings(e: me.ClickEvent):
    state = me.state(PageState)
    state.info_dialog_open = not state.info_dialog_open


def on_narrative_model_change(e: me.SelectSelectionChangeEvent):
    state = me.state(PageState)
    state.selected_narrative_model = e.value


def on_image_model_change(e: me.SelectSelectionChangeEvent):
    state = me.state(PageState)
    state.selected_image_model = e.value


def on_video_model_change(e: me.SelectSelectionChangeEvent):
    state = me.state(PageState)
    state.selected_video_model = e.value


def on_aspect_ratio_change(e: me.SelectSelectionChangeEvent):
    state = me.state(PageState)
    state.aspect_ratio = e.value


def on_prompt_blur(e: me.InputEvent):
    state = me.state(PageState)
    state.prompt = e.value


def on_overall_narrative_blur(e: me.InputEvent):
    state = me.state(PageState)
    state.story_narrative = e.value


def on_scene_narrative_blur(e: me.InputEvent, idx: int):
    state = me.state(PageState)
    if idx < len(state.scene_narratives):
        state.scene_narratives[idx] = e.value


def on_scene_image_prompt_blur(e: me.InputEvent, idx: int):
    state = me.state(PageState)
    if idx < len(state.scene_image_prompts):
        state.scene_image_prompts[idx] = e.value


def on_scene_video_prompt_blur(e: me.InputEvent, idx: int):
    state = me.state(PageState)
    if idx < len(state.scene_video_prompts):
        state.scene_video_prompts[idx] = e.value


# --- Upload & References Handlers ---


def on_upload_character_source(e: me.UploadEvent):
    state = me.state(PageState)
    file = e.files[0]
    gcs_uri = store_to_gcs(
        "storyboard_characters", file.name, file.mime_type, file.getvalue()
    )
    state.character_source_gcs_uri = gcs_uri
    state.character_source_display_url = create_display_url(gcs_uri)
    yield


def on_remove_character(e: me.ClickEvent):
    state = me.state(PageState)
    state.character_source_gcs_uri = ""
    state.character_source_display_url = ""
    state.character_sheet_gcs_uri = ""
    state.character_sheet_display_url = ""
    yield


def on_generate_character_sheet_click(e: me.ClickEvent):
    state = me.state(PageState)
    state.is_generating_character_sheet = True
    yield
    try:
        prompt = "Multi-view Character asset sheet, white background, 4 views: front, back, profile, three-quarters. Game character reference sheet."
        gcs_uris, _, _, _, _ = generate_image_from_prompt_and_images(
            prompt=prompt,
            images=[state.character_source_gcs_uri],
            aspect_ratio="16:9",
            gcs_folder="storyboard_character_sheets",
        )
        if gcs_uris:
            state.character_sheet_gcs_uri = gcs_uris[0]
            state.character_sheet_display_url = create_display_url(gcs_uris[0])
            # Automatically inject character sheet to reference list
            if state.character_sheet_gcs_uri not in state.uploaded_image_gcs_uris:
                state.uploaded_image_gcs_uris.append(state.character_sheet_gcs_uri)
                state.uploaded_image_display_urls.append(
                    state.character_sheet_display_url
                )
    except Exception as ex:
        yield from show_snackbar(state, f"Error generating character sheet: {ex}")
    finally:
        state.is_generating_character_sheet = False
        yield


def on_upload_reference(e: me.UploadEvent):
    state = me.state(PageState)
    for file in e.files:
        gcs_uri = store_to_gcs(
            "storyboard_references", file.name, file.mime_type, file.getvalue()
        )
        state.uploaded_image_gcs_uris.append(gcs_uri)
        state.uploaded_image_display_urls.append(create_display_url(gcs_uri))
    yield


def on_library_reference_select(e: LibrarySelectionChangeEvent):
    state = me.state(PageState)
    if e.gcs_uri not in state.uploaded_image_gcs_uris:
        state.uploaded_image_gcs_uris.append(e.gcs_uri)
        state.uploaded_image_display_urls.append(create_display_url(e.gcs_uri))
    yield


def on_remove_reference(e: me.ClickEvent, idx: int):
    state = me.state(PageState)
    if idx < len(state.uploaded_image_gcs_uris):
        state.uploaded_image_gcs_uris.pop(idx)
        state.uploaded_image_display_urls.pop(idx)
    yield


# --- Narrative & Media Operations ---


def on_generate_story_click(e: me.ClickEvent):
    state = me.state(PageState)
    state.is_generating_story = True
    yield
    try:
        narrative_response = generate_storyboard_narrative(
            user_prompt=state.prompt, model_name=state.selected_narrative_model
        )
        state.story_narrative = narrative_response.overall_story
        state.scene_narratives = [
            scene.narrative for scene in narrative_response.scenes
        ]
        state.scene_image_prompts = [
            scene.image_prompt for scene in narrative_response.scenes
        ]
        state.scene_video_prompts = [
            scene.video_prompt for scene in narrative_response.scenes
        ]
    except Exception as ex:
        yield from show_snackbar(state, f"Error generating story: {ex}")
    finally:
        state.is_generating_story = False
        yield


def on_generate_images_click(e: me.ClickEvent):
    state = me.state(PageState)
    state.is_generating_images = True
    state.generated_image_urls = []
    state.generated_image_gcs_uris = []
    state.generated_video_clips_display_urls = []
    state.final_video_display_url = ""
    yield
    try:
        # Generate each frame based on its corresponding scene_image_prompt and active references
        for idx in range(4):
            prompt = (
                state.scene_image_prompts[idx]
                if idx < len(state.scene_image_prompts)
                else state.prompt
            )
            gcs_uris, _, _, _, _ = generate_image_from_prompt_and_images(
                prompt=prompt,
                images=state.uploaded_image_gcs_uris,
                aspect_ratio=state.aspect_ratio,
                gcs_folder="storyboard_images",
                model_name=get_gemini_image_model_config(
                    state.selected_image_model
                ).model_name
                if get_gemini_image_model_config(state.selected_image_model)
                else None,
            )
            if gcs_uris:
                state.generated_image_gcs_uris.append(gcs_uris[0])
                state.generated_image_urls.append(create_display_url(gcs_uris[0]))
    except Exception as ex:
        yield from show_snackbar(state, f"Error generating storyboard images: {ex}")
    finally:
        state.is_generating_images = False
        yield


def on_regenerate_single_frame(e: me.ClickEvent, idx: int):
    state = me.state(PageState)
    if idx >= len(state.scene_image_prompts):
        return
    prompt = state.scene_image_prompts[idx]
    try:
        gcs_uris, _, _, _, _ = generate_image_from_prompt_and_images(
            prompt=prompt,
            images=state.uploaded_image_gcs_uris,
            aspect_ratio=state.aspect_ratio,
            gcs_folder="storyboard_images",
            model_name=get_gemini_image_model_config(
                state.selected_image_model
            ).model_name
            if get_gemini_image_model_config(state.selected_image_model)
            else None,
        )
        if gcs_uris:
            # Overwrite specific index
            while len(state.generated_image_gcs_uris) <= idx:
                state.generated_image_gcs_uris.append("")
                state.generated_image_urls.append("")
            state.generated_image_gcs_uris[idx] = gcs_uris[0]
            state.generated_image_urls[idx] = create_display_url(gcs_uris[0])
            # Clear video on single frame regen
            if idx < len(state.generated_video_clips_display_urls):
                state.generated_video_clips_display_urls[idx] = ""
    except Exception as ex:
        yield from show_snackbar(state, f"Error regenerating frame image: {ex}")
    yield


def on_animate_single_frame(e: me.ClickEvent, idx: int):
    state = me.state(PageState)
    if idx >= len(state.generated_image_gcs_uris):
        yield from show_snackbar(state, "Generate the frame image first.")
        return

    try:
        image_uri = state.generated_image_gcs_uris[idx]
        video_prompt = (
            state.scene_video_prompts[idx]
            if idx < len(state.scene_video_prompts)
            else state.prompt
        )

        request = VideoGenerationRequest(
            model_version_id=state.selected_video_model,
            reference_image_gcs=image_uri,
            reference_image_mime_type="image/png",
            duration_seconds=4,
            prompt=video_prompt,
            aspect_ratio=state.aspect_ratio,
            video_count=1,
            resolution="720p",
            enhance_prompt=True,
            generate_audio=True,
            person_generation="Allow (Adults only)",
        )

        video_uris, _ = generate_video(request)
        if video_uris:
            # Align sizes
            while len(state.generated_video_clips) <= idx:
                state.generated_video_clips.append("")
                state.generated_video_clips_display_urls.append("")

            state.generated_video_clips[idx] = video_uris[0]
            state.generated_video_clips_display_urls[idx] = create_display_url(
                video_uris[0]
            )
        else:
            yield from show_snackbar(state, "Failed to generate video for this frame.")
    except Exception as ex:
        yield from show_snackbar(state, f"Error generating frame video: {ex}")
    yield


def on_generate_video_click(e: me.ClickEvent):
    state = me.state(PageState)
    app_state = me.state(AppState)
    state.is_generating_video = True
    state.video_generation_status = "Initializing..."
    yield

    try:
        # Generate videos for any missing slots
        for i, image_uri in enumerate(state.generated_image_gcs_uris):
            if len(state.generated_video_clips) > i and state.generated_video_clips[i]:
                continue

            state.video_generation_status = (
                f"Generating clip {i + 1}/{len(state.generated_image_gcs_uris)}..."
            )
            yield

            video_prompt = (
                state.scene_video_prompts[i]
                if i < len(state.scene_video_prompts)
                else state.prompt
            )

            request = VideoGenerationRequest(
                model_version_id=state.selected_video_model,
                reference_image_gcs=image_uri,
                reference_image_mime_type="image/png",
                duration_seconds=4,
                prompt=video_prompt,
                aspect_ratio=state.aspect_ratio,
                video_count=1,
                resolution="720p",
                enhance_prompt=True,
                generate_audio=True,
                person_generation="Allow (Adults only)",
            )

            video_uris, _ = generate_video(request)

            while len(state.generated_video_clips) <= i:
                state.generated_video_clips.append("")
                state.generated_video_clips_display_urls.append("")

            if video_uris:
                state.generated_video_clips[i] = video_uris[0]
                state.generated_video_clips_display_urls[i] = create_display_url(
                    video_uris[0]
                )
            else:
                print(f"Failed to generate video for image {i}")

        # Concatenate video sequence
        valid_clips = [clip for clip in state.generated_video_clips if clip]
        if valid_clips:
            state.video_generation_status = "Concatenating clips..."
            yield

            final_uri = process_videos(valid_clips, "concat")
            state.final_video_uri = final_uri
            state.final_video_display_url = create_display_url(final_uri)

            # Save fully animated Storyboarder sequence to Library
            media_item = MediaItem(
                id=str(uuid.uuid4()),
                user_email=app_state.user_email,
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                media_type="video",
                mime_type="video/mp4",
                mode="Storyboarder",
                gcs_uris=[final_uri],
                thumbnail_uri=final_uri,
                prompt=state.prompt,
                comment="Generated by advanced Storyboarder Narrative Sequencer",
                source_images_gcs=state.generated_image_gcs_uris,
                captions=state.scene_narratives,
            )
            add_media_item_to_firestore(media_item)

            state.video_generation_status = "Complete!"
            yield from show_snackbar(
                state, "Storyboard video sequence saved to library!"
            )
        else:
            yield from show_snackbar(
                state, "Failed to generate storyboard video sequence."
            )

    except Exception as ex:
        yield from show_snackbar(state, f"Error generating video: {ex}")
    finally:
        state.is_generating_video = False
        yield
