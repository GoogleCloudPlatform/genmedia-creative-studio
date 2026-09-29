# MCP Servers for Genmedia: Go Implementations

This directory houses the Go language implementations of Model Context Protocol (MCP) servers designed to interface with Google Cloud's generative media APIs. Each subdirectory contains a standalone MCP server that can be built and run independently.

These servers enable MCP clients (such as AI agents or other applications) to leverage powerful media generation and manipulation capabilities.

## Getting Started: Installation

### Easy Installation (Pre-compiled Binaries)

For the fastest setup without needing the Go toolchain installed, you can use our online installer script. This script automatically detects your operating system and architecture, downloads the latest pre-compiled binaries from GitHub Releases, and places them in your `~/.local/bin` directory.

Run the following command in your terminal:

```bash
curl -sL https://raw.githubusercontent.com/GoogleCloudPlatform/genmedia-creative-studio/main/experiments/mcp-genmedia/mcp-genmedia-go/install-online.sh | bash
```

*Note: Ensure `~/.local/bin` is added to your system `PATH`.*

### Local Build Installer (Requires Go)

If you prefer to compile the servers from source or want to modify the code, you can use the local interactive installer script.


1.  **Run the Installer Script**
    From this `mcp-genmedia-go` directory, execute the following command:
    ```bash
    ./install.sh
    ```

2.  **Follow the On-Screen Instructions**
    The script will present you with a menu to install a single server or all of them. It will also check if Go is installed and if your `PATH` is configured correctly.

![run the install.sh](../assets/install-mcp-genmedia.gif)

### Manual Installation

This project uses a Go workspace (`go.work`) to manage the multiple modules. The following steps will ensure all dependencies are correctly synchronized and the server binaries are installed.

**Prerequisites:**
*   Go (version 1.18 or later is recommended for workspace support)
*   Git
*   Google Cloud CLI

**Instructions:**

1.  **Navigate to the Workspace Directory**
    All commands should be run from this `mcp-genmedia-go` directory.

2.  **Tidy Workspace Dependencies**
    This command synchronizes the dependencies between the modules in the workspace. This is a crucial step to avoid build errors.
    ```bash
    go work sync
    ```

3.  **Install the Binaries**
    This command explicitly builds and installs all the MCP server applications into your Go bin directory (`$GOPATH/bin` or `$GOBIN`).
    ```bash
    go install ./mcp-avtool-go ./mcp-chirp3-go ./mcp-gemini-go ./mcp-gemini-transcribe-go ./mcp-nanobanana-go ./mcp-lyria-go ./mcp-veo-go ./mcp-omni-go
    ```
    `mcp-imagen-go` is deprecated (see the server list below) and is not included above; append `./mcp-imagen-go` if you still need it.

4.  **Verify the Installation**
    Check that the binaries are available in your path.
    ```bash
    ls $(go env GOBIN)/mcp-*
    ```

### Validate the Installation

Before validating, ensure your Google Cloud project ID is set as an environment variable:
```bash
export GOOGLE_CLOUD_PROJECT=$(gcloud config get project)
# Or, if you prefer to set it manually:
# export GOOGLE_CLOUD_PROJECT="your-google-cloud-project-id"
```

With the MCP servers for genmedia installed, you can test that they're available by sending a STDIO "tools/list" command (substitute the MCP server in question as needed):

```bash
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | mcp-nanobanana-go
```
For a more readable output, you can pipe it to `jq` (if installed):
```bash
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | mcp-nanobanana-go | jq .
```

