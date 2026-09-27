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
from unittest.mock import MagicMock, patch

import pytest

from models.omni import (
    MissingMediaError,
    _build_input_parts,
    _extract_video_payload,
    _modify_prompt_for_omni,
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
    # Resolution is passed through to the Interactions API via response_format.
    _, call_kwargs = mock_client.interactions.create.call_args
    assert call_kwargs["response_format"] == [
        {"type": "video", "resolution": "1080p"},
    ]
    mock_save.assert_called_once_with("encoded_video_data")


def test_modify_prompt_for_omni_defaults() -> None:
    """Test prompt modification when defaults (16:9, 10s) are selected."""
    res = _modify_prompt_for_omni("A cute dog running", "16:9", 10)
    assert res == "A cute dog running"


def test_modify_prompt_for_omni_custom_aspect() -> None:
    """Test prompt modification when custom aspect ratio is selected."""
    res = _modify_prompt_for_omni("A cute dog running", "9:16", 10)
    assert res == "A cute dog running, aspect ratio 9:16"


def test_modify_prompt_for_omni_custom_duration() -> None:
    """Test prompt modification when custom duration is selected."""
    res = _modify_prompt_for_omni("A cute dog running", "16:9", 6)
    assert res == "A cute dog running, duration 6s"


def test_modify_prompt_for_omni_both_custom() -> None:
    """Test prompt modification when both aspect and duration are custom."""
    res = _modify_prompt_for_omni("A cute dog running", "9:16", 8)
    assert res == "A cute dog running, aspect ratio 9:16, duration 8s"


def test_modify_prompt_for_omni_with_trailing_comma() -> None:
    """Test prompt modification when prompt ends with a comma."""
    res = _modify_prompt_for_omni("A cute dog running,", "9:16", 8)
    assert res == "A cute dog running, aspect ratio 9:16, duration 8s"


@patch("pages.omni.me.state")
@patch("common.storage.generate_upload_signed_url")
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
    """The 1.1 model is the default and the legacy model remains selectable."""
    from config.omni_models import (
        DEFAULT_OMNI_VERSION_ID,
        get_omni_model_config,
    )

    assert DEFAULT_OMNI_VERSION_ID == "gemini-omni-1.1-flash-preview"

    new_model = get_omni_model_config("gemini-omni-1.1-flash-preview")
    assert new_model is not None
    assert new_model.resolutions == ["360p", "720p", "1080p", "4k"]

    # Legacy model kept selectable (Q1) and constrained to 720p.
    legacy_model = get_omni_model_config("gemini-omni-flash-preview")
    assert legacy_model is not None
    assert legacy_model.resolutions == ["720p"]


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
    mock_state.return_value = mock_page_state

    event = MagicMock()
    event.value = "gemini-omni-1.1-flash-preview"

    list(on_model_change(event))

    assert mock_page_state.omni_model == "gemini-omni-1.1-flash-preview"
    assert mock_page_state.resolution == "1080p"


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
