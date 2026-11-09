# Copyright 2024 Google LLC
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
"""Veo mesop UI page."""

import datetime  # Required for timestamp
import json
import time

import mesop as me

from common.analytics import log_ui_click, track_click
from common.error_handling import AsyncVeoPollingFailedError, GenerationError
from common.metadata import (
    MediaItem,
    add_media_item_to_firestore,
    get_media_item_by_id,
)
from common.storage import store_to_gcs
from common.utils import create_display_url, get_image_dimensions_from_base64
from common.veo_utils import start_async_veo_job
from components.dialog import dialog, dialog_actions
from components.header import header
from components.library.events import LibrarySelectionChangeEvent
from components.omni_hint.omni_hint import omni_hint
from components.page_scaffold import page_frame, page_scaffold
from components.veo.generation_controls import generation_controls
from components.veo.prompt_inputs import prompt_inputs
from components.veo.veo_modes import veo_modes
from components.veo.video_display import video_display
from config.default import ABOUT_PAGE_CONTENT, Default
from config.rewriters import VIDEO_REWRITER
from config.veo_models import get_veo_model_config
from models.gemini import rewriter
from models.model_setup import VeoModelSetup
from models.veo import APIReferenceImage, VideoGenerationRequest, generate_video
from state.state import AppState
from state.veo_state import PageState

config = Default()

veo_model = VeoModelSetup.init()


def on_veo_load(e: me.LoadEvent):
    """Handles page load events, including query parameters for deep linking."""
    state = me.state(PageState)
    image_path = me.query_params.get("image_path")  # Changed from image_uri
    veo_model_param = me.query_params.get("veo_model")

    if veo_model_param:
        _update_state_for_new_model(veo_model_param)

    if image_path:
        # When an image is passed, default to the i2v mode and Veo 3.1 Fast model.
        _update_state_for_new_model("3.1-fast")

        image_uri = ""
        if image_path.startswith("https://"):
            from common.utils import https_url_to_gcs_uri

            image_uri = https_url_to_gcs_uri(image_path)
        else:
            # Reconstruct the full GCS URI from the path for backward compatibility
            image_uri = f"gs://{image_path}"

        # Set the image from the query parameter
        state.reference_image_gcs = image_uri
        state.reference_image_uri = create_display_url(image_uri)
        # Switch to the Image-to-Video tab
        state.veo_mode = "i2v"
        # Provide a default prompt for a better user experience
        state.veo_prompt_input = "Animate this image with subtle motion."

    yield


@me.page(
    path="/veo",
    title="Veo - GenMedia Creative Studio",
    on_load=on_veo_load,
)
def veo_page():
    """Main Page."""
    state = me.state(AppState)
    with page_scaffold(page_name="veo"):  # pylint: disable=not-context-manager
        veo_content(state)


def on_selection_change_person_generation(e: me.SelectSelectionChangeEvent):
    """Handles changes to the person generation setting."""
    app_state = me.state(AppState)
    log_ui_click(
        element_id="veo_person_generation",
        page_name=app_state.current_page,
        session_id=app_state.session_id,
        extras={"value": e.value},
    )
    state = me.state(PageState)
    state.person_generation = e.value
    yield


def on_change_video_length_select(e: me.SelectSelectionChangeEvent):
    """Handles changes to the video length select dropdown."""
    state = me.state(PageState)
    state.video_length = int(e.value)
    yield


def on_selection_change_aspect_ratio(e: me.SelectSelectionChangeEvent):
    """Handles changes to the aspect ratio setting."""
    state = me.state(PageState)
    state.aspect_ratio = e.value
    yield


def on_selection_change_resolution(e: me.SelectSelectionChangeEvent):
    """Handles changes to the resolution setting."""
    state = me.state(PageState)
    state.resolution = e.value
    yield


def on_selection_change_video_count(e: me.SelectSelectionChangeEvent):
    """Handles changes to the video count slider."""
    state = me.state(PageState)
    state.video_count = int(e.value)
    yield


