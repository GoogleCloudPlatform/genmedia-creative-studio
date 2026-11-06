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

"""Tests for Storyboarder video-model routing (Gemini Omni and Veo)."""

import dataclasses
from unittest.mock import MagicMock, patch

import pytest

from common.error_handling import GenerationError
from config.omni_models import OMNI_MODELS
from config.veo_models import VEO_MODELS
from models import storyboard_video
from models.storyboard_video import (
    generate_storyboard_clip,
    is_omni_model,
    supported_aspect_ratios,
    video_model_options,
)
from pages.storyboarder import on_video_model_change
from state.storyboarder_state import PageState


def test_storyboarder_defaults_to_omni_1_2() -> None:
    """A fresh Storyboarder session animates with Gemini Omni 1.2."""
    defaults = {f.name: f.default for f in dataclasses.fields(PageState)}
    assert defaults["selected_video_model"] == "gemini-omni-1.2-flash"
    assert is_omni_model(defaults["selected_video_model"])
    # The default must be one of the dropdown choices and accept the default
    # aspect ratio.
    values = [value for _, value in video_model_options()]
    assert defaults["selected_video_model"] in values
    assert defaults["aspect_ratio"] in supported_aspect_ratios(
        defaults["selected_video_model"],
    )


def test_video_model_options_lists_omni_first_then_veo() -> None:
    """The dropdown is registry driven: i2v Omni models, then every Veo model."""
    options = video_model_options()
    omni_ids = [m.version_id for m in OMNI_MODELS if "i2v" in m.supported_modes]
    veo_ids = [m.version_id for m in VEO_MODELS]
    assert [value for _, value in options] == omni_ids + veo_ids
    assert options[0] == ("Gemini Omni 1.2 Flash", "gemini-omni-1.2-flash")
    assert len({value for _, value in options}) == len(options)


def test_supported_aspect_ratios() -> None:
    """Omni is limited to 16:9 and 9:16; Veo keeps the storyboard set."""
    assert supported_aspect_ratios("gemini-omni-1.2-flash") == ["16:9", "9:16"]
    assert supported_aspect_ratios(VEO_MODELS[0].version_id) == [
        "16:9",
        "9:16",
        "1:1",
    ]


@patch.object(storyboard_video, "generate_video")
@patch.object(storyboard_video, "generate_omni_video")
def test_generate_storyboard_clip_omni_sends_i2v_request(
    mock_omni: MagicMock,
    mock_veo: MagicMock,
) -> None:
    """Omni models receive an i2v request and never touch the Veo path."""
    mock_omni.return_value = ("gs://bucket/clip.mp4", "interaction-1")

    uri = generate_storyboard_clip(
        "gemini-omni-1.2-flash",
        "gs://bucket/frame.png",
        "The hero turns around.",
        "9:16",
    )

    assert uri == "gs://bucket/clip.mp4"
    mock_veo.assert_not_called()
    request = mock_omni.call_args.args[0]
    assert request.omni_mode == "i2v"
    assert request.model_version_id == "gemini-omni-1.2-flash"
    assert request.reference_image_gcs == "gs://bucket/frame.png"
    assert request.reference_image_mime_type == "image/png"
    assert request.prompt == "The hero turns around."
    assert request.aspect_ratio == "9:16"
    assert request.duration_seconds == 4
    assert request.resolution == "720p"


@patch.object(storyboard_video, "generate_video")
@patch.object(storyboard_video, "generate_omni_video")
def test_generate_storyboard_clip_omni_rejects_unsupported_aspect(
    mock_omni: MagicMock,
    mock_veo: MagicMock,
) -> None:
    """A 1:1 storyboard fails fast with a hint, before any billable call."""
    with pytest.raises(GenerationError, match="16:9, 9:16"):
        generate_storyboard_clip(
            "gemini-omni-1.2-flash",
            "gs://bucket/frame.png",
            "prompt",
            "1:1",
        )
    mock_omni.assert_not_called()
    mock_veo.assert_not_called()


@patch.object(storyboard_video, "generate_video")
@patch.object(storyboard_video, "generate_omni_video")
def test_generate_storyboard_clip_veo_keeps_existing_request(
    mock_omni: MagicMock,
    mock_veo: MagicMock,
) -> None:
    """Veo models keep the previous request shape and return the first clip."""
    mock_veo.return_value = (["gs://bucket/veo.mp4"], [])
    veo_id = VEO_MODELS[0].version_id

    uri = generate_storyboard_clip(
        veo_id,
        "gs://bucket/frame.png",
        "Camera pans left.",
        "16:9",
    )

    assert uri == "gs://bucket/veo.mp4"
    mock_omni.assert_not_called()
    request = mock_veo.call_args.args[0]
    assert request.model_version_id == veo_id
    assert request.reference_image_gcs == "gs://bucket/frame.png"
    assert request.duration_seconds == 4
    assert request.resolution == "720p"
    assert request.aspect_ratio == "16:9"
    assert request.generate_audio is True
    assert request.video_count == 1


@patch.object(storyboard_video, "generate_video")
def test_generate_storyboard_clip_veo_no_video_returns_none(
    mock_veo: MagicMock,
) -> None:
    """An empty Veo response is reported as None so the page can show an error."""
    mock_veo.return_value = ([], [])
    assert (
        generate_storyboard_clip(
            VEO_MODELS[0].version_id,
            "gs://bucket/frame.png",
            "prompt",
            "16:9",
        )
        is None
    )


def test_generate_storyboard_clip_unknown_model() -> None:
    """Unknown model ids raise a clear error instead of defaulting silently."""
    with pytest.raises(GenerationError, match="Unsupported storyboard video model"):
        generate_storyboard_clip("no-such-model", "gs://b/f.png", "p", "16:9")


@patch("pages.storyboarder.me.state")
def test_on_video_model_change_resets_unsupported_aspect_ratio(
    mock_state: MagicMock,
) -> None:
    """Switching to Omni snaps a 1:1 storyboard back to a supported ratio."""
    state = SimpleNamespaceState(aspect_ratio="1:1", selected_video_model="3.1-lite")
    mock_state.return_value = state

    on_video_model_change(MagicMock(value="gemini-omni-1.2-flash"))

    assert state.selected_video_model == "gemini-omni-1.2-flash"
    assert state.aspect_ratio == "16:9"


@patch("pages.storyboarder.me.state")
def test_on_video_model_change_keeps_supported_aspect_ratio(
    mock_state: MagicMock,
) -> None:
    """A ratio both models support is left alone."""
    state = SimpleNamespaceState(aspect_ratio="9:16", selected_video_model="3.1-lite")
    mock_state.return_value = state

    on_video_model_change(MagicMock(value="gemini-omni-1.2-flash"))

    assert state.aspect_ratio == "9:16"


class SimpleNamespaceState:
    """Minimal mutable stand-in for the Storyboarder page state."""

    def __init__(self, **kwargs: str) -> None:
        """Set each keyword argument as an attribute."""
        self.__dict__.update(kwargs)
