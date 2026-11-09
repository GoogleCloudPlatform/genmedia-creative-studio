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

"""Interior Design page."""

import copy
import datetime
import json
from collections.abc import Callable
import time
import uuid


import mesop as me

from common import authz
from common.analytics import log_ui_click, track_click
from common.metadata import MediaItem, add_media_item_to_firestore, save_storyboard
from common.storage import store_to_gcs
from common.utils import create_display_url
from components.dialog import dialog
from components.header import header
from components.interior_design.design_studio import design_studio
from components.interior_design.floor_plan_uploader import floor_plan_uploader
from components.interior_design.generated_3d_view import generated_3d_view
from components.interior_design.room_selector import room_selector
from components.interior_design.room_view import room_view
from components.interior_design.storyboard_item_tile import storyboard_item_tile
from components.interior_design.storyboard_video_tile import storyboard_video_tile
from components.library.events import LibrarySelectionChangeEvent
from components.page_scaffold import page_frame, page_scaffold
from components.snackbar import snackbar
from config.default import Default as cfg
from models.gemini import (
    extract_room_names_from_image,
    generate_image_from_prompt_and_images,
)
from models.video_processing import process_videos
from models.workflow_video import generate_workflow_image_to_video
from state.interior_design_v2_state import PageState
from state.state import AppState

with open("config/about_content.json", "r") as f:
    about_content = json.load(f)
    INTERIOR_DESIGN_INFO = next(
        (s for s in about_content["sections"] if s.get("id") == "interior_design"),
        None,
    )


def on_load(e: me.LoadEvent):
    """Loads a storyboard from Firestore if an ID is provided in the URL."""
    state = me.state(PageState)
    app_state = me.state(AppState)
    if not state.initial_load_complete:
        storyboard_id = me.query_params.get("storyboard_id")
        if storyboard_id:
            from config.firebase_config import FirebaseClient

            db = FirebaseClient().get_client()
            doc_ref = db.collection("interior_design_storyboards").document(
                storyboard_id
            )
            # Owner-scoped read: only the storyboard's owner (or a legacy
            # ownerless doc) is returned. A non-owner load is indistinguishable
            # from not-found (fail-closed, no existence/content leak).
            storyboard = authz.authorize_read(
                doc_ref,
                "user_email",
                app_state.user_email,
                resource="storyboard",
            )
            if storyboard is not None:
                # Hydrate old data: generate display URLs if they don't exist.
                if storyboard.get("original_floor_plan_uri") and not storyboard.get(
                    "original_floor_plan_display_url"
                ):
                    storyboard["original_floor_plan_display_url"] = create_display_url(
                        storyboard["original_floor_plan_uri"]
                    )
                if storyboard.get("generated_3d_view_uri") and not storyboard.get(
                    "generated_3d_view_display_url"
                ):
                    storyboard["generated_3d_view_display_url"] = create_display_url(
                        storyboard["generated_3d_view_uri"]
                    )
                if storyboard.get("final_video_uri") and not storyboard.get(
                    "final_video_display_url"
                ):
                    storyboard["final_video_display_url"] = create_display_url(
                        storyboard["final_video_uri"]
                    )

                for item in storyboard.get("storyboard_items", []):
                    if item.get("styled_image_uri") and not item.get(
                        "styled_image_display_url"
                    ):
                        item["styled_image_display_url"] = create_display_url(
                            item["styled_image_uri"]
                        )
                    if item.get("generated_video_uri") and not item.get(
                        "generated_video_display_url"
                    ):
                        item["generated_video_display_url"] = create_display_url(
                            item["generated_video_uri"]
                        )

                state.storyboard = storyboard
                print(f"Loaded storyboard {storyboard_id} from Firestore.")
            else:
                yield from show_snackbar(
                    state, f"Could not find storyboard with ID: {storyboard_id}"
                )
        state.initial_load_complete = True
    yield


@me.page(
    path="/interior_design",
    title="Interior Design",
    on_load=on_load,
)
def interior_design_page():
    with page_scaffold(page_name="interior_design_v2"):  # pylint: disable=E1129:not-context-manager
        with page_frame():  # pylint: disable=E1129:not-context-manager
            header(
                "Interior Design",
                "chair",
                show_info_button=True,
                on_info_click=open_info_dialog,
            )
            page_content()


