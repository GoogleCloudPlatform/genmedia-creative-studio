# ADK Genmedia Series — from a nine-line agent to a multi-agent ad pipeline

Welcome. This is a hands-on course in building **agents** on Google's
[Agent Development Kit (ADK)](https://google.github.io/adk-docs/) on top of the
[genmedia MCP tools](../../mcp-genmedia-go/) (image, video, music, voice, and AV
muxing). You'll work through it in order. Each step is a **self-contained,
runnable ADK project**, each teaches **exactly one** new ADK concept, and each
bakes in the genmedia "gotchas" so your examples never teach an invalid call.

By the end you'll have gone from a nine-line single-tool agent to a multi-agent
ad-creative pipeline — and you'll understand the four ADK constructs that get you
there: `LlmAgent`, `MCPToolset` (+ `tool_name_prefix`), `SequentialAgent`
(+ `output_key`), and `ParallelAgent` / `AgentTool`.

## Before you start

- **Install the genmedia MCP suite (≥ v3.18.1) on your `PATH`.** Every agent
  invokes the servers as PATH-installed stdio binaries (e.g.
  `mcp-nanobanana-go`). Use the suite's
  [`install.sh`](../../mcp-genmedia-go/install.sh).
- **Have a Google Cloud project with Vertex AI enabled** and application-default
  credentials (`gcloud auth application-default login`).
- **Set three environment variables** (each agent ships an `.env.example`):
  `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_VERTEXAI="True"`
  (plus `GENMEDIA_BUCKET` for GCS output).
- **You'll need `uv`** (each project uses `uv sync` → `adk web`), and **`ffmpeg`**
  once you reach the audio/video agents.

## The path

Follow these in order. Each links to the next and cross-links the non-ADK skill
or demo that does the same job on another surface.

| # | Step | You'll learn | Status |
|---|------|--------------|--------|
| 0 | **Meet ADK** — [the refreshed genmedia sample](../adk/) | an ADK agent is an `LlmAgent` + `MCPToolset`s; the LLM drives across many tools | baseline |
| 1 | **Your first genmedia agent** — [Photoshoot](./photoshoot/) | one `LlmAgent` + one `MCPToolset` (`tool_filter`); output modes + verify-by-existence | **ready** |
| 2 | **Now with video** — [Director / Videographer](./director-videographer/) | one tool again, but the Veo gotchas (verify by *listing*; explicit Veo-3 model) | **ready** |
| 3 | **Three servers, one agent** — [Music Producer](./music-producer/) | multiple `MCPToolset`s, `tool_name_prefix`, and the naming crosswalk | **ready** |
| 4 | **Your first pipeline** — [Scriptwriter / Storyboarder](./scriptwriter-storyboarder/) | `SequentialAgent` + `output_key` state passing between agents | **ready** |
| 5 | **A real multi-agent app** — [Ad creative-director's assistant](./ad-creative-director/) | `SequentialAgent` ⊃ `ParallelAgent` + `AgentTool`; composing the persona agents; plus an optional self-critique `LoopAgent` ("Editor's QC Room") that re-assembles until an objective check passes or a small iteration cap is hit — both profiles | **ready** |
| 6 | **Dogfood the studio — Creative Studio (storyboard profile)** — [same engine, storyboard profile + headless CLI](./ad-creative-director/#creative-studio--the-storyboard-profile-dogfood) | one engine, two profiles via a plain-Python profile factory; a machine-readable package + versioned `manifest.json` contract over a headless CLI | **ready** |

> All steps in the table above are live today; follow them in order, or jump
> straight to the one you need.

## How the series is organized

- **[`photoshoot/`](./photoshoot/)** and the other persona directories are each a
  standalone ADK project (`pyproject.toml`, `.env.example`, an `<agent>/agent.py`
  exposing `root_agent`, and a tutorial `README.md`).
- **[`NAMING.md`](./NAMING.md)** is the shared naming-crosswalk cheatsheet — the
  genmedia servers spell "the same" parameter (model, GCS bucket, local dir,
  output count) differently. Any agent wiring more than one server cites it.
- The **per-agent README** follows one fixed template (see Photoshoot's), so the
  series reads as a course rather than a pile of samples.

## A note on validation

Every agent in this series is meant to be validated by a **real credentialed
run** — `adk web`, the sample prompt, and a **verified** artifact (a file that
exists, or a GCS destination you listed — never a raw resource link). An example
that only *compiles* isn't done.

Start with **[Photoshoot →](./photoshoot/)**.