def _update_state_for_new_model(model_version_id: str):
    """Update state when the model changes."""
    state = me.state(PageState)
    state.veo_model = model_version_id

    # Get the config for the NEW model
    new_model_config = get_veo_model_config(model_version_id)
    if new_model_config:
        # If the current mode is not supported by the new model, reset to default 't2v'.
        if state.veo_mode not in new_model_config.supported_modes:
            state.veo_mode = "t2v"

        # If the new model has a specific list of supported durations (discontinuous values)
        if new_model_config.supported_durations:
            # Check if the current video length is in the allowed list.
            if state.video_length not in new_model_config.supported_durations:
                # If not, reset to the model's default duration.
                state.video_length = new_model_config.default_duration
        # Otherwise, use the continuous min/max range
        else:
            min_dur = new_model_config.min_duration
            max_dur = new_model_config.max_duration
            if not (min_dur <= state.video_length <= max_dur):
                state.video_length = new_model_config.default_duration

        # Check for aspect ratio override for the current mode
        if (
            new_model_config.mode_overrides
            and state.veo_mode in new_model_config.mode_overrides
        ):
            override = new_model_config.mode_overrides[state.veo_mode]
            if (
                override.supported_aspect_ratios
                and state.aspect_ratio not in override.supported_aspect_ratios
            ):
                state.aspect_ratio = override.supported_aspect_ratios[0]

        # Ensure selected resolution is supported by the new model
        if state.resolution not in new_model_config.resolutions:
            state.resolution = new_model_config.resolutions[0]

        # Force auto-enhance prompt if required
        if new_model_config.requires_prompt_enhancement:
            state.auto_enhance_prompt = True


def on_selection_change_veo_model(e: me.SelectSelectionChangeEvent):
    """Handle changes to the Veo model selection."""
    _update_state_for_new_model(e.value)
    yield


def on_change_auto_enhance_prompt(e: me.CheckboxChangeEvent):
    """Toggle auto-enhance prompt."""
    app_state = me.state(AppState)
    log_ui_click(
        element_id="veo_auto_enhance_prompt",
        page_name=app_state.current_page,
        session_id=app_state.session_id,
        extras={"checked": e.checked},
    )
    state = me.state(PageState)
    state.auto_enhance_prompt = e.checked
    yield



def on_blur_veo_seed(e: me.InputBlurEvent):
    """Handles blur event for the Veo seed input."""
    state = me.state(PageState)
    try:
        seed_value = int(e.value)
        state.veo_seed = seed_value if seed_value >= 0 else 0
    except ValueError:
        state.veo_seed = 0
    yield


def on_change_generate_audio(e: me.CheckboxChangeEvent):
    """Toggle audio generation."""
    app_state = me.state(AppState)
    log_ui_click(
        element_id="veo_generate_audio",
        page_name=app_state.current_page,
        session_id=app_state.session_id,
        extras={"checked": e.checked},
    )
    state = me.state(PageState)
    state.generate_audio = e.checked
    yield