def page_content():
    state = me.state(PageState)

    if state.is_detail_dialog_open:
        item_detail_dialog(on_close=on_close_detail_dialog)

    snackbar(is_visible=state.show_snackbar, label=state.snackbar_message)

    if state.info_dialog_open:
        with dialog(is_open=state.info_dialog_open):  # pylint: disable=not-context-manager
            if INTERIOR_DESIGN_INFO:
                me.text(f"About {INTERIOR_DESIGN_INFO[title]}", type="headline-6")
                me.markdown(INTERIOR_DESIGN_INFO["description"])
            else:
                me.text("About Interior Design", type="headline-6")
                me.markdown("Information for this page has not been configured yet.")
            
            me.divider()
            me.text("Current Settings", type="headline-6")
            me.text(f"Image Model: {cfg.INTERIOR_DESIGN_IMAGE_MODEL}")
            me.text(f"Video Model: {cfg.INTERIOR_DESIGN_VIDEO_MODEL}")
            me.text(f"Video Duration: {cfg.INTERIOR_DESIGN_VIDEO_DURATION} seconds")
            
            with me.box(style=me.Style(margin=me.Margin(top=16))):
                me.button("Close", on_click=close_info_dialog, type="flat")

    with me.box(
        style=me.Style(
            display="flex", flex_direction="column", gap=24, align_items="center"
        )
    ):
        # Input and Output Area
        with me.box(
            style=me.Style(
                display="flex", flex_direction="row", gap=32, justify_content="center"
            )
        ):
            floor_plan_uploader(
                storyboard=state.storyboard,
                on_upload=on_upload_floor_plan,
                on_library_select=on_select_floor_plan,
            )
            generated_3d_view(
                storyboard=state.storyboard,
                is_generating=state.is_generating,
                on_generate=on_generate_3d_view_click,
            )

        if state.storyboard and state.storyboard.get("room_names"):
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="column",
                    align_items="center",
                    gap=10,
                )
            ):
                me.text("Identified Rooms", type="headline-6")
                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="row",
                        gap=10,
                        flex_wrap="wrap",
                        justify_content="center",
                    )
                ):
                    for room in state.storyboard["room_names"]:
                        with me.content_button(
                            key=room, on_click=on_room_button_click, type="stroked"
                        ):
                            if (
                                state.is_generating_zoom
                                and state.storyboard.get("selected_room") == room
                            ):
                                me.progress_spinner(diameter=18)
                            else:
                                me.text(room)

        # Display the zoomed-in room view and design controls
        if state.storyboard and state.storyboard.get("storyboard_items"):
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="row",
                    gap=24,
                    margin=me.Margin(top=24),
                    width="100%",
                    justify_content="center",
                )
            ):
                room_view(
                    storyboard=state.storyboard,
                    is_generating_zoom=state.is_generating_zoom,
                )
                design_studio(
                    storyboard_item=next(
                        (
                            item
                            for item in state.storyboard["storyboard_items"]
                            if item["room_name"] == state.storyboard["selected_room"]
                        ),
                        None,
                    ),
                    design_image_display_url=state.design_image_display_url,
                    is_designing=state.is_designing,
                    on_upload_design_image=on_upload_design_image,
                    on_select_design_image=on_select_design_image,
                    on_design_prompt_input=on_design_prompt_input,
                    on_clear_design=on_clear_design,
                    on_design_click=on_design_click,
                )

        # Storyboard Carousel
        if state.storyboard and state.storyboard.get("storyboard_items"):
            with me.box(
                style=me.Style(
                    width="100%",
                    margin=me.Margin(top=32),
                )
            ):
                me.text(
                    "Storyboard",
                    type="headline-6",
                    style=me.Style(margin=me.Margin(bottom=16), text_align="center"),
                )
                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="row",
                        gap=16,
                        overflow_x="auto",
                        padding=me.Padding(bottom=16),  # for scrollbar
                    )
                ):
                    for item in state.storyboard["storyboard_items"]:
                        if item.get("generated_video_uri"):
                            storyboard_video_tile(
                                key=item["room_name"],
                                video_url=item.get("generated_video_display_url", ""),
                                room_name=item["room_name"],
                                on_click=on_open_detail_dialog_click,
                            )
                        elif item.get("styled_image_uri"):  # Use .get() for safety
                            storyboard_item_tile(
                                key=item["room_name"],
                                image_url=item.get("styled_image_display_url", ""),
                                room_name=item["room_name"],
                                on_click=on_storyboard_item_click,
                            )
                with me.box(
                    style=me.Style(
                        width="100%", text_align="center", margin=me.Margin(top=24)
                    )
                ):
                    with me.content_button(
                        on_click=on_generate_video_click,
                        type="raised",
                        disabled=state.is_generating_video
                        or not state.storyboard.get("storyboard_items"),
                    ):
                        if state.is_generating_video:
                            with me.box(
                                style=me.Style(
                                    display="flex", align_items="center", gap=8
                                )
                            ):
                                me.progress_spinner(diameter=18)
                                me.text(state.video_generation_status)
                        else:
                            me.text("Generate Video")

                final_video_uri = state.storyboard.get("final_video_uri")
                if final_video_uri:
                    with me.box(
                        style=me.Style(
                            margin=me.Margin(top=24),
                            display="flex",
                            justify_content="center",
                        )
                    ):
                        me.video(
                            src=state.storyboard.get("final_video_display_url", ""),
                            style=me.Style(
                                width="100%", max_width="720px", border_radius=8
                            ),
                        )


