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

"""Unit tests for Gemini Omni model backend services."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from common.error_handling import GenerationError
from models.omni import (
    MissingMediaError,
    _build_input_parts,
    _build_video_response_format,
    _extract_video_payload,
    find_missing_required_media,
    generate_omni_video,
)
from models.requests import APIReferenceImage, OmniVideoGenerationRequest


def test_build_input_parts_t2v() -> None:
    """Test building input parts for Text-to-Video mode."""
    req = OmniVideoGenerationRequest(
        prompt="A cute cat playing with yarn",
        duration_seconds=10,
        aspect_ratio="16:9",
        resolution="720p",
        omni_mode="t2v",
        model_version_id="gemini-omni-1.1-flash-preview",
    )
    parts = _build_input_parts(req)
    assert parts == [{"type": "text", "text": "A cute cat playing with yarn"}]


def test_build_input_parts_i2v() -> None:
    """Test building input parts for Image-to-Video mode."""
    req = OmniVideoGenerationRequest(
        prompt="Make it move",
        duration_seconds=10,
        aspect_ratio="16:9",
        resolution="720p",
        omni_mode="i2v",
        model_version_id="gemini-omni-1.1-flash-preview",
        reference_image_gcs="gs://bucket/image.png",
        reference_image_mime_type="image/png",
    )
    parts = _build_input_parts(req)
    assert len(parts) == 2
    assert parts[0] == {"type": "text", "text": "Make it move"}
    assert parts[1] == {
        "type": "image",
        "mime_type": "image/png",
        "uri": "gs://bucket/image.png",
    }


def test_build_input_parts_ref2v() -> None:
    """Test building input parts for Reference-to-Video mode."""
    req = OmniVideoGenerationRequest(
        prompt="Generate consistent video",
        duration_seconds=10,
        aspect_ratio="16:9",
        resolution="720p",
        omni_mode="ref2v",
        model_version_id="gemini-omni-1.1-flash-preview",
        r2v_references=[
            APIReferenceImage(gcs_uri="gs://bucket/ref1.jpg", mime_type="image/jpeg"),
            APIReferenceImage(gcs_uri="gs://bucket/ref2.jpg", mime_type="image/jpeg"),
        ],
    )
    parts = _build_input_parts(req)
    assert len(parts) == 3
    assert parts[0] == {"type": "text", "text": "Generate consistent video"}
    assert parts[1] == {
        "type": "image",
        "mime_type": "image/jpeg",
        "uri": "gs://bucket/ref1.jpg",
    }
    assert parts[2] == {
        "type": "image",
        "mime_type": "image/jpeg",
        "uri": "gs://bucket/ref2.jpg",
    }


def test_build_input_parts_edit() -> None:
    """Test building input parts for Video Editing mode."""
    req = OmniVideoGenerationRequest(
        prompt="Change character's shirt to blue",
        duration_seconds=10,
        aspect_ratio="16:9",
        resolution="720p",
        omni_mode="edit",
        model_version_id="gemini-omni-1.1-flash-preview",
        reference_image_gcs="gs://bucket/ref.png",
        reference_image_mime_type="image/png",
        reference_video_gcs="gs://bucket/base.mp4",
        reference_video_mime_type="video/mp4",
    )
    parts = _build_input_parts(req)
    assert len(parts) == 3
    assert parts[0] == {"type": "text", "text": "Change character's shirt to blue"}
    assert parts[1] == {
        "type": "image",
        "mime_type": "image/png",
        "uri": "gs://bucket/ref.png",
    }
    assert parts[2] == {
        "type": "video",
        "mime_type": "video/mp4",
        "uri": "gs://bucket/base.mp4",
    }


@patch("models.omni.download_from_gcs")
def test_build_input_parts_chat(mock_download: MagicMock) -> None:
    """Test building input parts for multi-turn chat mode."""
    mock_download.return_value = b"video_bytes_resolved"

    history = [
        {"type": "user_input", "content": [{"type": "text", "text": "Start video"}]},
        {
            "type": "model_output",
            "content": [
                {
                    "type": "video",
                    "gcs_uri": "gs://bucket/video.mp4",
                    "mime_type": "video/mp4",
                },
            ],
        },
    ]
    req = OmniVideoGenerationRequest(
        prompt="Make it faster",
        duration_seconds=10,
        aspect_ratio="16:9",
        resolution="720p",
        omni_mode="edit",
        model_version_id="gemini-omni-1.1-flash-preview",
        previous_interaction_id="int-123",
        chat_history_json=json.dumps(history),
    )
    parts = _build_input_parts(req)
    assert len(parts) == 3
    assert parts[0] == history[0]
    # Resolved model output containing base64 data
    assert parts[1] == {
        "type": "model_output",
        "content": [
            {
                "type": "video",
                "data": "dmlkZW9fYnl0ZXNfcmVzb2x2ZWQ=",
                "mime_type": "video/mp4",
            },
        ],
    }
    assert parts[2] == {
        "type": "user_input",
        "content": [{"type": "text", "text": "Make it faster"}],
    }
    mock_download.assert_called_once_with("gs://bucket/video.mp4")


def test_extract_video_payload() -> None:
    """Test parsing standard video payload from interaction steps."""
    mock_content = MagicMock()
    mock_content.type = "video"
    mock_content.data = "base64_data_here"

    mock_step = MagicMock()
    mock_step.type = "model_output"
    mock_step.content = [mock_content]

    mock_interaction = MagicMock()
    mock_interaction.id = "int-789"
    mock_interaction.steps = [mock_step]

    video_data, interaction_id = _extract_video_payload(mock_interaction)
    assert video_data == "base64_data_here"
    assert interaction_id == "int-789"


def test_extract_video_payload_failed_interaction_reports_errors() -> None:
    """A failed interaction surfaces the API's plural ``errors`` reason."""
    interaction = SimpleNamespace(
        id="int-failed",
        status="failed",
        steps=[SimpleNamespace(type="thought", content=[])],
        errors=[
            SimpleNamespace(
                message="Generation duration 20 seconds exceeds maximum duration 15 seconds.",
                code="invalid_request",
            ),
        ],
    )

    with pytest.raises(GenerationError) as exc_info:
        _extract_video_payload(interaction)

    message = str(exc_info.value)
    assert "failed" in message
    assert "exceeds maximum duration 15 seconds" in message
    assert "invalid_request" in message
    assert "No outputs returned" not in message


