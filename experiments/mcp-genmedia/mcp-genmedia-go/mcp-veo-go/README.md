# MCP Veo Server (Version: 3.7.0)

This tool provides video generation capabilities using Google's Veo models (via Vertex AI). It is one of the MCP tools for Google Cloud Genmedia services, acting as an MCP server component to allow LLMs and other MCP clients to generate videos from text prompts or source images.

## MCP Tool Definitions

The server exposes the following tools:

### 1. `veo_t2v` (Text-to-Video)

*   **Description**: Generate a video from a text prompt using Veo. Video is saved to GCS and optionally downloaded locally.
*   **Handler**: `veoTextToVideoHandler`
*   **Parameters**:
    *   `prompt` (string, required): Text prompt for video generation.
    *   `bucket` (string, optional): Google Cloud Storage bucket where the API will save the generated video(s) (e.g., "your-bucket/output-folder" or "gs://your-bucket/output-folder"). If not provided, and `GENMEDIA_BUCKET` env var is set, `gs://<GENMEDIA_BUCKET>/veo_outputs/` will be used. One of these (param or env var) is effectively required.
    *   `output_directory` (string, optional): If provided, specifies a local directory to download the generated video(s) to. Filenames will be generated automatically unless `output_filename` is set.
    *   `output_filename` (string, optional): Base name for the output(s), e.g. `clip.mp4`. The extension is forced to the true video type and, when more than one video is returned, a `_1..n` suffix is inserted before the extension. Veo lets the API write the objects to GCS and then renames them to this name (no `sample_*` originals remain on success). See [Naming Outputs](../README.md#naming-outputs-output_filename).
    *   `model` (string, optional): Model to use for video generation. Can be a full model ID or a common alias. See the `mcp-common/models.go` file for a complete list of supported models and aliases.
    *   `num_videos` (number, optional): Number of videos to generate. Note: the maximum is model-dependent.
    *   `aspect_ratio` (string, optional): Aspect ratio of the generated videos. Note: supported aspect ratios are model-dependent.
    *   `duration` (number, optional): Duration of the generated video in seconds. Note: the supported duration range is model-dependent.
    *   `seed` (number, optional): Non-negative integer seed for best-effort reproducible video generation.

Because Veo always writes to GCS, every Veo tool appends one MCP `resource_link` content item per generated video (`uri` = the `gs://` URI, plus `name`, `mimeType`, and a 1-based `description`). The text summary is unchanged. See [Resource Links for GCS Outputs](../README.md#resource-links-for-gcs-outputs).

### 2. `veo_i2v` (Image-to-Video)

*   **Description**: Generate a video from an input image (and optional prompt) using Veo. Video is saved to GCS and optionally downloaded locally. Supported image MIME types: image/jpeg, image/png.
*   **Handler**: `veoImageToVideoHandler`
*   **Parameters**:
    *   `image_uri` (string, required): GCS URI of the input image for video generation (e.g., "gs://your-bucket/input-image.png").
    *   `mime_type` (string, optional): MIME type of the input image. Supported types are 'image/jpeg' and 'image/png'. If not provided, an attempt will be made to infer it from the `image_uri` extension.
    *   `prompt` (string, optional): Optional text prompt to guide video generation from the image.
    *   `bucket` (string, optional): Google Cloud Storage bucket for output. Same logic as `veo_t2v`.
    *   `output_directory` (string, optional): Local directory for download. Same logic as `veo_t2v`.
    *   `output_filename` (string, optional): Base output name. Same logic as `veo_t2v`.
    *   `model` (string, optional): Model to use. Default: `"veo-3.1-fast-generate-001"`.
    *   `num_videos` (number, optional): Number of videos. Default: `1`. Min: `1`, Max: `4`.
    *   `aspect_ratio` (string, optional): Aspect ratio. Default: `"16:9"`.
    *   `duration` (number, optional): Duration in seconds. Default: `5`. Min: `5`, Max: `8`.
    *   `seed` (number, optional): Non-negative integer seed for best-effort reproducible video generation.

### 3. `veo_extend_video` (Extend Video)

*   **Description**: Extend an existing video using Veo. The input video must be MP4, 1-30s, 24fps, and 720p/1080p/4k in 16:9 or 9:16. Output is a 7s extension. Video is saved to GCS and optionally downloaded locally.
*   **Handler**: `veoExtendVideoHandler`
*   **Parameters**:
    *   `video_uri` (string, required): GCS URI of the input video for extension (e.g., "gs://your-bucket/input-video.mp4").
    *   `mime_type` (string, optional): MIME type of the input video. Currently, only 'video/mp4' is supported.
    *   `prompt` (string, optional): Optional text prompt to guide video extension.
    *   `bucket` (string, optional): Google Cloud Storage bucket for output. Same logic as `veo_t2v`.
    *   `output_directory` (string, optional): Local directory for download. Same logic as `veo_t2v`.
    *   `output_filename` (string, optional): Base output name. Same logic as `veo_t2v`.
    *   `model` (string, optional): Model to use. Supported by Veo 3.1 models.
    *   `num_videos` (number, optional): Number of videos. Default: `1`. Min: `1`, Max: `4`.
    *   `seed` (number, optional): Non-negative integer seed for best-effort reproducible video generation.

### 4. `veo_first_last_to_video` & `veo_reference_to_video` & `veo_ingredients_to_video`

*   **Description**: Advanced video generation features supporting reference images and start/end frame interpolation.
*   These tools also support the common Veo generation parameters, including `seed` (number, optional): a non-negative integer seed for best-effort reproducible video generation, and `output_filename` (string, optional): a base output name applied with the same logic as `veo_t2v` (see [Naming Outputs](../README.md#naming-outputs-output_filename)).

## Environment Variable Configuration

The tool utilizes the following environment variables:

*   `GOOGLE_CLOUD_PROJECT` (string): **Required**. Your Google Cloud Project ID. The application will terminate if this is not set. Note: `PROJECT_ID` is also supported as a fallback.
    *   **Override**: You can override this globally for this specific server by setting `VEO_PROJECT_ID`.
*   `GOOGLE_CLOUD_LOCATION` (string): The preferred Google Cloud location/region for Vertex AI services.
    *   Default: `"us-central1"`
    *   **Fallback**: `LOCATION` is also supported as a fallback for `GOOGLE_CLOUD_LOCATION`.
    *   **Override**: You can override this globally for this specific server by setting `VEO_LOCATION`.
*   `GENMEDIA_BUCKET` (string): An optional default Google Cloud Storage bucket to use for GCS outputs if the `bucket` parameter is not specified in the tool request. The path `veo_outputs/` will be appended to this bucket.
    *   Default: `""` (empty string).
*   `ALLOW_UNSAFE_MODELS` (boolean): Optional (`true`/`false`). Allows users to bypass strict local model constraint validation, enabling them to test experimental or pre-release model strings that are not yet hardcoded in the registry.
    *   Default: `false`
*   `ENABLE_OPTIONAL_HEADER_CAPTURE` (boolean): Optional (`true`/`false`). Intended for internal debugging. When set to `true`, the server intercepts API requests and injects the raw ADC Bearer token to capture and surface the `x-goog-sherlog-link` header in the tool output. This feature is currently **not supported** for Veo due to Go SDK limitations with long-running operations.
    *   Default: `false`
*   `PORT` (string, for HTTP transport): The port for the HTTP server to listen on.
    *   Default: `"8080"`

## Transports Supported

*   `stdio` (default)
*   `sse` (Server-Sent Events)
*   `http` (Streamable HTTP)

CORS is enabled for the HTTP transport, allowing all origins by default.

## Run

Build the tool using `go build` or `go install`.

*   **STDIO (Default)**:
    ```bash
    ./mcp-veo-go
    # or
    ./mcp-veo-go -transport stdio
    ```
*   **HTTP**:
    ```bash
    ./mcp-veo-go -transport http
    # Optionally set PORT environment variable, e.g., PORT=8084 ./mcp-veo-go -transport http
    ```
    The MCP server will be available at `http://localhost:<PORT>/mcp`.
*   **SSE (Server-Sent Events)**:
    ```bash
    ./mcp-veo-go -transport sse
    # SSE server typically runs on port 8081 by default in this configuration.
    ```
    The MCP server will be available at `http://localhost:8081`.

## Examples

### Text-to-Video (`veo_t2v`)
```json
{
  "method": "tools/call",
  "params": {
    "name": "veo_t2v",
    "arguments": {
      "prompt": "A majestic eagle soaring over a mountain range at sunset.",
      "model": "veo-3.1-fast-generate-001",
      "num_videos": 1,
      "aspect_ratio": "16:9",
      "duration": 8,
      "bucket": "your-gcs-bucket/veo_t2v_outputs",
      "output_directory": "./veo_videos_t2v"
    }
  }
}
```

### Image-to-Video (`veo_i2v`)
```json
{
  "method": "tools/call",
  "params": {
    "name": "veo_i2v",
    "arguments": {
      "image_uri": "gs://your-gcs-bucket/source_images/landscape.png",
      "mime_type": "image/png",
      "prompt": "Animate this landscape with a gentle breeze and flowing river.",
      "model": "veo-3.1-fast-generate-001",
      "num_videos": 1,
      "aspect_ratio": "16:9",
      "duration": 6,
      "bucket": "your-gcs-bucket/veo_i2v_outputs",
      "output_directory": "./veo_videos_i2v"
    }
  }
}
```
