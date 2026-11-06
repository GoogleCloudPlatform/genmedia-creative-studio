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
"""A test library page using the new media_tile component."""

import datetime
import json
from collections.abc import Generator
from dataclasses import asdict, dataclass, field, fields

import mesop as me

from common.analytics import log_ui_click
from common.metadata import MediaItem, get_media_for_page, get_media_item_by_id
from common.utils import create_display_url, get_media_type, https_url_to_gcs_uri
from components.header import header
from components.interior_design.storyboard_video_tile import storyboard_video_tile
from components.library.image_details import CarouselState
from components.lightbox_dialog.lightbox_dialog import lightbox_dialog
from components.media_detail_viewer.media_detail_viewer import media_detail_viewer
from components.media_tile.media_tile import get_pills_for_item, media_tile
from components.page_scaffold import page_frame, page_scaffold
from components.scroll_sentinel.scroll_sentinel import scroll_sentinel
from components.veo.extend_dialog import VeoExtendDialogState, extend_dialog
from config.default import Default as cfg
from state.state import AppState


@me.stateclass
@dataclass
class PageState:
    """State for the library page."""

    is_loading: bool = True
    media_items_json: str = ""
    show_details_dialog: bool = False
    selected_media_item_id: str | None = None
    initial_load_complete: bool = False
    current_page: int = 1
    all_items_loaded: bool = False
    user_filter: str = "mine"  # "all" or "mine"
    type_filters: list[str] = field(
        default_factory=lambda: ["all"],
    )  # "all", "images", "videos", "audio"
    error_filter: str = "all"  # "all", "no_errors", "only_errors"
    tour_dialog_active_tab: str = "details"
    extend_dialog_state: VeoExtendDialogState = field(
        default_factory=VeoExtendDialogState,
    )


def on_load(e: me.LoadEvent):
    """Handles page load events for permalinks and initial data fetch."""
    pagestate = me.state(PageState)
    media_id = me.query_params.get("media_id")

    # If it's a permalink, skip the initial load and just open the dialog.
    # The dialog has its own logic to fetch the specific item.
    if media_id and not pagestate.show_details_dialog:
        pagestate.selected_media_item_id = media_id
        pagestate.show_details_dialog = True
    else:
        # Otherwise, perform the initial load for the main library view.
        # This will also run every time the user navigates back to the page,
        # ensuring the view is fresh.
        yield from _load_media(pagestate, is_filter_change=True)

    yield


def _load_media(pagestate: PageState, is_filter_change: bool = False):
    """Central function to load media based on current filters and pagination."""
    app_state = me.state(AppState)
    user_email_to_filter = (
        app_state.user_email if pagestate.user_filter == "mine" else None
    )

    if is_filter_change:
        pagestate.current_page = 1
        pagestate.media_items_json = "[]"
        pagestate.all_items_loaded = False

    pagestate.is_loading = True
    yield

    new_items = get_media_for_page(
        page=pagestate.current_page,
        media_per_page=cfg().LIBRARY_MEDIA_PER_PAGE,
        sort_by_timestamp=True,
        type_filters=pagestate.type_filters,
        filter_by_user_email=user_email_to_filter,
        error_filter=pagestate.error_filter,
    )

    if not new_items:
        pagestate.all_items_loaded = True
    else:
        existing_items = []
        if pagestate.media_items_json and pagestate.media_items_json != "[]":
            try:
                existing_items = json.loads(pagestate.media_items_json)
            except json.JSONDecodeError:
                existing_items = []

        new_items_dicts = [asdict(item) for item in new_items]

        if is_filter_change:
            combined = new_items_dicts
        else:
            combined = existing_items + new_items_dicts

        pagestate.media_items_json = json.dumps(combined, default=str)

    pagestate.is_loading = False
    yield


def on_load_more(e: me.WebEvent):
    """Event handler for infinite scroll, fetches the next page of items."""
    pagestate = me.state(PageState)
    if pagestate.is_loading or pagestate.all_items_loaded:
        return

    pagestate.current_page += 1
    yield from _load_media(pagestate)


