"""
Component for the Design Studio.
"""

from typing import Callable
import mesop as me
from components.library.events import LibrarySelectionChangeEvent
from components.library.library_chooser_button import library_chooser_button
from components.omni_button.omni_button import omni_button
from components.veo_button.veo_button import veo_button


@me.component
def design_studio(
    storyboard_item: dict,
    design_image_display_url: str,
    is_designing: bool,
    on_upload_design_image: Callable,
    on_select_design_image: Callable,
    on_design_prompt_input: Callable, # Changed from on_blur
    on_clear_design: Callable,
    on_design_click: Callable,
):
    """
    Component for the Design Studio.
    """
    with me.box(
        style=me.Style(
            display="flex", flex_direction="column", gap=16, width=300
        )
    ):
        me.text("Design Studio", type="headline-6")
        with me.box(style=me.Style(
            flex_direction="column", display="flex",
        )):
            me.uploader(
                label="Upload Design Image",
                on_upload=on_upload_design_image,
                style=me.Style(width="100%"),
                accepted_file_types=["image/jpeg", "image/png", "image/webp"],
            )
            library_chooser_button(
                key="design_image_library_chooser",
                on_library_select=on_select_design_image,
                button_label="Add from Library",
            )
        if design_image_display_url:
            me.image(
                src=design_image_display_url,
                style=me.Style(width="100%", border_radius=8, margin=me.Margin(top=8)),
            )
        me.textarea(
            label="Design Modifications",
            on_input=on_design_prompt_input,
            value=storyboard_item.get("design_prompt", ""),
            style=me.Style(width="100%"),
        )
        with me.box(style=me.Style(display="flex", flex_direction="row", gap=8)):
            me.button("Clear", on_click=on_clear_design, type="stroked")
            with me.content_button(
                on_click=on_design_click,
                type="raised",
                disabled=is_designing,
            ):
                if is_designing:
                    me.progress_spinner(diameter=18)
                else:
                    me.text("Design")
        veo_button(gcs_uri=storyboard_item["styled_image_uri"] if storyboard_item else "")
        omni_button(
            gcs_uri=storyboard_item["styled_image_uri"] if storyboard_item else ""
        )
