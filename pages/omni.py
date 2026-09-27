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

"""UI pages and layout for the Gemini Omni Flash workspace."""

import json
import uuid
from collections.abc import Generator

import mesop as me

from common.analytics import get_logger
from common.metadata import MediaItem, add_media_item_to_firestore
from common.storage import generate_upload_signed_url, store_to_gcs
from common.utils import create_display_url
from components.dialog import dialog, dialog_actions
from components.gcs_uploader.gcs_uploader import gcs_uploader
from components.header import header
from components.library.events import LibrarySelectionChangeEvent
from components.library.library_chooser_button import library_chooser_button
from components.page_scaffold import page_frame, page_scaffold
from config.default import Default
from config.omni_models import OMNI_MODELS, get_omni_model_config
from models.omni import find_missing_required_media, generate_omni_video
from models.requests import APIReferenceImage, OmniVideoGenerationRequest
from state.omni_state import PageState
from state.state import AppState

config = Default()
MAX_R2V_REFERENCES = 3


def on_omni_load(_e: me.LoadEvent) -> Generator[None]:
    """Handle initial page load config for Gemini Omni."""
    state = me.state(PageState)
    state.omni_mode = "t2v"
    state.prompt = (
        "A head-on shot of a neon sign that reads 'Omni' glowing against a brick wall."
    )
    yield


@me.page(
    path="/gemini-omni",
    title="Gemini Omni - GenMedia Creative Studio",
    on_load=on_omni_load,
)
def omni_page() -> None:
    """Render the main Gemini Omni workspace page."""
    app_state = me.state(AppState)
    state = me.state(PageState)

    with page_scaffold(page_name="gemini-omni"):
        with page_frame():
            if state.info_dialog_open:
                with dialog(is_open=state.info_dialog_open):
                    me.text("About Gemini Omni", type="headline-6")
                    me.markdown(
                        "Gemini Omni supports cutting-edge multi-modal generation and video editing capabilities:\n\n"
                        "* **Text-to-Video (T2V)**: Generate videos from detailed prompt descriptions.\n"
                        "* **Image-to-Video (I2V)**: Bring a still image to life using an initial starting frame.\n"
                        "* **Reference-to-Video (Ref2V)**: Guide video character and style consistency with up to 3 reference images.\n"
                        "* **Video Editing**: Perform multi-turn conversational video edits on an existing base video.",
                    )
                    me.divider()
                    me.text("Current Settings", type="headline-6")
                    me.text(f"Mode: {state.omni_mode}")
                    me.text(f"Model: {state.omni_model}")
                    me.text(
                        f"Aspect Ratio: {state.aspect_ratio} | "
                        f"Resolution: {state.resolution} | "
                        f"Duration: {state.video_length}s",
                    )
                    with dialog_actions():
                        me.button("Close", on_click=close_info_dialog, type="flat")

            header(
                "Gemini Omni",
                "spark",
                show_info_button=True,
                on_info_click=open_info_dialog,
            )
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="row",
                    gap=24,
                    height="calc(100vh - 180px)",
                    padding=me.Padding(top=16, right=16, bottom=16, left=16),
                    overflow_y="hidden",
                ),
            ):
                # LEFT PANE: Workspace area or Chat Conversation Thread
                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="column",
                        flex_grow=1,
                        width="60%",
                        height="100%",
                        background=me.theme_var("surface-container-low"),
                        border_radius=12,
                        padding=me.Padding(top=16, right=16, bottom=16, left=16),
                    ),
                ):
                    # If chat has started, display the chat thread
                    if (
                        state.previous_interaction_id
                        or len(json.loads(state.chat_messages_json)) > 0
                    ):
                        render_chat_thread(state)
                    else:
                        render_single_turn_workspace(state)

                # RIGHT PANE: Control panel and model settings
                with me.box(
                    style=me.Style(
                        width="360px",
                        flex_shrink=0,
                        display="flex",
                        flex_direction="column",
                        gap=16,
                        background=me.theme_var("surface-container"),
                        border_radius=12,
                        padding=me.Padding(top=16, right=16, bottom=16, left=16),
                        overflow_y="auto",
                    ),
                ):
                    render_settings_panel(state, app_state)

        # Dialog box for handling exceptions
        with dialog(is_open=state.show_error_dialog):
            me.text("Generation Error", type="headline-5")
            me.text(state.error_message)
            with me.box(
                style=me.Style(
                    display="flex",
                    justify_content="flex-end",
                    margin=me.Margin(top=16),
                ),
            ):
                me.button("Close", type="flat", on_click=on_close_error_dialog)