def veo_content(app_state: me.state):
    """Veo Mesop Page."""
    state = me.state(PageState)

    if state.info_dialog_open:
        with dialog(is_open=state.info_dialog_open):  # pylint: disable=E1129:not-context-manager
            me.text("About Veo", type="headline-6")
            me.markdown(ABOUT_PAGE_CONTENT["sections"][1]["description"])
            me.divider()
            me.text("Current Settings", type="headline-6")
            me.text(f"Prompt: {state.veo_prompt_input}")
            me.text(f"Negative Prompt: {state.negative_prompt}")
            me.text(f"Model: {state.veo_model}")
            me.text(f"Duration: {state.video_length}s")

            # Mode-specific settings display
            if state.veo_mode == "i2v":
                if state.reference_image_gcs:
                    me.text(f"Input Image: {state.reference_image_gcs}")
            elif state.veo_mode == "interpolation":
                if state.reference_image_gcs:
                    me.text(f"First Frame: {state.reference_image_gcs}")
                if state.last_reference_image_gcs:
                    me.text(f"Last Frame: {state.last_reference_image_gcs}")
            elif state.veo_mode == "r2v":
                if state.r2v_reference_images:
                    me.text(f"Asset Images: {len(state.r2v_reference_images)} selected")
                if state.r2v_style_image:
                    me.text(f"Style Image: {state.r2v_style_image}")

            with dialog_actions():  # pylint: disable=E1129:not-context-manager
                me.button("Close", on_click=close_info_dialog, type="flat")

    with page_frame():  # pylint: disable=E1129:not-context-manager
        header("Veo", "movie", show_info_button=True, on_info_click=open_info_dialog)
        omni_hint()

        # Main container with a column direction
        with me.box(style=me.Style(display="flex", flex_direction="column", gap=20)):
            # --- TOP ROW ---
            # A nested container with a row direction
            with me.box(style=me.Style(display="flex", flex_direction="row", gap=10)):
                # Left column of the top row
                with me.box(
                    style=me.Style(
                        flex_basis="max(480px, calc(60% - 48px))",
                        display="flex",
                        flex_direction="column",
                        gap=10,
                    )
                ):
                    prompt_inputs(
                        on_click_generate=on_click_veo,
                        on_click_rewrite=on_click_custom_rewriter,
                        on_click_clear=on_click_clear,
                        on_blur_prompt=on_blur_veo_prompt,
                        on_blur_negative_prompt=on_blur_negative_prompt,
                    )

                # Right column of the top row
                veo_modes(
                    on_upload_image=on_upload_image,
                    on_upload_last_image=on_upload_last_image,
                    on_library_select=on_veo_image_from_library,
                    on_r2v_asset_add=on_r2v_asset_add,
                    on_r2v_asset_remove=on_r2v_asset_remove,
                    on_r2v_style_add=on_r2v_style_add,
                    on_r2v_style_remove=on_r2v_style_remove,
                    on_click_clear=on_click_clear,
                    on_clear_first_image=on_clear_first_image,
                    on_clear_last_image=on_clear_last_image,
                )

            # --- SECOND ROW ---
            # This component will now be in its own row underneath
            generation_controls(
                on_selection_change_veo_model=on_selection_change_veo_model,
                on_selection_change_aspect_ratio=on_selection_change_aspect_ratio,
                on_selection_change_resolution=on_selection_change_resolution,
                on_change_video_length_select=on_change_video_length_select,
                on_selection_change_video_count=on_selection_change_video_count,
                on_selection_change_person_generation=on_selection_change_person_generation,
                on_change_auto_enhance_prompt=on_change_auto_enhance_prompt,
                on_change_generate_audio=on_change_generate_audio,
                on_blur_veo_seed=on_blur_veo_seed,
            )

        me.box(style=me.Style(height=50))

        video_display(
            on_thumbnail_click=on_thumbnail_click,
            on_click_extend=on_click_extend_video,
        )

    with dialog(is_open=state.show_error_dialog):  # pylint: disable=E1129:not-context-manager
        me.text(
            "Generation Error",
            type="headline-6",
            style=me.Style(color=me.theme_var("error")),
        )
        me.text(state.error_message, style=me.Style(margin=me.Margin(top=16)))
        with dialog_actions():  # pylint: disable=E1129:not-context-manager
            me.button("Close", on_click=on_close_error_dialog, type="flat")


