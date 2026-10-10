---
name: mesop-to-lit
description: >-
  Assess and convert/port a Mesop (Python) app to a FastAPI backend + Lit web
  components + Web Awesome (default) or Material 3 (Material Web, opt-in) + Vite build.
  Use when asked to assess, plan, port, migrate, or convert a Mesop app (or a single
  Mesop page/feature) off Mesop to Lit/FastAPI — including "is this Mesop app worth converting",
  "what will the conversion involve", "map these Mesop constructs to Web Awesome or Material Web",
  or "scaffold the FastAPI+Lit target". Runs a deterministic analyzer over the app
  to inventory routes, state, the UI/logic seam, constructs, serve model, and hard
  topics (upload, IAP/auth, Firestore, Cloud Tasks), then applies a construct map
  and a stock/compose/custom component-decision framework to emit a conversion
  assessment. Encodes fixed facts: Web Awesome (@awesome.me/webawesome 3.14.0) is the default
  UI component library with full stock coverage (accordion, drawer, tooltip, copy-button, dialog);
  @material/web 2.5.0 is supported as an opt-in alternative when explicitly requested (in maintenance mode,
  stable components only, build custom Lit for tooltip/accordion/nav-drawer);
  there is no LLM token streaming to port; two Mesop serve models exist (plain WSGI
  and FastAPI+Mesop hybrid).
license: Apache-2.0
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/analyze_mesop_app.py *)
---

# Mesop → FastAPI + Lit + Vite + Web Awesome (or Material 3)

Convert a Mesop (Python) app to a **FastAPI** JSON backend + a **Lit** SPA built with **Vite** using
**Web Awesome** (`@awesome.me/webawesome`, default) or **Material 3 (`@material/web`)** (opt-in if explicitly requested).
This skill has two halves:

- **ASSESS** (below, fully specified): analyze a Mesop app and produce a conversion
  assessment — scope, component plan, endpoint surface, state plan, serve/deploy delta.
- **ASSIST** (below): perform the conversion using that assessment — scaffold the
  FastAPI + Vite/Lit target, derive the endpoints, build the components, stand up the tests.

## Fixed facts (do not re-derive)
- **Default UI library is Web Awesome (`@awesome.me/webawesome` 3.14.0, MIT).** It is actively maintained, built on
  Lit, and ships **stable, off-the-shelf components** for the common gaps: **`<wa-details>` / `<wa-accordion>` (accordion),
  `<wa-drawer>` (navigation drawer), `<wa-tooltip>` (tooltips), `<wa-copy-button>` (copy to clipboard)**, as well as `<wa-dialog>`,
  `<wa-button>`, `<wa-input>`, `<wa-textarea>`, `<wa-select>`, `<wa-range>`, `<wa-tab-group>`.
- **Material 3 (`@material/web` 2.5.0) is supported as an opt-in alternative ONLY when explicitly requested.**
  In that mode: `@material/web` is in **MAINTENANCE MODE**. "Stock" means a *stable* shipped component;
  **treat labs as absent** (they will not graduate). Build **custom Lit** for the known gaps:
  **tooltip, accordion/expansion-panel, navigation-drawer**.
- Baselines: **lit 3.3.3**, router **`@vaadin/router` 2.0.1** (stable).
- **There is no LLM token streaming** to port in these apps — generator `yield`s are spinner
  updates, not token streams. **Do not add streaming** (it is a behavior addition, not a port).
- **Two serve models exist:** plain Mesop WSGI (`app:me`/`main:me`) and FastAPI+Mesop hybrid
  (`main:app` + `WSGIMiddleware`). A hybrid app is already partway to the target.
- **Logic placement is a spectrum:** clean Mesop-free `services/`+`models/` seam → embedded
  Mesop-coupled logic → no Python logic at all (external backend). Do not assume a seam exists.

## ASSESS workflow (the assess → decide pipeline)

### 1. Run the analyzer
Deterministic, Python-3-stdlib-only, robust to large apps (handles ~28k-LOC repos without
crashing; never hard-fails on an unparseable file). Point it at the app directory (or a repo
root):
```
python3 ${CLAUDE_SKILL_DIR}/scripts/analyze_mesop_app.py <app_dir> [--target-ui webawesome|material-web] --json out.json --md out.md
```
- Defaults to `--target-ui webawesome`. If the user explicitly asks for Material Web 3, pass `--target-ui material-web`.
- Pointed at a **repo root** that vendors several apps, it excludes `experiments/` and
  `archive/` by default (separate apps). Pass `--include-nested` to override.