# ==============================================================================
# UI Panels & Rendering Helpers
# ==============================================================================


def render_single_turn_workspace(state: PageState) -> None:
    """Render the standard prompt and asset upload workspace."""
    me.text(
        "Gemini Omni",
        type="headline-5",
        style=me.Style(margin=me.Margin(bottom=16)),
    )

    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="row",
            gap=16,
            flex_wrap="wrap",
            margin=me.Margin(bottom=16),
        ),
    ):
        with me.box(
            style=me.Style(
                flex_basis="max(360px, calc(60% - 16px))",
                flex_grow=1,
            ),
        ):
            me.textarea(
                label="Prompt Description",
                value=state.prompt,
                on_blur=on_prompt_blur,
                style=me.Style(width="100%", height="140px"),
            )
        with me.box(
            style=me.Style(
                flex_basis="max(240px, calc(40% - 16px))",
                flex_grow=1,
                display="flex",
                flex_direction="column",
                gap=12,
            ),
        ):
            # Conditionally show components based on mode
            if state.omni_mode == "i2v":
                render_image_uploader(state, "Upload Starting Frame Image")
            elif state.omni_mode == "ref2v":
                render_reference_images_gallery(state)
            elif state.omni_mode == "edit":
                render_image_uploader(state, "Optional: Upload Reference/Style Image")
                me.box(style=me.Style(height=8))
                render_video_uploader(state, "Upload Base Video to Edit")

    me.box(style=me.Style(flex_grow=1))
    if state.result_display_url:
        me.text(
            "Latest Generation Output",
            type="headline-6",
            style=me.Style(margin=me.Margin(bottom=8)),
        )
        with me.box(
            style=me.Style(
                display="flex",
                justify_content="center",
                background="#000",
                border_radius=8,
                overflow="hidden",
            ),
        ):
            me.video(
                src=state.result_display_url,
                style=me.Style(width="100%", max_height="320px"),
            )
    else:
        with me.box(
            style=me.Style(
                display="flex",
                align_items="center",
                justify_content="center",
                flex_grow=1,
                border=me.Border.all(
                    me.BorderSide(
                        color=me.theme_var("outline-variant"),
                        width=1,
                        style="dashed",
                    ),
                ),
                border_radius=8,
                color=me.theme_var("on-surface-variant"),
            ),
        ):
            me.text("Generate a video to see preview here.")


def render_chat_thread(state: PageState) -> None:
    """Render the chat conversation thread."""
    me.text(
        "Chat Conversation (Multi-turn Editing)",
        type="headline-5",
        style=me.Style(margin=me.Margin(bottom=8)),
    )

    with me.box(
        style=me.Style(
            flex_grow=1,
            overflow_y="auto",
            display="flex",
            flex_direction="column",
            gap=12,
            padding=me.Padding(bottom=16),
        ),
    ):
        messages = json.loads(state.chat_messages_json)
        for msg in messages:
            if msg["role"] == "user":
                with me.box(
                    style=me.Style(
                        align_self="flex-end",
                        background=me.theme_var("primary-container"),
                        color=me.theme_var("on-primary-container"),
                        padding=me.Padding(top=8, right=12, bottom=8, left=12),
                        border_radius=12,
                        max_width="70%",
                    ),
                ):
                    me.text(msg["text"])
            else:
                with me.box(
                    style=me.Style(
                        align_self="flex-start",
                        background=me.theme_var("surface-container-high"),
                        padding=me.Padding(top=12, right=12, bottom=12, left=12),
                        border_radius=12,
                        max_width="80%",
                        display="flex",
                        flex_direction="column",
                        gap=8,
                    ),
                ):
                    me.text(
                        "Generated Edit Output:",
                        type="body-2",
                        style=me.Style(font_weight="bold"),
                    )
                    me.video(
                        src=msg["video_url"],
                        style=me.Style(width="360px", border_radius=6),
                    )
                    me.text(
                        f"Prompt context: {msg.get('text', '')}",
                        type="caption",
                        style=me.Style(font_style="italic"),
                    )

    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="row",
            gap=12,
            align_items="center",
            border_radius=8,
            padding=me.Padding(top=8),
        ),
    ):
        me.input(
            label="Chat refinement prompt...",
            value=state.omni_prompt_input,
            on_blur=on_chat_prompt_blur,
            style=me.Style(flex_grow=1),
        )
        me.button("Send", type="raised", on_click=on_send_chat_turn)
        me.button("Reset Chat", type="stroked", on_click=on_reset_chat)