def on_click_extend_video(e: me.ClickEvent):
    """Handles the click event for the Veo video extension."""
    state = me.state(PageState)
    app_state = me.state(AppState)

    # --- Input Validation ---
    if not state.veo_prompt_input:
        state.error_message = "Please enter a prompt for the extension."
        state.show_error_dialog = True
        yield
        return

    # --- Model Validation ---
    model_config = get_veo_model_config(state.veo_model)
    if not model_config or not model_config.supports_video_extension:
        state.error_message = "Video extension is not supported by the current model."
        state.show_error_dialog = True
        yield
        return

    # --- Video Selection Validation ---
    video_to_extend_url = (
        state.selected_video_url
        if state.selected_video_url
        else state.result_display_urls[0]
    )
    if not video_to_extend_url:
        state.error_message = "No video selected to extend."
        state.show_error_dialog = True
        yield
        return

    # Convert display URL back to GCS URI
    from common.utils import https_url_to_gcs_uri

    video_input_gcs = https_url_to_gcs_uri(video_to_extend_url)

    # --- Reset State for New Generation ---
    state.is_loading = True
    state.error_message = ""
    state.result_video = ""
    state.result_gcs_uris = []
    state.result_display_urls = []
    state.selected_video_url = ""
    state.timing = "Extending video..."
    start_time = time.time()
    yield

    # --- Prepare Request Data ---
    request = VideoGenerationRequest(
        prompt=state.veo_prompt_input,
        negative_prompt=state.negative_prompt,
        model_version_id=state.veo_model,
        aspect_ratio=state.aspect_ratio,
        resolution=state.resolution,
        duration_seconds=state.video_extend_length,  # Use extension length
        video_count=state.video_count,
        enhance_prompt=state.auto_enhance_prompt,
        seed=state.veo_seed if state.veo_seed > 0 else None,
        generate_audio=state.generate_audio,
        person_generation=state.person_generation,
        video_input_gcs=video_input_gcs,
        video_input_mime_type="video/mp4",  # Assumed MP4
    )

    # --- 1. Initiate Async Job ---
    try:
        data = start_async_veo_job(request, app_state.user_email, mode="extension")

        state.current_job_id = data["job_id"]
        state.job_status = data["status"]
        yield
    except Exception as e:
        state.error_message = f"Failed to start extension job: {e}"
        state.show_error_dialog = True
        state.is_loading = False
        yield
        return

    # --- 2. Poll for Completion ---
    while state.job_status in ["pending", "processing", "created"]:
        time.sleep(2)
        try:
            item = get_media_item_by_id(state.current_job_id)
            if not item:
                raise AsyncVeoPollingFailedError(
                    f"Job {state.current_job_id} not found in Firestore."
                )

            state.job_status = item.status

            if state.job_status == "complete":
                # Success! Update state with results.
                state.result_gcs_uris = item.gcs_uris or []
                if not state.result_gcs_uris and item.gcsuri:
                    state.result_gcs_uris = [item.gcsuri]

                state.result_display_urls = [
                    create_display_url(uri) for uri in state.result_gcs_uris
                ]
                if state.result_display_urls:
                    state.selected_video_url = state.result_display_urls[0]

                end_time = time.time()
                execution_time = end_time - start_time
                state.timing = f"Extension time: {round(execution_time)} seconds"
                state.is_loading = False
                yield
                break

            elif state.job_status == "failed":
                state.error_message = (
                    item.error_message or "Unknown error during extension."
                )
                state.show_error_dialog = True
                state.is_loading = False
                yield
                break

            yield

        except Exception as e:
            error = AsyncVeoPollingFailedError(f"Polling failed: {e}")
            state.error_message = str(error)
            state.show_error_dialog = True
            state.is_loading = False
            yield
            break


def on_input_prompt(e: me.InputEvent):
    state = me.state(PageState)
    state.prompt = e.value
    yield


def on_blur_negative_prompt(e: me.InputBlurEvent):
    state = me.state(PageState)
    state.negative_prompt = e.value
    yield


@track_click(element_id="veo_clear_button")
def on_click_clear(e: me.ClickEvent):  # pylint: disable=unused-argument
    """Clear prompt and video."""
    state = me.state(PageState)
    state.result_gcs_uris = []
    state.result_display_urls = []
    state.selected_video_url = ""
    state.prompt = None
    state.negative_prompt = ""
    state.veo_prompt_input = None
    state.original_prompt = None
    state.veo_prompt_textarea_key += 1
    state.veo_model = "3.1-fast"
    # Get default duration for the reset model
    model_config = get_veo_model_config(state.veo_model)
    state.video_length = model_config.default_duration if model_config else 8
    state.aspect_ratio = "16:9"
    # Clear all image types
    state.reference_image_gcs = None
    state.reference_image_uri = None
    state.last_reference_image_gcs = None
    state.last_reference_image_uri = None
    state.r2v_reference_images = []
    state.r2v_reference_mime_types = []
    state.r2v_style_image = None
    state.r2v_style_image_mime_type = None
    yield


