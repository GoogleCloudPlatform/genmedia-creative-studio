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

import datetime
import logging
import math
import os
import tempfile
import uuid

import cv2
import moviepy
import numpy as np
from moviepy import (
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    VideoClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
    vfx,
)
from moviepy.audio.io.AudioFileClip import AudioFileClip
from scipy.ndimage import gaussian_filter

from common.metadata import MediaItem, add_media_item_to_firestore
from common.storage import (
    _is_proxy_bucket_allowed,
    download_from_gcs,
    get_storage_client,
    store_to_gcs,
)
from config.default import Default

config = Default()


def _download_videos_to_temp(video_gcs_uris: list[str], tmpdir: str) -> list[str]:
    """Downloads videos from GCS to a temporary directory."""
    local_video_paths = []
    for i, gcs_uri in enumerate(video_gcs_uris):
        video_bytes = download_from_gcs(gcs_uri)
        base_name = os.path.basename(gcs_uri)
        unique_local_filename = f"{i}_{base_name}"
        local_filename = os.path.join(tmpdir, unique_local_filename)
        with open(local_filename, "wb") as f:
            f.write(video_bytes)
        local_video_paths.append(local_filename)
        print(f"Downloaded {gcs_uri} to {local_filename}")
    return local_video_paths


def _upload_to_gcs(local_path: str, destination_folder: str, mime_type: str) -> str:
    """Uploads a local file to GCS."""
    with open(local_path, "rb") as f:
        file_bytes = f.read()

    bucket_parts = config.VIDEO_BUCKET.split("/", 1)
    bucket_name = bucket_parts[0]
    base_folder = bucket_parts[1] if len(bucket_parts) > 1 else ""

    final_folder = os.path.join(base_folder, destination_folder).strip("/")
    file_name = os.path.basename(local_path)

    final_gcs_uri = store_to_gcs(
        folder=final_folder,
        file_name=file_name,
        mime_type=mime_type,
        contents=file_bytes,
        bucket_name=bucket_name,
    )
    return final_gcs_uri


# --- Transition Functions (moviepy v2.x compatible) --- #
print(f"DEBUG: Loading video_processing.py at {datetime.datetime.now()}. Moviepy version: {moviepy.__version__}")


def _safe_transition_duration(clip1, clip2, transition_duration):
    """Returns a transition duration that fits inside both clips."""
    transition_duration = float(transition_duration)
    if not math.isfinite(transition_duration) or transition_duration <= 0:
        raise ValueError("Transition duration must be a positive number.")

    max_transition_duration = min(clip1.duration, clip2.duration)
    if max_transition_duration <= 0:
        raise ValueError("Video clips must have positive duration for transitions.")

    return min(transition_duration, max_transition_duration)


def _match_clip_size(clip, target_size):
    """Fits a clip into target_size with letterboxing when needed."""
    if clip.size == target_size:
        return clip

    ratio = min(target_size[0] / clip.size[0], target_size[1] / clip.size[1])
    resized_clip = clip.resized(ratio)
    background = ColorClip(size=target_size, color=(0, 0, 0), duration=resized_clip.duration)
    fitted_clip = CompositeVideoClip(
        [background, resized_clip.with_position("center")],
        size=target_size,
    )

    if resized_clip.audio:
        fitted_clip.audio = resized_clip.audio

    if getattr(clip, "fps", None):
        fitted_clip.fps = clip.fps

    return fitted_clip