def render_settings_panel(state: PageState, _app_state: AppState) -> None:
    """Render the configuration settings panel."""
    # Once a conversation has started, lock the generation settings so the
    # whole conversation stays consistent. This mirrors the turn-gating used
    # for the left pane above (see render_page_content).
    chat_started = (
        bool(state.previous_interaction_id)
        or len(json.loads(state.chat_messages_json)) > 0
    )

    me.text("Model Settings", type="headline-6")

    if chat_started:
        me.text(
            "Settings are locked after the first turn to keep this "
            "conversation consistent. Start a new conversation (Reset Chat) "
            "to change them.",
            type="caption",
            style=me.Style(font_style="italic"),
        )

    me.text("Generation Mode", type="body-2")
    me.select(
        label="Mode",
        options=[
            me.SelectOption(label="Text-to-Video", value="t2v"),
            me.SelectOption(label="Image-to-Video", value="i2v"),
            me.SelectOption(label="Reference-to-Video", value="ref2v"),
            me.SelectOption(label="Video Editing", value="edit"),
        ],
        value=state.omni_mode,
        on_selection_change=on_mode_change,
        disabled=chat_started,
    )

    me.text("Omni Model Version", type="body-2")
    me.select(
        label="Model",
        options=[
            me.SelectOption(label=m.display_name, value=m.version_id)
            for m in OMNI_MODELS
        ],
        value=state.omni_model,
        on_selection_change=on_model_change,
        disabled=chat_started,
    )

    me.text("Aspect Ratio", type="body-2")
    me.select(
        label="Aspect Ratio",
        options=[
            me.SelectOption(label="Landscape (16:9)", value="16:9"),
            me.SelectOption(label="Portrait (9:16)", value="9:16"),
        ],
        value=state.aspect_ratio,
        on_selection_change=on_aspect_ratio_change,
        disabled=chat_started,
    )

    selected_model = get_omni_model_config(state.omni_model)
    resolution_options = (
        selected_model.resolutions if selected_model else [state.resolution]
    )
    me.text("Resolution", type="body-2")
    me.select(
        label="Resolution",
        options=[
            me.SelectOption(label=_resolution_label(r), value=r)
            for r in resolution_options
        ],
        value=state.resolution,
        on_selection_change=on_resolution_change,
        disabled=chat_started,
    )

    me.text(f"Video Duration: {state.video_length}s", type="body-2")
    me.slider(
        min=3,
        max=10,
        value=state.video_length,
        on_value_change=on_duration_change,
        disabled=chat_started,
    )

    me.box(style=me.Style(height=24))

    if state.is_loading:
        with me.box(
            style=me.Style(
                display="flex",
                justify_content="center",
                margin=me.Margin(top=16),
            ),
        ):
            me.progress_spinner()
    else:
        missing_media = find_missing_required_media(
            state.omni_mode,
            has_image=bool(state.reference_image_gcs),
            has_video=bool(state.reference_video_gcs),
            reference_count=len(json.loads(state.r2v_references_json)),
        )
        me.button(
            "Generate Video",
            type="raised",
            on_click=on_click_generate,
            disabled=bool(missing_media),
            style=me.Style(width="100%", height="48px"),
        )
        if missing_media:
            me.text(
                missing_media,
                type="body-2",
                style=me.Style(
                    color=me.theme_var("error"),
                    margin=me.Margin(top=8),
                    text_align="center",
                ),
            )


# ==============================================================================
# Sub-component Uploaders
# ==============================================================================


def render_image_uploader(state: PageState, label: str) -> None:
    """Render the base image input uploader."""
    me.text(label, type="body-2")
    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="row",
            gap=12,
            align_items="center",
            flex_wrap="wrap",
        ),
    ):
        me.uploader(
            label="Upload Image",
            accepted_file_types=["image/png", "image/jpeg", "image/webp"],
            on_upload=on_upload_image,
            key=str(state.reference_image_file_key),
        )
        library_chooser_button(
            on_library_select=on_image_select,
            button_label="Choose from Library",
            media_type=["images"],
            disabled=state.is_loading,
            key="omni_image_library",
        )
        if state.reference_image_uri:
            me.image(
                src=state.reference_image_uri,
                style=me.Style(
                    height="64px",
                    border_radius=6,
                    border=me.Border.all(me.BorderSide(color="#ccc", width=1)),
                ),
            )
            me.button("Remove", type="flat", on_click=on_remove_uploaded_image)