def test_extract_video_payload_failed_interaction_dict_and_singular_error() -> None:
    """Plain-dict responses and the singular ``error`` field are honoured too."""
    interaction = {
        "id": "int-failed",
        "status": "failed",
        "steps": [],
        "errors": [{"message": "first"}, {"message": "second", "code": "c"}],
        "error": {"message": "single"},
    }

    with pytest.raises(GenerationError) as exc_info:
        _extract_video_payload(interaction)

    message = str(exc_info.value)
    assert "first; second (code: c); single" in message


def test_extract_video_payload_failed_without_details() -> None:
    """A failed status with no errors list still raises, naming the status."""
    interaction = SimpleNamespace(
        id="int-failed",
        status="failed",
        steps=[],
        errors=None,
    )

    with pytest.raises(GenerationError, match="failed: no error details"):
        _extract_video_payload(interaction)


def test_extract_video_payload_completed_with_diagnostic_errors() -> None:
    """errors[] on a completed interaction is diagnostic; the video is kept."""
    interaction = SimpleNamespace(
        id="int-ok",
        status="completed",
        steps=[
            SimpleNamespace(
                type="model_output",
                content=[SimpleNamespace(type="video", data="ZGF0YQ==")],
            ),
        ],
        errors=[SimpleNamespace(message="minor diagnostic", code="warn")],
    )

    assert _extract_video_payload(interaction) == ("ZGF0YQ==", "int-ok")


@patch("models.omni.get_omni_client")
@patch("models.omni._save_video_to_gcs")
def test_generate_omni_video_success(
    mock_save: MagicMock,
    mock_get_client: MagicMock,
) -> None:
    """Test generate_omni_video orchestrator on success."""
    req = OmniVideoGenerationRequest(
        prompt="Cinematic city sunset",
        duration_seconds=10,
        aspect_ratio="16:9",
        resolution="1080p",
        omni_mode="t2v",
        model_version_id="gemini-omni-1.1-flash-preview",
    )

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_content = MagicMock()
    mock_content.type = "video"
    mock_content.data = "encoded_video_data"

    mock_step = MagicMock()
    mock_step.type = "model_output"
    mock_step.content = [mock_content]

    mock_interaction = MagicMock()
    mock_interaction.id = "new-interaction-id"
    mock_interaction.steps = [mock_step]

    mock_client.interactions.create.return_value = mock_interaction
    mock_save.return_value = "gs://bucket/videos/output.mp4"

    gcs_uri, interaction_id = generate_omni_video(req)
    assert gcs_uri == "gs://bucket/videos/output.mp4"
    assert interaction_id == "new-interaction-id"

    mock_client.interactions.create.assert_called_once()
    # Resolution, aspect ratio and duration are passed through to the
    # Interactions API via response_format, not the prompt text.
    _, call_kwargs = mock_client.interactions.create.call_args
    assert call_kwargs["response_format"] == [
        {
            "type": "video",
            "resolution": "1080p",
            "aspect_ratio": "16:9",
            "duration": "10s",
        },
    ]
    assert call_kwargs["input"][0] == {
        "type": "text",
        "text": "Cinematic city sunset",
    }
    mock_save.assert_called_once_with("encoded_video_data")


def test_build_video_response_format_generative_modes() -> None:
    """t2v/i2v/first_last/ref2v send resolution, aspect ratio and a 'Ns' duration."""
    for mode in ("t2v", "i2v", "first_last", "ref2v"):
        req = _omni_request(
            mode,
            resolution="360p",
            aspect_ratio="9:16",
            duration_seconds=5,
        )
        assert _build_video_response_format(req) == {
            "type": "video",
            "resolution": "360p",
            "aspect_ratio": "9:16",
            "duration": "5s",
        }


@pytest.mark.parametrize("mode", ["edit", "extend", "upscale"])
def test_build_video_response_format_input_derived_modes(mode: str) -> None:
    """Edit/extend/upscale keep the input's framing and length: resolution only.

    Verified live: edit with a duration that differs from the input length is
    rejected by the API with a 400.
    """
    req = _omni_request(
        mode,
        resolution="1080p",
        aspect_ratio="9:16",
        duration_seconds=5,
    )
    assert _build_video_response_format(req) == {
        "type": "video",
        "resolution": "1080p",
    }