def crossfade(clip1, clip2, transition_duration, speed_curve="sigmoid"):
    print("DEBUG: Entering crossfade function")
    transition_duration = _safe_transition_duration(clip1, clip2, transition_duration)
    transition_start = clip1.duration - transition_duration
    total_duration = clip1.duration + clip2.duration - transition_duration

    clip1 = clip1.copy()
    clip2 = clip2.copy()

    def sigmoid_curve(t):
        return 1 / (1 + np.exp(-10 * (t - 0.5)))

    def linear_curve(t):
        return t

    def quadratic_curve(t):
        return t**2

    def cubic_curve(t):
        return t**3

    curve_functions = {
        "sigmoid": sigmoid_curve,
        "linear": linear_curve,
        "quadratic": quadratic_curve,
        "cubic": cubic_curve,
    }
    curve_func = curve_functions[speed_curve]

    clip2 = clip2.with_start(transition_start)

    def make_frame(t):
        if t < transition_start:
            return clip1.get_frame(t)
        elif t >= clip1.duration:
            return clip2.get_frame(t - transition_start)
        else:
            frame1 = clip1.get_frame(t)
            frame2 = clip2.get_frame(t - transition_start)
            progress = (t - transition_start) / transition_duration
            weight = 1.0 - curve_func(progress)
            return (weight * frame1 + (1 - weight) * frame2).astype("uint8")

    final_clip = VideoClip(make_frame, duration=total_duration)
    final_clip.fps = clip1.fps  # Set fps for the new clip

    if clip1.audio and clip2.audio:
        print("DEBUG: Applying audio crossfade")
        audio1 = clip1.audio.with_effects([afx.AudioFadeOut(transition_duration)])
        audio2 = clip2.audio.with_effects([afx.AudioFadeIn(transition_duration)]).with_start(
            clip1.duration - transition_duration
        )
        final_audio = CompositeAudioClip([audio1, audio2])
        final_clip.audio = final_audio

    return final_clip


def wipe(clip1, clip2, transition_duration, direction="left-to-right"):
    transition_duration = _safe_transition_duration(clip1, clip2, transition_duration)
    width, height = clip1.size

    transition_start = clip1.duration - transition_duration
    total_duration = clip1.duration + clip2.duration - transition_duration

    clip2 = clip2.with_start(transition_start)

    def make_mask_frame(t):
        if t < transition_start:
            return np.ones((height, width), dtype=np.float32)
        elif t < clip1.duration:
            progress = (t - transition_start) / transition_duration
            mask = np.ones((height, width), dtype=np.float32)
            if direction == "left-to-right":
                edge_position = int(width * progress)
                if edge_position > 0:
                    mask[:, :edge_position] = 0.0
            elif direction == "right-to-left":
                edge_position = int(width * (1 - progress))
                if edge_position < width:
                    mask[:, edge_position:] = 0.0
            elif direction == "top-to-bottom":
                edge_position = int(height * progress)
                if edge_position > 0:
                    mask[:edge_position, :] = 0.0
            elif direction == "bottom-to-top":
                edge_position = int(height * (1 - progress))
                if edge_position < height:
                    mask[edge_position:, :] = 0.0
            return mask
        else:
            return np.zeros((height, width), dtype=np.float32)

    mask_clip = VideoClip(make_mask_frame, duration=total_duration, is_mask=True)
    clip1_masked = clip1.with_mask(mask_clip)

    final_clip = CompositeVideoClip([clip2, clip1_masked], size=(width, height))
    final_clip = final_clip.with_duration(total_duration)
    final_clip.fps = clip1.fps

    if clip1.audio and clip2.audio:
        audio1 = clip1.audio.with_effects([afx.AudioFadeOut(transition_duration)])
        audio2 = clip2.audio.with_effects([afx.AudioFadeIn(transition_duration)]).with_start(
            clip1.duration - transition_duration
        )
        final_audio = CompositeAudioClip([audio1, audio2])
        final_clip.audio = final_audio

    return final_clip


def dipToBlack(clip1, clip2, transition_duration, **kwargs):
    transition_duration = _safe_transition_duration(clip1, clip2, transition_duration)
    fade_duration = transition_duration / 2.0
    total_duration = clip1.duration + clip2.duration - fade_duration
    clip1_faded = clip1.with_effects([vfx.FadeOut(fade_duration)])
    clip2_faded = clip2.with_effects([vfx.FadeIn(fade_duration)]).with_start(
        clip1.duration - fade_duration
    )

    black_clip = ColorClip(
        size=clip1.size, color=(0, 0, 0), duration=total_duration
    )

    final_clip = CompositeVideoClip([black_clip, clip1_faded, clip2_faded])
    final_clip = final_clip.with_duration(total_duration)
    final_clip.fps = clip1.fps

    if clip1.audio and clip2.audio:
        audio1 = clip1.audio.with_effects([afx.AudioFadeOut(fade_duration)])
        audio2 = clip2.audio.with_effects([afx.AudioFadeIn(fade_duration)]).with_start(
            clip1.duration - fade_duration
        )
        final_audio = CompositeAudioClip([audio1, audio2])
        final_clip.audio = final_audio

    return final_clip


