# MCP Genmedia DevContainer

A ready-to-use development container that builds the MCP Genmedia Go servers and
wires them into the Gemini CLI, so you can exercise the genmedia tools (Veo,
Imagen, Nano Banana, Lyria, Chirp3-HD, AVTool, Gemini) without a manual setup.

## What it does

- **Toolchain** — pins Go (`GO_VERSION=1.26.0`) matching the module `go.work`,
  plus `ffmpeg`, `jq`, and `gettext-base`.
- **Servers** — builds every server via the module `Makefile` (`make build`), so
  each binary carries the ldflags-injected version from the single
  source-of-truth `VERSION` file, then installs them onto `PATH`.
- **Gemini CLI** — installs a `gemini` launcher and, on create, runs
  `scripts/configure-gemini.sh` to drop a `google-genmedia-devcontainer`
  extension into `~/.gemini/extensions/`.

## Configuration

The container reads these variables from your host environment (via
`containerEnv` in `devcontainer.json`):

| Variable | Purpose |
| --- | --- |
| `GOOGLE_CLOUD_PROJECT` | GCP project for Vertex AI (preferred). |
| `PROJECT_ID` | Legacy fallback for the project. |
| `GOOGLE_CLOUD_LOCATION` | Preferred Vertex AI region (`LOCATION` is the fallback). |
| `GEMINI_LOCATION` | Per-server override for the Gemini endpoint; defaults to `global`. |
| `GENMEDIA_BUCKET` | Default GCS bucket for generated media. |

`configure-gemini.sh` resolves the project (falling back to `gcloud config`),
derives a default `GENMEDIA_BUCKET` when unset, defaults the Gemini server to the
`global` endpoint, and renders the extension. The extension follows main's
canonical settings-based (`version 3.x`) pattern: per-server `env` carries only
timeouts, while `GOOGLE_CLOUD_PROJECT` and `GENMEDIA_BUCKET` are declared in the
top-level `settings` block and resolved from the environment at runtime.

## Usage

Open the `experiments/mcp-genmedia` folder in a Dev Containers-capable editor and
"Reopen in Container". Once built, run `gemini` and the genmedia MCP servers are
available.

## Attribution

This DevContainer re-lands the work originally contributed by @Haihan-Jiang in
[#1442](https://github.com/GoogleCloudPlatform/vertex-ai-creative-studio/pull/1442),
with alignment updates to match current `main`.