- With no `--json`/`--md`, it prints the markdown report to stdout.
- No pip installs. See `references/analysis-method.md` for every field's detection method.

### 2. Read the structured report
Key signals the report surfaces:
- **Serve model** (`plain-wsgi` | `fastapi-hybrid`) + evidence.
- **Routes:** distinct count, registrations, **double-registered** and **routed-but-hidden**.
- **State classes** with per-field classification (UI-only / derived-display / secret-config).
- **Seam:** `services_mesop_free` / `models_mesop_free`, and **in-view LLM calls** (logic-in-view
  red flag) — the backbone of how mechanical the port will be.
- **Duplicated components** (copy-paste → promote-shared under the DRY gate).
- **Construct inventory** (presence + line counts) and **hard topics** (streaming, upload
  native + custom GCS signed-URL, IAP/auth, Firestore, Cloud Tasks, legacy vertexai).
- **Per-page difficulty** (trivial / mechanical / needs-design / hard) for sequencing.
- **Stack facts** incl. requirements-vs-lockfile drift.

### 3. Apply the construct map + component-decision framework
- **Map every construct** with `references/construct-map.md` (Mesop → Lit + Material Web →
  FastAPI), re-confirming the Material Web column against live docs.
- **Decide every component** with `references/component-decisions.md`: Q1 layout→HTML/CSS;
  Q2 stable MWC 1:1→stock; Q3 2–3 MWC+glue→compose; Q4 MWC gap→custom; Q5 bespoke domain
  UI→custom. Apply the **DRY gate**: duplicated constructs promote to one shared component.
  **Never adopt labs.** The analyzer pre-computes these calls; override only with cause.
- **Classify state & plan transport** with `references/state-and-transport.md`: UI-only →
  browser state; derived-display → response bodies; secret-config → server-side; default to
  a **stateless backend**; generator-`yield` → a `loading` flag; delete the `on_blur`+`key++`
  remount hack (native two-way binding).

### 4. Emit the conversion ASSESSMENT
Produce a written assessment covering:
- **Scope & sequence** — pages in difficulty order; the smallest representative vertical slice
  to do first (scaffold + routing + theming + one endpoint + its custom component + tests).
- **Component list** — stock / composed / custom / promote-shared (from step 3).
- **Endpoint surface** — one route per real action, mirroring the service method signatures;
  pydantic request/response schemas.
- **State plan** — where each state field goes; stateless-backend decision.
- **Serve & deploy delta** — serve model detected → single-service FastAPI target; WSGI→ASGI;
  multi-stage Dockerfile; preserve timeout/port; CSP/`frame-ancestors`. See
  `references/serve-and-deploy.md`.
- **Hard-topic tasks** — upload, IAP/auth + identity bridge, Cloud Tasks, Firestore, blocking
  calls, "no seam → create one", legacy vertexai. See `references/hard-topics.md`.
- **Risks** — call out the Material Web maintenance-mode consequence (custom-for-gaps) and any
  requirements/lock drift to resolve before pinning the backend.

## ASSIST workflow (perform the conversion)

Drive this from the ASSESS output (scope/sequence, component list, endpoint surface, state
plan, serve delta). **Work one vertical slice at a time**: scaffold → one endpoint → its
custom component → its tests, all green, before widening. The slice IS the proof — do not
mark a conversion done until `vite build` succeeds and the API + component tests pass.

### 1. Scaffold the target (`references/assist-scaffold.md`)
Create the single-service tree: FastAPI `main.py` + `api/` and the Vite/Lit `web/`. **Copy**
the app's `services/`/`models/`/`config/` verbatim (grep them for `mesop` first — a Mesop
import there is a "no seam" task, do it before anything else). Pin lit 3.3.3,
`@material/web` 2.5.0, `@vaadin/router` 2.0.1. Verify the backend with `pytest` before the
frontend exists (guard the static mount with `isdir(dist)`); verify the frontend shell with
`vite build` before building components.