def add_blur_transition(
    clip, blur_duration, max_blur_strength=1.0, reverse=False, position="end"
):
    """
    Add a gradual blur effect to the start or end of a video clip.
    """
    if blur_duration > clip.duration:
        blur_duration = clip.duration
        print(
            f"Warning: Blur duration exceeds clip duration. Setting blur duration to {blur_duration} seconds."
        )

    if position.lower() == "start":
        effect_start_time = 0
        effect_end_time = blur_duration
    else:  # 'end'
        effect_start_time = clip.duration - blur_duration
        effect_end_time = clip.duration

    def get_blur_radius(t):
        if t < effect_start_time or t > effect_end_time:
            return 0
        effect_progress = (t - effect_start_time) / blur_duration
        max_radius = 15 * max_blur_strength
        if (position.lower() == "start" and not reverse) or (
            position.lower() == "end" and reverse
        ):
            return max_radius * (1 - effect_progress)
        else:
            return max_radius * effect_progress

    def make_frame_for_blur(t):
        frame = clip.get_frame(t)
        radius = get_blur_radius(t)
        if radius > 0:
            # Apply gaussian blur with scipy
            # Blur each color channel separately
            blurred = np.zeros_like(frame)
            for i in range(3):  # RGB channels
                blurred[:, :, i] = gaussian_filter(frame[:, :, i], sigma=radius)
            return blurred
        return frame

    return VideoClip(
        make_frame=make_frame_for_blur, duration=clip.duration, fps=clip.fps
    )


def blur(clip1, clip2, transition_duration=1.0, max_blur=1.0):
    blur_duration_per_clip = transition_duration / 2
    clip1_blurred = add_blur_transition(
        clip1,
        blur_duration=blur_duration_per_clip,
        max_blur_strength=max_blur,
        reverse=False,
        position="end",
    )
    clip2_blurred = add_blur_transition(
        clip2,
        blur_duration=blur_duration_per_clip,
        max_blur_strength=max_blur,
        reverse=True,
        position="start",
    )
    return concatenate_videoclips([clip1_blurred, clip2_blurred])


# --- Main Dispatcher --- #


def process_videos(
    video_gcs_uris: list[str],
    transition: str = "concat",
    transition_duration: float = 1.0,
) -> str:
    if not video_gcs_uris or len(video_gcs_uris) < 2:
        raise ValueError("At least two videos are required.")

    with tempfile.TemporaryDirectory() as tmpdir:
        local_paths = _download_videos_to_temp(video_gcs_uris, tmpdir)
        clips = [VideoFileClip(path) for path in local_paths]

        clip1 = clips[0]
        clip2 = clips[1]

        if transition != "concat":
            clip2 = _match_clip_size(clip2, clip1.size)

        if transition == "concat":
            final_clip = concatenate_videoclips(clips)
        elif transition == "x-fade":
            final_clip = crossfade(clip1, clip2, transition_duration)
        elif transition == "wipe":
            final_clip = wipe(clip1, clip2, transition_duration)
        elif transition == "dipToBlack":
            final_clip = dipToBlack(clip1, clip2, transition_duration)
        else:
            final_clip = concatenate_videoclips(clips)  # Default to concat

        output_filename = f"processed_{uuid.uuid4()}.mp4"
        final_clip_path = os.path.join(tmpdir, output_filename)
        final_clip.write_videofile(final_clip_path, codec="libx264")

        final_gcs_uri = _upload_to_gcs(final_clip_path, "processed_videos", "video/mp4")

        for clip in clips:
            clip.close()
        final_clip.close()

        return final_gcs_uri


