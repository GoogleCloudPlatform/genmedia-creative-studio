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

import random
import uuid
import json
import time
from dataclasses import field
from pathlib import Path


import mesop as me

from common.analytics import log_ui_click, track_click

from common.metadata import add_media_item
from common.storage import store_to_gcs
from components.header import header
from components.library.events import LibrarySelectionChangeEvent
from components.library.library_chooser_button import library_chooser_button
from components.page_scaffold import page_frame, page_scaffold
from config.default import Default
from models.image_models import generate_virtual_models
from models.virtual_model_generator import VirtualModelGenerator, DEFAULT_PROMPT
from models.vto import generate_vto_image
from models.vto_critique import run_vto_critique_workflow
from common.utils import create_display_url
from state.state import AppState
from config.default import ABOUT_PAGE_CONTENT
from components.dialog import dialog
from components.edit_button.edit_button import edit_button
from components.snackbar import snackbar
from components.veo_button.veo_button import veo_button

config = Default()

IMAGE_BOX_STYLE = me.Style(
    width=400,
    height=400,
    border=me.Border.all(
        me.BorderSide(width=2, style="dashed", color=me.theme_var("outline-variant")),
    ),
    border_radius=12,
    display="flex",
    align_items="center",
    justify_content="center",
    flex_direction="column",
    gap=8,
    margin=me.Margin(top=16),
)

with open("config/about_content.json", "r") as f:
    about_content = json.load(f)
    VTO_INFO = next(
        (s for s in about_content["sections"] if s.get("id") == "vto"), None
    )


@me.stateclass
class PageState:
    """VTO Page State"""

    person_image_file: me.UploadedFile = None
    person_image_gcs: str = ""
    person_image_display_url: str = ""
    product_image_file: me.UploadedFile = None
    product_image_gcs: str = ""
    product_image_display_url: str = ""
    result_gcs_uris: list[str] = field(default_factory=list)  # pylint: disable=invalid-field-call
    result_display_urls: list[str] = field(default_factory=list)  # pylint: disable=invalid-field-call
    vto_sample_count: int = 4
    vto_base_steps: int = 32
    person_generation: str = "allow_all"
    safety_filter_level: str = "block_only_high"
    is_loading: bool = False
    is_generating_person_image: bool = False
    is_analyzing: bool = False
    critique_results_json: str = "{}"
    show_snackbar: bool = False
    snackbar_message: str = ""
    error_dialog_open: bool = False
    error_message: str = ""

    info_dialog_open: bool = False

    # Load options once
    _options: dict = field(default_factory=dict, init=False) # pylint: disable=E3701:invalid-field-call

    def __post_init__(self):
        config_path = Path(__file__).parent.parent / "config/virtual_model_options.json"
        with open(config_path, "r") as f:
            self._options = json.load(f)


def on_upload_person(e: me.UploadEvent):
    """Upload person image handler."""
    state = me.state(PageState)
    state.person_image_file = e.file
    gcs_url = store_to_gcs(
        "vto_person_images", e.file.name, e.file.mime_type, e.file.getvalue()
    )
    state.person_image_gcs = gcs_url
    state.person_image_display_url = create_display_url(gcs_url)
    yield


def on_library_chooser(e: LibrarySelectionChangeEvent):
    """Person image from library handler."""
    print("EXECUTING: on_library_chooser")
    print(f"EVENT: {e}")
    state = me.state(PageState)
    if e.chooser_id == "person_library_chooser":
        print("STATE: person image")
        state.person_image_gcs = e.gcs_uri
        state.person_image_display_url = create_display_url(e.gcs_uri)
    elif e.chooser_id == "product_library_chooser":
        print("STATE: prod image")
        state.product_image_gcs = e.gcs_uri
        state.product_image_display_url = create_display_url(e.gcs_uri)
    yield


def on_upload_product(e: me.UploadEvent):
    """Upload product image handler."""
    state = me.state(PageState)
    state.product_image_file = e.file
    gcs_url = store_to_gcs(
        "vto_product_images", e.file.name, e.file.mime_type, e.file.getvalue()
    )
    state.product_image_gcs = gcs_url
    state.product_image_display_url = create_display_url(gcs_url)
    yield


