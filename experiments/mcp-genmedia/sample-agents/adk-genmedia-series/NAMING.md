# NAMING.md — the genmedia parameter crosswalk

The genmedia MCP servers were written at different times, so they spell "the
same" parameter differently. A single-server agent (like
[Photoshoot](./photoshoot/)) never notices. But the moment an agent wires **more
than one** server, the divergence bites: the model told the wrong parameter name
just gets its argument silently ignored, and the artifact lands nowhere (or
nowhere you looked).

This is the shared cheatsheet every multi-server agent in the series cites in its
instruction. Two rules make the friction manageable:

1. **Use ADK's `tool_name_prefix`** on each `MCPToolset` in a multi-server agent
   (e.g. `lyria_`, `tts_`, `av_`) so tool names never collide and the model's
   tool choices stay legible.
2. **Bake the exact parameter names for *that agent's* tools into its
   instruction.** The model cannot see these constraints from `tools/list`; if
   you don't state them, it will guess — and guess the majority spelling.

The names below are verified against the live Go server sources (see provenance
footnote); when in doubt, the server's own `main.go` / handler is ground truth.

## The five divergences

### 1. Model id — `model` vs `model_name` vs `model_id`

| Spelling | Servers / tools |
|----------|-----------------|
| `model` | nanobanana, gemini **image**, veo, omni, imagen (the majority) |
| `model_name` | gemini **TTS** (`gemini_audio_tts`) |
| `model_id` | lyria (`lyria_generate_music`) |

### 2. GCS output destination — `bucket` vs `gcs_bucket_uri` vs `output_gcs_bucket`

| Spelling | Servers / tools | Format note |
|----------|-----------------|-------------|
| `gcs_bucket_uri` | nanobanana, gemini image, omni, imagen | URI **prefix** of the form `gs://<your-bucket>/<prefix>/` (never a pasteable placeholder — a made-up URI will 403) |
| `bucket` | veo | bucket-style |
| `output_gcs_bucket` | lyria, avtool | bucket name |
| *(none)* | chirp3 | chirp3 has **no** GCS output — local WAV only |

Most image/video servers also fall back to the `GENMEDIA_BUCKET` env var when no
explicit GCS parameter is passed.

### 3. Local output directory — `output_directory` vs `local_path` vs `output_local_dir`

| Spelling | Servers / tools |
|----------|-----------------|
| `output_directory` | nanobanana, gemini image, veo, chirp3, omni, imagen (the majority) |
| `local_path` | lyria (`lyria_generate_music`) |
| `output_local_dir` | avtool |

### 4. Output count — `num_images` vs `num_videos` vs `sample_count`

| Spelling | Servers / tools |
|----------|-----------------|
| `num_images` | imagen |
| `num_videos` | veo |
| `sample_count` | lyria, omni |

> **Lyria caveat:** on the default Lyria-3 model `sample_count` (along with
> `negative_prompt` and `seed`) is **silently ignored** — only the first sample
> is returned. Don't promise these work in a Lyria agent's instruction.

### 5. Prompt overload — `prompt` (content) vs `text` (content) vs `prompt` (style)

- **Content** is `prompt` everywhere **except the TTS tools**, which use `text`
  for the words to speak:
  - chirp3 `chirp_tts` → `text` (content).
  - gemini `gemini_audio_tts` → `text` (content) **and** `prompt` (voice/**style**,
    not content). It also caps `text` at ~800 chars.
- Input media URIs diverge too: image/video servers take `images` / `videos`
  arrays (nanobanana, gemini image), while avtool takes `input_<kind>_uri(s)`.

## Quick reference by server

| Server | model param | GCS param | local param | content param |
|--------|-------------|-----------|-------------|---------------|
| nanobanana | `model` | `gcs_bucket_uri` | `output_directory` | `prompt` |
| gemini (image) | `model` | `gcs_bucket_uri` | `output_directory` | `prompt` |
| gemini (TTS) | `model_name` | — | `output_directory` | `text` (+ `prompt`=style) |
| veo | `model` | `bucket` | `output_directory` | `prompt` |
| omni | `model` | `gcs_bucket_uri` | `output_directory` | `prompt` |
| imagen | `model` | `gcs_bucket_uri` | `output_directory` | `prompt` |
| lyria | `model_id` | `output_gcs_bucket` | `local_path` | `prompt` |
| chirp3 | — | *(none — local WAV)* | `output_directory` | `text` |
| avtool | — | `output_gcs_bucket` | `output_local_dir` | *(transform-only)* |

## Why there's no shared translation module

A general cross-server parameter-reconciliation layer is a separate, larger
initiative and is deliberately **out of scope** for this series. Native
`tool_name_prefix` + this one doc + baked instruction prose gets the benefit
(examples that never emit an invalid call) without making each example depend on
a shared library — keeping every agent copy-paste self-contained. If a helper
ever proves worth it, it can be added without changing the agents.

---

<sub><b>Provenance.</b> This crosswalk was verified parameter-by-parameter against
the live genmedia Go sources at repo tip:
`mcp-nanobanana-go/main.go`, `mcp-gemini-go/main.go`, `mcp-veo-go/veo.go`,
`mcp-lyria-go/lyria.go`, `mcp-chirp3-go/chirp3.go`, `mcp-avtool-go/mcp_handlers.go`,
`mcp-omni-go/main.go`, and `mcp-imagen-go/imagen.go`. Live-source spellings win
over any doc if they ever diverge.</sub>
