# Hard topics: patterns beyond the clean reference app

Promptlandia is the *clean* reference (clear seam, no upload, no auth-in-code, no
streaming). Real apps — especially the flagship GMCS — add patterns the skill must still
handle. The analyzer reports each under `hard_topics`; this file says what to do with them.

## 1. Streaming is ABSENT everywhere — do NOT add it
Every surveyed app has **zero** LLM token streaming (`analyzer: streaming_present=False`).
Generator `yield`s are spinner updates, not token streams. Keep non-streaming (loading flag
+ single JSON response). Adding SSE/WebSocket is a *new behavior*, not a port — defer with a
documented hook (see `state-and-transport.md`). Watch for false friends: a variable named
`image_stream` or a `StreamingResponse` for file bytes is **not** LLM streaming.

## 2. File upload — two mechanisms
The analyzer distinguishes `upload_native`, `upload_web_component`, `upload_signed_url`, and
lists `custom_gcs_uploader_files`.
- **Native `me.uploader`** → `<input type="file">` (or an M3-styled file button); POST the
  file to a FastAPI `UploadFile` endpoint, or request a signed URL and PUT directly to GCS.
- **Custom `@me.web_component` signed-URL direct-to-GCS uploader** (GMCS's
  `components/gcs_uploader/gcs_uploader.{py,js}` fed by `GET /api/get_signed_url`) — the
  **hardest** variant. The JS half is already a web component; port it to a Lit element that
  (1) calls the signed-URL endpoint, (2) PUTs the file to GCS, (3) emits the resulting URI.
  Keep the `get_signed_url` route server-side. This is the one upload path that needs real
  design work; everything else is mechanical.

## 3. IAP / auth + ASGI→WSGI identity bridge
The analyzer flags `auth_iap`. GMCS verifies an **IAP** assertion off-thread, gates on
`REQUIRE_AUTHENTICATED_USER`, and **bridges identity from the ASGI (FastAPI) layer into the
WSGI (Mesop) sub-app** via a session cookie / request state.
- **Platform gating (IAP) is unaffected by the framework change** — it sits in front of
  Cloud Run. Keep it.
- In the **single-service FastAPI target there is no WSGI sub-app**, so the ASGI→WSGI
  identity bridge **disappears**: read the verified identity in FastAPI middleware/deps and
  pass it to handlers directly. Keep the IAP-assertion verification server-side.
- Provider auth (Vertex `vertexai=True`) stays server-side inside the LLM client.

## 4. Cloud Tasks / background jobs
The analyzer flags `cloud_tasks` (`google-cloud-tasks`, `CloudTasksClient`, FastAPI
`BackgroundTasks`). GMCS enqueues long media jobs and polls a job endpoint
(`POST /api/veo/generate_async`, `GET /api/veo/job/{id}`). In the target these stay
server-side FastAPI concerns — a hybrid-source app often already has the routers; keep them.
The frontend polls the job endpoint from a reactive `loading` state (same pattern as a
synchronous action, just with polling).

## 5. Firestore persistence
The analyzer flags `firestore` (GMCS: pervasive, `common/metadata.py` hub). Persistence is
**backend-only** and orthogonal to the UI port — the Firestore access layer moves into
FastAPI services unchanged. Do not try to move it to the browser.

## 6. Blocking-synchronous LLM calls (no generator)
Some apps (e.g. creative-genmedia-workflow) call the LLM **synchronously inside the click
handler** with no `yield` — the Mesop UI freezes during the call (analyzer:
`generator_yield` absent but LLM calls present, logic embedded in a view). In the target
these become normal `async def` routes + a client `loading` flag; the freeze goes away for
free. Flag them because they often also lack a seam (next item).

## 7. "No seam → create one" extraction path
The logic-placement spectrum spans: clean Mesop-free `services/`+`models/` seam
(Promptlandia) → strong `models/`+`services/`+`common/` seam (GMCS, arena) → **fully
embedded, Mesop-coupled logic in one file** (creative-genmedia-workflow, imagen-cs) → **no
Python logic at all**, delegated to an external service over HTTP (babel). The analyzer
reports `services_mesop_free` / `models_mesop_free` and **in-view LLM calls**.
- If a clean seam exists → the backend is "almost verbatim."
- If logic lives in view handlers (`in_view_llm` non-empty, or `services_mesop_free` is
  `None`/`False`) → **the first conversion task is to create the seam**: lift each
  LLM/business call out of the handler into a Mesop-free service module, covered by the
  existing service-test pattern. Do this as its own commit *before* the frontend work.

## 8. Legacy `vertexai` SDK vs `google.genai`
The analyzer flags `legacy_vertexai` (`import vertexai`, `GenerativeModel(`,
`ImageGenerationModel(`, `vertexai.preview`). Note: `genai.Client(vertexai=True)` is the
**new** SDK pointed at the Vertex backend and is **not** flagged as legacy. Where the legacy
SDK is present (imagen-cs, parts of arena, and 2 GMCS model files — `models/model_setup.py`,
`models/lyria.py`), the port is a good moment to migrate to `google.genai`, but it is a
backend-only change independent of the UI port — do it in the seam, not the view.

## 9. Faked navigation
Some apps fake multi-page nav with a single `@me.page` and a `match state.current_page`
switcher (babel). The analyzer reports 1 route but multiple page modules. In the target
these become **real client routes** — one route per logical page in the route table.

## Quick reference
| Topic | Analyzer field | Default action |
|---|---|---|
| streaming | `streaming` | keep non-streaming; never add |
| upload (native) | `upload_native` | `<input type=file>` → UploadFile / signed URL |
| upload (custom GCS) | `upload_web_component`, `custom_gcs_uploader_files` | port the web component to Lit; keep signed-URL route |
| IAP / auth | `auth_iap` | keep platform gating; drop the WSGI identity bridge |
| Cloud Tasks | `cloud_tasks` | keep server-side; client polls job endpoint |
| Firestore | `firestore` | backend-only; moves unchanged |
| blocking calls | `generator_yield` absent + LLM present | async route + loading flag |
| no seam | `services_mesop_free`/`in_view_llm` | create the seam first (pre-phase) |
| legacy vertexai | `legacy_vertexai` | optional backend migration, not UI work |
