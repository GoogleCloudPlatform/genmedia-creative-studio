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

"""Object Rotation page."""

import datetime
import time
from dataclasses import field
from typing import Callable

import mesop as me

from common import authz
from common.storage import store_to_gcs
from common.utils import create_display_url
from components.header import header
from components.image_thumbnail import image_thumbnail
from components.library.events import LibrarySelectionChangeEvent
from components.library.library_chooser_button import library_chooser_button
from components.snackbar import snackbar

# Each uploader placeholder needs its own chooser key: the shared library
# chooser opens the dialog whose key matches the clicked button, and reports it
# back as ``LibrarySelectionChangeEvent.chooser_id``.
MAIN_IMAGE_CHOOSER_ID = "object_rotation_main"
VIEW_CHOOSER_IDS = {
    "front": "object_rotation_front",
    "back": "object_rotation_back",
    "left": "object_rotation_left",
    "right": "object_rotation_right",
}


def apply_library_selection(
    project: dict, chooser_id: str, gcs_uri: str, user_email: str | None
) -> dict | None:
    """Records a library selection on a rotation project.

    Args:
        project: The current rotation project (may be empty before step 1).
        chooser_id: The chooser that produced the selection.
        gcs_uri: The selected asset.
        user_email: Owner to stamp on a newly created project.

    Returns:
        The updated project, or None if the selection was ignored (empty URI
        or unknown chooser).
    """
    if not gcs_uri:
        return None
    if chooser_id == MAIN_IMAGE_CHOOSER_ID:
        if not project:
            project = {
                "user_email": user_email,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        project["main_product_image_uri"] = gcs_uri
        return project
    for view_name, view_chooser_id in VIEW_CHOOSER_IDS.items():
        if chooser_id == view_chooser_id:
            project.setdefault("product_views", {})[view_name] = gcs_uri
            return project
    return None


@me.component
def _uploader_placeholder(
    on_upload: Callable, on_library_select: Callable, chooser_key: str
):
    with me.box(
        style=me.Style(
            height=100,
            width=100,
            border=me.Border.all(
                me.BorderSide(
                    width=1, style="dashed", color=me.theme_var("outline")
                )
            ),
            border_radius=8,
            display="flex",
            flex_direction="column",
            align_items="center",
            justify_content="center",
            gap=8,
        )
    ):
        me.uploader(
            label="Upload", on_upload=on_upload, style=me.Style(flex_grow=1)
        )
        library_chooser_button(
            on_library_select=on_library_select,
            button_type="icon",
            key=chooser_key,
        )
from components.page_scaffold import page_frame, page_scaffold

from components.dialog import dialog
import json

with open("config/about_content.json", "r") as f:
    about_content = json.load(f)
    OBJECT_ROTATION_INFO = next(
        (s for s in about_content["sections"] if s.get("id") == "object_rotation"),
        None,
    )

def open_info_dialog(e: me.ClickEvent):
    state = me.state(PageState)
    state.info_dialog_open = True
    yield

def close_info_dialog(e: me.ClickEvent):
    state = me.state(PageState)
    state.info_dialog_open = False
    yield

from components.stepper import stepper
from models.object_rotation import generate_product_views, save_object_rotation_project
from state.state import AppState
from config.default import Default as cfg


@me.stateclass
class PageState:
    rotation_project: dict = field(default_factory=dict)  # pylint: disable=E3701:invalid-field-call
    current_step: int = 1
    max_completed_step: int = 1
    is_generating_views: bool = False
    is_generating_video: bool = False
    initial_load_complete: bool = False
    show_snackbar: bool = False
    info_dialog_open: bool = False
    snackbar_message: str = ""


def show_snackbar(state: PageState, message: str):
    """Displays a snackbar message at the bottom of the page."""
    state.snackbar_message = message
    state.show_snackbar = True
    yield
    time.sleep(3)
    state.show_snackbar = False
    yield


def on_load(e: me.LoadEvent):
    """Loads a rotation project from Firestore if an ID is provided in the URL."""
    state = me.state(PageState)
    app_state = me.state(AppState)
    if not state.initial_load_complete:
        object_rotation_id = me.query_params.get("object_rotation_id")
        if object_rotation_id:
            from config.firebase_config import FirebaseClient
            db = FirebaseClient().get_client()
            doc_ref = db.collection("object_rotation_projects").document(object_rotation_id)
            # Owner-scoped read: only the project's owner (or a legacy ownerless
            # doc) is returned. A non-owner load is indistinguishable from
            # not-found (fail-closed, no existence/content leak).
            project = authz.authorize_read(
                doc_ref,
                "user_email",
                app_state.user_email,
                resource="object rotation project",
            )
            if project is not None:
                # Hydrate display URLs
                if project.get("main_product_image_uri"):
                    project["main_product_image_display_url"] = create_display_url(project["main_product_image_uri"])
                if project.get("final_video_uri"):
                    project["final_video_display_url"] = create_display_url(project["final_video_uri"])
                # Iterate over a copy of the items to avoid changing dict size during iteration
                for view, uri in list(project.get("product_views", {}).items()):
                    project["product_views"][f"{view}_display_url"] = create_display_url(uri)

                state.rotation_project = project
                state.current_step = 3
                state.max_completed_step = 3
                print(f"Loaded rotation project {object_rotation_id} from Firestore.")
            else:
                yield from show_snackbar(
                    state,
                    f"Could not find project with ID: {object_rotation_id}",
                )
        state.initial_load_complete = True
    yield


@me.page(
    path="/object-rotation",
    title="Object Rotation - GenMedia Creative Studio",
    on_load=on_load,
)
def object_rotation_page():
    state = me.state(PageState)
    with page_scaffold(page_name="object_rotation"):  # pylint: disable=E1129:not-context-manager
        with page_frame():  # pylint: disable=E1129:not-context-manager
            header(
                "Object Rotation",
                "360",
                show_info_button=True,
                on_info_click=open_info_dialog,
            )
            page_content()
        snackbar(is_visible=state.show_snackbar, label=state.snackbar_message)


def page_content():
    state = me.state(PageState)

    if state.info_dialog_open:
        with dialog(is_open=state.info_dialog_open):  # pylint: disable=not-context-manager
            if OBJECT_ROTATION_INFO:
                me.text(f"About {OBJECT_ROTATION_INFO["title"]}", type="headline-6")
                me.markdown(OBJECT_ROTATION_INFO["description"])
            else:
                me.text("About Object Rotation", type="headline-6")
                me.markdown("Information for this page has not been configured yet.")
            
            me.divider()
            me.text("Current Settings", type="headline-6")
            me.text(f"Image Model: {cfg.OBJECT_ROTATION_IMAGE_MODEL}")
            me.text(f"Video Model: {cfg.OBJECT_ROTATION_VIDEO_MODEL}")
            
            with me.box(style=me.Style(margin=me.Margin(top=16))):
                me.button("Close", on_click=close_info_dialog, type="flat")

    with me.box(style=me.Style(margin=me.Margin(top=24))):
        stepper(
            steps=[
                "Describe and Add Product",
                "Generate or Upload Product Views",
                "Generate a Video",
            ],
            current_step=state.current_step,
            max_completed_step=state.max_completed_step,
            on_change=on_step_change,
        )

    # Conditionally render step content
    if state.current_step == 1:
        step1_content()
    elif state.current_step == 2:
        step2_content()
    elif state.current_step == 3:
        step3_content()


@me.component
def step1_content():
    state = me.state(PageState)
    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="row",
            gap=32,
            margin=me.Margin(top=24),
            justify_content="center",
        )
    ):
        me.textarea(
            label="Product Description",
            value=state.rotation_project.get("product_description", ""),
            on_blur=on_description_input,
            style=me.Style(width=400, height=200),
        )
        with me.box(style=me.Style(display="flex", flex_direction="column", gap=8, align_items="center")):
            me.text("Product Image", type="headline-6")
            if state.rotation_project.get("main_product_image_uri"):
                image_thumbnail(
                    image_uri=create_display_url(state.rotation_project.get("main_product_image_uri")),
                    on_remove=on_remove_main_image,
                    index=0,
                    icon_size=18,
                )
            else:
                _uploader_placeholder(
                    on_upload=on_main_image_upload,
                    on_library_select=on_select_from_library,
                    chooser_key=MAIN_IMAGE_CHOOSER_ID,
                )

    with me.box(
        style=me.Style(
            display="flex", justify_content="flex-end", margin=me.Margin(top=24)
        )
    ):
        me.button(
            "Next",
            on_click=on_step1_next,
            type="raised",
            disabled=not state.rotation_project.get("main_product_image_uri"),
        )