def render_video_uploader(state: PageState, label: str) -> None:
    """Render the base video input uploader using direct GCS uploads."""
    me.text(label, type="body-2")
    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="row",
            gap=12,
            align_items="center",
            flex_wrap="wrap",
        ),
    ):
        gcs_uploader(
            signed_url=state.video_upload_signed_url,
            gcs_uri=state.video_upload_gcs_uri,
            accepted_file_types=["video/mp4"],
            disabled=state.is_loading,
            label="Upload Video",
            on_request_signed_url=on_request_signed_url_video,
            on_upload_complete=on_upload_complete_video,
            on_upload_progress=on_upload_progress_video,
            on_upload_error=on_upload_error_video,
            key=str(state.reference_video_file_key),
        )
        library_chooser_button(
            on_library_select=on_video_select,
            button_label="Choose from Library",
            media_type=["videos"],
            disabled=state.is_loading,
            key="omni_video_library",
        )
        if state.reference_video_uri:
            me.video(
                src=state.reference_video_uri,
                style=me.Style(
                    height="64px",
                    border_radius=6,
                    border=me.Border.all(me.BorderSide(color="#ccc", width=1)),
                ),
            )
            me.button("Remove", type="flat", on_click=on_remove_uploaded_video)


def render_reference_images_gallery(state: PageState) -> None:
    """Render multiple reference image uploaders for Reference-to-Video."""
    me.text("Upload Reference Images (guides consistency, max 3)", type="body-2")

    r2v_refs = json.loads(state.r2v_references_json)

    if len(r2v_refs) < MAX_R2V_REFERENCES:
        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="row",
                gap=12,
                align_items="center",
                flex_wrap="wrap",
            ),
        ):
            me.uploader(
                label="Add Reference Image",
                accepted_file_types=["image/png", "image/jpeg"],
                on_upload=on_upload_ref_image,
                key=str(state.r2v_upload_key),
            )
            library_chooser_button(
                on_library_select=on_r2v_image_select,
                button_label="Choose from Library",
                media_type=["images"],
                disabled=state.is_loading,
                key="omni_r2v_image_library",
            )

    if r2v_refs:
        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="row",
                gap=8,
                margin=me.Margin(top=8),
                flex_wrap="wrap",
            ),
        ):
            for idx, ref in enumerate(r2v_refs):
                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="column",
                        align_items="center",
                        gap=4,
                    ),
                ):
                    me.image(
                        src=ref["display_url"],
                        style=me.Style(height="80px", border_radius=6),
                    )
                    me.button(
                        "Remove",
                        type="flat",
                        on_click=lambda _e, i=idx: on_remove_ref_image(i),
                    )


# ==============================================================================
# UI Event Handlers
# ==============================================================================


def on_prompt_blur(e: me.InputBlurEvent) -> None:
    """Handle prompt input blur."""
    state = me.state(PageState)
    state.prompt = e.value
    yield


def on_chat_prompt_blur(e: me.InputBlurEvent) -> None:
    """Handle chat message prompt input blur."""
    state = me.state(PageState)
    state.omni_prompt_input = e.value
    yield


def on_mode_change(e: me.SelectSelectionChangeEvent) -> None:
    """Handle active generation mode changes."""
    state = me.state(PageState)
    state.omni_mode = e.value
    yield


def _resolution_label(resolution: str) -> str:
    """Return a display label for a resolution value (e.g. '4k' -> '4K')."""
    return "4K" if resolution == "4k" else resolution


def on_model_change(e: me.SelectSelectionChangeEvent) -> None:
    """Handle model version selection changes."""
    state = me.state(PageState)
    state.omni_model = e.value
    # Keep the selected resolution valid for the newly selected model.
    model_config = get_omni_model_config(e.value)
    if model_config and state.resolution not in model_config.resolutions:
        state.resolution = (
            model_config.resolutions[0] if model_config.resolutions else "720p"
        )
    yield