def on_clear_first_image(e: me.ClickEvent):  # pylint: disable=unused-argument
    """Clears the first reference image for i2v or interpolation."""
    state = me.state(PageState)
    state.reference_image_gcs = None
    state.reference_image_uri = None
    yield


def on_clear_last_image(e: me.ClickEvent):  # pylint: disable=unused-argument
    """Clears the last reference image for interpolation."""
    state = me.state(PageState)
    state.last_reference_image_gcs = None
    state.last_reference_image_uri = None
    yield


@track_click(element_id="veo_rewrite_button")
def on_click_custom_rewriter(e: me.ClickEvent):  # pylint: disable=unused-argument
    """Veo custom rewriter."""
    state = me.state(PageState)
    if not state.veo_prompt_input:
        print("Prompt is empty, skipping rewrite.")
        yield
        return

    # Gather mode-appropriate reference images so the rewriter has visual
    # context. Each entry is a (gcs_uri, mime_type) pair; empty URIs are skipped
    # by the rewriter. Use the mime types stored in state (not a hardcoded
    # image/png) for correctness.
    images: list[tuple[str, str]] = []
    if state.veo_mode == "i2v":
        if state.reference_image_gcs:
            images.append(
                (state.reference_image_gcs, state.reference_image_mime_type)
            )
    elif state.veo_mode == "interpolation":
        if state.reference_image_gcs:
            images.append(
                (state.reference_image_gcs, state.reference_image_mime_type)
            )
        if state.last_reference_image_gcs:
            images.append(
                (
                    state.last_reference_image_gcs,
                    state.last_reference_image_mime_type,
                )
            )
    elif state.veo_mode == "r2v":
        images.extend(
            zip(state.r2v_reference_images, state.r2v_reference_mime_types)
        )
        # NOTE: r2v_style_image is deliberately NOT included: a style image
        # influences the look, not the content, of the rewrite. This is an
        # easily-changed default if owner preference shifts.

    rewritten_prompt = rewriter(
        state.veo_prompt_input, VIDEO_REWRITER, images=images
    )
    state.veo_prompt_input = rewritten_prompt
    state.veo_prompt_placeholder = rewritten_prompt
    yield


