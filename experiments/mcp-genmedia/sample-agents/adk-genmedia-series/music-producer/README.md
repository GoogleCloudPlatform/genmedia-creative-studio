# Music Producer — three servers, one agent

> This README follows the series' eight-section template (see
> [Photoshoot](../photoshoot/README.md)): **What you'll build · What you'll
> learn · Prerequisites · Run it · How it works · The gotcha this teaches ·
> See also · Next in the series.**

## What you'll build

A music-producer agent. You give it a mood/genre for a music bed and a short
voiceover (VO) script — *"a warm lo-fi study beat, and a narrator says 'welcome
back'"* — and it (1) generates a music bed with **lyria**, (2) generates the VO
with **gemini TTS**, (3) **mixes** the two into one file with **avtool**, and
tells you exactly where all three files are. It is the first agent in the series
that wires **more than one MCP server**.

## What you'll learn

**The one new ADK concept: wiring multiple `MCPToolset`s in a single `LlmAgent`
and giving each a distinct `tool_name_prefix`** (`music`, `tts`, `av`) so the
servers' tool names never collide and the model's tool choices stay legible
(exposed as `music_*`, `tts_*`, `av_*`).

With more than one server comes the second lesson: **the genmedia servers spell
"the same" parameter differently.** The model can't see those differences from
`tools/list`, so this agent's instruction **bakes the exact names for its three
tools** and cites the shared crosswalk, [`../NAMING.md`](../NAMING.md). Told the
wrong parameter name, a server silently ignores the argument and your artifact
lands nowhere you looked — so this is a real correctness issue, not style.

## Prerequisites

