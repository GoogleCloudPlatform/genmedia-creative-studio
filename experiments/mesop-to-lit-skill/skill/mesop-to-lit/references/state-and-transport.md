# State & transport: Mesop server-state → browser state + stateless FastAPI

Today, a Mesop app holds **all** UI state on the server (`@me.stateclass`, per-session)
and *every* interaction (typing blur, button, slider) is a server round-trip that mutates
state and re-renders. The target inverts this: **the browser owns transient UI state; the
server is stateless request/response** and is called only for the real actions.

## Field classification (drives everything)
Classify every field of every `@me.stateclass`. The analyzer does a name-based first pass
(`ui-only` / `derived-display` / `secret-config`); confirm by reading the field's use.

| Class | Examples | Where it goes |
|---|---|---|
| **UI-only** | `sidenav_open`, `theme_mode`, textarea values, `*_textarea_key`, slider/select/tab/modal flags, stop-seq list, char counts, `loading`/`status` | **Browser state** (Lit reactive `@state`). No endpoint. The `*_textarea_key` remount hack is **deleted**. |
| **derived-display** | `*_response`, `improved_prompt`, `trimmer_output/analysis/duration`, `parsed_response_json_str`, `commentary_suffix` | **Response bodies** from action endpoints; held in the browser only while displayed. |
| **secret-config** | `PROJECT_ID`, model IDs, Vertex location, buckets, API keys | **Stay server-side.** Expose a read-only subset (`GET /api/config`) only if the UI displays it. |

## The stateless-backend default
Default to a **fully stateless backend** unless the app has genuinely shared/cross-session
state (most Mesop apps do not — their state is trivial and per-session). A session store
adds session IDs + expiry for zero behavioral gain. Override only when real cross-session
or multi-user state exists.

## Transport shift — only real actions become HTTP
Every Mesop event is a round-trip today; in the target, **only the handful of real
backend actions are `fetch` calls**. All typing/selecting/toggling is local DOM. Derive
the endpoint set from the app's action handlers — one route per action, mirroring the
existing service method signatures. Typical Promptlandia-shaped surface:

```
POST /api/improve      {system_prompt, prompt, instructions} -> {plan, improved_prompt}
POST /api/generate     {prompt, model?}                        -> {text}
POST /api/checklist     {prompt}                                -> {categories:[...], raw?}
POST /api/video-checklist {prompt}                              -> {categories:[...], raw?}   # same schema, kind=video
POST /api/trim         {prompt}        -> {trimmed_prompt, analysis_xml, duration_seconds}
POST /api/playground   {prompt, model, region, temperature, token_limit, stop_sequences} -> {text}
GET  /api/config        -> {model_id, alternative_model_id, gemini_location, system_prompts}
```
Keep request/response as pydantic models in `api/schemas.py`; they mirror the service
signatures almost 1:1.

## Generator-`yield` → loading flag (NOT streaming)
Mesop generator handlers that `yield` repeatedly are **spinner/progress updates, not token
streaming** (confirm: the analyzer reports `streaming_present` — it is `False` in every
surveyed app). Each generator maps to:
```
this.loading = true;
try { this.result = await client.action(req); }
finally { this.loading = false; }
```
A single `await fetch()` + a `loading` reactive flag reproduces the current UX exactly.
**Do not add SSE/WebSocket** — that is a behavior *addition*, not a port. If streaming is
wanted later, it is additive (a parallel `POST /api/x/stream` → `StreamingResponse` over
`generate_content_stream`, consumed by `EventSource`), documented as a hook, not built.

## `on_blur` + `key++` two-way-binding removal
The Mesop idiom — commit input to state only on blur, and "clear" a field by incrementing
a `*_textarea_key` to force a re-mount — exists only because of Mesop's render model. In
Lit it **disappears entirely**: bind the field value to a reactive property and set it to
`""` to clear. The analyzer flags `native_textarea`, `on_blur`, and the key-bump pattern so
you can find every site.

## The JSON-in-state workaround
Some Mesop apps serialize a parsed pydantic object to a **JSON string in state** to dodge
Mesop's (de)serialization of nested models (e.g. Promptlandia's checklist). This is a
Mesop coupling, not a requirement: it becomes a **normal typed JSON response body**. Reuse
the existing parser (e.g. `parse_evaluation_markdown` / `from_json_dict`) server-side to
build the typed response; the frontend receives typed JSON directly.