Either of these should result in a JSON response with a list of tools, similar to this (output truncated for brevity):

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "nanobanana_image_generation",
        "description": "Generates content (text and/or images) based on a multimodal prompt using Gemini Image generation models...",
        // ... more tool details
      }
    ]
  }
}
```

## 🛠️ Agent Skills

To get the most out of these servers, we recommend using our expert **Agent Skills**. These skills provide AI agents with the procedural knowledge needed to orchestrate complex workflows like podcast generation or video composition.

See the [Agent Skills](../skills/README.md) directory for installation instructions for Gemini CLI and Antigravity.

## Using Prompts

In addition to tools, the MCP servers now support prompts, providing a more interactive and user-friendly way to access their core functionality. Prompts guide the user through a task, asking for required information if it's not provided.

### Listing and Using Prompts

You can list the available prompts for a server using the `prompts/list` method:

```bash
echo '{"jsonrpc":"2.0","method":"prompts/list","id":1}' | mcp-veo-go | jq .
```

To use a prompt, you call the `prompts/get` method with the prompt's name and any required arguments. If you omit a required argument, the server will respond with a message asking for it.

**Example: Using the `generate-video` prompt with `mcp-veo-go`**

```bash
# Call the prompt with a required argument
export GOOGLE_CLOUD_PROJECT=$(gcloud config get project)
echo '{"jsonrpc":"2.0","method":"prompts/get","id":2,"params":{"name":"generate-video","arguments":{"prompt":"a futuristic cityscape at sunset"}}}' | mcp-veo-go | jq .

# Call the prompt without a required argument
echo '{"jsonrpc":"2.0","method":"prompts/get","id":3,"params":{"name":"generate-video"}}' | mcp-veo-go | jq .
```

This will result in a more conversational interaction, making the servers easier to use for interactive clients.

## Client Configurations

The MCP servers can be used with various clients and hosts. A sample MCP configuration JSON can be found at [genmedia-config.json](../sample-agents/mcp-inspector/genmedia-config.json).

This repository provides AI application samples for:

*   [Google ADK (Agent Development Kit)](../sample-agents/adk/README.md)
*   [Google Firebase Genkit](../sample-agents/genkit/README.md)
*   [Google Gemini CLI](../sample-agents/geminicli/README.md)


## Available Go MCP Servers:

*   **`mcp-avtool-go`**:
    *   Provides audio/video compositing and manipulation tools by instrumenting `ffmpeg` and `ffprobe`.
    *   Capabilities include media info retrieval, format conversion (e.g., WAV to MP3), GIF creation, combining audio/video, overlaying images, concatenating files, volume adjustment, and audio layering.
    *   Supports local file paths and GCS URIs for inputs/outputs.

*   **`mcp-chirp3-go`**:
    *   Offers Text-to-Speech (TTS) synthesis using Google Cloud TTS with Chirp3-HD voices.
    *   Tools: `chirp_tts` for synthesis (with custom pronunciation support) and `list_chirp_voices` for discovering available voices.
    *   Audio can be returned as base64 data or saved to a local directory.

*   **`mcp-gemini-go`**:
    *   Provides a multimodal interface to Google's Gemini models.
    *   Tools include `gemini_image_generation` for generating text and images, and `gemini_audio_tts` for synthesizing speech with Gemini TTS models.
    *   Also includes the `list_gemini_voices` helper tool and the `gemini://language_codes` resource.
    *   Output can be saved to a local directory or GCS.

*   **`mcp-gemini-transcribe-go`**:
    *   Provides synchronous speech-to-text transcription using Google's Gemini 3.5 Transcribe model via Vertex AI.
    *   Tool: `gemini_transcribe` for transcribing pre-recorded audio files to text.
    *   The single-purpose sibling of the `gemini_transcribe` tool bundled into `mcp-gemini-go`; served only in the `global` location.

*   **`mcp-imagen-go`** (Deprecated — use `mcp-nanobanana-go` or `mcp-gemini-go` for new work; Imagen models are deprecated as of June 30, 2026):
    *   Enables image generation using Google's Imagen models via Vertex AI.
    *   Tool: `imagen_t2i` for text-to-image generation.
    *   Supports various parameters like aspect ratio and number of images. Output can be directed to GCS, saved locally (including download from GCS if API saves there), or returned as base64 data.


*   **`mcp-nanobanana-go`**:
    *   Provides a dedicated multimodal interface to Google's Nano Banana (Gemini Image) models.
    *   Tool: `nanobanana_image_generation` for generating text and images.
    *   Output can be saved to a local directory or GCS.