def show_snackbar(state: PageState, message: str):
    """Displays a snackbar message at the bottom of the page."""
    state.snackbar_message = message
    state.show_snackbar = True
    yield


# --- Event Handlers ---


def on_upload_floor_plan(e: me.UploadEvent):
    """Upload floor plan handler."""
    state = me.state(PageState)
    app_state = me.state(AppState)
    file = e.files[0]
    gcs_url = store_to_gcs(
        "interior_design_uploads", file.name, file.mime_type, file.getvalue()
    )
    state.storyboard = {
        "user_email": app_state.user_email,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "original_floor_plan_uri": gcs_url,
        "original_floor_plan_display_url": create_display_url(gcs_url),
        "room_names": [],
        "storyboard_items": [],
        "selected_room": "",
    }
    state.storyboard = save_storyboard(state.storyboard)
    print(f"storyboard created: {state.storyboard}")
    yield


def on_select_floor_plan(e: LibrarySelectionChangeEvent):
    """Floor plan selection from library handler."""
    state = me.state(PageState)
    app_state = me.state(AppState)
    state.storyboard = {
        "user_email": app_state.user_email,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "original_floor_plan_uri": e.gcs_uri,
        "original_floor_plan_display_url": create_display_url(e.gcs_uri),
        "room_names": [],
        "storyboard_items": [],
        "selected_room": "",
    }
    state.storyboard = save_storyboard(state.storyboard)
    print(f"storyboard created: {state.storyboard}")
    yield


@track_click(element_id="interior_design_generate_3d_view_button")
def on_generate_3d_view_click(e: me.ClickEvent):
    """Handles the 3D view generation."""
    state = me.state(PageState)
    state.is_generating = True
    state.storyboard["generated_3d_view_uri"] = ""
    state.storyboard["room_names"] = []
    state.error_message = ""
    yield

    try:
        prompt = "create a 3D version for the floor plan. make it realistic. keep the furnitures as per the floor plan and follow the measurement. retain the names of rooms in the appropriate location"

        gcs_uris, _, _, _, _ = generate_image_from_prompt_and_images(
            prompt=prompt,
            images=[state.storyboard["original_floor_plan_uri"]],
            aspect_ratio="16:9",
            gcs_folder="interior_design_generations",
        model_name=cfg.INTERIOR_DESIGN_IMAGE_MODEL,
        )

        if gcs_uris:
            state.storyboard["generated_3d_view_uri"] = gcs_uris[0]
            state.storyboard["generated_3d_view_display_url"] = create_display_url(
                gcs_uris[0]
            )

            try:
                room_names = extract_room_names_from_image(
                    state.storyboard["original_floor_plan_uri"]
                )
                if not room_names:
                    yield from show_snackbar(
                        state, "No rooms were identified in the floor plan."
                    )
                state.storyboard["room_names"] = room_names
            except Exception as room_ex:
                print(f"Could not extract room names: {room_ex}")
                yield from show_snackbar(
                    state,
                    "An error occurred while extracting room names from the floor plan.",
                )

        else:
            yield from show_snackbar(
                state, "Image generation failed to return a result."
            )

    except Exception as ex:
        yield from show_snackbar(state, f"An error occurred during generation: {ex}")
    finally:
        state.is_generating = False
        state.storyboard = save_storyboard(state.storyboard)
        yield