# Event Handlers for Step 1


def on_description_input(e: me.InputEvent):
    state = me.state(PageState)

    state.rotation_project["product_description"] = e.value

    yield


def on_main_image_upload(e: me.UploadEvent):
    state = me.state(PageState)
    app_state = me.state(AppState)
    file = e.files[0]
    gcs_uri = store_to_gcs(
        "object_rotation_uploads", file.name, file.mime_type, file.getvalue()
    )

    if not state.rotation_project:
        state.rotation_project = {
            "user_email": app_state.user_email,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    state.rotation_project["main_product_image_uri"] = gcs_uri
    yield

    state.rotation_project = save_object_rotation_project(state.rotation_project)
    yield


def on_select_from_library(e: LibrarySelectionChangeEvent):
    """Applies a library selection to the main image or the chosen view."""
    state = me.state(PageState)
    app_state = me.state(AppState)

    project = apply_library_selection(
        state.rotation_project, e.chooser_id, e.gcs_uri, app_state.user_email
    )
    if project is None:
        yield
        return

    state.rotation_project = project
    yield

    state.rotation_project = save_object_rotation_project(state.rotation_project)
    yield


def on_remove_main_image(e: me.ClickEvent):
    state = me.state(PageState)
    state.rotation_project["main_product_image_uri"] = None
    yield

def on_remove_view(e: me.ClickEvent, view_name: str):
    state = me.state(PageState)
    if "product_views" in state.rotation_project and view_name in state.rotation_project["product_views"]:
        del state.rotation_project["product_views"][view_name]
        yield


def on_step1_next(e: me.ClickEvent):
    state = me.state(PageState)

    # Save the project to Firestore before proceeding
    state.rotation_project = save_object_rotation_project(state.rotation_project)

    state.current_step = 2
    state.max_completed_step = 2
    yield


@me.component
def step2_content():
    state = me.state(PageState)
    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="column",
            align_items="center",
            gap=16,
            margin=me.Margin(top=24),
        )
    ):
        me.button(
            "Generate 4 Views",
            on_click=on_generate_views,
            type="raised",
            disabled=state.is_generating_views,
        )
        if state.is_generating_views:
            me.progress_spinner()

        with me.box(
            style=me.Style(
                display="grid",
                grid_template_columns="1fr 1fr",
                gap=16,
                margin=me.Margin(top=16),
            )
        ):
            # Front View
            with me.box(style=me.Style(display="flex", flex_direction="column", gap=8, align_items="center")):
                me.text("Front", type="headline-6")
                if state.rotation_project.get("product_views", {}).get("front"):
                    image_thumbnail(
                        image_uri=create_display_url(state.rotation_project.get("product_views", {}).get("front")),
                        on_remove=on_front_view_remove,
                        index=0,
                        icon_size=18,
                    )
                else:
                    _uploader_placeholder(
                        on_upload=on_front_view_upload,
                        on_library_select=on_select_from_library,
                        chooser_key=VIEW_CHOOSER_IDS["front"],
                    )

            # Back View
            with me.box(style=me.Style(display="flex", flex_direction="column", gap=8, align_items="center")):
                me.text("Back", type="headline-6")
                if state.rotation_project.get("product_views", {}).get("back"):
                    image_thumbnail(
                        image_uri=create_display_url(state.rotation_project.get("product_views", {}).get("back")),
                        on_remove=on_back_view_remove,
                        index=1,
                        icon_size=18,
                    )
                else:
                    _uploader_placeholder(
                        on_upload=on_back_view_upload,
                        on_library_select=on_select_from_library,
                        chooser_key=VIEW_CHOOSER_IDS["back"],
                    )

            # Left View
            with me.box(style=me.Style(display="flex", flex_direction="column", gap=8, align_items="center")):
                me.text("Left", type="headline-6")
                if state.rotation_project.get("product_views", {}).get("left"):
                    image_thumbnail(
                        image_uri=create_display_url(state.rotation_project.get("product_views", {}).get("left")),
                        on_remove=on_left_view_remove,
                        index=2,
                        icon_size=18,
                    )
                else:
                    _uploader_placeholder(
                        on_upload=on_left_view_upload,
                        on_library_select=on_select_from_library,
                        chooser_key=VIEW_CHOOSER_IDS["left"],
                    )

            # Right View
            with me.box(style=me.Style(display="flex", flex_direction="column", gap=8, align_items="center")):
                me.text("Right", type="headline-6")
                if state.rotation_project.get("product_views", {}).get("right"):
                    image_thumbnail(
                        image_uri=create_display_url(state.rotation_project.get("product_views", {}).get("right")),
                        on_remove=on_right_view_remove,
                        index=3,
                        icon_size=18,
                    )
                else:
                    _uploader_placeholder(
                        on_upload=on_right_view_upload,
                        on_library_select=on_select_from_library,
                        chooser_key=VIEW_CHOOSER_IDS["right"],
                    )

    with me.box(
        style=me.Style(
            display="flex", justify_content="flex-end", margin=me.Margin(top=24)
        )
    ):
        me.button(
            "Next",
            on_click=on_step2_next,
            type="raised",
            disabled=len(state.rotation_project.get("product_views", {})) < 4,
        )