- **Python ≥ 3.13** and [`uv`](https://docs.astral.sh/uv/).
- **The genmedia MCP suite ≥ v3.18.1, installed on your `PATH`.** This is a HARD
  requirement here: the Lyria fixes shipped in v3.18.1 (`#1768` parse, `#1777`
  MP3/C2PA container) are what make lyria return usable audio that **avtool can
  mux**. On older builds this agent's mix step has nothing to work with. This
  agent calls three binaries — `mcp-lyria-go`, `mcp-gemini-go`, `mcp-avtool-go`.
  Install them from the suite's
  [`install.sh`](../../../mcp-genmedia-go/install.sh); confirm they're reachable:
  ```bash
  which mcp-lyria-go mcp-gemini-go mcp-avtool-go
  ```
- **`ffmpeg` AND `ffprobe` on your `PATH`.** avtool is a wrapper over ffmpeg; it
  shells out to both binaries, so the mix/convert step fails without them:
  ```bash
  which ffmpeg ffprobe
  ```
- **A Google Cloud project with Vertex AI enabled**, and application-default
  credentials (`gcloud auth application-default login`).
- **Environment variables** — copy `.env.example` to `.env` and fill in:
  - `GOOGLE_CLOUD_PROJECT` — your project id.
  - `GOOGLE_CLOUD_LOCATION="global"` — `gemini-3.8-flash` is served globally, and
    the default Lyria model (Interactions API) is **global-only**, so this must
    be `global`.
  - `GOOGLE_GENAI_USE_VERTEXAI="True"` — use the Vertex backend.
  - `GENMEDIA_BUCKET` — a bucket name (no `gs://`) for GCS-mode output. Optional
    for the all-local flow this agent defaults to.

## Run it

```bash
cp .env.example .env      # then edit .env with your values
uv sync                   # create the venv and install google-adk[gcp,mcp]
source .venv/bin/activate
adk web                   # open the printed URL, pick the "music_producer" agent
```

Try this sample prompt:

> Make a warm, mellow lo-fi hip-hop study beat with soft piano and vinyl crackle,
> about 30 seconds, and a calm female narrator saying "Welcome back. Let's get
> focused." Mix them into one MP3 and save everything locally.

The agent will generate `./output/`-saved music and VO files, mix them into a
single `.mp3`, and report the three concrete paths (and how to list them).

## How it works

The entire agent is `music_producer/agent.py`. Three `MCPToolset`s, one
`LlmAgent`:

```python
MODEL = "gemini-3.8-flash"            # one constant; GLOBAL region

lyria = MCPToolset(                   # server 1: music
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(command="mcp-lyria-go", env=server_env),
        timeout=180,
    ),
    tool_filter=["lyria_generate_music"],   # tool_filter matches the BASE name
    tool_name_prefix="music",         # -> music_lyria_generate_music
)

tts = MCPToolset(                     # server 2: voiceover
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(command="mcp-gemini-go", env=server_env),
        timeout=120,
    ),
    tool_filter=["gemini_audio_tts"],
    tool_name_prefix="tts",           # -> tts_gemini_audio_tts
)

avtool = MCPToolset(                  # server 3: mix / convert
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(command="mcp-avtool-go", env=server_env),
        timeout=180,
    ),
    tool_filter=["ffmpeg_layer_audio_files",     # base names, applied
                 "ffmpeg_convert_audio_wav_to_mp3",  # before prefixing
                 "ffmpeg_get_media_info"],
    tool_name_prefix="av",            # -> av_ffmpeg_layer_audio_files, ...
)

root_agent = LlmAgent(model=MODEL, name="music_producer",
                      instruction=INSTRUCTION, tools=[lyria, tts, avtool])
```

`tool_name_prefix` is the teaching point: without it, three servers could each
expose a tool the model refers to ambiguously; with it, every tool the model can
call is unambiguously namespaced (`music_*`, `tts_*`, `av_*`). Two details that
make this a *correct* prefixing example, not just a working one:

- **ADK inserts the separator itself** — it exposes each tool as
  `f"{prefix}_{tool.name}"` ([`base_toolset.py:143` @ `v2.8.0`](https://github.com/google/adk-python/blob/v2.8.0/src/google/adk/tools/base_toolset.py#L143)).
  So the prefix VALUES are **bare role tokens with no trailing underscore**
  (`"music"`, not `"music_"`) — otherwise you'd get a doubled `music__…`. And you
  name them by **role**, not by echoing the server (`"music"`, not `"lyria"`),
  so the result reads `music_lyria_generate_music`, not a stuttering
  `lyria_lyria_generate_music`.
- **`tool_filter` matches the BASE tool name** (it is applied *before* prefixing),
  so the filter values stay `lyria_generate_music` / `gemini_audio_tts` /
  `ffmpeg_*` even though the exposed names gain the prefix.

The `INSTRUCTION` then does the sequencing — generate music → generate VO → mix —
referring to tools by their **exposed** names (`music_lyria_generate_music`,
`tts_gemini_audio_tts`, `av_ffmpeg_*`) and baking the **exact, per-tool parameter
names** (below) because the model can't infer them from the tool schema.

### Why gemini TTS (and not chirp3)

The series lets a multi-server agent pick **either** `chirp_tts` (chirp3) **or**
`gemini_audio_tts` (gemini). This agent uses **`gemini_audio_tts`** because, as
the series' reference example for the naming crosswalk, it demonstrates the most
divergences in one tool: the `model_name` spelling (unique to gemini TTS among
all servers — NAMING.md §1) **and** the `text`-is-content / `prompt`-is-style
overload (NAMING.md §5), plus a concrete, source-verified **800-character cap**
to teach as a hard constraint. It can also emit MP3, matching Lyria's MP3 output
for a clean same-format mix. (chirp3's own quirk — WAV-only, no GCS param — is
still noted in NAMING.md and in the validation recipe's alternate path.)

### The naming crosswalk for this agent's three tools

Every name below is verified against the genmedia Go sources (file:line in
`agent.py`); it is a concrete instance of [`../NAMING.md`](../NAMING.md):

| Concept | `music_lyria_generate_music` | `tts_gemini_audio_tts` | `av_*` (e.g. layer/convert) |
|---|---|---|---|
| content | `prompt` | `text` (+ `prompt` = **style**) | — (transform-only) |
| model id | `model_id` | `model_name` | — |
| local dir | `local_path` | `output_directory` | `output_local_dir` |
| GCS bucket | `output_gcs_bucket` | *(none — local only)* | `output_gcs_bucket` |
| output name | `output_filename` | `output_filename` | `output_filename` (ext = container) |

## The gotcha this teaches

**Multi-server = colliding names + diverging params; `tool_name_prefix` fixes
the first, baked instructions fix the second.** Concretely, this agent bakes:

1. **Lyria dropped params + global-only.** On the default model
   (`lyria-3-clip-preview`, Vertex Interactions API) `negative_prompt`, `seed`,
   and `sample_count` are **silently ignored** — only `prompt` reaches the model
   and only the first sample returns. The instruction never promises them, and
   the model is region-**global-only** (hence `GOOGLE_CLOUD_LOCATION=global`).
2. **The TTS `text`/`prompt` overload + 800-char cap.** `text` is the words to
   speak; `prompt` is *style*, not content; `text` is capped at 800 chars.
3. **avtool is transform-only.** It cannot generate — it needs an INPUT file, so
   it must run *after* lyria and TTS have saved real files; it needs `ffmpeg` and
   `ffprobe` on PATH; and **the output filename extension selects the container**
   (`mix.mp3` → MP3, `mix.wav` → WAV).
4. **Verify by existence — never trust a resource link.** A successful tool
   return isn't proof of a file. The agent reports each concrete saved path/URI
   and how to confirm it (`ls -l …` locally, `gcloud storage ls …` for GCS), and
   treats an unnamed result as *not verified* rather than fabricating a path.

## See also

- **The `genmedia-audio-engineer` skill** —
  [`experiments/mcp-genmedia/skills/genmedia-audio-engineer/SKILL.md`](../../../skills/genmedia-audio-engineer/SKILL.md).
  The same music+VO+mux craft (lyria, TTS, avtool) expressed as an agent
  **skill** rather than an ADK agent — read it for deeper audio-production
  technique.
- **The `genmedia-producer` skill** —
  [`experiments/mcp-genmedia/skills/genmedia-producer/SKILL.md`](../../../skills/genmedia-producer/SKILL.md).
  The producer/showrunner voice that sequences multiple genmedia tools into a
  finished piece — the multi-tool orchestration this agent does in miniature.
- **[`../NAMING.md`](../NAMING.md)** — the shared parameter crosswalk this agent
  cites; required reading for any multi-server agent.

## Next in the series

Head back to the [series overview](../README.md), or jump to
[**Scriptwriter / Storyboarder**](../scriptwriter-storyboarder/README.md) — your
first true *pipeline*, where a `SequentialAgent` passes state between agents with
`output_key` instead of one agent driving every tool itself.
