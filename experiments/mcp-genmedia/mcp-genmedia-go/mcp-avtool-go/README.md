# AV Compositing Tool (avtool)

Version: 2.0.0

## Overview

`avtool` is a versatile Model Context Protocol (MCP) server designed for various audio and video processing tasks. It leverages powerful command-line utilities like FFMpeg and FFprobe to offer a range of compositing and media manipulation capabilities. This tool can be run with different transport protocols (STDIO, HTTP (Streamable HTTP), SSE) to integrate into various workflows.

## Features

The `avtool` provides the following functionalities, exposed as MCP tools:

*   **`ffmpeg_get_media_info`**:
    *   Retrieves detailed information about a media file (streams, format, metadata, etc.) using `ffprobe`.
    *   Input: URI of the media file (local path or GCS URI).
    *   Output: JSON string containing the media information.

*   **`ffmpeg_convert_audio_wav_to_mp3`**:
    *   Converts WAV audio files to MP3 format.
    *   Input: URI of the input WAV audio file.
    *   Output: MP3 audio file. Can be saved locally and/or to a GCS bucket.

*   **`ffmpeg_video_to_gif`**:
    *   Creates an animated GIF from an input video file.
    *   Uses a two-pass FFMpeg process (palette generation and use) for optimal quality.
    *   Inputs: URI of the input video file, scale width factor, FPS.
    *   Output: GIF image file. Can be saved locally and/or to a GCS bucket.

*   **`ffmpeg_combine_audio_and_video`**:
    *   Combines a separate video file and an audio file into a single video file. If the video already has an audio track, it mixes the new audio with the existing audio.
    *   Inputs: URI of the input video file, URI of the input audio file, optional `input_video_volume_db_change`, optional `input_audio_volume_db_change`.
    *   Output: Combined video file (e.g., MP4). Can be saved locally and/or to a GCS bucket.

*   **`ffmpeg_overlay_image_on_video`**:
    *   Overlays a static image onto a video at specified X/Y coordinates.
    *   Inputs: URI of the input video file, URI of the input image file, X coordinate, Y coordinate.
    *   Output: Video file with the image overlay. Can be saved locally and/or to a GCS bucket.

*   **`ffmpeg_concatenate_media_files`**:
    *   Concatenates multiple media files (videos or audios) into a single output file.
    *   **Behavior for WAV output**: If the intended output file has a `.wav` extension, all input files *must* be PCM WAV audio files. The tool will attempt to directly concatenate them, preserving the PCM audio codec. If any input is not a PCM WAV file, or if PCM WAV inputs have differing characteristics (sample rate, sample format, channel count), the operation is rejected. The error message will guide the user to either:
    a) Convert all inputs to a common PCM WAV format using an external tool if precise WAV-to-WAV characteristic changes are needed.
    b) Convert inputs to a compatible intermediate format like MP3 (using `ffmpeg_convert_audio_wav_to_mp3` if applicable) and then concatenate to a more flexible output format like M4A.
    c) Choose a different output format directly (e.g., M4A, MP4) for the concatenation, which allows `avtool` to handle the necessary conversions.
    *   **Behavior for other outputs (e.g., MP4, M4A)**: For non-WAV outputs, or if inputs are video/mixed, the tool employs a two-stage process: first standardizing inputs (e.g., to common resolution/FPS for video, and AAC audio in an MP4 container), then concatenating these standardized files using the FFMpeg concat demuxer for robustness.
    *   Input: Array of URIs for the input media files.
    *   Output: Concatenated media file. Can be saved locally and/or to a GCS bucket.

*   **`ffmpeg_adjust_volume`**:
    *   Adjusts the volume of an audio file by a specified decibel (dB) amount.
    *   Inputs: URI of the input audio file, volume change in dB.
    *   Output: Audio file with adjusted volume. Can be saved locally and/or to a GCS bucket.

*   **`ffmpeg_layer_audio_files`**:
    *   Layers (mixes) multiple audio files together into a single audio track.
    *   Input: Array of URIs for the input audio files.
    *   Output: Mixed audio file. Can be saved locally and/or to a GCS bucket.