# Event Handlers for Step 2


# Define dedicated handlers for each view to avoid lambda issues
def on_front_view_upload(e: me.UploadEvent):
    yield from on_view_upload(e, "front")


def on_back_view_upload(e: me.UploadEvent):
    yield from on_view_upload(e, "back")


def on_left_view_upload(e: me.UploadEvent):
    yield from on_view_upload(e, "left")


def on_right_view_upload(e: me.UploadEvent):
    yield from on_view_upload(e, "right")

def on_front_view_remove(e: me.ClickEvent): yield from on_remove_view(e, "front")
def on_back_view_remove(e: me.ClickEvent): yield from on_remove_view(e, "back")
def on_left_view_remove(e: me.ClickEvent): yield from on_remove_view(e, "left")
def on_right_view_remove(e: me.ClickEvent): yield from on_remove_view(e, "right")


async def on_generate_views(e: me.ClickEvent):
    state = me.state(PageState)
    state.is_generating_views = True
    yield

    try:
        views = await generate_product_views(
            product_description=state.rotation_project.get("product_description", ""),
            image_uri=state.rotation_project["main_product_image_uri"],
            image_model=cfg.OBJECT_ROTATION_IMAGE_MODEL
        )
        if not views:
            raise Exception("Model did not return any views.")
        if "product_views" not in state.rotation_project:
            state.rotation_project["product_views"] = {}
        state.rotation_project["product_views"].update(views)
        state.rotation_project = save_object_rotation_project(state.rotation_project)
    except Exception as ex:
        # Handle and display error
        print(f"Error generating views: {ex}")
        for _ in show_snackbar(state, f"Error generating views: {ex}"):
            yield
    finally:
        state.is_generating_views = False
        yield