*   **`mcp-lyria-go`**:
    *   Facilitates music generation using Google's Lyria models via Vertex AI.
    *   Tool: `lyria_generate_music` for creating music from text prompts.
    *   Supports parameters like negative prompts and seed. Output can be directed to GCS, saved locally, or returned as base64 data.

*   **`mcp-veo-go`**:
    *   Provides video generation capabilities using Google's Veo models via Vertex AI.
    *   Tools: `veo_t2v` (text-to-video) and `veo_i2v` (image-to-video).
    *   Supports parameters like aspect ratio and duration. Videos are saved to GCS by the API and can optionally be downloaded to a local directory.

*   **`mcp-omni-go`**:
    *   Provides video generation (with optional embedded audio) using Google's Gemini Omni model via the Vertex Interactions API.
    *   Tool: `omni_video_generation` for generating video from a text prompt, optionally conditioned on input images and/or videos.
    *   Uses Application Default Credentials (ADC) against the `global` Interactions endpoint. Output can be saved to a local directory and/or GCS (with a best-effort V4 signed URL).

## Common Features:

*   **Transport Protocols**: Most servers support `stdio` (default), `http` (streamable HTTP with CORS), and `sse` (Server-Sent Events, legacy) transports.
*   **Google Cloud Authentication**: Relies on Application Default Credentials (ADC) or service account keys.

## Naming Outputs: `output_filename`

Every media-generating tool accepts a single optional `output_filename` (string)
with identical name and semantics, so a client can **predict the exact output
name** from the tool and request. The same computed name is applied consistently
across all sinks — the inline response, the local `output_directory`, and GCS.

- **Precedence.** When more than one naming argument is supplied, `output_filename`
  always wins. Otherwise the server's legacy parameter (with its legacy semantics)
  is used, and otherwise the server's default naming scheme. When `output_filename`
  is unset, behavior is byte-for-byte unchanged from before this feature.
- **Extension is forced to the true output type.** You provide the file *stem*; the
  extension is set from the model's actual output MIME type. `hero.jpeg` on a PNG
  response becomes `hero.png`, and a missing extension is added. **`mcp-avtool-go`
  is the one exception** — for `ffmpeg` the extension selects the output
  container/codec, so avtool honors the extension you provide (and only warns if it
  looks unexpected).
- **Multiple outputs get a `_1..n` suffix.** For a single output the name is
  exactly `<stem>.<ext>` (no suffix). For `n > 1` outputs the names are
  `<stem>_1.<ext> … <stem>_n.<ext>` — 1-based, no zero-padding, contiguous, in
  generation order.
- **Collisions overwrite, with a warning.** If the computed name already exists
  (local file or GCS object) it is overwritten and a warning is logged — no error
  and no automatic renaming, so re-running with the same name is idempotent.
- **Path traversal is sanitized.** Any directory components or `..` in
  `output_filename` are stripped to a single safe name; use `output_directory` /
  `gcs_bucket_uri` to choose the destination.
- **Path-C servers (imagen, veo).** These let the Vertex API name the objects
  (`sample_*`) in the output prefix, then copy each object to the requested name
  and delete the original. On success no `sample_*` originals remain; the copy adds
  a small amount of tool latency (a fast metadata operation for same-region
  buckets, proportional to size for large/cross-region objects).

### Deprecated legacy aliases

The following per-server parameters are still accepted for backward compatibility
but are **deprecated — prefer `output_filename`** (no removal is planned in this
release):

| Server | Legacy parameter | Notes |
| --- | --- | --- |
| `mcp-avtool-go` | `output_file_name` | Full output name (extension not forced). |
| `mcp-lyria-go` | `file_name` | Full output name. |
| `mcp-chirp3-go`, `mcp-gemini-go` (TTS) | `output_filename_prefix` | A *prefix* only (a timestamp/voice + extension is appended); `output_filename` provides the full name. |

## Resource Links for GCS Outputs