def on_aspect_ratio_change(e: me.SelectSelectionChangeEvent) -> None:
    """Handle aspect ratio selection changes."""
    state = me.state(PageState)
    state.aspect_ratio = e.value
    yield


def on_resolution_change(e: me.SelectSelectionChangeEvent) -> None:
    """Handle resolution selection changes."""
    state = me.state(PageState)
    state.resolution = e.value
    yield


def on_duration_change(e: me.SliderValueChangeEvent) -> None:
    """Handle duration slider value changes."""
    state = me.state(PageState)
    state.video_length = int(e.value)
    yield


def on_close_error_dialog(_e: me.ClickEvent) -> None:
    """Close the error detail dialog."""
    state = me.state(PageState)
    state.show_error_dialog = False
    yield


def open_info_dialog(_e: me.ClickEvent) -> None:
    """Open the info dialog."""
    state = me.state(PageState)
    state.info_dialog_open = True
    yield


def close_info_dialog(_e: me.ClickEvent) -> None:
    """Close the info dialog."""
    state = me.state(PageState)
    state.info_dialog_open = False
    yield


# Upload actions


def on_upload_image(e: me.UploadEvent) -> Generator[None]:
    """Upload base reference image to GCS."""
    state = me.state(PageState)
    try:
        gcs_path = store_to_gcs(
            "uploads",
            e.file.name,
            e.file.mime_type,
            e.file.getvalue(),
        )
        state.reference_image_gcs = gcs_path
        state.reference_image_uri = create_display_url(gcs_path)
        state.reference_image_mime_type = e.file.mime_type
    except Exception as ex:  # noqa: BLE001
        state.error_message = f"Failed to upload image: {ex}"
        state.show_error_dialog = True
    yield


def on_remove_uploaded_image(_e: me.ClickEvent) -> None:
    """Remove uploaded image from state."""
    state = me.state(PageState)
    state.reference_image_gcs = ""
    state.reference_image_uri = ""
    state.reference_image_mime_type = ""
    state.reference_image_file_key += 1
    yield


def on_request_signed_url_video(e: me.WebEvent) -> Generator[None]:
    """Generate GCS Signed URL for video upload."""
    state = me.state(PageState)
    try:
        data = json.loads(e.value["value"])
        filename = data["filename"]
        content_type = data["contentType"]

        unique_id = str(uuid.uuid4())
        gcs_filename = f"{unique_id}_{filename}"

        target_gcs_uri = f"gs://{config.GENMEDIA_BUCKET}/uploads/{gcs_filename}"

        url = generate_upload_signed_url(
            bucket_name=config.GENMEDIA_BUCKET,
            blob_name=f"uploads/{gcs_filename}",
            content_type=content_type,
        )

        state.video_upload_signed_url = url
        state.video_upload_gcs_uri = target_gcs_uri
        state.video_upload_error = ""
    except Exception as ex:  # noqa: BLE001
        state.error_message = f"Failed to prepare video upload: {ex}"
        state.show_error_dialog = True
    yield


def on_upload_complete_video(e: me.WebEvent) -> Generator[None]:
    """Handle successful direct upload of base video."""
    state = me.state(PageState)
    gcs_uri = e.value["value"]
    state.reference_video_gcs = gcs_uri
    state.reference_video_uri = create_display_url(gcs_uri)
    state.reference_video_mime_type = "video/mp4"

    state.video_upload_signed_url = ""
    state.video_upload_gcs_uri = ""
    state.video_upload_progress = 0
    yield


def on_upload_progress_video(e: me.WebEvent) -> Generator[None]:
    """Handle direct upload progress updates."""
    state = me.state(PageState)
    state.video_upload_progress = int(e.value["value"])
    yield


def on_upload_error_video(e: me.WebEvent) -> Generator[None]:
    """Handle direct upload errors."""
    state = me.state(PageState)
    state.error_message = f"Video upload failed: {e.value['value']}"
    state.show_error_dialog = True

    state.video_upload_signed_url = ""
    state.video_upload_gcs_uri = ""
    state.video_upload_progress = 0
    yield


def on_video_select(e: LibrarySelectionChangeEvent) -> Generator[None]:
    """Handle selecting a video from the library."""
    state = me.state(PageState)
    state.reference_video_gcs = e.gcs_uri
    state.reference_video_uri = create_display_url(e.gcs_uri)
    state.reference_video_mime_type = "video/mp4"
    yield