def test_build_video_response_format_edit_without_resolution_is_none() -> None:
    """No response_format at all when nothing is left to send."""
    req = _omni_request("edit", resolution="", aspect_ratio="9:16", duration_seconds=5)
    assert _build_video_response_format(req) is None


def test_build_input_parts_never_appends_format_to_prompt() -> None:
    """Aspect ratio and duration must not pollute the prompt text."""
    req = _omni_request(
        "t2v",
        prompt="A cute dog running",
        aspect_ratio="9:16",
        duration_seconds=8,
    )
    assert _build_input_parts(req) == [
        {"type": "text", "text": "A cute dog running"},
    ]


@pytest.mark.parametrize(
    ("image_path", "expected"),
    [
        ("bucket/dir/img.png", "gs://bucket/dir/img.png"),
        ("gs://bucket/dir/img.png", "gs://bucket/dir/img.png"),
        (
            "https://storage.googleapis.com/bucket/dir/img.png?X-Goog-Signature=abc",
            "gs://bucket/dir/img.png",
        ),
    ],
)
def test_resolve_image_path_param(image_path: str, expected: str) -> None:
    """Deep-link image paths normalize to gs:// URIs."""
    from pages.omni import resolve_image_path_param

    assert resolve_image_path_param(image_path) == expected


@patch("pages.omni.create_display_url", return_value="https://display/img.jpg")
@patch("pages.omni.me.query_params", {"image_path": "bucket/dir/img.jpg"})
@patch("pages.omni.me.state")
def test_on_omni_load_with_image_path(
    mock_state: MagicMock, _mock_display: MagicMock
) -> None:
    """An image_path query param preloads the first-frame image in i2v mode."""
    from pages.omni import on_omni_load

    mock_page_state = MagicMock()
    mock_state.return_value = mock_page_state

    list(on_omni_load(MagicMock()))

    assert mock_page_state.omni_mode == "i2v"
    assert mock_page_state.reference_image_gcs == "gs://bucket/dir/img.jpg"
    assert mock_page_state.reference_image_uri == "https://display/img.jpg"
    assert mock_page_state.reference_image_mime_type == "image/jpeg"
    assert "Animate" in mock_page_state.prompt


@patch("pages.omni.me.query_params", {})
@patch("pages.omni.me.state")
def test_on_omni_load_without_image_path(mock_state: MagicMock) -> None:
    """Without an image_path the page keeps its text-to-video defaults."""
    from pages.omni import on_omni_load

    mock_page_state = MagicMock()
    mock_state.return_value = mock_page_state

    list(on_omni_load(MagicMock()))

    assert mock_page_state.omni_mode == "t2v"
    assert "Omni" in mock_page_state.prompt


@patch("components.omni_button.omni_button.log_ui_click")
@patch("components.omni_button.omni_button.me.navigate")
@patch("components.omni_button.omni_button.me.state")
def test_on_send_to_omni_navigates(
    _mock_state: MagicMock, mock_navigate: MagicMock, mock_log: MagicMock
) -> None:
    """The Omni button navigates to the Omni page with the image path."""
    from components.omni_button.omni_button import on_send_to_omni

    event = MagicMock()
    event.key = "gs://bucket/dir/img.png"

    list(on_send_to_omni(event))

    mock_navigate.assert_called_once_with(
        url="/gemini-omni",
        query_params={"image_path": "bucket/dir/img.png"},
    )
    mock_log.assert_called_once()


@patch("pages.omni.me.state")
@patch("pages.omni.generate_upload_signed_url")
def test_on_request_signed_url_video(
    mock_sign: MagicMock,
    mock_state: MagicMock,
) -> None:
    """Test generating signed URL event handler."""
    from pages.omni import on_request_signed_url_video

    mock_page_state = MagicMock()
    mock_state.return_value = mock_page_state

    mock_sign.return_value = "https://gcs-signed-url.com/upload"

    event = MagicMock()
    # Mesop's WebEvent mapper json.loads()s the whole dispatched object, so the
    # handler receives the wrapper dict the JS component sent, not the inner value.
    event.value = {
        "value": (
            '{"filename": "test_video.mp4", "contentType": "video/mp4", "fileSize": 1024}'
        ),
    }

    gen = on_request_signed_url_video(event)
    list(gen)

    assert (
        mock_page_state.video_upload_signed_url == "https://gcs-signed-url.com/upload"
    )
    assert "test_video.mp4" in mock_page_state.video_upload_gcs_uri
    assert mock_page_state.video_upload_error == ""
    mock_sign.assert_called_once()


@patch("pages.omni.me.state")
def test_on_upload_complete_video(mock_state: MagicMock) -> None:
    """Test direct upload completion event handler."""
    from pages.omni import on_upload_complete_video

    mock_page_state = MagicMock()
    mock_state.return_value = mock_page_state

    event = MagicMock()
    event.value = {"value": "gs://bucket/uploads/uuid_test_video.mp4"}

    gen = on_upload_complete_video(event)
    list(gen)

    assert (
        mock_page_state.reference_video_gcs == "gs://bucket/uploads/uuid_test_video.mp4"
    )
    assert "uuid_test_video.mp4" in mock_page_state.reference_video_uri
    assert mock_page_state.video_upload_signed_url == ""