def on_user_filter_change(e: me.ButtonToggleChangeEvent):
    """Handles changes to the user filter."""
    pagestate = me.state(PageState)
    pagestate.user_filter = e.value
    yield from _load_media(pagestate, is_filter_change=True)


def on_type_filter_change(e: me.ButtonToggleChangeEvent):
    """Handles changes to the media type filter."""
    pagestate = me.state(PageState)
    new_filters = e.values
    if not new_filters:
        pagestate.type_filters = ["all"]
    elif "all" in new_filters and len(new_filters) > 1:
        pagestate.type_filters = [val for val in new_filters if val != "all"]
    else:
        pagestate.type_filters = new_filters
    yield from _load_media(pagestate, is_filter_change=True)


def on_error_filter_change(e: me.ButtonToggleChangeEvent):
    """Handles changes to the error filter."""
    pagestate = me.state(PageState)
    pagestate.error_filter = e.value
    yield from _load_media(pagestate, is_filter_change=True)


@me.page(
    path="/library_v2",
    title="GenMedia Creative Studio - Library",
    on_load=on_load,
)
def page():
    """Main Page."""
    with page_scaffold(page_name="library"):  # pylint: disable=E1129:not-context-manager
        library_content()  # pylint: disable=E1129:not-context-manager


def library_content():
    """The main content of the library page."""
    pagestate = me.state(PageState)

    with page_frame():  # pylint: disable=E1129:not-context-manager
        header("Library", "perm_media")

        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="row",
                gap=10,
                margin=me.Margin(bottom=20),
            ),
        ):
            me.button_toggle(
                value=pagestate.type_filters,
                buttons=[
                    me.ButtonToggleButton(label="All Types", value="all"),
                    me.ButtonToggleButton(label="Images", value="images"),
                    me.ButtonToggleButton(label="Videos", value="videos"),
                    me.ButtonToggleButton(label="Audio", value="audio"),
                ],
                multiple=True,
                on_change=on_type_filter_change,
            )
            me.button_toggle(
                value=pagestate.user_filter,
                buttons=[
                    me.ButtonToggleButton(label="All Users", value="all"),
                    me.ButtonToggleButton(label="Mine Only", value="mine"),
                ],
                on_change=on_user_filter_change,
            )
            me.button_toggle(
                value=pagestate.error_filter,
                buttons=[
                    me.ButtonToggleButton(label="Show All", value="all"),
                    me.ButtonToggleButton(label="No Errors", value="no_errors"),
                    me.ButtonToggleButton(label="Only Errors", value="only_errors"),
                ],
                on_change=on_error_filter_change,
            )

        with me.box(
            style=me.Style(
                display="grid",
                grid_template_columns="repeat(auto-fill, minmax(300px, 1fr))",
                gap="16px",
                width="100%",
            ),
        ):
            items_dicts = (
                json.loads(pagestate.media_items_json)
                if pagestate.media_items_json
                else []
            )
            media_items = []
            for d in items_dicts:
                valid_keys = {f.name for f in fields(MediaItem)}
                clean_d = {k: v for k, v in d.items() if k in valid_keys}
                if "timestamp" in clean_d and isinstance(clean_d["timestamp"], str):
                    try:
                        clean_d["timestamp"] = datetime.datetime.fromisoformat(
                            clean_d["timestamp"],
                        )
                    except ValueError:
                        pass
                media_items.append(MediaItem(**clean_d))

            if not media_items and not pagestate.is_loading:
                with me.box(
                    style=me.Style(padding=me.Padding.all(20), text_align="center"),
                ):
                    me.text("No media items found for the selected filters.")
            else:
                for item in media_items:
                    gcs_uri = (
                        item.gcsuri
                        if item.gcsuri
                        else (item.gcs_uris[0] if item.gcs_uris else None)
                    )
                    https_url = create_display_url(gcs_uri) if gcs_uri else ""
                    render_type = get_media_type(
                        mime_type=item.mime_type,
                        url=https_url,
                    )

                    # Use thumbnail as a static preview for video tiles when available
                    thumbnail_url = ""
                    if getattr(item, "thumbnail_uri", None):
                        thumbnail_url = create_display_url(item.thumbnail_uri)

                    display_url = https_url
                    display_type = render_type
                    if render_type == "video" and thumbnail_url:
                        if not any(
                            thumbnail_url.lower().endswith(ext)
                            for ext in [".mp4", ".mov", ".avi", ".webm", ".mkv"]
                        ):
                            display_url = thumbnail_url
                            display_type = "image"

                    media_tile(
                        key=item.id,
                        on_click=on_media_item_click,
                        media_type=display_type,
                        https_url=display_url,
                        pills_json=get_pills_for_item(item, https_url),
                    )

        scroll_sentinel(
            on_visible=on_load_more,
            is_loading=pagestate.is_loading,
            all_items_loaded=pagestate.all_items_loaded,
        )

        library_dialog(pagestate)
        extend_dialog(pagestate.extend_dialog_state, on_close=on_close_extend_dialog)