@track_click(element_id="interior_design_room_button")
def on_room_button_click(e: me.ClickEvent):
    """Handles the generation of a zoomed-in view for a specific room."""
    state = me.state(PageState)
    state.design_prompt = ""
    room_name = e.key

    storyboard_item = next(
        (
            item
            for item in state.storyboard["storyboard_items"]
            if item["room_name"] == room_name
        ),
        None,
    )
    if not storyboard_item:
        storyboard_item = {
            "room_name": room_name,
            "styled_image_uri": "",
            "style_history": [],
        }
        state.storyboard["storyboard_items"].append(storyboard_item)

    state.is_generating_zoom = True
    state.storyboard["selected_room"] = room_name
    storyboard_item["styled_image_uri"] = ""
    yield

    try:
        prompt = f"Using the provided 3D rendering as a layout guide, create a photorealistic interior photograph. The photo should be from a first-person perspective, as if a person is standing in the hallway or adjacent room and looking through the doorway into the {room_name}. Capture the sense of entering the room for the first time on a house tour. Ensure the lighting and furniture placement are consistent with the 3D model."

        gcs_uris, _, _, _, _ = generate_image_from_prompt_and_images(
            prompt=prompt,
            images=[state.storyboard["generated_3d_view_uri"]],
            aspect_ratio="16:9",
            gcs_folder="interior_design_zoomed_views",
        model_name=cfg.INTERIOR_DESIGN_IMAGE_MODEL,
        )

        if gcs_uris:
            storyboard_item["styled_image_uri"] = gcs_uris[0]
            storyboard_item["styled_image_display_url"] = create_display_url(
                gcs_uris[0]
            )
            storyboard_item["style_history"].append(gcs_uris[0])
        else:
            yield from show_snackbar(
                state, "Zoomed view generation failed to return a result."
            )

    except Exception as ex:
        yield from show_snackbar(
            state, f"An error occurred during zoom generation: {ex}"
        )
    finally:
        state.is_generating_zoom = False
        state.storyboard = save_storyboard(state.storyboard)
        yield


def on_design_prompt_input(e: me.InputEvent):
    """Updates the design prompt in the page state."""
    state = me.state(PageState)
    state.design_prompt = e.value


def on_clear_design(e: me.ClickEvent):
    """Clear design prompt and image."""
    state = me.state(PageState)
    state.design_prompt = ""
    state.design_image_uri = ""
    state.design_image_display_url = ""
    yield


def on_upload_design_image(e: me.UploadEvent):
    """Upload design image handler."""
    state = me.state(PageState)
    file = e.files[0]
    gcs_url = store_to_gcs(
        "interior_design_uploads", file.name, file.mime_type, file.getvalue()
    )
    state.design_image_uri = gcs_url
    state.design_image_display_url = create_display_url(gcs_url)
    yield


def on_select_design_image(e: LibrarySelectionChangeEvent):
    """Design image selection from library handler."""
    state = me.state(PageState)
    state.design_image_uri = e.gcs_uri
    state.design_image_display_url = create_display_url(e.gcs_uri)
    yield