def on_remove_uploaded_video(_e: me.ClickEvent) -> None:
    """Remove uploaded video from state."""
    state = me.state(PageState)
    state.reference_video_gcs = ""
    state.reference_video_uri = ""
    state.reference_video_mime_type = ""
    state.reference_video_file_key += 1
    yield


def on_upload_ref_image(e: me.UploadEvent) -> Generator[None]:
    """Add a reference image to list for Reference-to-Video mode."""
    state = me.state(PageState)
    try:
        gcs_path = store_to_gcs(
            "uploads",
            e.file.name,
            e.file.mime_type,
            e.file.getvalue(),
        )
        refs = json.loads(state.r2v_references_json)
        refs.append(
            {
                "gcs_uri": gcs_path,
                "mime_type": e.file.mime_type,
                "display_url": create_display_url(gcs_path),
            },
        )
        state.r2v_references_json = json.dumps(refs)
        state.r2v_upload_key += 1
    except Exception as ex:  # noqa: BLE001
        state.error_message = f"Failed to upload reference: {ex}"
        state.show_error_dialog = True
    yield


def on_image_select(e: LibrarySelectionChangeEvent) -> Generator[None]:
    """Handle selecting an image from the library."""
    state = me.state(PageState)
    state.reference_image_gcs = e.gcs_uri
    state.reference_image_uri = create_display_url(e.gcs_uri)
    state.reference_image_mime_type = "image/png"
    yield


def on_r2v_image_select(e: LibrarySelectionChangeEvent) -> Generator[None]:
    """Handle selecting a reference image from the library for Reference-to-Video."""
    state = me.state(PageState)
    refs = json.loads(state.r2v_references_json)
    if len(refs) < MAX_R2V_REFERENCES:
        refs.append(
            {
                "gcs_uri": e.gcs_uri,
                "mime_type": "image/png",
                "display_url": create_display_url(e.gcs_uri),
            },
        )
        state.r2v_references_json = json.dumps(refs)
    yield


def on_remove_ref_image(idx: int) -> None:
    """Remove reference image from Reference-to-Video list."""
    state = me.state(PageState)
    refs = json.loads(state.r2v_references_json)
    if 0 <= idx < len(refs):
        refs.pop(idx)
    state.r2v_references_json = json.dumps(refs)
    yield


# Core Execution Handlers


def on_click_generate(_e: me.ClickEvent) -> Generator[None]:
    """Trigger single-turn video generation or editing request."""
    state = me.state(PageState)
    app_state = me.state(AppState)

    state.is_loading = True
    state.result_gcs_uri = ""
    state.result_display_url = ""
    yield

    # Re-check required media on the server. PageState round-trips through the
    # browser, so a button enabled at render time may no longer be valid by
    # click time; this guard is the authority, the disabled button is UX
    # (issue #1929).
    missing_media = find_missing_required_media(
        state.omni_mode,
        has_image=bool(state.reference_image_gcs),
        has_video=bool(state.reference_video_gcs),
        reference_count=len(json.loads(state.r2v_references_json)),
    )
    if missing_media:
        state.error_message = missing_media
        state.show_error_dialog = True
        state.is_loading = False
        yield
        return

    # Map references list
    r2v_refs = json.loads(state.r2v_references_json)
    refs_list = [
        APIReferenceImage(gcs_uri=ref["gcs_uri"], mime_type=ref["mime_type"])
        for ref in r2v_refs
    ]

    # Prepare Pydantic Request
    req = OmniVideoGenerationRequest(
        prompt=state.prompt,
        duration_seconds=state.video_length,
        aspect_ratio=state.aspect_ratio,
        resolution=state.resolution,
        omni_mode=state.omni_mode,
        model_version_id=state.omni_model,
        reference_image_gcs=state.reference_image_gcs
        if state.reference_image_gcs
        else None,
        reference_image_mime_type=state.reference_image_mime_type
        if state.reference_image_mime_type
        else None,
        reference_video_gcs=state.reference_video_gcs
        if state.reference_video_gcs
        else None,
        reference_video_mime_type=state.reference_video_mime_type
        if state.reference_video_mime_type
        else None,
        r2v_references=refs_list if refs_list else None,
    )

    try:
        model_config = get_omni_model_config(state.omni_model)
        gcs_uri, interaction_id = generate_omni_video(req)

        state.result_gcs_uri = gcs_uri
        state.result_display_url = create_display_url(gcs_uri)
        state.previous_interaction_id = interaction_id

        # Hydrate initial chat history JSON
        history = [
            {
                "type": "user_input",
                "content": [{"type": "text", "text": state.prompt}],
            },
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "video",
                        "gcs_uri": gcs_uri,
                        "mime_type": "video/mp4",
                    },
                ],
            },
        ]
        state.chat_history_json = json.dumps(history)

        # Hydrate UI message representations
        ui_messages = [
            {"role": "user", "text": state.prompt},
            {
                "role": "model",
                "text": state.prompt,
                "video_url": state.result_display_url,
                "gcs_uri": gcs_uri,
            },
        ]
        state.chat_messages_json = json.dumps(ui_messages)

        # Log item to library
        item = MediaItem(
            gcs_uris=[gcs_uri],
            prompt=state.prompt,
            mime_type="video/mp4",
            aspect=state.aspect_ratio,
            resolution=state.resolution,
            user_email=app_state.user_email,
            model=model_config.model_name,
            comment=f"Generated via Gemini Omni mode: {state.omni_mode}",
        )
        add_media_item_to_firestore(item)

    except Exception as ex:  # noqa: BLE001
        state.error_message = f"Failed to generate video: {ex}"
        state.show_error_dialog = True
    finally:
        state.is_loading = False
        yield


