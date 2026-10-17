---
title: "MCP Imagen Server"
---

> **⚠️ DEPRECATED.** The Imagen family of models reached its announced
> sunset on **2026-06-30**, and `install.sh` / `deploy-cloudrun.sh` already
> exclude `mcp-imagen-go` from the standard install loop. Do not enable
> this server in new deployments.
>
> **For new image-generation work, use [`mcp-nanobanana-go`](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/tree/main/experiments/mcp-genmedia/mcp-genmedia-go/mcp-nanobanana-go)
> (Nano Banana / Gemini 3.1 Flash Image) or [`mcp-gemini-go`](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/tree/main/experiments/mcp-genmedia/mcp-genmedia-go/mcp-gemini-go).**
>
> The directory is kept in-tree for reference while the core app's upscale
> (`imagen-4.0-upscale-preview`) and Virtual Try-On (`virtual-try-on-001`)
> surfaces still target Imagen-family models. Verified Nano Banana
> approximations exist for both but are not drop-in replacements — see the
> 2026-08-22 inventory and correction on
> [issue #1588](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/issues/1588).
>
> The full audit of remaining references lives in-tree
> (`mcp-imagen-go/DEPRECATION.md`, added by
> [PR #1912](https://github.com/GoogleCloudPlatform/genmedia-creative-studio/pull/1912)).

This tool provides image generation capabilities using Google's Imagen models (via Google Cloud AI). It is one of the MCP tools for Google Cloud Genmedia services, functioning as an MCP server component to allow LLMs and other MCP clients to generate images from text prompts.

## MCP Tool Definition

The following tool is exposed by this server:

### 1. `imagen_t2i`

*   **Description**: Generates an image based on a text prompt using Google's Imagen models. The image can be returned as base64 data, saved to a local directory, or stored in a Google Cloud Storage bucket.
*   **Handler**: `imagenGenerationHandler` (via wrapper)
*   **Parameters**:
    *   `prompt` (string, required): Prompt for text to image generation.
    *   `model` (string, optional): The model for image generation. Can be a full model ID or a common alias. See the `mcp-common/models.go` file for a complete list of supported models and aliases.
    *   `num_images` (number, optional): Number of images to generate.
        *   Default: `1`
        *   Note: The maximum number of images depends on the selected model (see table above).
    *   `aspect_ratio` (string, optional): The aspect ratio for the generated image.
        *   Default: `"1:1"`
        *   Common values: `"1:1"` (square), `"16:9"` (widescreen), `"9:16"` (portrait)
    *   `gcs_bucket_uri` (string, optional): GCS URI prefix to store the generated images (e.g., "your-bucket/outputs/" or "gs://your-bucket/outputs/"). If provided, images are saved to GCS instead of returning bytes directly.
    *   `output_directory` (string, optional): If provided, specifies a local directory to save the generated image(s) to.
    *   `output_filename` (string, optional): Base name for the output(s), e.g. `hero.png`. The extension is forced to the true image type and, when more than one image is generated, a `_1..n` suffix is inserted before the extension. Applied identically to local files and GCS objects. See [Naming Outputs](../index.md#naming-outputs-output_filename).

When images are written to GCS, the tool appends one MCP `resource_link` content item per image — and one for the edited image on image-editing calls (`uri` = the `gs://` URI, plus `name`, `mimeType`, and a 1-based `description`); the text summary is unchanged. See [Resource Links for GCS Outputs](../index.md#resource-links-for-gcs-outputs).

### Resources

The server exposes the following resources:

*   `imagen://models`: Returns a JSON object detailing the supported Imagen models and their aliases. You can read this resource using `mcptools resources get imagen://models ./mcp-imagen-go`.
*   `imagen://segmentation_classes`: Returns a JSON object of supported classes for semantic masking in image editing.

## Environment Variable Configuration

The tool utilizes the following environment variables:

*   `GOOGLE_CLOUD_PROJECT` (string): **Required**. Your Google Cloud Project ID. The application will terminate if this is not set. Note: `PROJECT_ID` is also supported as a fallback.
    *   **Override**: You can override this globally for this specific server by setting `IMAGEN_PROJECT_ID`.
*   `GOOGLE_CLOUD_LOCATION` (string): The preferred Google Cloud location/region for Google Cloud AI services.
    *   Default: `"us-central1"`
    *   **Fallback**: `LOCATION` is also supported as a fallback for `GOOGLE_CLOUD_LOCATION`.
    *   **Override**: You can override this globally for this specific server by setting `IMAGEN_LOCATION`.
*   `GENMEDIA_BUCKET` (string): An optional default Google Cloud Storage bucket to use for GCS outputs if `gcs_bucket_uri` is not specified in the tool request. The path `imagen_outputs/` will be appended to this bucket.
    *   Default: `""` (empty string, meaning no default GCS output path is formed from this variable unless `gcs_bucket_uri` is also absent).
*   `ALLOW_UNSAFE_MODELS` (boolean): Optional (`true`/`false`). Allows users to bypass strict local model constraint validation, enabling them to test experimental or pre-release model strings that are not yet hardcoded in the registry.
    *   Default: `false`
*   `ENABLE_OPTIONAL_HEADER_CAPTURE` (boolean): Optional (`true`/`false`). Intended for internal debugging. When set to `true`, the server intercepts API requests and injects the raw ADC Bearer token to capture and surface the `x-goog-sherlog-link` header in the tool output. This feature is supported for Imagen.
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
    ./mcp-imagen-go
    # or
    ./mcp-imagen-go -transport stdio
    ```
*   **HTTP**:
    ```bash
    ./mcp-imagen-go -transport http
    # Optionally set PORT environment variable, e.g., PORT=8083 ./mcp-imagen-go -transport http
    ```
    The MCP server will be available at `http://localhost:<PORT>/mcp`.
*   **SSE (Server-Sent Events)**:
    ```bash
    ./mcp-imagen-go -transport sse
    # SSE server typically runs on port 8081 by default in this configuration.
    ```
    The MCP server will be available at `http://localhost:8081`.

## Example

### Imagen Text-to-Image Generation
```json
{
  "method": "tools/call",
  "params": {
    "name": "imagen_t2i",
    "arguments": {
      "prompt": "A photorealistic image of a cat wearing a small wizard hat, sitting on a pile of ancient books.",
      "model": "imagen-3.0-generate-002",
      "num_images": 1,
      "aspect_ratio": "1:1",
      "output_directory": "./imagen_output"
    }
  }
}
```