@track_click(element_id="veo_create_button")
def on_click_veo(e: me.ClickEvent):  # pylint: disable=unused-argument
    """Handles the click event for the Veo generation button."""
    state = me.state(PageState)
    app_state = me.state(AppState)

    # --- Input Validation ---
    if not state.veo_prompt_input:
        state.error_message = "Please enter a prompt."
        state.show_error_dialog = True
        yield
        return

    # --- Reset State for New Generation ---
    state.is_loading = True
    state.error_message = ""
    state.result_video = ""
    state.result_gcs_uris = []
    state.result_display_urls = []
    state.selected_video_url = ""
    state.timing = ""
    start_time = time.time()
    yield

    # --- Prepare Request Data ---
    # (Logic copied from original to maintain parity)
    request = VideoGenerationRequest(
        prompt=state.veo_prompt_input,
        negative_prompt=state.negative_prompt,
        model_version_id=state.veo_model,
        aspect_ratio=state.aspect_ratio,
        resolution=state.resolution,
        duration_seconds=state.video_length,
        video_count=state.video_count,
        enhance_prompt=state.auto_enhance_prompt,
        seed=state.veo_seed if state.veo_seed > 0 else None,
        generate_audio=state.generate_audio,
        person_generation=state.person_generation,
        reference_image_gcs=state.reference_image_gcs
        if state.veo_mode in ["i2v", "r2v", "interpolation"]
        and state.reference_image_gcs
        else None,
        reference_image_mime_type=state.reference_image_mime_type,
        last_reference_image_gcs=state.last_reference_image_gcs
        if state.veo_mode == "interpolation" and state.last_reference_image_gcs
        else None,
        last_reference_image_mime_type=state.last_reference_image_mime_type,
        r2v_references=[
            APIReferenceImage(gcs_uri=uri, mime_type=mime)
            for uri, mime in zip(
                state.r2v_reference_images, state.r2v_reference_mime_types
            )
        ]
        if state.veo_mode == "r2v" and state.r2v_reference_images
        else None,
        r2v_style_image=APIReferenceImage(
            gcs_uri=state.r2v_style_image, mime_type=state.r2v_style_image_mime_type
        )
        if state.veo_mode == "r2v" and state.r2v_style_image
        else None,
    )

    # --- 1. Initiate Async Job ---
    try:
        data = start_async_veo_job(request, app_state.user_email, mode=state.veo_mode)

        state.current_job_id = data["job_id"]
        state.job_status = data["status"]
        yield
    except Exception as e:
        state.error_message = f"Failed to start generation job: {e}"
        state.show_error_dialog = True
        state.is_loading = False
        yield
        return

    # --- 2. Poll for Completion ---
    # NOTE: In a real production app, consider using a more robust polling mechanism
    # or WebSockets if available. For now, this simple loop with yields works
    # within Mesop's generator-based event handlers to keep the UI responsive.
    while state.job_status in ["pending", "processing", "created"]:
        time.sleep(2)
        try:
            item = get_media_item_by_id(state.current_job_id)
            if not item:
                raise AsyncVeoPollingFailedError(
                    f"Job {state.current_job_id} not found in Firestore."
                )

            state.job_status = item.status

            if state.job_status == "complete":
                # Success! Update state with results.
                state.result_gcs_uris = item.gcs_uris or []
                # If only one URI is returned but we expected a list, handle it.
                if not state.result_gcs_uris and item.gcsuri:
                    state.result_gcs_uris = [item.gcsuri]

                state.result_display_urls = [
                    create_display_url(uri) for uri in state.result_gcs_uris
                ]
                if state.result_display_urls:
                    state.selected_video_url = state.result_display_urls[0]

                end_time = time.time()
                execution_time = end_time - start_time
                state.timing = f"Generation time: {round(execution_time)} seconds"
                state.is_loading = False
                yield
                break

            elif state.job_status == "failed":
                # Failure. Show error.
                state.error_message = (
                    item.error_message or "Unknown error during generation."
                )
                state.show_error_dialog = True
                state.is_loading = False
                yield
                break

            # Still polling...
            yield

        except Exception as e:
            error = AsyncVeoPollingFailedError(f"Polling failed: {e}")
            state.error_message = str(error)
            state.show_error_dialog = True
            state.is_loading = False
            yield
            break


def on_blur_veo_prompt(e: me.InputBlurEvent):
    """Veo prompt blur event."""
    state = me.state(PageState)
    state.veo_prompt_input = e.value
    yield


def on_thumbnail_click(e: me.ClickEvent):
    """Sets the clicked thumbnail as the main selected video."""
    state = me.state(PageState)
    state.selected_video_url = e.key
    yield


def on_close_error_dialog(e: me.ClickEvent):  # pylint: disable=unused-argument
    """Handler to close the error dialog."""
    state = me.state(PageState)
    state.show_error_dialog = False
    yield


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


def on_upload_image(e: me.UploadEvent):
    """Upload image to GCS and update state."""
    state = me.state(PageState)
    try:
        # Store the uploaded file to GCS
        gcs_path = store_to_gcs(
            "uploads", e.file.name, e.file.mime_type, e.file.getvalue()
        )
        # Update the state with the new image details
        state.reference_image_gcs = gcs_path
        state.reference_image_uri = create_display_url(gcs_path)
        state.reference_image_mime_type = e.file.mime_type
        print(f"Image uploaded to {gcs_path} with mime type {e.file.mime_type}")
    except Exception as ex:
        state.error_message = f"Failed to upload image: {ex}"
        state.show_error_dialog = True
    yield


