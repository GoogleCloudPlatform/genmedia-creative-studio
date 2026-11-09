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

"""Tests for Omni-or-Veo routing in the Interior Design and Object Rotation workflows."""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.error_handling import GenerationError
from config.default import Default
from config.omni_models import get_omni_model_config
from models import workflow_video
from models.workflow_video import (
    generate_workflow_image_to_video,
    generate_workflow_reference_video,
    is_omni_model_name,
)

OMNI = "gemini-omni-1.2-flash"
VEO = "veo-3.1-lite-generate-001"


@pytest.mark.parametrize(
    "name",
    ["INTERIOR_DESIGN_VIDEO_MODEL", "OBJECT_ROTATION_VIDEO_MODEL"],
)
def test_workflow_video_defaults_are_registered_omni_models(name: str) -> None:
    """Both workflows default to a registered Gemini Omni model."""
    value = Default.__dataclass_fields__[name].default
    assert is_omni_model_name(value)
    assert get_omni_model_config(value) is not None


def test_is_omni_model_name() -> None:
    """Veo names and unknown names are not Omni models."""
    assert is_omni_model_name(OMNI)
    assert not is_omni_model_name(VEO)
    assert not is_omni_model_name("nope")


@patch.object(workflow_video, "generate_video")
@patch.object(workflow_video, "generate_omni_video")
def test_image_to_video_omni(mock_omni, mock_veo) -> None:
    """An Omni model name sends a 16:9 720p i2v Omni request."""
    mock_omni.return_value = ("gs://b/out.mp4", "interaction-1")

    result = generate_workflow_image_to_video(OMNI, "gs://b/room.png", "pan", 6)

    assert result == "gs://b/out.mp4"
    mock_veo.assert_not_called()
    request = mock_omni.call_args.args[0]
    assert request.omni_mode == "i2v"
    assert request.model_version_id == OMNI
    assert request.reference_image_gcs == "gs://b/room.png"
    assert request.duration_seconds == 6
    assert request.aspect_ratio == "16:9"
    assert request.resolution == "720p"


@pytest.mark.parametrize(("requested", "expected"), [(1, 3), (6, 6), (60, 15)])
@patch.object(workflow_video, "generate_omni_video")
def test_image_to_video_omni_clamps_duration(mock_omni, requested, expected) -> None:
    """Durations are clamped into the Omni model's range."""
    mock_omni.return_value = ("gs://b/out.mp4", "id")

    generate_workflow_image_to_video(OMNI, "gs://b/room.png", "pan", requested)

    assert mock_omni.call_args.args[0].duration_seconds == expected


@patch.object(workflow_video, "generate_omni_video")
@patch.object(workflow_video, "generate_video")
def test_image_to_video_veo(mock_veo, mock_omni) -> None:
    """A Veo model name keeps the original silent Veo request."""
    mock_veo.return_value = (["gs://b/veo.mp4"], "op")

    result = generate_workflow_image_to_video(VEO, "gs://b/room.png", "pan", 6)

    assert result == "gs://b/veo.mp4"
    mock_omni.assert_not_called()
    request = mock_veo.call_args.kwargs["request"]
    assert request.model_version_id == "3.1-lite"
    assert request.reference_image_gcs == "gs://b/room.png"
    assert request.generate_audio is False
    assert request.resolution == "720p"
    assert request.aspect_ratio == "16:9"


@patch.object(workflow_video, "generate_video")
def test_image_to_video_unknown_model_falls_back_to_veo_lite(mock_veo) -> None:
    """An unregistered name keeps the historical Veo 3.1 Lite fallback."""
    mock_veo.return_value = ([], "op")

    assert generate_workflow_image_to_video("mystery", "gs://b/r.png", "p", 6) is None
    assert mock_veo.call_args.kwargs["request"].model_version_id == "3.1-lite"


@patch.object(workflow_video, "modes_for_model", return_value=["t2v"])
def test_image_to_video_rejects_omni_without_i2v(_modes) -> None:
    """An Omni model that cannot do i2v fails before any billable call."""
    with pytest.raises(GenerationError):
        generate_workflow_image_to_video(OMNI, "gs://b/r.png", "p", 6)


@patch.object(workflow_video, "generate_video")
@patch.object(workflow_video, "generate_omni_video")
def test_reference_video_omni(mock_omni, mock_veo) -> None:
    """An Omni model name sends a ref2v request with the references in order."""
    mock_omni.return_value = ("gs://b/rot.mp4", "id")
    uris = ["gs://b/front.png", "gs://b/back.png", "gs://b/left.png"]

    result = generate_workflow_reference_video(OMNI, uris, "rotate")

    assert result == "gs://b/rot.mp4"
    mock_veo.assert_not_called()
    request = mock_omni.call_args.args[0]
    assert request.omni_mode == "ref2v"
    assert [r.gcs_uri for r in request.r2v_references] == uris
    assert request.duration_seconds == workflow_video.ROTATION_OMNI_SECONDS
    assert request.aspect_ratio == "16:9"
    assert request.resolution == "720p"


@patch.object(workflow_video, "generate_omni_video")
@patch.object(workflow_video, "generate_video")
def test_reference_video_veo(mock_veo, mock_omni) -> None:
    """A Veo model name keeps the original r2v Veo request."""
    mock_veo.return_value = (["gs://b/rot.mp4"], "op")
    uris = ["gs://b/front.png", "gs://b/back.png", "gs://b/left.png"]

    result = generate_workflow_reference_video("veo-3.1-generate-001", uris, "rotate")

    assert result == "gs://b/rot.mp4"
    mock_omni.assert_not_called()
    request = mock_veo.call_args.args[0]
    assert request.model_version_id == "3.1"
    assert request.enhance_prompt is True
    assert request.generate_audio is True
    assert request.person_generation == "dont_allow"
    assert [r.gcs_uri for r in request.r2v_references] == uris


@patch.object(workflow_video, "modes_for_model", return_value=["t2v"])
def test_reference_video_rejects_omni_without_ref2v(_modes) -> None:
    """An Omni model that cannot do ref2v fails before any billable call."""
    with pytest.raises(GenerationError):
        generate_workflow_reference_video(OMNI, ["gs://b/a.png"], "p")


@patch.object(workflow_video, "generate_video")
def test_reference_video_unknown_model_raises(mock_veo) -> None:
    """Unregistered, non-fallback Veo versions are rejected."""
    with patch.object(workflow_video, "get_veo_model_config", return_value=None):
        with pytest.raises(GenerationError):
            generate_workflow_reference_video("mystery", ["gs://b/a.png"], "p")
    mock_veo.assert_not_called()


@patch.object(workflow_video, "generate_omni_video")
def test_generate_rotation_video_passes_views_in_order(mock_omni) -> None:
    """generate_rotation_video sends front, back, left to the helper in order."""
    from models.object_rotation import generate_rotation_video

    mock_omni.return_value = ("gs://b/rot.mp4", "id")
    views = {"left": "gs://l", "front": "gs://f", "back": "gs://b"}

    assert generate_rotation_video(views, OMNI) == "gs://b/rot.mp4"
    refs = mock_omni.call_args.args[0].r2v_references
    assert [r.gcs_uri for r in refs] == ["gs://f", "gs://b", "gs://l"]

    with pytest.raises(ValueError, match="Missing required views"):
        generate_rotation_video({"front": "gs://f"}, OMNI)