@track_click(element_id="vto_generate_person_button")
def on_click_generate_person(e: me.ClickEvent):
    """Generate person image handler."""
    state = me.state(PageState)
    state.is_generating_person_image = True
    yield

    try:
        # Randomly select options
        selected_gender_obj = random.choice(state._options.get("genders", []))
        selected_silhouette_obj = random.choice(state._options.get("silhouette_presets", []))
        selected_mst_obj = random.choice(state._options.get("MST", []))
        selected_variant_obj = random.choice(state._options.get("variants", []))

        # Build the prompt
        generator = VirtualModelGenerator(DEFAULT_PROMPT)
        generator.set_value("gender", selected_gender_obj["prompt_fragment"])
        generator.set_value("silhouette", selected_silhouette_obj["prompt_fragment"])
        generator.set_value("MST", selected_mst_obj["prompt_fragment"])
        generator.set_value("variant", selected_variant_obj["prompt_fragment"])
        prompt = generator.build_prompt()

        print(f"Generated prompt: {prompt}")

        # Generate the image
        image_urls = generate_virtual_models(prompt=prompt, num_images=1)

        if not image_urls:
            raise Exception("Image generation failed to return a URL.")

        # The result from generate_virtual_models is a GCS URI, so we can use it directly
        gcs_url = image_urls[0]

        state.person_image_gcs = gcs_url
        state.person_image_display_url = create_display_url(gcs_url)

    except Exception as e:
        state.error_message = str(e)
        state.show_error_dialog = True
    finally:
        state.is_generating_person_image = False
        yield


def show_snackbar(state: PageState, message: str):
    """Displays an auto-dismissing snackbar message."""
    state.snackbar_message = message
    state.show_snackbar = True
    yield
    time.sleep(3)
    state.show_snackbar = False
    yield


@track_click(element_id="vto_generate_button")
def on_generate(e: me.ClickEvent):
    """Generate VTO handler."""
    app_state = me.state(AppState)
    state = me.state(PageState)
    state.is_loading = True
    state.critique_results_json = "{}"
    yield

    result_gcs_uris: list[str] = []
    try:
        start_time = time.time()
        result_gcs_uris = generate_vto_image(
            state.person_image_gcs, # Pass the correct gs:// URI
            state.product_image_gcs, # Pass the correct gs:// URI
            state.vto_sample_count,
            state.vto_base_steps,
            person_generation=state.person_generation,
            safety_filter_level=state.safety_filter_level,
        )
        end_time = time.time()
        generation_time = end_time - start_time
        print(f"Result GCS URIs: {result_gcs_uris}")
        state.result_gcs_uris = result_gcs_uris
        state.result_display_urls = [create_display_url(uri) for uri in result_gcs_uris]
        add_media_item(
            user_email=app_state.user_email,
            model=config.VTO_MODEL_ID,
            mime_type="image/png",
            gcs_uris=result_gcs_uris,
            person_image_gcs=state.person_image_gcs,
            product_image_gcs=state.product_image_gcs,
            generation_time=generation_time,
        )
    except Exception as e:
        state.error_message = str(e)
        state.error_dialog_open = True
    finally:
        state.is_loading = False
        yield

    if result_gcs_uris and state.product_image_gcs:
        state.is_analyzing = True
        yield
        critique_map: dict[str, dict[str, str | bool]] = {}
        critique_error: str = ""
        try:
            for uri in result_gcs_uris:
                critique_data = run_vto_critique_workflow(
                    apparel_image_gcs=state.product_image_gcs,
                    result_image_gcs=uri,
                )
                critique_map[uri] = critique_data
                state.critique_results_json = json.dumps(
                    critique_map, default=str
                )
                yield
        except Exception as err:
            critique_error = str(err)
        finally:
            state.is_analyzing = False
            yield

        if critique_error:
            yield from show_snackbar(state, f"VTO critique error: {critique_error}")
    yield


def on_sample_count_change(e: me.SliderValueChangeEvent):
    """Handles changes to the sample count slider."""
    app_state = me.state(AppState)
    log_ui_click(
        element_id="vto_sample_count_slider",
        page_name=app_state.current_page,
        session_id=app_state.session_id,
        extras={"value": e.value},
    )
    state = me.state(PageState)
    state.vto_sample_count = int(e.value)
    yield


def on_person_generation_change(e: me.SelectSelectionChangeEvent):
    """Handles changes to the person generation select."""
    state = me.state(PageState)
    state.person_generation = e.value
    yield


def on_safety_filter_change(e: me.SelectSelectionChangeEvent):
    """Handles changes to the safety filter select."""
    state = me.state(PageState)
    state.safety_filter_level = e.value
    yield


