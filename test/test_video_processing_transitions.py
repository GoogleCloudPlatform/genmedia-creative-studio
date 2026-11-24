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

import importlib
import sys
import types

import pytest
from moviepy import ColorClip


@pytest.fixture
def video_processing(monkeypatch):
    """Imports video_processing without initializing external services."""
    metadata = types.ModuleType("common.metadata")
    metadata.MediaItem = type("MediaItem", (), {})
    metadata.add_media_item_to_firestore = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "common.metadata", metadata)

    storage = types.ModuleType("common.storage")
    storage.download_from_gcs = lambda *args, **kwargs: b""
    storage.store_to_gcs = lambda *args, **kwargs: "gs://test-bucket/output.mp4"
    storage.get_storage_client = lambda: None
    storage._is_proxy_bucket_allowed = lambda bucket_name: True
    monkeypatch.setitem(sys.modules, "common.storage", storage)

    config_default = types.ModuleType("config.default")

    class Default:
        VIDEO_BUCKET = "test-bucket/videos"

    config_default.Default = Default
    monkeypatch.setitem(sys.modules, "config.default", config_default)

    sys.modules.pop("models.video_processing", None)
    return importlib.import_module("models.video_processing")


def _clip(size=(16, 16), duration=0.5, color=(255, 0, 0)):
    return ColorClip(size=size, color=color, duration=duration).with_fps(10)


def _write_clip(path, size=(16, 16), duration=0.5, color=(255, 0, 0)):
    clip = _clip(size=size, duration=duration, color=color)
    try:
        clip.write_videofile(str(path), codec="libx264", audio=False, logger=None)
    finally:
        clip.close()


def test_transition_duration_is_limited_to_shorter_clip(video_processing):
    clip1 = _clip(duration=0.5)
    clip2 = _clip(duration=0.25, color=(0, 0, 255))

    try:
        assert video_processing._safe_transition_duration(clip1, clip2, 1.0) == pytest.approx(0.25)
    finally:
        clip1.close()
        clip2.close()


@pytest.mark.parametrize(
    ("transition_name", "expected_duration"),
    [
        ("crossfade", 0.5),
        ("wipe", 0.5),
        ("dipToBlack", 0.625),
    ],
)
def test_short_clips_produce_finite_transition(video_processing, transition_name, expected_duration):
    clip1 = _clip(duration=0.5)
    clip2 = _clip(duration=0.25, color=(0, 0, 255))

    transition = getattr(video_processing, transition_name)
    final_clip = transition(clip1, clip2, 1.0)

    try:
        assert final_clip.duration == pytest.approx(expected_duration)
        assert final_clip.get_frame(0).shape == (16, 16, 3)
        assert final_clip.get_frame(final_clip.duration - 0.1).shape == (16, 16, 3)
    finally:
        final_clip.close()
        clip1.close()
        clip2.close()


def test_clip_size_matching_letterboxes_second_clip(video_processing):
    clip = _clip(size=(8, 16), duration=0.5)

    fitted_clip = video_processing._match_clip_size(clip, (16, 16))

    try:
        assert fitted_clip.size == (16, 16)
        assert fitted_clip.duration == pytest.approx(0.5)
        assert fitted_clip.get_frame(0).shape == (16, 16, 3)
    finally:
        fitted_clip.close()
        clip.close()


def test_process_videos_finishes_short_mismatched_transition(
    video_processing,
    monkeypatch,
    tmp_path,
):
    first_video = tmp_path / "first.mp4"
    second_video = tmp_path / "second.mp4"
    _write_clip(first_video, size=(16, 16), duration=0.5)
    _write_clip(second_video, size=(8, 16), duration=0.25, color=(0, 0, 255))

    videos_by_uri = {
        "gs://test/input/first.mp4": first_video.read_bytes(),
        "gs://test/input/second.mp4": second_video.read_bytes(),
    }
    monkeypatch.setattr(
        video_processing,
        "download_from_gcs",
        lambda uri: videos_by_uri[uri],
    )

    uploaded = {}

    def store_to_gcs(**kwargs):
        uploaded["contents"] = kwargs["contents"]
        return "gs://test-bucket/processed/output.mp4"

    monkeypatch.setattr(video_processing, "store_to_gcs", store_to_gcs)

    output_uri = video_processing.process_videos(
        ["gs://test/input/first.mp4", "gs://test/input/second.mp4"],
        transition="x-fade",
        transition_duration=1.0,
    )

    assert output_uri == "gs://test-bucket/processed/output.mp4"
    assert len(uploaded["contents"]) > 0