@patch("pages.omni.me.state")
def test_on_upload_progress_video(mock_state: MagicMock) -> None:
    """Test upload progress tracking event handler."""
    from pages.omni import on_upload_progress_video

    mock_page_state = MagicMock()
    mock_state.return_value = mock_page_state

    event = MagicMock()
    event.value = {"value": "45"}

    gen = on_upload_progress_video(event)
    list(gen)

    assert mock_page_state.video_upload_progress == 45


@patch("pages.omni.me.state")
def test_on_upload_error_video(mock_state: MagicMock) -> None:
    """Test upload error event handler."""
    from pages.omni import on_upload_error_video

    mock_page_state = MagicMock()
    mock_state.return_value = mock_page_state

    event = MagicMock()
    event.value = {"value": "Network timeout"}

    gen = on_upload_error_video(event)
    list(gen)

    assert mock_page_state.error_message == "Video upload failed: Network timeout"
    assert mock_page_state.show_error_dialog is True
    assert mock_page_state.video_upload_progress == 0


@patch("pages.omni.me.state")
def test_on_video_select(mock_state: MagicMock) -> None:
    """Test selecting a video from library callback."""
    from components.library.events import LibrarySelectionChangeEvent
    from pages.omni import on_video_select

    mock_page_state = MagicMock()
    mock_state.return_value = mock_page_state

    event = LibrarySelectionChangeEvent(gcs_uri="gs://bucket/library/vid.mp4")

    gen = on_video_select(event)
    list(gen)

    assert mock_page_state.reference_video_gcs == "gs://bucket/library/vid.mp4"
    assert "vid.mp4" in mock_page_state.reference_video_uri


def test_omni_registry_default_and_legacy_model() -> None:
    """The 1.2 model is the default and earlier models remain selectable."""
    from config.omni_models import (
        DEFAULT_OMNI_VERSION_ID,
        get_omni_model_config,
    )

    assert DEFAULT_OMNI_VERSION_ID == "gemini-omni-1.2-flash"

    latest = get_omni_model_config("gemini-omni-1.2-flash")
    assert latest is not None
    assert latest.resolutions == ["360p", "720p", "1080p", "4k"]
    assert latest.supported_aspect_ratios == ["16:9", "9:16"]
    assert (latest.min_duration, latest.max_duration) == (3, 15)
    assert latest.default_duration == 10

    # The 1.1 model stays selectable with its original limits.
    new_model = get_omni_model_config("gemini-omni-1.1-flash-preview")
    assert new_model is not None
    assert new_model.resolutions == ["360p", "720p", "1080p", "4k"]
    assert (new_model.min_duration, new_model.max_duration) == (3, 10)

    # Legacy model kept selectable (Q1) and constrained to 720p.
    legacy_model = get_omni_model_config("gemini-omni-flash-preview")
    assert legacy_model is not None
    assert legacy_model.resolutions == ["720p"]


def test_omni_registry_default_config_matches_registry() -> None:
    """The configured default model names resolve to a registered model."""
    from config.default import Default
    from config.omni_models import get_omni_model_config

    cfg = Default()
    assert get_omni_model_config(cfg.DEFAULT_OMNI_MODEL_NAME) is not None
    assert get_omni_model_config(cfg.OMNI_MODEL_ID) is not None


def test_omni_page_state_defaults_to_1_2() -> None:
    """A fresh Omni page session starts on 1.2 with settings it supports."""
    import dataclasses

    from config.omni_models import get_omni_model_config, modes_for_model
    from state.omni_state import PageState

    defaults = {f.name: f.default for f in dataclasses.fields(PageState)}

    assert defaults["omni_model"] == "gemini-omni-1.2-flash"

    # The remaining defaults must be valid for the default model so the page
    # never opens in a state that on_model_change would have to repair.
    config = get_omni_model_config(defaults["omni_model"])
    assert config is not None
    assert defaults["omni_mode"] in modes_for_model(defaults["omni_model"])
    assert defaults["resolution"] in config.resolutions
    assert defaults["aspect_ratio"] in config.supported_aspect_ratios
    assert config.min_duration <= defaults["video_length"] <= config.max_duration
    assert (defaults["resolution"], defaults["video_length"]) == ("720p", 10)


def test_omni_modes_offered_by_default_model_include_extend_and_upscale() -> None:
    """The default model exposes the full 1.2 mode list in the page selector."""
    from config.omni_models import modes_for_model
    from state.omni_state import PageState

    default_modes = modes_for_model(PageState.omni_model)
    assert "extend" in default_modes
    assert "upscale" in default_modes


def test_modes_for_model_gates_extend_and_upscale() -> None:
    """Extend and upscale are offered only by models that support them."""
    from config.omni_models import modes_for_model

    assert modes_for_model("gemini-omni-1.2-flash") == [
        "t2v",
        "i2v",
        "first_last",
        "ref2v",
        "edit",
        "extend",
        "upscale",
    ]
    assert modes_for_model("gemini-omni-1.1-flash-preview") == [
        "t2v",
        "i2v",
        "first_last",
        "ref2v",
        "edit",
    ]
    # The legacy model has not been verified for first/last frame.
    assert "first_last" not in modes_for_model("gemini-omni-flash-preview")
    # Unknown models fall back to the four common modes.
    assert modes_for_model("no-such-model") == ["t2v", "i2v", "ref2v", "edit"]


