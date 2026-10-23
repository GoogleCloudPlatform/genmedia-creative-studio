---
title: "MCP Omni Server"
---

This tool provides video generation (with optional embedded audio) using Google's Gemini Omni model (`gemini-omni-1.1-flash-preview`) via the **Vertex Interactions API**. It is one of the MCP tools for Google Cloud Genmedia services, acting as an MCP server component to allow LLMs and other MCP clients to generate videos from a text prompt, optionally conditioned on input images and/or videos.

Unlike the other genmedia servers (which use the Vertex `genai` client), Omni is reachable only through the Interactions API, so this server calls the shared `common.GenerateOmniVideo` helper (which owns the Interactions client) rather than a `genai.Client`. The Interactions endpoint is **global-only**: `LOCATION` defaults to `global` and the API call is always made against the `global` endpoint.

## MCP Tool Definitions

The server exposes the following tool:

### 1. `omni_video_generation`

*   **Description**: Generates video (with optional embedded audio) from a text prompt, optionally conditioned on input images and/or videos, using Google's Gemini Omni model via the Vertex Interactions API. Returns MP4(s) saved locally and/or to GCS.
*   **Handler**: `omniVideoGenerationHandler`
*   **Parameters**:
    *   `prompt` (string, required): The text prompt describing the video to generate.
    *   `model` (string, optional): Model to use. Can be the canonical model ID (`gemini-omni-1.1-flash-preview`) or a common alias (e.g. `Omni`, `Omni 1.1`, `Gemini Omni 1.1 Flash`). The prior `gemini-omni-flash-preview` remains selectable via its ID or the `Gemini Omni Flash` alias. See `mcp-common/models.go` for the supported list. Defaults to `gemini-omni-1.1-flash-preview`.
    *   `resolution` (string, optional): Video output resolution: `360p`, `720p`, `1080p`, or `4k` (`gemini-omni-1.1-flash-preview` supports all four; `gemini-omni-flash-preview` supports `720p`). Sent in `response_format`.
    *   `aspect_ratio` (string, optional): Video output aspect ratio: `16:9` or `9:16`. Sent in `response_format`.
    *   `duration_seconds` (number, optional): Video output duration in seconds (`3`-`10`, maximum `10` seconds with or without audio). Sent in `response_format`.
    *   `images` (array of string, optional): Up to 10 input images to condition generation on (first/last frames, character/style references, or starting frame). Each entry is a local file path (up to 20 MB) or a `gs://` URI (up to 30 MB). The MIME type is inferred from the file extension: `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `image/heic`, `image/heif`.
    *   `videos` (array of string, optional): Up to 3 input videos to reference, edit, or extend. Each entry is a local file path (up to 20 MB) or a `gs://` URI (`video/mp4`, `video/webm`, `video/quicktime`, `video/mpeg`, `video/x-flv`, `video/wmv`, `video/3gpp`).
    *   `sample_count` (number, optional): Number of videos to generate (1-3, default 1). Clamped to the model maximum of 3.
    *   `temperature` (number, optional): Sampling temperature, `0.0`-`2.0` (default `1.0`; higher = more varied). Sent in `generation_config`.
    *   `top_p` (number, optional): Nucleus sampling probability mass, `0.0`-`1.0` (default `0.95`). Sent in `generation_config`.
    *   `output_directory` (string, optional): Local directory to save the generated video(s) to. Filenames (`omni_<timestamp>_<n>.mp4`) are generated automatically unless `output_filename` is set.
    *   `output_filename` (string, optional): Base name for the output(s), e.g. `clip.mp4`. The extension is forced to the true video type and, when more than one video is generated, a `_1..n` suffix is inserted before the extension. Applied identically to local files and GCS objects. See [Naming Outputs](../index.md#naming-outputs-output_filename).
    *   `gcs_bucket_uri` (string, optional): GCS URI prefix to store generated video(s) (e.g., `your-bucket/outputs/`). If not provided and `GENMEDIA_BUCKET` is set, `gs://<GENMEDIA_BUCKET>/omni_outputs/` is used. For each uploaded video a best-effort V4 signed HTTPS URL is also returned (see `OMNI_SIGNED_URL_EXPIRY_HOURS`).

## Model Specifications (`gemini-omni-1.1-flash-preview`)

Per the [Google Cloud Gemini Omni 1.1 Flash documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/omni-1-1-flash):

| Specification | Details |
| :--- | :--- |
| **Model ID** | `gemini-omni-1.1-flash-preview` (default) |
| **API & Endpoint** | Vertex Interactions API (`global` location) |
| **Modalities** | Text (input & output), Image (input only), Video (input & output, with embedded speech, music, and sound effects) |
| **Token Limits** | Max input: `131,072` tokens · Max output: `57,920` tokens |
| **Supported Capabilities** | Thinking, Text-to-Video, Image-to-Video, Reference-to-Video, First/Last Frame Video, Sound Generation (speech, music, SFX), Video Editing, Video Extension, Content Credentials (C2PA) |
| **Video Output Specs** | Max length: `10s` (with or without audio) · Aspect ratios: `16:9`, `9:16` · Resolutions: `360p`, `720p`, `1080p`, `4k` |
| **Input Limits** | Up to `10` images per prompt (`<=20 MB` inline / `<=30 MB` GCS) · Up to `3` videos per prompt |

## Authentication

This server uses **Application Default Credentials (ADC)** to authenticate to the Vertex Interactions API — run `gcloud auth application-default login` locally, or rely on the attached service account when running on Google Cloud. The Interactions API is invoked against the **`global`** location only; per-region overrides do not apply to the Interactions call itself.

## Environment Variable Configuration

The tool utilizes the following environment variables:

*   `GOOGLE_CLOUD_PROJECT` (string): **Required**. Your Google Cloud Project ID. The application will terminate if this is not set. Note: `PROJECT_ID` is also supported as a fallback.
    *   **Override**: You can override this globally for this specific server by setting `OMNI_PROJECT_ID`.
*   `GOOGLE_CLOUD_LOCATION` (string): The preferred Google Cloud location. For Omni this defaults to `global` and the Interactions call is always made against the `global` endpoint.
    *   **Fallback**: `LOCATION` is also supported as a fallback for `GOOGLE_CLOUD_LOCATION`.
    *   **Override**: You can override this globally for this specific server by setting `OMNI_LOCATION`.
*   `GENMEDIA_BUCKET` (string): An optional default Google Cloud Storage bucket to use for GCS outputs if the `gcs_bucket_uri` parameter is not specified in the tool request. The path `omni_outputs/` will be appended to this bucket.
    *   Default: `""` (empty string).
*   `OMNI_SIGNED_URL_EXPIRY_HOURS` (number): Validity, in hours, of the V4 signed HTTPS URL returned for each uploaded video. Clamped to `168` (the V4 maximum); `0` disables signed-URL generation (the `gs://` URI is still returned). Signing under ADC without a private key requires `roles/iam.serviceAccountTokenCreator` on the runtime service account (non-fatal if absent).
    *   Default: `24`
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
    ./mcp-omni-go
    # or
    ./mcp-omni-go -transport stdio
    ```
*   **HTTP**:
    ```bash
    ./mcp-omni-go -transport http
    # Optionally set PORT environment variable, e.g., PORT=8084 ./mcp-omni-go -transport http
    ```
    The MCP server will be available at `http://localhost:<PORT>/mcp`.
*   **SSE (Server-Sent Events)**:
    ```bash
    ./mcp-omni-go -transport sse
    # SSE server typically runs on port 8081 by default in this configuration.
    ```
    The MCP server will be available at `http://localhost:8081`.

## Examples

### Text-to-Video (`omni_video_generation`)
```json
{
  "method": "tools/call",
  "params": {
    "name": "omni_video_generation",
    "arguments": {
      "prompt": "A majestic eagle soaring over a mountain range at sunset.",
      "sample_count": 1,
      "gcs_bucket_uri": "your-gcs-bucket/omni_outputs",
      "output_directory": "./omni_videos"
    }
  }
}
```

### Image-conditioned generation (`omni_video_generation`)
```json
{
  "method": "tools/call",
  "params": {
    "name": "omni_video_generation",
    "arguments": {
      "prompt": "Animate this landscape with a gentle breeze and flowing river.",
      "images": ["gs://your-gcs-bucket/source_images/landscape.png"],
      "output_directory": "./omni_videos"
    }
  }
}
```