def on_send_chat_turn(_e: me.ClickEvent) -> Generator[None]:
    """Execute a multi-turn refinement chat edit step."""
    state = me.state(PageState)
    app_state = me.state(AppState)

    if not state.omni_prompt_input:
        yield
        return

    state.is_loading = True
    yield

    chat_prompt = state.omni_prompt_input
    state.omni_prompt_input = ""

    ui_messages = json.loads(state.chat_messages_json)
    ui_messages.append({"role": "user", "text": chat_prompt})
    state.chat_messages_json = json.dumps(ui_messages)
    yield

    # Prepare Request
    req = OmniVideoGenerationRequest(
        prompt=chat_prompt,
        duration_seconds=state.video_length,
        aspect_ratio=state.aspect_ratio,
        resolution=state.resolution,
        omni_mode=state.omni_mode,
        model_version_id=state.omni_model,
        previous_interaction_id=state.previous_interaction_id,
        chat_history_json=state.chat_history_json,
    )

    try:
        model_config = get_omni_model_config(state.omni_model)
        # Call model
        gcs_uri, interaction_id = generate_omni_video(req)

        state.result_gcs_uri = gcs_uri
        state.result_display_url = create_display_url(gcs_uri)
        state.previous_interaction_id = interaction_id

        # Update JSON history structures for SDK
        history = json.loads(state.chat_history_json)
        history.append(
            {
                "type": "user_input",
                "content": [{"type": "text", "text": chat_prompt}],
            },
        )
        history.append(
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "video",
                        "gcs_uri": gcs_uri,
                        "mime_type": "video/mp4",
                    },
                ],
            },
        )
        state.chat_history_json = json.dumps(history)

        # Update UI messages with model bubble
        ui_messages.append(
            {
                "role": "model",
                "text": chat_prompt,
                "video_url": state.result_display_url,
                "gcs_uri": gcs_uri,
            },
        )
        state.chat_messages_json = json.dumps(ui_messages)

        # Log item to library
        item = MediaItem(
            gcs_uris=[gcs_uri],
            prompt=chat_prompt,
            mime_type="video/mp4",
            aspect=state.aspect_ratio,
            resolution=state.resolution,
            user_email=app_state.user_email,
            model=model_config.model_name,
            comment="Refined via Gemini Omni chat",
        )
        add_media_item_to_firestore(item)

    except Exception as ex:  # noqa: BLE001
        state.error_message = f"Failed to refine video: {ex}"
        state.show_error_dialog = True
        ui_messages = json.loads(state.chat_messages_json)
        if ui_messages and ui_messages[-1]["role"] == "user":
            ui_messages.pop()
        state.chat_messages_json = json.dumps(ui_messages)
    finally:
        state.is_loading = False
        yield


def on_reset_chat(_e: me.ClickEvent) -> Generator[None]:
    """Reset the chat thread and history states back to single-turn."""
    state = me.state(PageState)
    state.previous_interaction_id = ""
    state.chat_history_json = "[]"
    state.chat_messages_json = "[]"
    state.result_gcs_uri = ""
    state.result_display_url = ""
    yield
