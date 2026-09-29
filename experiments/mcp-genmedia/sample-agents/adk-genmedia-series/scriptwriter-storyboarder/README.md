# Scriptwriter / Storyboarder — your first pipeline

## What you'll build

A two-stage pipeline. You give it a one-line brief — *"a lonely lighthouse
keeper's last night on the job"* — and a **scriptwriter** agent turns it into a
numbered shot list, then a **storyboarder** agent reads that shot list and
generates one storyboard still per shot, verifies each file, and hands you a
shot→image map. It's the first agent in the series that is more than a single
`LlmAgent`: it's two agents wired into an ordered pipeline that pass work between
each other.

## What you'll learn

**The one new ADK concept: `SequentialAgent` + `output_key` state passing.** One
agent writes a value into session state under an `output_key`; the next agent
reads it back by name in its instruction with the `{key}` template. That is ADK's
native, no-glue way to hand a result from one stage of a pipeline to the next:

- the `scriptwriter` sets `output_key="shot_list"`, so ADK stores its final text
  in `state["shot_list"]`;
- the `storyboarder`'s instruction contains `{shot_list}`, so ADK substitutes
  that stored text into the prompt before the storyboarder runs;
- a `SequentialAgent` runs the two in order, so the write always happens before
  the read.

You'll also carry forward the crawl-tier habits: nanobanana output modes and
**verify-by-existence** — now applied once per shot.

## Prerequisites

- **Python ≥ 3.13** and [`uv`](https://docs.astral.sh/uv/).
- **The genmedia MCP suite ≥ v3.18.1, installed on your `PATH`.** The
  storyboarder calls `mcp-nanobanana-go`. Install it from the suite's
  [`install.sh`](../../../mcp-genmedia-go/install.sh); confirm it's reachable:
  ```bash
  which mcp-nanobanana-go
  ```
- **A Google Cloud project with Vertex AI enabled**, and application-default
  credentials (`gcloud auth application-default login`).
- **Environment variables** — copy `.env.example` to `.env` and fill in:
  - `GOOGLE_CLOUD_PROJECT` — your project id.
  - `GOOGLE_CLOUD_LOCATION="global"` — `gemini-3.8-flash` is served globally.
  - `GOOGLE_GENAI_USE_VERTEXAI="True"` — use the Vertex backend.
  - `GENMEDIA_BUCKET` — a bucket name (no `gs://`) for GCS-mode output. Optional
    if you only use local output.
- **ffmpeg:** not needed here. (Later audio/video agents need it.)

## Run it

```bash
cp .env.example .env      # then edit .env with your values
uv sync                   # create the venv and install google-adk[gcp,mcp]
source .venv/bin/activate
adk web                   # open the printed URL, pick "scriptwriter_storyboarder"
```

Try this sample prompt:

> A lonely lighthouse keeper's last night on the job. Save the stills locally.

The scriptwriter will write a numbered shot list (≤ 6 shots); then the
storyboarder will generate one still per shot into `./output/` and report a
shot→image map. To try GCS instead:

> Same brief, but 16:9 and save the stills to my GCS bucket.

## How it works

The whole pipeline is `scriptwriter_storyboarder/agent.py`. Annotated:

```python
MODEL = "gemini-3.8-flash"            # one constant; change it to a model you have

scriptwriter = LlmAgent(              # stage 1: text only, no tools
    model=MODEL,
    name="scriptwriter",
    instruction=SCRIPTWRITER_INSTRUCTION,   # "turn the brief into a numbered shot list, <= 6"
    output_key="shot_list",          # <-- ADK writes its final text to state["shot_list"]
)

storyboarder = LlmAgent(             # stage 2: wires the nanobanana image tool
    model=MODEL,
    name="storyboarder",
    instruction=STORYBOARDER_INSTRUCTION,   # contains {shot_list}  <-- ADK reads state here
    tools=[nanobanana],
)

root_agent = SequentialAgent(        # run scriptwriter, THEN storyboarder
    name="scriptwriter_storyboarder",
    sub_agents=[scriptwriter, storyboarder],
)
```

The hand-off is the lesson, and it's two lines:

1. **The write.** `output_key="shot_list"` tells ADK to copy the scriptwriter's
   final text response into session state under `shot_list`. (In ADK 2.8.0 this
   happens in `LlmAgent`'s `output_key` handling —
   `google/adk/agents/llm_agent.py`, the field at line 419 and the write
   `event.actions.state_delta[self.output_key] = result` at line 1045.)
2. **The read.** The storyboarder's instruction string contains the literal
   `{shot_list}`. Before each LLM call, ADK runs *instruction templating* over
   the instruction and substitutes `{key}` with `state[key]`
   (`google/adk/utils/instructions_utils.py` → `inject_session_state` →
   `_render_with_regex` / `_replace_match`). So the storyboarder literally sees
   the scriptwriter's shot list inside its prompt.

`SequentialAgent` guarantees the order — scriptwriter first (write), storyboarder
second (read) — so the value is always in state by the time it's needed.

## The gotcha this teaches

**The state-passing contract: the reader must use the exact key the writer
wrote.** `output_key="shot_list"` and `{shot_list}` are two halves of one
contract — spell the key the same in both places or the hand-off silently breaks.
Two things worth knowing about the `{...}` template:

1. **A plain `{shot_list}` is required, not optional.** If the key is missing
   from state, ADK raises `KeyError` rather than passing an empty prompt. In a
   `SequentialAgent` the scriptwriter always runs first, so the key is always
   present — and if it somehow isn't, you *want* the loud failure, because it
   means the pipeline's hand-off is broken. (ADK also supports an optional form,
   `{shot_list?}`, which substitutes an empty string when the key is absent; we
   deliberately do **not** use it here — an empty shot list is not a valid input
   to the storyboarder.)
2. **Verify by existence, still — now per shot.** Exactly as in Photoshoot, a
   returned tool call is not proof of a file. The storyboarder reports the
   concrete saved path (local) or `gs://` URI (GCS) for *each* shot, and for GCS
   you confirm with `gcloud storage ls`. The number of rows in the shot→image map
   must equal the number of shots — that 1:1 correspondence is the visible proof
   that the storyboarder actually read the scriptwriter's `{shot_list}`.

## See also

- **The `story-generator` skill** —
  [`experiments/mcp-genmedia/skills/story-generator/SKILL.md`](../../../skills/story-generator/SKILL.md).
  Same "writers room → per-scene generation" shape (a script stage that feeds a
  per-scene media stage), expressed as an agent **skill** instead of an ADK
  pipeline. This Scriptwriter / Storyboarder agent ports that *shape* into ADK's
  `SequentialAgent` + `output_key` form; read the skill for the deeper
  storytelling craft, and use this agent as the ADK-runnable surface of the same
  idea. (Cross-linked, not forked.)

## Next in the series

Head back to the [series overview](../README.md), or continue to
[**Ad creative-director's assistant**](../ad-creative-director/README.md) — where
this pipeline grows into a real multi-agent app: a `SequentialAgent` wrapping a
`ParallelAgent` fan-out that composes the crawl personas (Photoshoot / Director /
Music Producer) as tools to turn a brand brief into an assembled ad.
