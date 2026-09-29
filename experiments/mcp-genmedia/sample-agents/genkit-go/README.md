# Genkit **Go** genmedia example series

A tiered, bottom-up tutorial series that drives the [genmedia MCP servers][genmedia]
from **Genkit Go**. Each tier is an independently runnable program and an
independently reviewable PR. The through-line of the whole series is the
**Genkit Developer UI and per-turn tracing** — every tier is meant to be *run*,
then *read* at `http://localhost:4000`.

> **The whole series is here.** All four tiers (0-3) are merged and independently
> runnable from this directory: Tiers 0-2 on stable Genkit Go API, and **Tier 3**
> as a **PREVIEW** capstone on experimental `.../exp` APIs. Start at
> [Tier 0](#run-tier-0-then-read-the-trace) — the minimal "one tool, one generate"
> program (also the Go counterpart to the JavaScript
> [Nano Banana sample](../genkit/); see [Related samples](#related-samples)) — then
> climb: [Tier 1](#run-tier-1-then-read-the-flow-trace) adds a `DefineFlow` chain,
> [Tier 2](#run-tier-2-then-read-the-producer-trace) composes **four** genmedia MCP
> servers (`nanobanana` → `veo_i2v` → `lyria` → `avtool`) into one traced producer
> flow, and [Tier 3 (PREVIEW)](#run-tier-3-preview--agentic-producer-with-delegation--a-human-approval-interrupt)
> hands sequencing to a delegating orchestrator with a human-approval interrupt.
> Every tier proves each artifact by verify-by-listing.

## Contents

- [The series](#the-series)
- [Why lead with the Dev UI](#why-lead-with-the-dev-ui)
- [Prerequisites](#prerequisites)
- [Run Tier 0, then read the trace](#run-tier-0-then-read-the-trace)
- [Run Tier 1, then read the flow trace](#run-tier-1-then-read-the-flow-trace)
- [Run Tier 2, then read the producer trace](#run-tier-2-then-read-the-producer-trace)
- [Run Tier 3 (PREVIEW)](#run-tier-3-preview--agentic-producer-with-delegation--a-human-approval-interrupt)
- [The `resource_link` rule](#the-resource_link-rule)
- [Where the genmedia binary comes from](#where-the-genmedia-binary-comes-from)
- [Version pins](#version-pins)
- [Contributing](#contributing)
- [Related samples](#related-samples)

## The series

| Tier | What it adds | Servers/tools | Status |
|------|--------------|---------------|--------|
| 0 · `tier0-image/` | single tool, single `generate` | `nanobanana` | STABLE |
| 1 · `tier1-video/` | `DefineFlow`, linear chain | `nanobanana` → `veo_i2v` | STABLE |
| 2 · `tier2-producer/` | multi-server producer flow + in-prompt crosswalk | nb → veo → lyria → avtool | STABLE |
| 3 · `tier3-preview/` | **agents middleware** (delegation) + **tool interrupt** (human approval) | all, partitioned across sub-agents | **PREVIEW** — see [Tier 3](#run-tier-3-preview--agentic-producer-with-delegation--a-human-approval-interrupt) |

Tiers land one per PR. They share the foundation Tier 0 established and later
tiers consume without changes:

```
genkit-go/
  go.mod                 module .../sample-agents/genkit-go ; go 1.25.0 ; genkit/go v1.13.1
  bin/genmedia-launch    pinned, SHA-256-verifying download-on-launch script (copy of agent_tools')
  internal/
    genmedia/            the shared fan-out interface
      client.go          NewClient(ctx, g, "<server>") over mcp.NewGenkitMCPClient
      launch.go          StdioFor("<server>") -> mcp.StdioConfig at bin/genmedia-launch
      quirks.go          QuirksPrompt: the genmedia footguns the LLM cannot see
    verify/
      verify.go          Verify / VerifyRecursive(ctx, dest): confirm output by LISTING, not by trusting the tool result
  tier0-image/main.go    Tier 0 — single tool, single generate
  tier1-video/main.go    Tier 1 — DefineFlow: nanobanana -> veo_i2v
  tier2-producer/main.go Tier 2 — DefineFlow: nanobanana -> veo_i2v -> lyria -> avtool (one shared toolset)
  tier3-preview/main.go  Tier 3 — PREVIEW: orchestrator agent delegates to image/video/music/av sub-agents; pauses on a human-approval interrupt before Veo (experimental .../exp APIs)
```

## Why lead with the Dev UI

genmedia calls are slow, expensive, and multi-step. Genkit's Dev UI renders each
turn as a **trace**: the model call, every tool call nested inside it, the
arguments, and the timing. For genmedia that trace *is* the product — it is how
you see what the model asked the tool to do and where the output went. This is
Genkit's signature asset and has no equivalent in the sibling ADK series's
samples, so every tier of this series leads with it.

## Prerequisites

- **Go 1.25+** and the **Genkit CLI** (`npm i -g genkit-cli`) for the Dev UI.
- A **Google Cloud project** with the Vertex AI API enabled, and Application
  Default Credentials (`gcloud auth application-default login`).
- **`gcloud`** on your `PATH` — Tier 0 confirms the generated image by running
  `gcloud storage ls` on the destination (the [verify-by-listing](#the-resource_link-rule)
  rule below).
- The genmedia server binary. By default it is fetched for you on first run by
  `bin/genmedia-launch` (see [Where the genmedia binary comes from](#where-the-genmedia-binary-comes-from)).
  Tier 0 needs `mcp-nanobanana-go`; Tier 1 also uses `mcp-veo-go` (both ship in
  the same pinned tarball, so no extra install). Tiers 2+ that touch `avtool` will
  also require **`ffmpeg`/`ffprobe`** on `PATH`.

Environment variables the tiers read (Tier 1 requires `GENMEDIA_BUCKET` to be `gs://`):

| Variable | Required | Meaning |
|----------|----------|---------|
| `GOOGLE_CLOUD_PROJECT` (or `PROJECT_ID`) | **yes** | Vertex AI + genmedia project |
| `GENMEDIA_BUCKET` | **yes** | `gs://…` URI (or local dir) the image is written to and verified |
| `GOOGLE_CLOUD_LOCATION` (or `GOOGLE_CLOUD_REGION`) | no | Vertex location for the **media** MCP servers (Veo/Imagen/nanobanana); regional, defaults to `us-central1` |
| `GEMINI_LOCATION` | no | Vertex location for the **text orchestrator** model; defaults to `global` (the gemini-3.x flash family is global-only) |
| `GENMEDIA_RELEASE_TAG` | no | genmedia release the launcher downloads; defaults to `v3.18.0` |
| `GENMEDIA_LAUNCH` | no | override the launcher (see below) |
| `GENMEDIA_CACHE` | no | writable cache dir for downloaded binaries |

## Run Tier 0, then read the trace

```bash
cd experiments/mcp-genmedia/sample-agents/genkit-go

export GOOGLE_CLOUD_PROJECT=your-project
export GENMEDIA_BUCKET=gs://your-bucket/tier0

# Launch the program under the Dev UI:
genkit start -- go run ./tier0-image
```

You can pass a custom subject as arguments:
`genkit start -- go run ./tier0-image "a watercolor lighthouse at sunset"`.

Then open **`http://localhost:4000`** and open the most recent trace. You are
reading Tier 0's one new thing:

- **one `generate` span** — the Gemini call, with the `QuirksPrompt` as its
  system message and the nanobanana tool offered to it; and
- **one nested tool-call span** — `nanobanana_nanobanana_image_generation`
  (the MCP tools are namespaced `<client>_<tool>`), showing the arguments the
  model chose (note `gcs_bucket_uri` and `prompt`) and the raw tool result.

This is what a genmedia tool call looks like from the inside. In the terminal
you will also see the program's own `verify:` line confirming the image by
**listing the destination** — which is the point of the next section.

## Run Tier 1, then read the flow trace

Tier 1 wraps two tool calls in one **`genkit.DefineFlow`** named `image-to-clip`.
The flow runs four steps in a fixed Go order — it is *deterministic*, not
LLM-sequenced: the flow decides the order; the model only fills in each tool's
arguments.

```
generate-image  ->  nanobanana_image_generation writes a still to GCS
verify-image    ->  LIST the destination: confirm the still, learn its gs:// URI
generate-video  ->  veo_i2v turns that still into a clip (explicit Veo-3 model)
verify-video    ->  LIST the destination: confirm the clip
```

```bash
cd experiments/mcp-genmedia/sample-agents/genkit-go

export GOOGLE_CLOUD_PROJECT=your-project
export GENMEDIA_BUCKET=gs://your-bucket/tier1   # must be gs:// for Tier 1 (see below)
export GOOGLE_CLOUD_LOCATION=us-central1

# Launch the flow under the Dev UI:
genkit start -- go run ./tier1-video
```

Pass a custom subject as arguments to change what gets drawn (then animated):
`genkit start -- go run ./tier1-video "a paper boat on a rain-soaked street"`.

Then open **`http://localhost:4000`**. Tier 1's one new thing is the **flow span**:

- a single **`image-to-clip` flow span** wrapping the whole run, with the four
  named step spans nested inside it in order;
- inside `generate-image` and `generate-video`, the **`generate` span** and its
  nested tool-call span (`nanobanana_nanobanana_image_generation`, then
  `veo_veo_i2v`) — so you can see the still's `gcs_bucket_uri`, then the clip's
  `image_uri`/`bucket`/`model` arguments the model chose; and
- the **GCS write between the two steps**: `verify-image` is where the still's
  `gs://` URI is confirmed by listing and carried into `veo_i2v` as `image_uri`.

**The flow is the deterministic contract; the trace is the receipt.** The order
you read in the trace is the order the Go code fixed, every run.

### Two veo footguns Tier 1 bakes in

- **Explicit Veo-3 model.** `veo_i2v` defaults to `veo-2.0-generate-001` when no
  `model` is passed, and Veo-2 **rejects** `generate_audio=true` (the tool's own
  default) — so a "minimal" call fails. `QuirksPrompt` tells the model to pass an
  explicit Veo-3 model; Tier 1 uses `veo-3.1-fast-generate-001`
  (`veoModel` in `tier1-video/main.go`).
- **`resource_link`, carried across a step.** The still's real location is learned
  by **listing** (`verify-image`), never from nanobanana's `resource_link`, and
  that listed `gs://` URI is what feeds `veo_i2v`. veo then returns its own
  `resource_link` for the clip, which `verify-video` again confirms by listing.

> **GCS is required for Tier 1.** `veo_i2v` only accepts a `gs://` input image
> (the server rejects a non-GCS `image_uri`), so `GENMEDIA_BUCKET` must be a
> `gs://` URI — a local directory works for Tier 0 but cannot carry the still into
> the video step here. Tier 1 fails fast with a clear message if it is not `gs://`.

## Run Tier 2, then read the producer trace

Tier 2 is the **capstone**: one **`genkit.DefineFlow`** named `produce-scored-clip`
that composes **four** genmedia servers into a production line. As in Tier 1 the
order is fixed in Go (deterministic, not LLM-sequenced), but now **all four
servers' tools are offered to every step at once** — the model, not the code,
picks which tool to call from a single shared toolset:

```
generate-image  ->  nanobanana writes a still to GCS
verify-image    ->  LIST: confirm the still, carry its gs:// URI forward
generate-video  ->  veo_i2v turns that still into a clip (explicit Veo-3 model)
verify-video    ->  LIST recursively: carry the clip's .mp4 leaf forward
generate-music  ->  lyria composes a score to GCS
verify-music    ->  LIST recursively: carry the score's audio leaf forward
generate-final  ->  avtool muxes the clip + score into one scored video
verify-final    ->  LIST: confirm the finished artifact
```

```bash
cd experiments/mcp-genmedia/sample-agents/genkit-go

export GOOGLE_CLOUD_PROJECT=your-project
export GENMEDIA_BUCKET=gs://your-bare-bucket   # BARE bucket, no path (see below)
export GOOGLE_CLOUD_LOCATION=us-central1

# Launch the flow under the Dev UI:
genkit start -- go run ./tier2-producer
```

Pass a custom subject as arguments to change what gets drawn, animated, and scored:
`genkit start -- go run ./tier2-producer "a paper boat on a rain-soaked street"`.

Then open **`http://localhost:4000`**. Tier 2's one new thing is the **multi-server
producer trace**: a single `produce-scored-clip` flow span wrapping **eight** named
step spans, with **four** `generate` spans — and each one shows *which tool the
model chose out of all sixteen* offered from the four servers. That is the tier's
whole lesson made visible.

### The in-prompt crosswalk (Tier 2's one new idea)

Four servers put sixteen tools into one toolset, several with lookalike names
(`veo` alone contributes six variants). Tier 2 does **not** rename or prefix them.
Instead the **system prompt** — `QuirksPrompt` plus a `producerCrosswalk` fragment
in `tier2-producer/main.go` — tells the model which namespaced tool does which job:

```
IMAGE (text -> still): nanobanana_nanobanana_image_generation
VIDEO (still -> clip): veo_veo_i2v         (not veo_veo_t2v, veo_veo_extend_video, …)
MUSIC (text -> score): lyria_lyria_generate_music
MUX  (clip+score -> scored video): avtool_ffmpeg_combine_audio_and_video
```

The MCP client's `<server>_<tool>` namespacing keeps the names *unique*; the prompt
tells the model which name to *pick*. This is the deliberate contrast with the ADK
genmedia sibling, which resolves the same collision **structurally** with
`tool_name_prefix` on each toolset. Same problem, two philosophies: **ADK renames
the tools; Tier 2 instructs the model.** The producer also guards startup —
`mcp.NewMCPHost` logs-and-continues when a server fails to connect, so Tier 2
asserts every required tool is present before the flow runs.

> **A BARE bucket is required for Tier 2.** `nanobanana` and `veo` accept a
> bucket **and** a path prefix (Tier 2 writes them under `…/<runID>/image` and
> `…/<runID>/video`), but `lyria` and `avtool` take a bucket **name only** — they
> strip `gs://` and upload the object at the bucket root using just the filename, so
> a prefixed value becomes an invalid bucket name and the upload fails. Set
> `GENMEDIA_BUCKET` to a bare `gs://bucket` (no path); the producer adds all per-run
> structure itself and fails fast with a clear message if a path is present.
> `avtool` also needs **`ffmpeg`/`ffprobe`** on your `PATH`.

> **Teaching caveat — prompt-injection surface.** As in Tiers 0-1, the positional
> CLI argument is fed as free text into the model prompt, which then calls tools —
> a (benign here, local-dev) prompt-injection surface, called out in
> `tier2-producer/main.go`. A production caller should treat any untrusted input as
> adversarial: constrain it and/or validate the tool arguments the model chooses,
> rather than trusting free text.

## Run Tier 3 (PREVIEW) — agentic producer with delegation + a human-approval interrupt

> ### ⚠️ PREVIEW — experimental APIs, not stable
> Tier 3 is a **PREVIEW capstone**. It uses the **experimental Genkit `.../exp`
> packages** (`genkit/exp`, `ai/exp`, `ai/exp/localstore`, `ai/exp/tool`,
> `plugins/middleware/exp`) behind **`genkit.WithExperimental()`**. That API is
> **not stable**, is **pinned to `genkit/go v1.13.1`**, and **may break on
> upgrade**. Tier 3 is **additive and self-contained**: nothing in Tiers 0–2
> depends on it, and the dependency floor is unchanged (`genkit/go v1.13.1` +
> `mcp-go v0.33.0`, no `replace` directives). Treat it as a flourish that shows
> where Genkit Go is going — not as the series' foundation.

Where Tier 2's **code** fixes the order of the four servers (still → clip → score
→ mux) and the **model** only picks each tool's arguments, Tier 3 hands the
sequencing to an **orchestrator agent**. It **delegates** to four specialist
sub-agents through the experimental **Agents middleware**, and it **pauses for a
human** — a **tool interrupt** — before the expensive Veo render.

```
producer (agent, Agents middleware)
  ├─ delegate_to_image-agent   -> image-agent : generate_image (nanobanana)
  ├─ approve_video_render       -> INTERRUPT: pause for human approve/reject
  ├─ delegate_to_video-agent   -> video-agent : veo_render (GATED, Veo 3)
  ├─ delegate_to_music-agent   -> music-agent : compose_music (lyria)
  └─ delegate_to_av-agent      -> av-agent    : combine_av (avtool mux)
```

Run it under the Dev UI to watch the delegation spans and the interrupt
pause/resume:

```bash
export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_CLOUD_LOCATION=us-central1        # media models (Veo/Imagen) are regional; NOT "global"
# The text orchestrator ignores GOOGLE_CLOUD_LOCATION and runs at GEMINI_LOCATION
# (default "global") because the gemini-3.x flash family is global-only.
export GENMEDIA_BUCKET=gs://your-bare-bucket     # BARE bucket, no path (lyria/avtool write at the root)

genkit start -- go run ./tier3-preview           # then open http://localhost:4000
```

In the Dev UI trace you see the orchestrator turn with a `delegate_to_<name>`
span per sub-agent nested inside it, each sub-agent's own tool call nested under
that, and — between the image and video delegations — the `approve_video_render`
tool **pausing** the run. Approve it in the UI and the trace resumes into the
video delegation; reject it and the run stops before Veo ever executes.

**No Dev UI? Drive it headless.** The program also drives the approve/reject
resume itself (the stand-in for a human), so it runs with no CLI installed:

```bash
go run ./tier3-preview            # approve path: image -> (approve) -> video -> music -> mux
go run ./tier3-preview -reject    # reject path: image -> (reject) -> STOP, no video
```

### The two things Tier 3 shows (and one honest adaptation)

- **Delegation (Agents middleware).** The orchestrator holds only the sub-agents
  (via `middlewarex.Agents{Agents: […Ref()], ArtifactStrategy: session}`) and an
  approval tool. The middleware injects one `delegate_to_<name>` tool per
  sub-agent and lists them in the orchestrator's system prompt; each specialist
  owns exactly one genmedia step.
- **Human-in-the-loop (tool interrupt).** `approve_video_render` is an
  interruptible tool: it **pauses** with a typed payload (the still URI + motion
  prompt), and the client resumes it with an approve/reject decision.
- **The honest adaptation.** In `v1.13.1`, a **sub-agent cannot itself hold an
  interactive interrupt** — the Agents middleware turns a sub-agent interrupt
  into a plain tool response ("Interactive sub-agent interrupts are not currently
  supported"). So the interrupt lives on the **orchestrator**, and the Veo render
  is gated on a process flag the approval flips: the video specialist's
  `veo_render` **refuses** until approval has opened the gate. This guarantees —
  provably, by listing — that **Veo only ever runs after approval**. The
  top-of-file comment in `tier3-preview/main.go` records the full list of
  experimental-API corrections found against the real `v1.13.1` source.

Tier 3 keeps the series' discipline intact: it reuses `internal/genmedia` and
`internal/verify`, carries the same [footguns](#the-resource_link-rule) (bare
bucket; explicit Veo-3 model; Lyria's forced extension + global region), and
**proves every artifact by verify-by-listing** — each specialist tool confirms
its own output, and the program independently lists every destination at the end.

> **The same journey elsewhere.** Delegation + human approval is a shape you can
> also build in the sibling **ADK genmedia series** ([`../adk/`](../adk/)) and,
> stably, atop **Tier 2** ([`tier2-producer/`](tier2-producer/)) in this same
> Genkit Go series — see [Related samples](#related-samples). Tier 3 is the
> *preview* of doing it with Genkit's first-class agent primitives.

## The `resource_link` rule

The genmedia GCS-writing tools (nanobanana/gemini image, veo, lyria, omni)
return a **`resource_link`** content item pointing at a `gs://` URI — **not** the
generated bytes. A `resource_link` in the trace is *not* proof the file exists,
and it is not renderable. So Tier 0 never claims success from the tool result:
`internal/verify` runs `gcloud storage ls` on the destination and reports what it
actually finds. Every later tier verifies every GCS-writing step the same way,
through the same shared helper.

> **Per-run subprefix.** Because verify-by-listing checks a *prefix*, a re-run
> against a `GENMEDIA_BUCKET` that already holds a prior run's image would see
> that old object and report success even if the current run produced nothing.
> Tier 0 avoids the false positive by writing each run to a unique per-run
> subprefix (a timestamp + short random id under `GENMEDIA_BUCKET`) and verifying
> that subprefix, so each run confirms its own output.

The other invisible-to-the-LLM constraints (the Veo-3 model requirement, Lyria's
dropped parameters, the 3-way parameter-naming crosswalk, …) live in
`internal/genmedia/quirks.go` as `QuirksPrompt`, injected as the system prompt of
every tier. The tool schema does not describe them, so the prompt must.

## Where the genmedia binary comes from

Tier 0 launches the nanobanana server through **`bin/genmedia-launch`**, a copy of
the launcher the [`agent_tools` genmedia plugin][launcher] ships. On first run it
detects your platform, downloads the pinned GoReleaser tarball, verifies its
SHA-256 against **both** a value pinned in the script **and** the release's own
`checksums.txt`, caches the binaries, and execs the requested server over stdio.
Subsequent runs use the cache. linux/darwin only.

**Already have the binaries?** Put `mcp-nanobanana-go` on your `PATH` and set
`GENMEDIA_LAUNCH=mcp-nanobanana-go` (or a thin passthrough) to bypass the
download bridge — `StdioConfig.Command` resolves it directly.

> `bin/genmedia-launch` is a **copy** kept in sync with its canonical source at
> `experiments/agent_tools/plugins/genmedia/bin/genmedia-launch`; its header
> records the source commit and the pinned SHA-256s.

## Version pins

| Thing | Pin | Where |
|-------|-----|-------|
| Genkit Go | `github.com/firebase/genkit/go v1.13.1` | `go.mod` |
| Go | `go 1.25.0` | `go.mod` |
| genmedia release | `v3.18.0` | `internal/genmedia` `DefaultReleaseTag` + `bin/genmedia-launch` `PINNED_TAG` |
| Orchestrating model | `vertexai/gemini-3.5-flash` (runs at `GEMINI_LOCATION`, default `global`) | `tier{0,1,2}-*/main.go` `modelName`; `tier3-preview/main.go` `defaultModel` |
| Veo model (Tiers 1-3) | `veo-3.1-fast-generate-001` | `tier{1,2}-*/main.go` + `tier3-preview/main.go` `veoModel` |
| Lyria model (Tiers 2-3) | `lyria-3-clip-preview` | `tier2-producer/main.go` + `tier3-preview/main.go` `lyriaModel` |
| **Tier 3 (PREVIEW) experimental APIs** | `genkit/exp`, `ai/exp`, `ai/exp/localstore`, `ai/exp/tool`, `plugins/middleware/exp` behind `WithExperimental()` — **pinned to `genkit/go v1.13.1`, may break on upgrade** | `tier3-preview/main.go` |

## Contributing

This sample lives in the `genmedia-creative-studio` monorepo. Contributions are welcome; please
read the repository's [`CONTRIBUTING.md`](../../../../CONTRIBUTING.md) first — it requires a signed
Google [Contributor License Agreement](https://cla.developers.google.com/) and routes all changes
through GitHub pull-request review. Keep a change scoped to one tier's `main.go` (or the shared
`internal/` packages) and update the matching section of this README in the same PR.

## Related samples

- **JavaScript Nano Banana** — [`../genkit/`](../genkit/): the JS peer of this
  Go Tier 0.
- **ADK genmedia series** — [`../adk/`](../adk/): the same journey in Python/ADK;
  a parallel sibling program (declarative agent graphs vs. Genkit's Dev-UI /
  traced deployable flows).
- **`agent_tools` genmedia plugin** — [`../../../agent_tools/`](../../../agent_tools/):
  the packaged plugin/skills distribution surface and the canonical home of the
  `genmedia-launch` launcher this series reuses.

[genmedia]: ../../mcp-genmedia-go/
[launcher]: ../../../agent_tools/plugins/genmedia/bin/genmedia-launch