def test_clamp_duration_uses_model_range() -> None:
    """Durations are clamped into each model's supported range."""
    from config.omni_models import clamp_duration

    assert clamp_duration("gemini-omni-1.2-flash", 15) == 15
    assert clamp_duration("gemini-omni-1.2-flash", 30) == 15
    assert clamp_duration("gemini-omni-1.2-flash", 1) == 3
    assert clamp_duration("gemini-omni-1.1-flash-preview", 15) == 10
    assert clamp_duration("no-such-model", 42) == 42


@patch("pages.omni.me.state")
def test_on_resolution_change(mock_state: MagicMock) -> None:
    """Resolution selection updates page state."""
    from pages.omni import on_resolution_change

    mock_page_state = MagicMock()
    mock_state.return_value = mock_page_state

    event = MagicMock()
    event.value = "1080p"

    list(on_resolution_change(event))

    assert mock_page_state.resolution == "1080p"


@patch("pages.omni.me.state")
def test_on_model_change_resets_unsupported_resolution(mock_state: MagicMock) -> None:
    """Switching to the legacy model resets a resolution it doesn't support."""
    from pages.omni import on_model_change

    mock_page_state = MagicMock()
    mock_page_state.resolution = "4k"
    mock_page_state.omni_mode = "t2v"
    mock_page_state.video_length = 10
    mock_state.return_value = mock_page_state

    event = MagicMock()
    event.value = "gemini-omni-flash-preview"

    list(on_model_change(event))

    assert mock_page_state.omni_model == "gemini-omni-flash-preview"
    # 4k is not supported by the legacy model; it falls back to its first option.
    assert mock_page_state.resolution == "720p"


@patch("pages.omni.me.state")
def test_on_model_change_keeps_supported_resolution(mock_state: MagicMock) -> None:
    """Switching models keeps a resolution the new model supports."""
    from pages.omni import on_model_change

    mock_page_state = MagicMock()
    mock_page_state.resolution = "1080p"
    mock_page_state.omni_mode = "t2v"
    mock_page_state.video_length = 10
    mock_state.return_value = mock_page_state

    event = MagicMock()
    event.value = "gemini-omni-1.1-flash-preview"

    list(on_model_change(event))

    assert mock_page_state.omni_model == "gemini-omni-1.1-flash-preview"
    assert mock_page_state.resolution == "1080p"


@patch("pages.omni.me.state")
def test_on_model_change_resets_unsupported_mode_and_clamps_duration(
    mock_state: MagicMock,
) -> None:
    """Switching 1.2 -> 1.1 drops extend/upscale and clamps 15s to 10s."""
    from pages.omni import on_model_change

    mock_page_state = MagicMock()
    mock_page_state.resolution = "720p"
    mock_page_state.omni_mode = "extend"
    mock_page_state.video_length = 15
    mock_state.return_value = mock_page_state

    event = MagicMock()
    event.value = "gemini-omni-1.1-flash-preview"

    list(on_model_change(event))

    assert mock_page_state.omni_mode == "t2v"
    assert mock_page_state.video_length == 10


@patch("pages.omni.me.state")
def test_on_model_change_keeps_supported_mode_and_duration(
    mock_state: MagicMock,
) -> None:
    """Switching to 1.2 keeps a mode and duration it supports."""
    from pages.omni import on_model_change

    mock_page_state = MagicMock()
    mock_page_state.resolution = "720p"
    mock_page_state.omni_mode = "upscale"
    mock_page_state.video_length = 12
    mock_state.return_value = mock_page_state

    event = MagicMock()
    event.value = "gemini-omni-1.2-flash"

    list(on_model_change(event))

    assert mock_page_state.omni_mode == "upscale"
    assert mock_page_state.video_length == 12


# ==============================================================================
# Required-media validation (issue #1929)
# ==============================================================================


def _omni_request(mode: str, **overrides: object) -> OmniVideoGenerationRequest:
    """Build a minimal OmniVideoGenerationRequest for a given mode."""
    kwargs = {
        "prompt": "A neon sign glowing on a brick wall",
        "duration_seconds": 10,
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "omni_mode": mode,
        "model_version_id": "gemini-omni-1.1-flash-preview",
    }
    kwargs.update(overrides)
    return OmniVideoGenerationRequest(**kwargs)


def test_find_missing_required_media_t2v_never_requires_media() -> None:
    """Text-to-Video needs no media, so nothing is ever reported missing."""
    assert (
        find_missing_required_media(
            "t2v",
            has_image=False,
            has_video=False,
            reference_count=0,
        )
        is None
    )


def test_find_missing_required_media_i2v() -> None:
    """Image-to-Video requires an image; missing when absent, satisfied when present."""
    assert (
        find_missing_required_media(
            "i2v",
            has_image=False,
            has_video=False,
            reference_count=0,
        )
        is not None
    )
    assert (
        find_missing_required_media(
            "i2v",
            has_image=True,
            has_video=False,
            reference_count=0,
        )
        is None
    )


def test_find_missing_required_media_ref2v() -> None:
    """Reference-to-Video requires at least one reference image."""
    assert (
        find_missing_required_media(
            "ref2v",
            has_image=False,
            has_video=False,
            reference_count=0,
        )
        is not None
    )
    assert (
        find_missing_required_media(
            "ref2v",
            has_image=False,
            has_video=False,
            reference_count=1,
        )
        is None
    )