def on_media_item_click(e: me.ClickEvent):
    """Saves the selected item's ID to the state and opens the dialog."""
    pagestate = me.state(PageState)
    pagestate.selected_media_item_id = e.key
    pagestate.show_details_dialog = True
    yield


def on_extend_click(e: me.WebEvent):
    """Handles 'Extend' click from media viewer."""
    state = me.state(PageState)
    proxy_url = e.value["url"]
    print(f"DEBUG: on_extend_click triggered. Proxy URL: {proxy_url}")
    if proxy_url:
        # Use common utility to handle various URL formats
        gcs_path = https_url_to_gcs_uri(proxy_url)
        print(f"DEBUG: Extracted GCS Path: {gcs_path}")

        # Open the extend dialog
        state.extend_dialog_state.is_open = True
        state.extend_dialog_state.input_video_uri = gcs_path
        print(
            f"DEBUG: Set extend_dialog_state.is_open = {state.extend_dialog_state.is_open}",
        )
        print(
            f"DEBUG: Set extend_dialog_state.input_video_uri = {state.extend_dialog_state.input_video_uri}",
        )
    yield


def on_close_extend_dialog(e: me.ClickEvent):
    """Closes the extend dialog and resets state."""
    state = me.state(PageState)
    # Check if we should refresh the library (if generation succeeded)
    if state.extend_dialog_state.generated_video_uri:
        yield from _load_media(state, is_filter_change=True)

    # Reset dialog state
    state.extend_dialog_state = VeoExtendDialogState()
    yield


@me.component
def library_dialog(pagestate: PageState):
    """Renders the details dialog. Fetches the item on-demand to avoid state issues."""
    # The dialog is always in the DOM, just hidden/shown via is_open.
    # We only fetch and render the content if an item is selected.
    if pagestate.show_details_dialog and pagestate.selected_media_item_id:
        # FETCH ON DEMAND
        item_to_display = get_media_item_by_id(pagestate.selected_media_item_id)

        with lightbox_dialog(is_open=True, on_close=on_close_details_dialog):  # pylint: disable=E1129:not-context-manager
            if not item_to_display:
                with me.box(style=me.Style(padding=me.Padding.all(16))):
                    me.text("Error: Could not load media item details.")
                return

            # If the item has a storyboard_id, fetch the data and render the tour dialog.
            if item_to_display.storyboard_id:
                from config.firebase_config import FirebaseClient

                db = FirebaseClient().get_client()
                doc_ref = db.collection("interior_design_storyboards").document(
                    item_to_display.storyboard_id,
                )
                doc = doc_ref.get()
                if doc.exists:
                    # Pass the fetched storyboard dict as a parameter
                    render_tour_detail_dialog(storyboard=doc.to_dict())
                else:
                    me.text(
                        f"Error: Could not find storyboard with ID: {item_to_display.storyboard_id}",
                    )
            else:
                # Pass the freshly fetched item as a parameter
                render_default_detail_dialog(item=item_to_display)
    else:
        # Render an empty, closed dialog if nothing is selected.
        # This is important so the dialog can be opened by changing the state.
        with lightbox_dialog(is_open=False, on_close=on_close_details_dialog):  # pylint: disable=E1129:not-context-manager
            pass  # Render nothing inside the closed dialog