def on_upload_last_image(e: me.UploadEvent):
    """Upload last image to GCS and update state."""
    state = me.state(PageState)
    try:
        # Store the uploaded file to GCS
        gcs_path = store_to_gcs(
            "uploads", e.file.name, e.file.mime_type, e.file.getvalue()
        )
        # Update the state with the new image details
        state.last_reference_image_gcs = gcs_path
        state.last_reference_image_uri = create_display_url(gcs_path)
        state.last_reference_image_mime_type = e.file.mime_type
    except Exception as ex:
        state.error_message = f"Failed to upload image: {ex}"
        state.show_error_dialog = True
    yield


def on_r2v_asset_add(e: me.UploadEvent):
    """Adds a new asset reference image for R2V mode."""
    state = me.state(PageState)
    if len(state.r2v_reference_images) >= 3:
        state.error_message = "You can upload a maximum of 3 asset images."
        state.show_error_dialog = True
        yield
        return

    try:
        gcs_path = store_to_gcs(
            "uploads", e.file.name, e.file.mime_type, e.file.getvalue()
        )
        state.r2v_reference_images.append(gcs_path)
        state.r2v_reference_mime_types.append(e.file.mime_type)
    except Exception as ex:
        state.error_message = f"Failed to upload image: {ex}"
        state.show_error_dialog = True
    yield


def on_r2v_asset_remove(e: me.ClickEvent):
    """Removes an asset reference image from the R2V list."""
    state = me.state(PageState)
    index_to_remove = int(e.key)
    if 0 <= index_to_remove < len(state.r2v_reference_images):
        state.r2v_reference_images.pop(index_to_remove)
        state.r2v_reference_mime_types.pop(index_to_remove)
    yield


def on_r2v_style_add(e: me.UploadEvent):
    """Adds a style reference image for R2V mode."""
    state = me.state(PageState)
    try:
        gcs_path = store_to_gcs(
            "uploads", e.file.name, e.file.mime_type, e.file.getvalue()
        )
        state.r2v_style_image = gcs_path
        state.r2v_style_image_mime_type = e.file.mime_type
    except Exception as ex:
        state.error_message = f"Failed to upload image: {ex}"
        state.show_error_dialog = True
    yield


def on_r2v_style_remove(e: me.ClickEvent):
    """Removes the style reference image."""
    state = me.state(PageState)
    state.r2v_style_image = None
    state.r2v_style_image_mime_type = None
    yield


def on_veo_image_from_library(e: LibrarySelectionChangeEvent):
    """VEO image from library handler."""
    state = me.state(PageState)

    # Helper to infer mime type from extension
    def infer_mime(uri: str) -> str:
        if uri.lower().endswith(".png"):
            return "image/png"
        if uri.lower().endswith(".jpg") or uri.lower().endswith(".jpeg"):
            return "image/jpeg"
        if uri.lower().endswith(".webp"):
            return "image/webp"
        return "image/png"  # Default fallback

    if e.chooser_id.startswith("i2v") or e.chooser_id.startswith("first_frame"):
        state.reference_image_gcs = e.gcs_uri
        state.reference_image_uri = create_display_url(e.gcs_uri)
        state.reference_image_mime_type = infer_mime(e.gcs_uri)
    elif e.chooser_id.startswith("interpolation_last"):
        state.last_reference_image_gcs = e.gcs_uri
        state.last_reference_image_uri = create_display_url(e.gcs_uri)
        state.last_reference_image_mime_type = infer_mime(e.gcs_uri)
    elif e.chooser_id.startswith("r2v_asset_library_chooser"):
        if len(state.r2v_reference_images) >= 3:
            state.error_message = "You can upload a maximum of 3 asset images."
            state.show_error_dialog = True
            yield
            return
        state.r2v_reference_images.append(e.gcs_uri)
        state.r2v_reference_mime_types.append(infer_mime(e.gcs_uri))
    elif e.chooser_id.startswith("r2v_style_library_chooser"):
        state.r2v_style_image = e.gcs_uri
        state.r2v_style_image_mime_type = infer_mime(e.gcs_uri)

    yield