@track_click(element_id="interior_design_design_button")
def on_design_click(e: me.ClickEvent):
    """Handles the iterative design generation."""
    state = me.state(PageState)
    state.show_snackbar = False

    if not state.design_prompt:
        yield from show_snackbar(state, "Please enter a design modification prompt.")
        return

    state.is_designing = True
    yield

    try:
        storyboard_item = next(
            (
                item
                for item in state.storyboard["storyboard_items"]
                if item["room_name"] == state.storyboard["selected_room"]
            ),
            None,
        )
        if not storyboard_item:
            yield from show_snackbar(state, "Could not find the current room to style.")
            return

        images = [storyboard_item["styled_image_uri"]]
        if state.design_image_uri:
            images.append(state.design_image_uri)

        gcs_uris, _, _, _, _ = generate_image_from_prompt_and_images(
            prompt=state.design_prompt,
            images=images,
            aspect_ratio="16:9",
            gcs_folder="interior_design_iterations",
        model_name=cfg.INTERIOR_DESIGN_IMAGE_MODEL,
        )

        if gcs_uris:
            storyboard_item["styled_image_uri"] = gcs_uris[0]
            storyboard_item["styled_image_display_url"] = create_display_url(
                gcs_uris[0]
            )
            storyboard_item["style_history"].append(gcs_uris[0])
            state.design_prompt = ""
            state.design_image_uri = ""
        else:
            yield from show_snackbar(
                state, "Design generation failed to return a result."
            )

    except Exception as ex:
        yield from show_snackbar(
            state, f"An error occurred during design generation: {ex}"
        )
    finally:
        state.is_designing = False
        state.storyboard = save_storyboard(state.storyboard)
        yield


def on_storyboard_item_click(e: me.ClickEvent):
    """Sets the selected room when a storyboard tile is clicked."""
    state = me.state(PageState)
    state.storyboard["selected_room"] = e.key
    yield


def on_open_detail_dialog_click(e: me.ClickEvent):
    """Opens the detail dialog for a storyboard item."""
    state = me.state(PageState)
    state.selected_room_for_dialog = e.key
    state.is_detail_dialog_open = True
    yield


def on_generate_video_click(e: me.ClickEvent):
    """Generates a video from the storyboard and creates/updates the library item."""
    state = me.state(PageState)
    app_state = me.state(AppState)
    state.show_snackbar = False
    state.is_generating_video = True
    state.video_generation_status = "Starting..."
    yield

    try:
        # Step 1: Generate any missing video clips
        for item in state.storyboard["storyboard_items"]:
            if item["styled_image_uri"] and not item.get("generated_video_uri"):
                state.video_generation_status = (
                    f"Generating video for {item['room_name']}..."
                )
                yield
                video_uri = generate_workflow_image_to_video(
                    model_name=cfg.INTERIOR_DESIGN_VIDEO_MODEL,
                    image_gcs_uri=item["styled_image_uri"],
                    prompt="A slow, gentle panning shot of the room.",
                    duration_seconds=cfg.INTERIOR_DESIGN_VIDEO_DURATION,
                )
                if video_uri:
                    item["generated_video_uri"] = video_uri
                    item["generated_video_display_url"] = create_display_url(
                        video_uri
                    )

        # Step 2: Concatenate the video
        video_clips = [
            item["generated_video_uri"]
            for item in state.storyboard["storyboard_items"]
            if item.get("generated_video_uri")
        ]
        if not video_clips:
            yield from show_snackbar(state, "No video clips to process.")
            state.video_generation_status = ""
            return

        state.video_generation_status = "Concatenating video clips..."
        yield

        final_video_uri = (
            process_videos(video_clips, "concat")
            if len(video_clips) > 1
            else video_clips[0]
        )
        state.final_video_uri = final_video_uri
        state.storyboard["final_video_uri"] = final_video_uri
        state.storyboard["final_video_display_url"] = create_display_url(
            final_video_uri
        )

        # Step 3: Create or Update MediaItem
        media_item_id = state.storyboard.get("library_media_item_id")
        if media_item_id:
            print(f"Found existing MediaItem ID: {media_item_id}")
        else:
            print("No existing MediaItem ID found, will create a new one.")
            media_item_id = str(uuid.uuid4())

        print("Step 3: Creating MediaItem...")
        media_item = MediaItem(
            id=media_item_id,
            user_email=app_state.user_email,
            timestamp=datetime.datetime.now(
                datetime.UTC
            ).isoformat(),  # Convert to string
            media_type="video",
            mode="Interior Design",
            gcs_uris=[final_video_uri],
            thumbnail_uri=final_video_uri,
            storyboard_id=state.storyboard["id"],
            prompt="Interior Design Storyboard Tour",
        )
        print(f"...MediaItem created in memory with ID: {media_item.id}")
        add_media_item_to_firestore(media_item)
        print("...add_media_item_to_firestore called.")

        # Step 4: Save the MediaItem ID back to the storyboard
        print(
            f"Step 4: Saving MediaItem ID ({media_item.id}) back to storyboard ({state.storyboard['id']})..."
        )
        state.storyboard["library_media_item_id"] = media_item.id
        state.storyboard = save_storyboard(state.storyboard)
        print("...save_storyboard called.")

        yield from show_snackbar(state, "Video tour saved to library!")
        state.video_generation_status = "Video tour complete!"

    except Exception as ex:
        yield from show_snackbar(
            state, f"An error occurred during video generation: {ex}"
        )
        state.video_generation_status = "An error occurred."
    finally:
        state.is_generating_video = False
        yield