def on_close_details_dialog(e: me.ClickEvent):
    pagestate = me.state(PageState)
    carousel_state = me.state(CarouselState)
    pagestate.show_details_dialog = False
    pagestate.selected_media_item_id = None
    carousel_state.current_index = 0
    yield


def handle_edit_click(e: me.WebEvent):
    app_state = me.state(AppState)
    log_ui_click(
        element_id="media_detail_viewer_edit_button",
        page_name=app_state.current_page,
        session_id=app_state.session_id,
    )
    gcs_uri = https_url_to_gcs_uri(e.value["url"])
    me.navigate("/nano-banana", query_params={"image_uri": gcs_uri})


def on_veo_click(e: me.WebEvent):
    """Event handler for when the VEO button is clicked in the detail viewer."""
    proxy_url = e.value[
        "url"
    ]  # This is now the proxy URL, e.g., /media/bucket/object.png
    if proxy_url:
        # Convert the proxy URL back to just the GCS path (bucket/object.png)
        gcs_path = proxy_url.replace("/media/", "", 1)
        me.navigate(url="/veo", query_params={"image_path": gcs_path})
    yield


def on_omni_click(e: me.WebEvent) -> Generator[None]:
    """Event handler for when the Omni button is clicked in the detail viewer."""
    app_state = me.state(AppState)
    log_ui_click(
        element_id="media_detail_viewer_omni_button",
        page_name=app_state.current_page,
        session_id=app_state.session_id,
    )
    # The viewer sends a proxy (/media/bucket/object) or signed URL; normalize to
    # gs:// and pass the bare path, the same convention as the Veo button.
    gcs_uri = https_url_to_gcs_uri(e.value["url"])
    if gcs_uri:
        me.navigate(
            url="/gemini-omni",
            query_params={"image_path": gcs_uri.replace("gs://", "", 1)},
        )
    yield


def json_default_serializer(o):
    """A default serializer for json.dumps to handle datetimes."""
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