def test_find_missing_required_media_edit_requires_base_video() -> None:
    """Edit requires a base video; an image alone is not a valid edit."""
    # Nothing attached -> missing.
    assert (
        find_missing_required_media(
            "edit",
            has_image=False,
            has_video=False,
            reference_count=0,
        )
        is not None
    )
    # Image only (no base video) -> still missing (image-only edit is not valid).
    assert (
        find_missing_required_media(
            "edit",
            has_image=True,
            has_video=False,
            reference_count=0,
        )
        is not None
    )
    # Base video present -> satisfied.
    assert (
        find_missing_required_media(
            "edit",
            has_image=False,
            has_video=True,
            reference_count=0,
        )
        is None
    )


@patch("models.omni.get_omni_client")
@patch("models.omni.track_model_call")
def test_generate_omni_video_i2v_missing_image_no_model_call(
    mock_track: MagicMock,
    mock_get_client: MagicMock,
) -> None:
    """i2v without an image raises before the model-call span (no false failure)."""
    req = _omni_request("i2v")

    with pytest.raises(MissingMediaError):
        generate_omni_video(req)

    # The raise happens before track_model_call is entered, so no model_call
    # (success or failure) is ever logged, and no client is created/called.
    mock_track.assert_not_called()
    mock_get_client.assert_not_called()


@patch("models.omni.get_omni_client")
@patch("models.omni.track_model_call")
def test_generate_omni_video_ref2v_missing_refs_no_model_call(
    mock_track: MagicMock,
    mock_get_client: MagicMock,
) -> None:
    """ref2v without references raises before the model-call span."""
    req = _omni_request("ref2v")

    with pytest.raises(MissingMediaError):
        generate_omni_video(req)

    mock_track.assert_not_called()
    mock_get_client.assert_not_called()


@patch("models.omni.get_omni_client")
@patch("models.omni.track_model_call")
def test_generate_omni_video_edit_no_media_is_not_billed(
    mock_track: MagicMock,
    mock_get_client: MagicMock,
) -> None:
    """Edit with neither video nor image must not reach the billable API.

    Regression guard for the #1929 billing hole: before the fix this request
    fell through to ``client.interactions.create`` with a prompt-only input.
    """
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    req = _omni_request("edit")

    with pytest.raises(MissingMediaError):
        generate_omni_video(req)

    # No billable interaction created, and no model_call span opened.
    mock_client.interactions.create.assert_not_called()
    mock_track.assert_not_called()


@patch("models.omni.get_omni_client")
@patch("models.omni.track_model_call")
def test_generate_omni_video_edit_image_only_is_not_billed(
    mock_track: MagicMock,
    mock_get_client: MagicMock,
) -> None:
    """Edit with an image but no base video is rejected before any billed call."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    req = _omni_request(
        "edit",
        reference_image_gcs="gs://bucket/ref.png",
        reference_image_mime_type="image/png",
    )

    with pytest.raises(MissingMediaError):
        generate_omni_video(req)

    mock_client.interactions.create.assert_not_called()
    mock_track.assert_not_called()


@patch("models.omni._save_video_to_gcs")
@patch("models.omni.get_omni_client")
def test_generate_omni_video_multiturn_skips_media_check(
    mock_get_client: MagicMock,
    mock_save: MagicMock,
) -> None:
    """Multi-turn refinement skips the per-mode media requirement.

    Multi-turn operates on an existing interaction, so the check does not apply
    even when no media is attached to the follow-up turn.
    """
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_content = MagicMock()
    mock_content.type = "video"
    mock_content.data = "encoded_video_data"
    mock_step = MagicMock()
    mock_step.type = "model_output"
    mock_step.content = [mock_content]
    mock_interaction = MagicMock()
    mock_interaction.id = "int-next"
    mock_interaction.steps = [mock_step]
    mock_client.interactions.create.return_value = mock_interaction
    mock_save.return_value = "gs://bucket/videos/output.mp4"

    req = _omni_request(
        "edit",
        previous_interaction_id="int-prev",
        chat_history_json=json.dumps(
            [
                {
                    "type": "user_input",
                    "content": [{"type": "text", "text": "Start"}],
                },
            ],
        ),
    )

    gcs_uri, interaction_id = generate_omni_video(req)
    assert gcs_uri == "gs://bucket/videos/output.mp4"
    assert interaction_id == "int-next"
    mock_client.interactions.create.assert_called_once()


# ==============================================================================
# Extend and upscale (Gemini Omni 1.2)
# ==============================================================================

OMNI_12 = "gemini-omni-1.2-flash"


def test_find_missing_required_media_extend_and_upscale() -> None:
    """Extend and upscale both need a video; an image or references don't help."""
    for mode in ("extend", "upscale"):
        assert (
            find_missing_required_media(
                mode,
                has_image=True,
                has_video=False,
                reference_count=3,
            )
            is not None
        )
        assert (
            find_missing_required_media(
                mode,
                has_image=False,
                has_video=True,
                reference_count=0,
            )
            is None
        )