def on_view_upload(e: me.UploadEvent, view_name: str):
    state = me.state(PageState)
    file = e.files[0]
    gcs_uri = store_to_gcs(
        f"object_rotation_uploads/{view_name}",
        file.name,
        file.mime_type,
        file.getvalue(),
    )
    if "product_views" not in state.rotation_project:
        state.rotation_project["product_views"] = {}
    state.rotation_project["product_views"][view_name] = gcs_uri
    state.rotation_project = save_object_rotation_project(state.rotation_project)
    yield


def on_step2_next(e: me.ClickEvent):
    state = me.state(PageState)
    state.current_step = 3
    state.max_completed_step = 3
    yield


@me.component
def step3_content():
    state = me.state(PageState)
    with me.box(
        style=me.Style(
            display="flex",
            flex_direction="column",
            align_items="center",
            gap=16,
            margin=me.Margin(top=24),
        )
    ):
        me.button(
            "Generate Video",
            on_click=on_generate_video,
            type="raised",
            disabled=state.is_generating_video,
        )
        if state.is_generating_video:
            me.progress_spinner()

        if state.rotation_project.get("final_video_uri"):
            me.video(
                src=create_display_url(state.rotation_project["final_video_uri"]),
                style=me.Style(
                    width="100%",
                    max_width=720,
                    margin=me.Margin(top=16),
                    border_radius=8,
                ),
            )


# Event Handlers for Step 3
from common.metadata import MediaItem, add_media_item_to_firestore
from models.object_rotation import generate_rotation_video


def on_generate_video(e: me.ClickEvent):
    state = me.state(PageState)
    app_state = me.state(AppState)
    state.is_generating_video = True
    yield

    try:
        video_uri = generate_rotation_video(
            state.rotation_project["product_views"],
            video_model=cfg.OBJECT_ROTATION_VIDEO_MODEL
        )
        state.rotation_project["final_video_uri"] = video_uri

        # Create and save the final MediaItem
        source_images = [state.rotation_project["main_product_image_uri"]] + list(
            state.rotation_project["product_views"].values()
        )

        media_item = MediaItem(
            user_email=app_state.user_email,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            gcsuri=video_uri,
            mime_type="video/mp4",
            source_images_gcs=source_images,
            object_rotation_project_id=state.rotation_project["id"],
            model="object-rotation-v1",
            prompt=state.rotation_project.get("product_description", "Object Rotation"),
        )
        add_media_item_to_firestore(media_item)

        # Save the MediaItem ID back to the project for two-way linking
        state.rotation_project["library_media_item_id"] = media_item.id
        state.rotation_project = save_object_rotation_project(state.rotation_project)

    except Exception as ex:
        # Handle and display error
        print(f"Error generating video: {ex}")
        yield from show_snackbar(state, f"Error generating video: {ex}")
    finally:
        state.is_generating_video = False
        yield


def on_step_change(step: int):
    print(f"Stepper clicked. Received step: {step}")
    state = me.state(PageState)
    if step <= state.max_completed_step:
        state.current_step = step
    yield