@me.component
def item_detail_dialog(on_close: Callable):
    """Dialog to show details of a storyboard item."""
    state = me.state(PageState)
    item = next(
        (
            item
            for item in state.storyboard["storyboard_items"]
            if item["room_name"] == state.selected_room_for_dialog
        ),
        None,
    )
    if not item:
        me.text("Error: Could not find selected item.")
        return

    with dialog(is_open=True):  # pylint: disable=E1129:not-context-manager
        me.text(f"Details for {item['room_name']}", type="headline-6")
        with me.box(
            style=me.Style(
                display="flex", flex_direction="row", gap=16, margin=me.Margin(top=16)
            )
        ):
            with me.box(style=me.Style(flex_grow=1)):
                me.text("Source Image", type="headline-5")
                me.image(
                    src=item.get("styled_image_display_url", ""),
                    style=me.Style(width="100%", border_radius=8),
                )

            with me.box(style=me.Style(flex_grow=1)):
                me.text("Generated Video", type="headline-5")
                if item.get("generated_video_uri"):
                    me.video(
                        src=item.get("generated_video_display_url", ""),
                        style=me.Style(width="100%", border_radius=8),
                    )
                else:
                    me.text("Video not generated yet.")

        with me.box(
            style=me.Style(
                display="flex",
                justify_content="flex-end",
                gap=8,
                margin=me.Margin(top=24),
            )
        ):
            me.button("Close", on_click=on_close, type="stroked")
            me.button(
                "Edit Image",
                on_click=on_edit_image_click,
                key=item["room_name"],
                type="stroked",
            )
            me.button(
                "Regenerate Video", on_click=on_regenerate_video_click, type="stroked"
            )


def on_close_detail_dialog(e: me.ClickEvent):
    """Closes the item detail dialog."""
    state = me.state(PageState)
    state.is_detail_dialog_open = False
    state.selected_room_for_dialog = None
    yield


def on_edit_image_click(e: me.ClickEvent):
    """Handles the 'Edit Image' button click from the detail dialog."""
    state = me.state(PageState)
    state.storyboard["selected_room"] = e.key
    state.is_detail_dialog_open = False
    state.selected_room_for_dialog = None
    yield


def on_regenerate_video_click(e: me.ClickEvent):
    """Handles the 'Regenerate Video' button click from the detail dialog."""
    state = me.state(PageState)
    if state.selected_room_for_dialog:
        for item in state.storyboard["storyboard_items"]:
            if item["room_name"] == state.selected_room_for_dialog:
                item["generated_video_uri"] = None
                break

    state.is_detail_dialog_open = False
    state.selected_room_for_dialog = None
    yield

    yield from on_generate_video_click(e)


def open_info_dialog(e: me.ClickEvent):
    """Open the info dialog."""
    print("DEBUG: open_info_dialog called")
    state = me.state(PageState)
    state.info_dialog_open = True
    yield


@track_click(element_id="interior_design_close_info_dialog_button")
def close_info_dialog(e: me.ClickEvent):
    """Close the info dialog."""
    state = me.state(PageState)
    state.info_dialog_open = False
    yield