def test_build_input_parts_extend_sends_prompt_and_video() -> None:
    """Extend sends the prompt (unmodified) followed by the base video."""
    req = _omni_request(
        "extend",
        prompt="Keep going as the camera pulls back",
        duration_seconds=5,
        aspect_ratio="9:16",
        model_version_id=OMNI_12,
        reference_video_gcs="gs://bucket/base.mp4",
        reference_video_mime_type="video/mp4",
    )
    parts = _build_input_parts(req)
    # No aspect ratio / duration suffix: the output follows the input video.
    assert parts == [
        {"type": "text", "text": "Keep going as the camera pulls back"},
        {"type": "video", "mime_type": "video/mp4", "uri": "gs://bucket/base.mp4"},
    ]


def test_build_input_parts_upscale_is_video_only() -> None:
    """Upscale must not send any text part (the API rejects text for upscale)."""
    req = _omni_request(
        "upscale",
        prompt="ignored",
        model_version_id=OMNI_12,
        reference_video_gcs="gs://bucket/base.mp4",
        reference_video_mime_type="video/mp4",
    )
    parts = _build_input_parts(req)
    assert parts == [
        {"type": "video", "mime_type": "video/mp4", "uri": "gs://bucket/base.mp4"},
    ]


def _mock_video_interaction(interaction_id: str = "int-1") -> MagicMock:
    """Build a mock Interactions response holding one video output."""
    content = MagicMock()
    content.type = "video"
    content.data = "encoded_video_data"
    step = MagicMock()
    step.type = "model_output"
    step.content = [content]
    interaction = MagicMock()
    interaction.id = interaction_id
    interaction.steps = [step]
    return interaction


@pytest.mark.parametrize("mode", ["extend", "upscale"])
@patch("models.omni._save_video_to_gcs")
@patch("models.omni.get_omni_client")
def test_generate_omni_video_sends_explicit_task(
    mock_get_client: MagicMock,
    mock_save: MagicMock,
    mode: str,
) -> None:
    """Extend and upscale send generation_config.video_config.task."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.interactions.create.return_value = _mock_video_interaction()
    mock_save.return_value = "gs://bucket/videos/output.mp4"

    req = _omni_request(
        mode,
        resolution="1080p",
        model_version_id=OMNI_12,
        reference_video_gcs="gs://bucket/base.mp4",
    )
    generate_omni_video(req)

    _, kwargs = mock_client.interactions.create.call_args
    assert kwargs["generation_config"] == {"video_config": {"task": mode}}
    assert kwargs["response_format"] == [{"type": "video", "resolution": "1080p"}]
    if mode == "upscale":
        assert all(p["type"] != "text" for p in kwargs["input"])


def test_find_missing_required_media_first_last() -> None:
    """First/Last Frame needs both images; a video or references don't help."""
    assert (
        find_missing_required_media(
            "first_last",
            has_image=True,
            has_last_image=False,
            has_video=True,
            reference_count=3,
        )
        is not None
    )
    assert (
        find_missing_required_media(
            "first_last",
            has_image=False,
            has_last_image=True,
            has_video=False,
            reference_count=0,
        )
        is not None
    )
    assert (
        find_missing_required_media(
            "first_last",
            has_image=True,
            has_last_image=True,
            has_video=False,
            reference_count=0,
        )
        is None
    )


def test_build_input_parts_first_last_orders_first_then_last() -> None:
    """The first-frame image is sent before the last-frame image, after the prompt."""
    req = _omni_request(
        "first_last",
        prompt="Day turns to night",
        model_version_id=OMNI_12,
        reference_image_gcs="gs://bucket/first.png",
        reference_image_mime_type="image/png",
        last_reference_image_gcs="gs://bucket/last.jpg",
        last_reference_image_mime_type="image/jpeg",
    )
    assert _build_input_parts(req) == [
        {"type": "text", "text": "Day turns to night"},
        {"type": "image", "mime_type": "image/png", "uri": "gs://bucket/first.png"},
        {"type": "image", "mime_type": "image/jpeg", "uri": "gs://bucket/last.jpg"},
    ]


