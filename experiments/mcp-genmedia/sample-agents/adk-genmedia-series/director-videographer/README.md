# Director / Videographer — now with video

## What you'll build

A director agent. You give it a scene — *"a red kite tangling free of a
power line at golden hour"* — and it composes a cinematic prompt, generates a
short video clip with [Veo](../../../mcp-genmedia-go/mcp-veo-go/), and tells you
exactly where the file landed so you can confirm it's really there. Same shape as
[Photoshoot](../photoshoot/) — one ADK agent, one tool class — but this time the
output is video, and the "verify by existence" habit becomes **verify by
*listing*.**

## What you'll learn

**The new thing: the same `LlmAgent` + one `MCPToolset` shape carries a much
sharper gotcha, and Gemini's reasoning is what defuses it.** Video generation has
a model-gating footgun — the *default* model can't do audio, so a naive call
fails — and Gemini has to reason about the shot (does it need sound? is it
vertical? how long?) to pick the correct Veo-3 model. You'll also learn why a tool
returning a link is *not* proof of a result: you verify by listing the
destination.

## Prerequisites

- **Python ≥ 3.13** and [`uv`](https://docs.astral.sh/uv/).
- **The genmedia MCP suite ≥ v3.18.1, installed on your `PATH`.** This agent
  calls `mcp-veo-go`. Install it from the suite's
  [`install.sh`](../../../mcp-genmedia-go/install.sh); confirm it's reachable:
  ```bash
  which mcp-veo-go
  ```
- **A Google Cloud project with Vertex AI enabled**, and application-default
  credentials (`gcloud auth application-default login`).
- **A GCS bucket.** Veo always writes the video to Cloud Storage, so you need a
  bucket — set `GENMEDIA_BUCKET` (below) or name one in your prompt.
- **Environment variables** — copy `.env.example` to `.env` and fill in:
  - `GOOGLE_CLOUD_PROJECT` — your project id.
  - `GOOGLE_CLOUD_LOCATION="global"` — `gemini-3.8-flash` is served globally.
  - `GOOGLE_GENAI_USE_VERTEXAI="True"` — use the Vertex backend.
  - `GENMEDIA_BUCKET` — a bucket name (no `gs://`) for the GCS destination.
- **ffmpeg:** not needed for this agent. (The later audio/AV agents need it.)

## Run it

```bash
cp .env.example .env      # then edit .env with your values
uv sync                   # create the venv and install google-adk[gcp,mcp]
source .venv/bin/activate
adk web                   # open the printed URL, pick "director_videographer"
```

Try this sample prompt:

> Direct a 6-second cinematic clip: a lone red umbrella tumbling down a
> rain-slicked Tokyo street at night, neon reflections, with ambient rain sound.
> Save it to my GCS bucket.

The agent will compose a shot, pick an explicit **Veo-3** model (so the ambient
sound works), generate the clip to GCS, and report the `gs://` URI. Then verify it
yourself:

```bash
gcloud storage ls gs://<your-bucket>/veo_outputs/
```

To try image-to-video, give it a starting frame that already lives in GCS:

> Animate gs://my-bucket/stills/umbrella.png — slow push-in, gentle rain. 9:16.

(9:16 forces the agent to a Veo-3.1 model; see the gotcha below.)

## How it works

The entire agent is `director_videographer/agent.py`. Annotated:

```python
MODEL = "gemini-3.8-flash"            # one constant; change it to a model you have

server_env = dict(os.environ)         # forward the environment to the server...
if project_id:
    server_env["PROJECT_ID"] = project_id   # ...adding PROJECT_ID only when set

veo = MCPToolset(                     # one MCP server, wired over stdio
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="mcp-veo-go",                     # the PATH-installed binary
            env=server_env,
        ),
        timeout=300,                                  # video gen + polling is slow
    ),
    tool_filter=["veo_t2v", "veo_i2v"],               # expose exactly two tools
)

root_agent = LlmAgent(                # the agent ADK's `adk web` discovers
    model=MODEL,
    name="director_videographer",
    instruction=INSTRUCTION,          # the shot-direction + model-gating + verify recipe
    tools=[veo],
)
```

It's the identical shape you learned in Photoshoot — `LlmAgent` + one
`MCPToolset`, narrowed with `tool_filter`. All the new weight is in the
`INSTRUCTION`: it tells Gemini to (1) direct a real cinematic prompt, (2) **pick
the correct Veo-3 model** for the shot's audio/aspect/duration needs, (3) choose a
GCS destination, and (4) **verify by listing** — never by reading the returned
link.

## The gotcha this teaches

Video is where two footguns become mandatory. Both are baked into the
instruction, and every rule below is **source-verified against the live
genmedia Go sources** — the veo server files (`veo.go`, `handlers.go`, `utils.go`,
`video_logic.go`) live in
[`../../../mcp-genmedia-go/mcp-veo-go/`](../../../mcp-genmedia-go/mcp-veo-go/), and
the shared model registry (`models.go`) lives in
[`../../../mcp-genmedia-go/mcp-common/`](../../../mcp-genmedia-go/mcp-common/):

**1. Pick an explicit Veo-3 model, or the "minimal" call fails.**
`generate_audio` defaults to **true** (`utils.go:127`), but if you leave `model`
unset the handler falls back to **`veo-2.0-generate-001`** (`utils.go:44-47`) —
and that Veo-2 model has `SupportsGenerateAudio: false`
(`mcp-common/models.go:257-264`), so
the server returns *"generate_audio is set to true, but is not supported by
model"* (`utils.go:132-134`). A bare "make me a video" therefore errors out. The
agent always passes an explicit Veo-3 model (default
`veo-3.1-fast-generate-001`, which matches the tool's own schema default at
`veo.go:115-118`). This is the reasoning showcase: Gemini reads the shot and
chooses a model that clears the gate.

**2. Model-gated aspect ratio & duration.** The server validates these against the
chosen model and errors on a bad combo:
- Aspect ratio (`utils.go:106-124`): Veo-3.1 supports `16:9` **and** `9:16`
  (`mcp-common/models.go:312-330`); Veo-3.0 supports **`16:9` only**
  (`mcp-common/models.go:290-308`). So a vertical `9:16` clip *requires* a Veo-3.1
  model — the agent knows this.
- Duration (`utils.go:81-104`): Veo-3 models support **4, 6, 8** seconds
  (`mcp-common/models.go:290-363`); other values error.
- Count is `num_videos` (`veo.go:119-122`), **not** `sample_count`.

**3. GCS is required — and it's `bucket`, not `gcs_bucket_uri`.** Veo writes to
Cloud Storage; the destination param is spelled **`bucket`** (`veo.go:106-108`).
With no `bucket`, the server falls back to `GENMEDIA_BUCKET`, writing under
`gs://<bucket>/veo_outputs/` (`utils.go:56-62`). With neither, it has nowhere to
write. `output_directory` (`veo.go:109-111`) is only an *additional* local copy.

**4. Verify by LISTING — never trust the `resource_link`.** Veo appends a
`resource_link` per video to its result (`video_logic.go:475-506`) — but a
returned link is **not** proof the object persisted, and many clients can't render
it. What is trustworthy is the text result, *"Videos saved to GCS: gs://..."*
(`video_logic.go:426-427`), emitted only after the API wrote the objects. The
agent relays that `gs://` URI and tells you to confirm with
`gcloud storage ls`. This is exactly the case the Photoshoot README warned about:
persisted-path report is fine, but the real check is **listing the destination.**

> **Naming note.** Veo diverges from the image servers: it uses `bucket` (not
> `gcs_bucket_uri`) for GCS and `num_videos` (not `num_images`/`sample_count`) for
> the count. When you build a multi-server agent later, [`../NAMING.md`](../NAMING.md)
> is the full crosswalk — this agent's spellings are the veo row there.

## See also

- **The `genmedia-video-editor` skill** —
  [`experiments/mcp-genmedia/skills/genmedia-video-editor/SKILL.md`](../../../skills/genmedia-video-editor/SKILL.md).
  Same Veo craft (the five-part cinematic prompt formula, soundstage direction,
  first/last-frame and reference-image workflows, plus FFmpeg compositing over
  `mcp-avtool-go`), expressed as an agent **skill** instead of an ADK agent. Read
  it for deeper prompting and editing technique; this Director agent is the
  ADK-runnable surface of the same idea.

## Next in the series

Head back to the [series overview](../README.md), or jump to
[**Music Producer**](../music-producer/README.md) — the first agent that wires
**more than one** MCP server (lyria + TTS + avtool), where you meet
`tool_name_prefix` and the full naming crosswalk you just got a taste of.