@track_click(element_id="vto_clear_button")
def on_clear(e: me.ClickEvent):
    state = me.state(PageState)
    state.person_image_gcs = ""
    state.person_image_display_url = ""
    state.product_image_gcs = ""
    state.product_image_display_url = ""
    state.result_gcs_uris = []
    state.result_display_urls = []
    state.critique_results_json = "{}"
    state.is_analyzing = False
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

def close_error_dialog(e: me.ClickEvent):
    """Close the error dialog."""
    state = me.state(PageState)
    state.error_dialog_open = False
    yield


@me.page(path="/vto", title="GenMedia Creative Studio - Virtual Try-On")
def page():
    state = me.state(PageState)

    if state.error_dialog_open:
        with dialog(is_open=state.error_dialog_open):  # pylint: disable=E1129
            me.text("VTO Generation Error", type="headline-6")
            me.text(state.error_message)
            with me.box(style=me.Style(margin=me.Margin(top=16))):
                me.button("Close", on_click=close_error_dialog, type="flat")

    if state.info_dialog_open:
        with dialog(is_open=state.info_dialog_open):  # pylint: disable=E1129
            me.text(f'About {VTO_INFO["title"]}', type="headline-6")
            me.markdown(VTO_INFO["description"])
            me.divider()
            me.text("Current Settings", type="headline-6")
            me.text(f"Person Image: {state.person_image_gcs}")
            me.text(f"Garment Image: {state.product_image_gcs}")
            me.text(f"VTO Model: {config.VTO_MODEL_ID}")
            with me.box(style=me.Style(margin=me.Margin(top=16))):
                me.button("Close", on_click=close_info_dialog, type="flat")

    with page_scaffold(page_name="vto"):  # pylint: disable=E1129
        with page_frame():  # pylint: disable=E1129
            header("Virtual Try-On", "checkroom", show_info_button=True, on_info_click=open_info_dialog) # pylint: disable=E1129

            with me.box(style=me.Style(display="flex", flex_direction="row", gap=16)):
                # Person Image Section
                with me.box(
                    style=me.Style(
                        width="calc(50% - 8px)",
                        display="flex",
                        flex_direction="column",
                        align_items="center",
                    )
                ):
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="row",
                            gap=8,
                            align_items="center",
                        ),
                    ):
                        me.uploader(
                            label="Upload Person Image",
                            on_upload=on_upload_person,
                            key="person_uploader",
                        )
                        library_chooser_button(
                            key="person_library_chooser",
                            on_library_select=on_library_chooser,
                            button_label="Add from Library",
                        )
                        me.button(
                            "Create Virtual Model",
                            on_click=on_click_generate_person,
                        )
                    with me.box(style=IMAGE_BOX_STYLE):
                        if state.is_generating_person_image:
                            me.progress_spinner()
                        elif state.person_image_display_url:
                            me.image(
                                src=state.person_image_display_url,
                                key="person_image",
                                style=me.Style(
                                    width=400,
                                    height=400,
                                    border_radius=12,
                                    object_fit="contain",
                                ),
                            )
                        else:
                            me.icon("person_outline", style=me.Style(font_size=32, width="50px", height="60px"))
                            me.text("Upload a person image")

                # Product Image Section
                with me.box(
                    style=me.Style(
                        width="calc(50% - 8px)",
                        display="flex",
                        flex_direction="column",
                        align_items="center",
                    )
                ):
                    with me.box(
                        style=me.Style(
                            display="flex",
                            flex_direction="row",
                            gap=8,
                            align_items="center",
                        ),
                    ):
                        me.uploader(
                            label="Upload Product Image",
                            on_upload=on_upload_product,
                            key="product_uploader",
                        )
                        library_chooser_button(
                            key="product_library_chooser",
                            on_library_select=on_library_chooser,
                            button_label="Add from Library",
                        )
                    with me.box(style=IMAGE_BOX_STYLE):
                        if state.product_image_display_url:
                            me.image(
                                src=state.product_image_display_url,
                                key="product_image",
                                style=me.Style(
                                    width=400,
                                    height=400,
                                    border_radius=12,
                                    object_fit="contain",
                                ),
                            )
                        else:
                            me.icon("backpack", style=me.Style(font_size=32, width="50px", height="60px"))
                            me.text("Upload a product image")

            me.box(style=me.Style(height=36))

            with me.box(
                style=me.Style(
                    display="flex",
                    flex_direction="row",
                    gap=10,
                    align_items="center",
                    justify_content="center",
                ),
            ):
                with me.box(style=me.Style(margin=me.Margin(top=16))):
                    with me.box(
                        style=me.Style(display="flex", justify_content="space-between"),
                    ):
                        me.text(f"Number of images: {state.vto_sample_count}")
                    me.slider(
                        min=1,
                        max=4,
                        step=1,
                        value=state.vto_sample_count,
                        on_value_change=on_sample_count_change,
                    )

                me.box(style=me.Style(width=36))

                me.select(
                    label="Person Generation",
                    options=[
                        me.SelectOption(label="Allow (All ages)", value="allow_all"),
                        me.SelectOption(label="Allow (Adults only)", value="allow_adult"),
                        #me.SelectOption(label="Don't Allow", value="dont_allow"),
                    ],
                    appearance="outline",
                    value=state.person_generation,
                    on_selection_change=on_person_generation_change,
                    style=me.Style(width=200),
                )

                me.box(style=me.Style(width=36))

                me.select(
                    label="Safety Filter",
                    options=[
                        me.SelectOption(label="Block most", value="block_low_and_above"),
                        me.SelectOption(label="Block some", value="block_medium_and_above"),
                        me.SelectOption(label="Block few", value="block_only_high"),
                    ],
                    appearance="outline",
                    value=state.safety_filter_level,
                    on_selection_change=on_safety_filter_change,
                    style=me.Style(width=200),
                )


                me.box(style=me.Style(width=36))

                me.button("Generate", on_click=on_generate, type="flat")
                me.button("Clear", on_click=on_clear, type="stroked")

            if state.is_loading:
                with me.box(
                    style=me.Style(
                        display="flex",
                        align_items="center",
                        justify_content="center",
                    )
                ):
                    me.progress_spinner()

            if state.is_analyzing:
                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_direction="row",
                        gap=12,
                        align_items="center",
                        justify_content="center",
                        margin=me.Margin(top=16),
                    )
                ):
                    me.progress_spinner()
                    me.text("Analyzing garment placement with Gemini...")

            critique_map: dict[str, dict[str, str | bool]] = {}
            if state.critique_results_json:
                try:
                    critique_map = json.loads(state.critique_results_json)
                except json.JSONDecodeError:
                    critique_map = {}

            if state.result_display_urls:
                print(f"Images: {state.result_display_urls}")
                with me.box(
                    style=me.Style(
                        display="flex",
                        flex_wrap="wrap",
                        gap=16,
                        margin=me.Margin(top=16),
                        justify_content="center",
                    )
                ):
                    for i, display_url in enumerate(state.result_display_urls):
                        gcs_uri = state.result_gcs_uris[i]
                        critique = critique_map.get(gcs_uri)
                        with me.box(
                            style=me.Style(
                                display="flex",
                                flex_direction="column",
                                gap=8,
                                width="400px",
                            )
                        ):
                            me.image(
                                src=display_url,
                                style=me.Style(width="400px", border_radius=12),
                            )
                            with me.box(
                                style=me.Style(
                                    display="flex",
                                    flex_direction="row",
                                    gap=8,
                                    justify_content="center",
                                )
                            ):
                                edit_button(gcs_uri=gcs_uri)
                                veo_button(gcs_uri=gcs_uri)
                            if critique:
                                is_accurate = bool(critique.get("accurate", True))
                                with me.box(
                                    style=me.Style(
                                        background=me.theme_var(
                                            "surface-container-low"
                                        ),
                                        padding=me.Padding.all(12),
                                        border_radius=12,
                                        display="flex",
                                        flex_direction="column",
                                        gap=6,
                                    )
                                ):
                                    with me.box(
                                        style=me.Style(
                                            display="flex",
                                            flex_direction="row",
                                            gap=6,
                                            align_items="center",
                                        )
                                    ):
                                        me.icon(
                                            "verified"
                                            if is_accurate
                                            else "info",
                                            style=me.Style(
                                                color=me.theme_var("primary")
                                                if is_accurate
                                                else me.theme_var("error"),
                                                font_size=18,
                                            ),
                                        )
                                        me.text(
                                            "Placement Critique",
                                            style=me.Style(
                                                font_weight="bold",
                                                font_size=14,
                                            ),
                                        )
                                    me.markdown(
                                        str(
                                            critique.get(
                                                "placement_analysis",
                                                "Critique not available.",
                                            )
                                        )
                                    )

            snackbar(is_visible=state.show_snackbar, label=state.snackbar_message)