@me.component
def render_tour_detail_dialog(storyboard: dict):
    """Renders a dedicated dialog for viewing Interior Design Tours."""
    pagestate = me.state(PageState)

    if not storyboard:
        return

    with lightbox_dialog(is_open=True, on_close=on_close_details_dialog):  # pylint: disable=E1129:not-context-manager
        me.text("Interior Design Tour", type="headline-5")

        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="row",
                gap=24,
                margin=me.Margin(top=16),
            ),
        ):
            # Left Column: Video and Carousel
            with me.box(
                style=me.Style(
                    flex_grow=1,
                    display="flex",
                    flex_direction="column",
                    gap=16,
                ),
            ):
                final_video_uri = storyboard.get("final_video_uri")
                if final_video_uri:
                    me.video(
                        src=create_display_url(final_video_uri),
                        style=me.Style(width="100%", border_radius=8),
                    )

                with me.box():
                    me.text("Storyboard Clips", type="headline-6")
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="row",
                            gap=16,
                            overflow_x="auto",
                            padding=me.Padding(top=8, bottom=16),
                        ),
                    ):
                        for item in storyboard.get("storyboard_items", []):
                            if item.get("generated_video_uri"):
                                storyboard_video_tile(
                                    key=item["room_name"],
                                    video_url=create_display_url(
                                        item["generated_video_uri"],
                                    ),
                                    room_name=item["room_name"],
                                    on_click=lambda e: None,
                                )

            # Right Column: Metadata with Tabs
            with me.box(
                style=me.Style(
                    width=300,
                    flex_shrink=0,
                    max_height="80vh",
                    overflow_y="auto",
                ),
            ):
                # Tab header
                with me.box(
                    style=me.Style(
                        display="flex",
                        border=me.Border.all(
                            me.BorderSide(color=me.theme_var("outline-variant")),
                        ),
                        margin=me.Margin(bottom=16),
                    ),
                ):
                    with me.content_button(
                        on_click=lambda e: setattr(
                            pagestate,
                            "tour_dialog_active_tab",
                            "details",
                        ),
                        style=me.Style(
                            border=me.Border.all(me.BorderSide(width=0)),
                            padding=me.Padding.all(0),
                        ),
                    ):
                        me.text(
                            "Details",
                            style=me.Style(
                                padding=me.Padding(bottom=8, left=16, right=16),
                                font_weight="bold"
                                if pagestate.tour_dialog_active_tab == "details"
                                else "normal",
                                border=me.Border(
                                    bottom=me.BorderSide(
                                        width=2,
                                        style="solid",
                                        color=me.theme_var("primary")
                                        if pagestate.tour_dialog_active_tab == "details"
                                        else "transparent",
                                    ),
                                ),
                            ),
                        )
                    with me.content_button(
                        on_click=lambda e: setattr(
                            pagestate,
                            "tour_dialog_active_tab",
                            "raw",
                        ),
                        style=me.Style(
                            border=me.Border.all(me.BorderSide(width=0)),
                            padding=me.Padding.all(0),
                        ),
                    ):
                        me.text(
                            "Raw",
                            style=me.Style(
                                padding=me.Padding(bottom=8, left=16, right=16),
                                font_weight="bold"
                                if pagestate.tour_dialog_active_tab == "raw"
                                else "normal",
                                border=me.Border(
                                    bottom=me.BorderSide(
                                        width=2,
                                        style="solid",
                                        color=me.theme_var("primary")
                                        if pagestate.tour_dialog_active_tab == "raw"
                                        else "transparent",
                                    ),
                                ),
                            ),
                        )

                # Tab content
                if pagestate.tour_dialog_active_tab == "details":
                    me.text(f"Storyboard ID: {storyboard.get('id')}")
                    me.text(f"Created: {storyboard.get('timestamp')}")

                if pagestate.tour_dialog_active_tab == "raw":
                    me.code(
                        json.dumps(
                            storyboard,
                            indent=2,
                            default=json_default_serializer,
                        ),
                        language="json",
                    )

        with me.box(
            style=me.Style(
                display="flex",
                justify_content="flex-end",
                gap=8,
                margin=me.Margin(top=24),
            ),
        ):
            me.button("Close", on_click=on_close_details_dialog, type="stroked")
            me.button(
                "Continue Styling",
                on_click=on_continue_styling_click,
                key=storyboard.get("id"),
                type="raised",
            )