*   **`ffmpeg_trim_media`**:
    *   Trims (cuts) a single segment from an audio or video file, keeping only the portion between a start time and an end time (or for a given duration). Works identically for audio and video.
    *   Inputs: URI of the input media file, start time (seconds), and either a duration or an end time (seconds). Optional `re_encode` flag.
    *   By default the segment is extracted with a fast, lossless stream copy (`-c copy`). Because a stream copy can only begin on a keyframe, the cut may start at the nearest keyframe at or before the requested start time, so it may not be exactly frame-accurate. Set `re_encode=true` for a frame-accurate cut (slower, slightly lossy). If a stream copy is not possible for the chosen output container, the tool automatically falls back to a re-encode.
    *   Output: The trimmed media file (input container/extension preserved by default). Can be saved locally and/or to a GCS bucket.

*   **`ffmpeg_extract_frame`**:
    *   Extracts a single still frame from a video as a PNG or JPEG image.
    *   `mode=last_frame` (default) captures the exact final frame of the clip (decodes the tail and keeps the last decoded frame, so it is frame-accurate even for very short clips); `mode=at_timestamp` captures the frame at a given `timestamp` (seconds from the start, must be `>= 0` and less than the input's duration).
    *   Inputs: URI of the input video file (must contain a video stream), optional `mode`, conditional `timestamp` (required for `at_timestamp`), optional `output_format` (`png` default/lossless, or `jpg`).
    *   The output image path/URI drops straight into reference-image conditioning (e.g. `mcp-omni-go`'s `omni_video_generation` `images`, or Veo first/last / reference-image inputs) to chain long-form video segments on the previous clip's last frame. Fails if the input has no video stream.
    *   Output: A single image file (PNG by default; JPEG via `output_format` or the `output_filename` extension). Can be saved locally and/or to a GCS bucket.

*   **`ffmpeg_normalize_loudness`**:
    *   Normalizes the perceived loudness of an audio file (or the audio track of a video file) to a target level using EBU R128 loudness normalization. Works for both pure-audio inputs and videos with an audio track.
    *   Uses the accurate two-pass `loudnorm` method: a first pass measures the input's actual integrated loudness, true peak, loudness range and threshold, and a second pass applies a linear correction toward the target using those measurements. This is more accurate than a single-pass normalize.
    *   Inputs: URI of the input media file. Optional `target_loudness` (integrated LUFS, default `-16`), `target_true_peak` (dBTP, default `-1.5`), and `target_loudness_range` (LU, default `11`). The `-16` LUFS default suits streaming/web/podcast playback; use `-23` for EBU R128 broadcast delivery.
    *   When the input is a video, its video stream is copied unchanged and only the audio is normalized. The audio sample rate is preserved. Fails if the input has no audio stream.
    *   Output: The loudness-normalized media file (input container/extension preserved by default). Can be saved locally and/or to a GCS bucket.

*   **`ffmpeg_resize_reframe`**:
    *   Resizes and reframes an image or a video to a target geometry. A single image is treated as a one-frame stream, so the same tool handles both image and video inputs.
    *   Inputs: URI of the input image or video file, plus a target specified as an explicit `width` and/or `height` (pixels) and/or an `aspect_ratio` shorthand (`16:9`, `9:16`, `1:1`). Providing both `width` and `height` sets the exact frame (any `aspect_ratio` is ignored). An `aspect_ratio` combined with a single `width` or `height` computes the other side; used alone it keeps the input's width. A single `width` or `height` alone performs a proportional resize that keeps the input's aspect ratio.
    *   `reframe_mode` selects how an aspect-ratio mismatch is reconciled: `pad` (default) scales the whole picture to fit and fills the remainder with bars (letterbox/pillarbox), preserving all content; `crop` scales to fill the frame edge-to-edge and trims the overflow. `pad` is the default because it never discards picture content. The pad fill colour is configurable via `pad_color` (default `black`).
    *   Target dimensions are automatically rounded to even numbers, which many video codecs (e.g. H.264/yuv420p) require. Any audio stream is copied through unchanged.
    *   Output: The resized/reframed media file (input container/extension preserved by default). Can be saved locally and/or to a GCS bucket.

## Requirements

*   **Go**: Version 1.18 or higher (as per `go.mod` if specified, otherwise latest stable).
*   **FFMpeg**: Must be installed and accessible in the system PATH.
*   **FFprobe**: Must be installed and accessible in the system PATH (usually comes with FFMpeg).
*   **Google Cloud Storage (Optional)**: For reading inputs from or writing outputs to GCS, appropriate credentials and setup are required.

## Configuration

The tool is configured using environment variables:

*   `MCP_CUSTOM_PATH`: (Optional) Overrides the system `PATH` for `ffmpeg` and `ffprobe` tool executions. Useful for pointing to custom binary installations (e.g., Homebrew) without polluting the host environment.
*   `GOOGLE_CLOUD_PROJECT`: (Required for GCS operations) Your Google Cloud Project ID. Note: `PROJECT_ID` is also supported as a fallback.
    *   **Override**: You can override this globally for this specific server by setting `AVTOOL_PROJECT_ID`.
*   `GENMEDIA_BUCKET`: (Optional) Default Google Cloud Storage bucket to use for outputs if not specified in the tool request.
*   `GOOGLE_CLOUD_LOCATION`: (Optional) The preferred Google Cloud location (e.g., `us-central1`). Defaults to `us-central1`. Primarily for GCS client initialization context.
    *   **Fallback**: `LOCATION` is also supported as a fallback for `GOOGLE_CLOUD_LOCATION`.
    *   **Override**: You can override this globally for this specific server by setting `AVTOOL_LOCATION`.
*   `PORT`: (Optional, for HTTP transport) The port for the HTTP server to listen on. Defaults to `8080`.

## Running the Tool

Build the tool using `go build` in the project directory.

Run the compiled executable with a transport flag:

*   **STDIO (Default)**:
    ```bash
    ./avtool
    # or
    ./avtool -transport stdio
    ```
*   **HTTP**:
    ```bash
    ./avtool -transport http
    # Optionally set PORT environment variable, e.g., PORT=8081 ./avtool -transport http
    ```
    The MCP server will be available at `http://localhost:<PORT>/mcp`.
*   **SSE (Server-Sent Events)**:
    ```bash
    ./avtool -transport sse
    ```
    The MCP server will be available at `http://localhost:8081` (default SSE port).

## How to Use

`avtool` acts as an MCP (Media Control Protocol) server. Client applications can interact with it by sending MCP `CallToolRequest` messages (e.g., via JSON-RPC) to invoke the features listed above. The server will process the request, perform the media operations, and return an `mcp.CallToolResult`.

Input files can be specified as local file system paths or as GCS URIs (e.g., `gs://your-bucket/path/to/file.mp4`).
Output files can be saved to a specified local directory and/or uploaded to a GCS bucket. If no output locations are specified, temporary files are created for processing and then cleaned up.

### Output naming (`output_filename`)

Each tool accepts an optional `output_filename` (string) to name its output,
consistent with the rest of the genmedia suite (see
[Naming Outputs](../README.md#naming-outputs-output_filename)). **AVTool is
intentionally exempt from extension-forcing**: because the extension selects the
`ffmpeg` output container/codec, the extension you supply is honored (e.g.
`clip.mkv` stays `.mkv`); a missing extension falls back to the tool's default.
AVTool produces a single output, so no `_1..n` suffix is applied.

The legacy `output_file_name` parameter is still accepted but is
**deprecated — prefer `output_filename`** (`output_filename` wins when both are
set). No removal is planned in this release.

## Development

For a detailed description of the `ffmpeg` and `ffprobe` commands used in this service, see the `compositing_recipes.md` file.

The codebase is structured as follows:

*   `avtool.go`: Main application entry point, MCP server setup, transport handling.
*   `mcp_handlers.go`: MCP tool registration and the top-level handler functions for each tool.
*   `ffmpeg_commands.go`: Functions that build and execute FFMpeg commands.
*   `ffprobe_commands.go`: Functions that build and execute FFprobe commands.

The `mcp-common` package provides common functionality for configuration, file handling, and GCS operations.

To add a new tool:
1.  Define the FFMpeg/FFprobe command logic (if new) in `ffmpeg_commands.go` or `ffprobe_commands.go`.
2.  Create a new handler function in `mcp_handlers.go`.
3.  Register the tool in `avtool.go` by calling the `add<NewToolName>Tool(s, cfg)` function.