When a tool writes an artifact to Google Cloud Storage, it additionally returns
one MCP [`resource_link`](https://modelcontextprotocol.io/specification/2025-06-18/server/tools#resource-links)
content item **per GCS artifact**, so an MCP client can address the output as a
first-class resource rather than parsing it out of the text summary.

- **GCS sink only.** A `resource_link` is emitted **only when the artifact was
  uploaded to GCS** (`gcs_bucket_uri` or a server's bucket fallback). Inline-only
  and local-only responses are unchanged — no link is added.
- **One link per artifact,** appended after the existing content in generation
  order (so for `n` GCS artifacts you get `n` links, aligned 1..n).
- **`uri` is the `gs://` URI** — the durable identity of the object, **not** the
  expiring V4-signed HTTPS URL. The signed URL (when generated) still appears in
  the text summary as before; the `resource_link` gives clients a stable handle.
- **`name`** is the object's name, **`mimeType`** is the artifact's true output
  MIME type, and **`description`** is a 1-based human label (e.g.
  `nanobanana output 1 of 1`).
- **Text output is unchanged (back-compat).** The `resource_link` items are
  *appended*; the existing text content (model text, signed-URL line, saved-files
  summary) is byte-for-byte identical to before this feature.

**In scope:** `mcp-nanobanana-go`, `mcp-gemini-go` (image generation/editing),
`mcp-imagen-go` (text-to-image and edit), `mcp-veo-go`, `mcp-lyria-go`, and the
shared omni renderer. **Out of scope:** `mcp-chirp3-go`, `mcp-gemini-go` **TTS**,
and `mcp-avtool-go` do not emit `resource_link` items.

## Configuration (Environment Variables)

All servers in this project are configured using environment variables. While some servers have unique variables, the following are common to most of them:

See [ENV_VARS.md](./ENV_VARS.md) for the complete environment-variable reference covering every server.

### Using a `.env` File

For easier local development, you can place a `.env` file in the directory where you run the MCP server. The server will automatically load environment variables from this file.

**Precedence Order:**

1.  **Environment variables set in the shell:** These take the highest precedence.
2.  **Variables in the `.env` file:** These are loaded but will **not** override any variables already set in your shell.

This allows you to have default values in your `.env` file and override them for specific cases by setting the variable in your terminal.

**Available Variables:**

The following variables can be defined in your `.env` file or as shell environment variables:

*   `GOOGLE_CLOUD_PROJECT` (string): **Required**. Your Google Cloud Project ID. The application will terminate if this is not set. Note: `PROJECT_ID` is also supported as a fallback.
    *   **Per-Server Override**: You can override the global project ID for specific servers using `VEO_PROJECT_ID`, `IMAGEN_PROJECT_ID`, `LYRIA_PROJECT_ID`, `GEMINI_PROJECT_ID`, `CHIRP3_PROJECT_ID`, `AVTOOL_PROJECT_ID`, `NANOBANANA_PROJECT_ID`, or `OMNI_PROJECT_ID`.
*   `GOOGLE_CLOUD_LOCATION` (string): The preferred Google Cloud location/region for Vertex AI services. Defaults to `us-central1` if not set.
    *   **Fallback**: `LOCATION` is also supported as a fallback for `GOOGLE_CLOUD_LOCATION`.
    *   **Per-Server Override**: You can override the global location for specific servers using `<PREFIX>_LOCATION` (e.g., `VEO_LOCATION`, `IMAGEN_LOCATION`, `LYRIA_LOCATION`, `GEMINI_LOCATION`, `CHIRP3_LOCATION`, `AVTOOL_LOCATION`, `NANOBANANA_LOCATION`, or `OMNI_LOCATION`). Note: `mcp-omni-go` defaults `LOCATION` to `global` and the Interactions API call is always made against the `global` endpoint.
*   `GENMEDIA_BUCKET` (string): An optional default Google Cloud Storage bucket to use for GCS outputs if a bucket is not specified in a tool request.
*   `ALLOW_UNSAFE_MODELS` (boolean): Optional (`true`/`false`). Allows users to bypass strict local model constraint validation, enabling them to test experimental or pre-release model strings that are not yet hardcoded in the registry. Defaults to `false`.
*   `ENABLE_OPTIONAL_HEADER_CAPTURE` (boolean): Optional (`true`/`false`). Intended for internal debugging. When set to `true`, the server intercepts API requests and injects the raw ADC Bearer token to capture and surface the `x-goog-sherlog-link` header in the tool output. This feature is supported for Imagen, Gemini, NanoBanana, and Lyria, but currently not supported for Veo due to Go SDK limitations with long-running operations. Defaults to `false`.
*   `PORT` (string): Specifies the port for the `http` transport. If not set, it defaults to `8080`. Note that for the `sse` transport, most servers use a hardcoded port (typically `8081`) to avoid conflicts.
*   `GCS_DOWNLOAD_TIMEOUT` (string): The timeout for GCS download/streaming operations. Accepts Go duration strings (e.g. `"30s"`, `"5m"`, `"2m30s"`). Defaults to `5m` if not set. Increase this value when working with large media files like videos or high-resolution images.

*Example:*
```bash
export GOOGLE_CLOUD_PROJECT="your-google-cloud-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"
```

### Local Development & OpenTelemetry

When running the MCP servers locally, you may want to connect to a local OpenTelemetry (OTel) collector for tracing. By default, the servers attempt a secure (TLS) connection. If your local collector is running in insecure mode, you will need to set the following environment variable to disable TLS:

```bash
# This tells the application to use an insecure connection for the OTLP exporter.
export OTEL_EXPORTER_OTLP_INSECURE=true
```

When deploying the application to a production environment (like GKE, Cloud Run, etc.), you should **not** set this variable. The application will correctly default to requiring a secure TLS connection to the OTel collector.

You can also specify the OTel collector endpoint using an environment variable:

```bash
# Example for a local collector
export OTEL_EXPORTER_OTLP_ENDPOINT="localhost:4317"
```
If `OTEL_EXPORTER_OTLP_ENDPOINT` is not set, it will default to `localhost:4317`.

Please refer to the `README.md` file within each server's subdirectory for detailed information on its specific tools, parameters, environment variables, and usage examples.

## Developing MCP Servers for Genmedia

This section provides guidance on how to understand the architecture and extend or create a new MCP server for Genmedia.

See [RELEASING.md](./RELEASING.md) for the release and versioning process, and [CHANGELOG.md](./CHANGELOG.md) for the change history.

### Architecture

The MCP servers in this repository are all structured in a similar way. They all use the `mcp-common` package for configuration, file handling, and OpenTelemetry. They all use the `mcp-go` library to create the MCP server and tools. They all support the same transport protocols (`stdio`, `http`, and `sse`).

The `mcp-common` package provides the following functionality:

*   **Configuration**: The `config.go` file provides a way to load configuration from environment variables.
*   **File Utilities**: The `file_utils.go` file provides utility functions for working with files.
*   **GCS Utilities**: The `gcs_utils.go` file provides utility functions for working with Google Cloud Storage.
*   **OpenTelemetry**: The `otel.go` file provides a function for initializing OpenTelemetry.

### Extending an Existing Server

To extend an existing server, you'll need to do the following:

1.  Add a new tool to the server. You can do this by calling the `AddTool` method on the `server.MCPServer` struct.
2.  Implement the tool's handler function. The handler function will be called when the tool is invoked. The handler function should take a `context.Context` and a `mcp.CallToolRequest` as input and should return a `mcp.CallToolResult` and an error.

### Creating a New Server

To create a new server, you'll need to do the following:

1.  Create a new directory for the server.
2.  Create a new `go.mod` file for the server.
3.  Create a new `main.go` file for the server.
4.  In the `main.go` file, you'll need to do the following:
    1.  Create a new `server.MCPServer` struct.
    2.  Add one or more tools to the server.
    3.  Start the server.