def layer_audio_on_video(video_gcs_uri: str, audio_gcs_uri: str) -> str:
    """
    Layers an audio track over a video file. If the video already has audio,
    it will be replaced.
    """
    if not video_gcs_uri or not audio_gcs_uri:
        raise ValueError("A video URI and an audio URI are required.")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Download both files
        video_path = _download_videos_to_temp([video_gcs_uri], tmpdir)[0]
        audio_path = _download_videos_to_temp([audio_gcs_uri], tmpdir)[0]

        # Process with moviepy
        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(audio_path)

        # Set the audio of the video clip by direct attribute assignment
        video_clip.audio = audio_clip

        # Write the output file
        output_filename = f"audio_layered_{uuid.uuid4()}.mp4"
        final_clip_path = os.path.join(tmpdir, output_filename)
        video_clip.write_videofile(final_clip_path, codec="libx264", audio_codec="aac")

        # Upload to GCS
        final_gcs_uri = _upload_to_gcs(final_clip_path, "processed_videos", "video/mp4")

        # Clean up
        video_clip.close()
        audio_clip.close()

        return final_gcs_uri


def _calculate_motion_score(clip: VideoFileClip, sample_interval_seconds: float = 0.5) -> float:
    """Calculates a motion score based on frame-to-frame differences."""
    frame_diffs = []
    prev_frame = None

    for t in np.arange(0, clip.duration, sample_interval_seconds):
        frame = clip.get_frame(t)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if prev_frame is not None:
            diff = cv2.absdiff(gray_frame, prev_frame)
            frame_diffs.append(np.mean(diff))
        
        prev_frame = gray_frame

    if not frame_diffs:
        return 0.0

    return np.mean(frame_diffs)


def get_video_duration(gcs_uri: str) -> float:
    """
    Downloads the video from GCS and returns its duration in seconds.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            local_path = _download_videos_to_temp([gcs_uri], tmpdir)[0]
            with VideoFileClip(local_path) as clip:
                duration = clip.duration
            return duration
        except Exception as e:
            logging.error(f"Failed to get video duration for {gcs_uri}: {e}")
            return 0.0


# --- GIF Conversion --- #


class GifSourceRejectedError(ValueError):
    """The GIF source is outside the app's buckets or over the size/duration limits."""


def _check_gif_source(source_video_gcs_uri: str) -> None:
    """Reject a GIF source before it is downloaded.

    The source must be an object in one of the app's own buckets (the URI can
    come from client state) and no larger than ``GIF_MAX_SOURCE_MB``.
    """
    bucket_name, _, blob_name = (
        (source_video_gcs_uri or "").removeprefix("gs://").partition("/")
    )
    if (
        not source_video_gcs_uri.startswith("gs://")
        or not blob_name
        or not _is_proxy_bucket_allowed(bucket_name)
    ):
        raise GifSourceRejectedError("Video not found")
    blob = get_storage_client().bucket(bucket_name).get_blob(blob_name)
    if blob is None:
        raise GifSourceRejectedError("Video not found")
    max_bytes = config.GIF_MAX_SOURCE_MB * 1024 * 1024
    if blob.size is None or blob.size > max_bytes:
        raise GifSourceRejectedError(
            f"Video is larger than the {config.GIF_MAX_SOURCE_MB} MB GIF limit",
        )