### 2. Derive endpoints + schemas (`references/assist-endpoints.md`)
**One route per real service method.** Method params → request model; return type → a clean
typed response model + a `from_parsed(...)` adapter (the internal type is often lossy — the
parser drops fields; document that). Thin routes: validate → call the unchanged service →
adapt → return. Construct the service behind a `Depends(...)` provider so tests inject a
mocked client. Reshape every failure to the `{"error":{"code","message"}}` envelope (422
validation reshaped, 500 catch-all); the parse-*fallback* is a 200 with `raw`, not an error.

### 3. Build the components (`references/assist-components.md`)
Build leaves→composites: `theme` → `md-markdown` (marked + **DOMPurify**, mandatory) →
`prompt-input` (native textarea, deletes the `on_blur`+`key++` hack) → `app-accordion`
(`<details>`) → the bespoke `checklist-results` → `app-header`/`app-sidenav` → pages →
`app-root` shell. **Keep unit-tested components MWC-free** and register stable MWC **only in
`main.ts`** (MWC crashes happy-dom). The generator-yield spinner → a `loading` flag; the
JSON-in-state hack → the typed response body. **Heed the happy-dom template rules**: wrap
every `html` body in a static container element (a nested template at the template root
mis-parses and shifts bindings), and build interpolated phrases as single JS strings.

### 4. Stand up the tests (`references/assist-testing.md`)
Mock the LLM at the client boundary — **no real Vertex/Gemini calls**. Backend: FastAPI
`TestClient` (happy path, 422, error-envelope, parse-fallback, CSP) with
`raise_server_exceptions=False`; carry over the parser/service unit tests. Frontend: Vitest
+ `@open-wc/testing-helpers` for `checklist-results`/`prompt-input`/`app-accordion`.
Optional Playwright e2e mirroring the Mesop page smoke test (stub the API route). Gate:
`pytest` + `vitest run` + `vite build` all green.

### 5. Wire the single-service deploy
Per `references/serve-and-deploy.md`: multi-stage Dockerfile (node build → python runtime),
WSGI→ASGI (uvicorn worker, preserve the long LLM timeout + port), CSP/`frame-ancestors`,
drop `mesop` from deps. (A scratch proof may stop at the passing slice; a real conversion
finishes the deploy.)

## References (progressive disclosure — open when you reach that step)
- `references/analysis-method.md` — the STEP-1 inventory checklist + each detection method
  (reproduce/audit the analyzer by hand).
- `references/construct-map.md` — Mesop → Lit + Material Web (M3) → FastAPI table, with the
  stable-vs-custom outcome and the maintenance-mode caveat.
- `references/component-decisions.md` — the stock/compose/custom Q1–Q5 procedure + the DRY
  gate, with worked Promptlandia examples.
- `references/state-and-transport.md` — state classification, stateless-backend default,
  generator-yield→loading-flag, on_blur+key++ removal, JSON-in-state → typed body.
- `references/serve-and-deploy.md` — detect plain-WSGI vs FastAPI-hybrid; single-service
  target; multi-stage Dockerfile; WSGI→ASGI; CSP/`frame-ancestors`.
- `references/hard-topics.md` — upload (native + custom GCS signed-URL), IAP/auth + ASGI→WSGI
  identity bridge, Cloud Tasks, Firestore, blocking calls, no-seam extraction, legacy vertexai,
  streaming-is-absent.
- `references/assist-scaffold.md` — the concrete FastAPI `api/` + Vite/Lit `web/` tree, pins,
  step order, `main.py`/`pyproject.toml`/`vite.config.ts`/`tsconfig.json` recipes + pitfalls.
- `references/assist-endpoints.md` — one-route-per-service-method derivation, request/response
  schemas + the lossy-return adapter, thin routes, DI for mocking, the error envelope.
- `references/assist-components.md` — build order + recipes (md-markdown, prompt-input,
  app-accordion, checklist-results, sidenav) + the happy-dom Lit-under-test template rules.
- `references/assist-testing.md` — the test pyramid: FastAPI `TestClient` (LLM mocked),
  Vitest + @open-wc, optional Playwright, and the green-gate verify commands.

## Tooling
- `scripts/analyze_mesop_app.py` — the deterministic analyzer. **Executed via Bash, not read
  into context.** Python 3 standard library only; no dependencies to install.

## Tooling (ASSIST)
- No analyzer script — ASSIST is recipe-driven (the four `references/assist-*.md`). The
  verify gate is the real tooling: `pytest`, `vitest run`, `vite build` (see
  `references/assist-testing.md`). All three must pass before a conversion is "done".