@me.component
def render_default_detail_dialog(item: MediaItem):
    """Renders the default detail view for standard media items."""
    primary_urls = []
    # If there are multiple URIs in gcs_uris, create a display URL for each.
    if item.gcs_uris:
        primary_urls = [create_display_url(uri) for uri in item.gcs_uris]
    # Fallback for single gcsuri for backward compatibility.
    elif item.gcsuri:
        primary_urls = [create_display_url(item.gcsuri)]

    # Handle case where timestamp might be a string from Firestore
    timestamp_display = "N/A"
    if isinstance(item.timestamp, datetime.datetime):
        timestamp_display = item.timestamp.isoformat()
    elif isinstance(item.timestamp, str):
        timestamp_display = item.timestamp

    metadata = {
        "Prompt": item.prompt,
        "Model": item.model,
        "Timestamp": timestamp_display,
        "Generation Time (s)": item.generation_time,
    }

    render_type = get_media_type(
        mime_type=item.mime_type,
        url=primary_urls[0] if primary_urls else "",
    )

    # The main detail viewer now only shows the primary asset and metadata
    media_detail_viewer(
        media_type=render_type,
        primary_urls_json=json.dumps(primary_urls),
        source_urls_json="[]",  # Pass empty list as sources are rendered below
        metadata_json=json.dumps(metadata),
        id=item.id,
        raw_metadata_json=json.dumps(
            asdict(item),
            indent=2,
            default=json_default_serializer,
        ),
        on_edit_click=handle_edit_click,
        on_veo_click=on_veo_click,
        on_omni_click=on_omni_click,
        on_extend_click=on_extend_click,
    )

    # Add a button to link back to the object rotation page if applicable
    if item.object_rotation_project_id:
        with me.box(style=me.Style(margin=me.Margin(top=16))):
            me.button(
                "View Rotation Project",
                on_click=on_view_rotation_project_click,
                key=item.object_rotation_project_id,
                type="stroked",
            )

    # --- Categorized Source Asset Sections ---

    # R2V Style
    if item.r2v_style_image:
        _render_source_section("Style Reference", [item.r2v_style_image])

    # R2V Assets
    if item.r2v_reference_images:
        _render_source_section("Asset References", item.r2v_reference_images)

    # I2V / Interpolation Frames
    i2v_frames = []
    if item.reference_image:
        i2v_frames.append(item.reference_image)
    if item.last_reference_image:
        i2v_frames.append(item.last_reference_image)
    if i2v_frames:
        # Use a more specific title if it's interpolation
        title = "Interpolation Frames" if item.last_reference_image else "Source Frame"
        _render_source_section(title, i2v_frames)

    # Virtual Try-On
    vto_assets = []
    if item.person_image_gcs:
        vto_assets.append(item.person_image_gcs)
    if item.product_image_gcs:
        vto_assets.append(item.product_image_gcs)
    if vto_assets:
        _render_source_section("Virtual Try-On Sources", vto_assets)

    # Generic / Legacy Sources
    generic_sources = []
    if item.source_uris:
        generic_sources.extend(item.source_uris)
    if item.source_images_gcs:
        generic_sources.extend(item.source_images_gcs)
    if generic_sources:
        _render_source_section("Source Assets", generic_sources)


@me.component
def _render_source_section(title: str, uris: list[str]):
    """Helper to render a titled section of source asset tiles."""
    if not uris:
        return

    with me.box(style=me.Style(margin=me.Margin(top=24))):
        me.text(title, type="headline-6")
        with me.box(
            style=me.Style(
                display="grid",
                grid_template_columns="repeat(auto-fill, minmax(200px, 1fr))",
                gap="16px",
                margin=me.Margin(top=16),
            ),
        ):
            for source_uri in uris:
                # Construct the display URL
                https_url = create_display_url(source_uri)

                render_type = get_media_type(url=https_url)

                # Create a dummy MediaItem for pill generation if needed,
                # though for source assets pills might be overkill.
                # We keep it for consistency with the previous implementation.
                source_item = MediaItem(gcsuri=source_uri, media_type=render_type)

                media_tile(
                    key=source_uri,
                    media_type=render_type,
                    https_url=https_url,
                    pills_json=get_pills_for_item(source_item, https_url),
                    # Not clickable for now
                    on_click=None,
                )


def on_continue_styling_click(e: me.ClickEvent):
    """Navigates the user to the interior design page to continue styling."""
    storyboard_id = e.key
    if storyboard_id:
        me.navigate(
            url="/interior_design",
            query_params={
                "storyboard_id": f"{storyboard_id}",
            },
        )

    yield


def on_view_rotation_project_click(e: me.ClickEvent):
    """Navigates the user to the object rotation page to view a project."""
    project_id = e.key
    if project_id:
        me.navigate(
            url="/object-rotation",
            query_params={
                "object_rotation_id": f"{project_id}",
            },
        )
    yield