def convert_mp4_to_gif(source_video_gcs_uri: str, user_email: str, target_mb: int = 8) -> str:
    _check_gif_source(source_video_gcs_uri)
    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = _download_videos_to_temp([source_video_gcs_uri], tmpdir)[0]

        output_filename = f"{os.path.splitext(os.path.basename(local_path))[0]}{uuid.uuid4()}.gif"
        output_path = os.path.join(tmpdir, output_filename)

        clip = VideoFileClip(local_path)
        if not clip.duration or clip.duration > config.GIF_MAX_DURATION_S:
            clip.close()
            raise GifSourceRejectedError(
                f"Video is longer than the {config.GIF_MAX_DURATION_S} second GIF limit",
            )

        # --- Intelligent Resizing Logic ---
        motion_score = _calculate_motion_score(clip)
        logging.info(f"Calculated motion score: {motion_score:.2f}")

        TARGET_SIZE_BYTES = target_mb * 1024 * 1024
        # Start with reasonable quality defaults
        fps = min(clip.fps, 12) 
        resize_factor = 1.0
        
        # Adjust heuristic based on motion. A higher score means more motion and less compressibility.
        # A motion score of ~30 is moderate. Let's make the heuristic more directly influenced by it.
        # Start with a base heuristic and add a motion factor.
        # base_heuristic = 0.35
        # motion_factor = (motion_score / 50.0) # Normalize based on an expected max motion of ~50
        # bytes_per_pixel_heuristic = base_heuristic + motion_factor * 0.2 # Motion adjusts heuristic by up to 0.2
        
        # Let's map the motion score (e.g., 0-50) to a more aggressive heuristic range (e.g., 0.6 - 1.4)
        normalized_motion = min(motion_score / 50.0, 1.0) # Normalize score, cap at 1.0
        bytes_per_pixel_heuristic = 0.6 + (normalized_motion * 0.8) # Map to 0.6-1.4 range

        logging.info(f"Using motion-adjusted heuristic: {bytes_per_pixel_heuristic:.2f}")

        # Estimate initial size
        estimated_size = (
            clip.size[0] * resize_factor * 
            clip.size[1] * resize_factor * 
            fps * 
            clip.duration * 
            bytes_per_pixel_heuristic
        )

        # Iteratively reduce quality if estimate is too high
        while estimated_size > TARGET_SIZE_BYTES and (resize_factor > 0.2 or fps > 8):
            if resize_factor > 0.3:
                resize_factor -= 0.1
            elif fps > 8:
                fps -= 2
            else: # Last resort
                resize_factor -= 0.05

            estimated_size = (
                clip.size[0] * resize_factor * 
                clip.size[1] * resize_factor * 
                fps * 
                clip.duration * 
                bytes_per_pixel_heuristic
            )
            logging.info(f"Adjusting parameters. New resize_factor: {resize_factor:.2f}, New fps: {fps}, Estimated Size: {estimated_size / 1024 / 1024:.2f} MB")

        final_params_comment = f"GIF generation params: resize_factor={resize_factor:.2f}, fps={fps}"
        logging.info(f"FINAL PARAMS: {final_params_comment}")
        
        final_clip = clip.resized(resize_factor)
        final_clip.write_gif(output_path, fps=fps)

        # Get file sizes for metadata
        source_video_size_mb = os.path.getsize(local_path) / (1024 * 1024)
        final_gif_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        size_comment = f"Source Video: {source_video_size_mb:.2f} MB, Final GIF: {final_gif_size_mb:.2f} MB"
        logging.info(size_comment)
        final_params_comment += f". {size_comment}"

        clip.close()
        final_clip.close()

        gif_uri = _upload_to_gcs(output_path, "generated_gifs", "image/gif")

        add_media_item_to_firestore(
            MediaItem(
                gcsuri=gif_uri,
                user_email=user_email,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
                mime_type="image/gif",
                source_images_gcs=[source_video_gcs_uri], # Source is the concatenated video
                comment=final_params_comment,
                model="pixie-compositor-v1-gif",
            )
        )

        return gif_uri


def extract_and_upload_thumbnail(video_gcs_uri: str, timestamp_s: float) -> str:
    """Extracts a frame from a video at the given timestamp and uploads it to GCS."""
    logging.info(f"Extracting thumbnail for {video_gcs_uri} at {timestamp_s}s")

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            local_path = _download_videos_to_temp([video_gcs_uri], tmpdir)[0]
            output_filename = f"thumbnail_{uuid.uuid4()}.png"
            output_path = os.path.join(tmpdir, output_filename)

            with VideoFileClip(local_path) as clip:
                # Ensure the timestamp doesn't exceed clip duration
                safe_timestamp = min(max(0.0, timestamp_s), clip.duration - 0.1)

                # Get the frame
                frame = clip.get_frame(safe_timestamp)

                # Save as PNG
                # Convert from RGB (MoviePy default) to BGR for OpenCV
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                cv2.imwrite(output_path, frame_bgr)

            # Upload to GCS
            thumbnail_uri = _upload_to_gcs(output_path, "thumbnails", "image/png")
            logging.info(f"Successfully uploaded thumbnail to {thumbnail_uri}")
            return thumbnail_uri

        except Exception as e:
            logging.error(f"Failed to extract and upload thumbnail: {e}")
            return ""