@patch("models.omni._save_video_to_gcs")
@patch("models.omni.get_omni_client")
def test_generate_omni_video_first_last_sends_image_to_video_task(
    mock_get_client: MagicMock,
    mock_save: MagicMock,
) -> None:
    """First/Last Frame is image_to_video with two images, aspect and duration."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.interactions.create.return_value = _mock_video_interaction()
    mock_save.return_value = "gs://bucket/videos/output.mp4"

    req = _omni_request(
        "first_last",
        resolution="360p",
        aspect_ratio="16:9",
        duration_seconds=5,
        model_version_id=OMNI_12,
        reference_image_gcs="gs://bucket/first.png",
        last_reference_image_gcs="gs://bucket/last.png",
    )
    generate_omni_video(req)

    _, kwargs = mock_client.interactions.create.call_args
    assert kwargs["generation_config"] == {"video_config": {"task": "image_to_video"}}
    assert kwargs["response_format"] == [
        {
            "type": "video",
            "resolution": "360p",
            "aspect_ratio": "16:9",
            "duration": "5s",
        },
    ]
    uris = [p["uri"] for p in kwargs["input"] if p["type"] == "image"]
    assert uris == ["gs://bucket/first.png", "gs://bucket/last.png"]


@pytest.mark.parametrize("model", [OMNI_12, "gemini-omni-1.1-flash-preview"])
@pytest.mark.parametrize("ref_count", [1, 2, 3])
@patch("models.omni._save_video_to_gcs")
@patch("models.omni.get_omni_client")
def test_generate_omni_video_ref2v_sends_reference_to_video_task(
    mock_get_client: MagicMock,
    mock_save: MagicMock,
    ref_count: int,
    model: str,
) -> None:
    """Reference to video sends an explicit task for 1-3 references.

    Inferred, a single reference image is treated as the literal first frame.
    """
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.interactions.create.return_value = _mock_video_interaction()
    mock_save.return_value = "gs://bucket/videos/output.mp4"

    refs = [
        APIReferenceImage(gcs_uri=f"gs://bucket/ref{i}.png", mime_type="image/png")
        for i in range(ref_count)
    ]
    req = _omni_request(
        "ref2v",
        model_version_id=model,
        r2v_references=refs,
    )
    generate_omni_video(req)

    _, kwargs = mock_client.interactions.create.call_args
    assert kwargs["generation_config"] == {
        "video_config": {"task": "reference_to_video"},
    }
    uris = [p["uri"] for p in kwargs["input"] if p["type"] == "image"]
    assert uris == [r.gcs_uri for r in refs]


@pytest.mark.parametrize("mode", ["first_last", "ref2v", "extend"])
@patch("models.omni._save_video_to_gcs")
@patch("models.omni.get_omni_client")
def test_generate_omni_video_chat_follow_up_omits_task(
    mock_get_client: MagicMock,
    mock_save: MagicMock,
    mode: str,
) -> None:
    """Follow-ups never send a task: the API rejects it with previous_interaction_id.

    Live: "previous_interaction_id is not allowed when video task is set".
    """
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.interactions.create.return_value = _mock_video_interaction()
    mock_save.return_value = "gs://bucket/videos/output.mp4"

    req = _omni_request(
        mode,
        model_version_id=OMNI_12,
        previous_interaction_id="int-prev",
        chat_history_json=json.dumps(
            [{"type": "user_input", "content": [{"type": "text", "text": "Start"}]}],
        ),
    )
    generate_omni_video(req)

    _, kwargs = mock_client.interactions.create.call_args
    assert "generation_config" not in kwargs
    assert kwargs["previous_interaction_id"] == "int-prev"


@patch("models.omni.get_omni_client")
@patch("models.omni.track_model_call")
def test_generate_omni_video_first_last_missing_last_frame_not_billed(
    mock_track: MagicMock,
    mock_get_client: MagicMock,
) -> None:
    """A missing last frame never reaches the billable API."""
    req = _omni_request(
        "first_last",
        model_version_id=OMNI_12,
        reference_image_gcs="gs://bucket/first.png",
    )

    with pytest.raises(MissingMediaError, match="first and a last frame"):
        generate_omni_video(req)

    mock_track.assert_not_called()
    mock_get_client.assert_not_called()


@patch("models.omni.get_omni_client")
@patch("models.omni.track_model_call")
def test_generate_omni_video_first_last_rejected_on_legacy_model(
    mock_track: MagicMock,
    mock_get_client: MagicMock,
) -> None:
    """A model without first/last frame is rejected before any billable call."""
    req = _omni_request(
        "first_last",
        model_version_id="gemini-omni-flash-preview",
        reference_image_gcs="gs://bucket/first.png",
        last_reference_image_gcs="gs://bucket/last.png",
    )

    with pytest.raises(GenerationError, match="first_last"):
        generate_omni_video(req)

    mock_track.assert_not_called()
    mock_get_client.assert_not_called()


@patch("models.omni._save_video_to_gcs")
@patch("models.omni.get_omni_client")
def test_generate_omni_video_other_modes_omit_task(
    mock_get_client: MagicMock,
    mock_save: MagicMock,
) -> None:
    """Modes the model can infer keep the plain request shape (no task)."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_client.interactions.create.return_value = _mock_video_interaction()
    mock_save.return_value = "gs://bucket/videos/output.mp4"

    generate_omni_video(_omni_request("t2v", model_version_id=OMNI_12))

    _, kwargs = mock_client.interactions.create.call_args
    assert "generation_config" not in kwargs


@pytest.mark.parametrize("mode", ["extend", "upscale"])
@patch("models.omni.get_omni_client")
@patch("models.omni.track_model_call")
def test_generate_omni_video_extend_upscale_rejected_on_1_1(
    mock_track: MagicMock,
    mock_get_client: MagicMock,
    mode: str,
) -> None:
    """A model without the mode is rejected before any billable call."""
    from common.error_handling import GenerationError

    req = _omni_request(mode, reference_video_gcs="gs://bucket/base.mp4")

    with pytest.raises(GenerationError, match=mode):
        generate_omni_video(req)

    mock_track.assert_not_called()
    mock_get_client.assert_not_called()


@pytest.mark.parametrize("mode", ["extend", "upscale"])
@patch("models.omni.get_omni_client")
@patch("models.omni.track_model_call")
def test_generate_omni_video_extend_upscale_missing_video_not_billed(
    mock_track: MagicMock,
    mock_get_client: MagicMock,
    mode: str,
) -> None:
    """Extend/upscale without a video never reach the billable API."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    with pytest.raises(MissingMediaError):
        generate_omni_video(_omni_request(mode, model_version_id=OMNI_12))

    mock_client.interactions.create.assert_not_called()
    mock_track.assert_not_called()
