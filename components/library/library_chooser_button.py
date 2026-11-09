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

import json
from dataclasses import asdict, field
from functools import partial
from typing import Callable, Optional

import mesop as me

from common.metadata import MediaItem, get_media_for_page_optimized
from common.utils import create_display_url, warm_display_urls
from components.dialog import dialog
from components.library.events import LibrarySelectionChangeEvent
from components.library.library_image_selector import library_image_selector
from state.state import AppState


def selectable_gcs_uri(item: MediaItem) -> str | None:
    """Return the item's primary GCS URI, or None if it can't be chosen.

    Failed generations (``error_message`` set, or no stored asset) are not
    selectable and must not take up a slot in the chooser page.
    """
    if item.error_message:
        return None
    if item.gcsuri:
        return item.gcsuri
    return item.gcs_uris[0] if item.gcs_uris else None


def load_chooser_items_json(
    media_type: list[str],
    user_email: str | None,
    page_size: int = 20,
) -> str:
    """Fetch one page of selectable library items as a JSON string.

    Failed generations are dropped, and the page's display URLs are signed in
    parallel here (while the dialog shows its spinner) so the render that
    follows hits the URL cache instead of signing each asset serially.
    """
    items, _ = get_media_for_page_optimized(
        page_size,
        media_type,
        filter_by_user_email=user_email,
    )
    items = [item for item in items if selectable_gcs_uri(item)]
    warm_display_urls([selectable_gcs_uri(item) for item in items])
    return json.dumps([asdict(item) for item in items], default=str)


@me.stateclass
class State:
    """Local mesop state for the library chooser button."""

    show_library_dialog: bool = False
    active_chooser_key: str = ""
    is_loading: bool = False
    media_items_json: str = ""
    show_only_my_items: bool = False
    media_type: list[str] = field(default_factory=lambda: ["images"])


@me.component
def library_chooser_button(
    on_library_select: Callable[[LibrarySelectionChangeEvent], None],
    button_label: Optional[str] = None,
    button_type: str = "stroked",
    key: str = "",
    media_type: list[str] | None = None,
    disabled: bool = False,
):
    """Render a button that opens a dialog to select media from the library."""
    state = me.state(State)
    app_state = me.state(AppState)

    # Default to ["images"] if not provided, but allow passing it in.
    # We use a local variable to avoid mutable default argument issues in Python,
    # although Mesop re-executes this function, so it might be fine.
    # Safer to use None as default in signature.
    current_media_type = media_type if media_type is not None else ["images"]

    def _fetch_and_update_items():
        """Helper to fetch items based on current state and update UI."""
        state.is_loading = True
        yield
        user_email = app_state.user_email if state.show_only_my_items else None
        # Use the media_type stored in state, which was set when opening the dialog
        print(f"DEBUG: fetching items with media_type={state.media_type}")
        state.media_items_json = load_chooser_items_json(
            state.media_type,
            user_email,
        )
        state.is_loading = False
        yield

    def open_dialog(e: me.ClickEvent, media_type: list[str]):
        """Dedicated click handler for opening the dialog and fetching data."""
        print(
            f"CLICK on library_chooser_button with key: '{e.key}', media_type: {media_type}",
        )
        state.active_chooser_key = e.key
        state.show_library_dialog = True
        # Capture the media_type for this specific button click into the shared state
        state.media_type = media_type
        yield from _fetch_and_update_items()

    def on_toggle_my_items(e: me.SlideToggleChangeEvent):
        """Handles the toggle for showing only user's items."""
        state.show_only_my_items = not state.show_only_my_items
        yield from _fetch_and_update_items()

    def on_select_from_library(e: LibrarySelectionChangeEvent):
        """Callback to handle image selection from the library dialog."""
        state.show_library_dialog = False
        e.chooser_id = state.active_chooser_key
        yield from on_library_select(e)
        yield

    # Determine icon based on media_type
    icon_name = "photo_library"
    if current_media_type == ["videos"]:
        icon_name = "video_library"
    elif current_media_type == ["audio"]:
        icon_name = "library_music"
    elif "all" in current_media_type:
        icon_name = "perm_media"

    with me.content_button(
        on_click=partial(open_dialog, media_type=current_media_type),
        type=button_type,
        key=key,
        disabled=disabled,
    ):
        with me.box(
            style=me.Style(
                display="flex",
                flex_direction="row",
                gap=8,
                align_items="center",
            ),
        ):
            me.icon(icon_name)
            if button_label:
                me.text(button_label)

    dialog_style = me.Style(
        width="65vw",
        height="35vh",
        display="flex",
        flex_direction="column",
    )

    is_active = state.show_library_dialog and state.active_chooser_key == key
    with dialog(is_open=is_active, dialog_style=dialog_style):  # pylint: disable=E1129
        if is_active:
            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="column",
                    gap=16,
                    flex_grow=1,
                ),
            ):
                # Header with title and toggle
                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="row",
                        justify_content="space-between",
                        align_items="center",
                    ),
                ):
                    # Dynamic title based on media type
                    media_type_label = "Media"
                    if state.media_type == ["images"]:
                        media_type_label = "Image"
                    elif state.media_type == ["videos"]:
                        media_type_label = "Video"
                    elif state.media_type == ["audio"]:
                        media_type_label = "Audio"

                    me.text(
                        f"Select {media_type_label} from Library",
                        type="headline-6",
                    )
                    me.slide_toggle(
                        label="Show only my items",
                        checked=state.show_only_my_items,
                        on_change=on_toggle_my_items,
                    )

                with me.box(style=me.Style(flex_grow=1, overflow_y="auto")):
                    if state.is_loading:
                        with me.box(
                            style=me.Style(
                                display="flex",
                                justify_content="center",
                                align_items="center",
                                height="100%",
                            ),
                        ):
                            me.progress_spinner()
                    else:
                        items_dicts = (
                            json.loads(state.media_items_json)
                            if state.media_items_json
                            else []
                        )
                        media_items = []
                        for d in items_dicts:
                            # Safely ignore extra kwargs
                            valid_keys = MediaItem.__dataclass_fields__.keys()
                            clean_d = {k: v for k, v in d.items() if k in valid_keys}
                            item = MediaItem(**clean_d)
                            gcs_uri = selectable_gcs_uri(item)
                            item.signed_url = (
                                create_display_url(gcs_uri) if gcs_uri else ""
                            )
                            media_items.append(item)

                        library_image_selector(
                            on_select=on_select_from_library,
                            media_items=media_items,
                        )
                with me.box(
                    style=me.Style(
                        display="flex",
                        justify_content="flex-end",
                        margin=me.Margin(top=24),
                    ),
                ):
                    me.button(
                        "Cancel",
                        on_click=lambda e: setattr(state, "show_library_dialog", False),
                        type="stroked",
                    )
