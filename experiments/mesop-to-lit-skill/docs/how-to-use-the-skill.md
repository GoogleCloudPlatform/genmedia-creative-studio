# How to use the `mesop-to-lit` skill

An operator-facing, step-by-step guide to running the **`mesop-to-lit`** Agent Skill — the one
that **assesses** whether a Mesop (Python) app is worth converting to the target stack and then
**assists** the conversion to a **FastAPI** JSON backend + **Lit + Material 3 (Material Web)** SPA
built with **Vite**.

This guide is the operator manual. For the *method* behind it, see the companion playbook
`playbook-draft.md`; for depth on any single step, open the skill's own `references/*.md` (cited
inline below) rather than re-reading them here.

---

## 1. When to use it (and when not)

**Use it when** you are asked to assess, plan, port, migrate, or convert a Mesop app — or a single
Mesop page/feature — off Mesop to Lit/FastAPI/Material 3. Typical triggers:

- "Is this Mesop app worth converting?" / "What will the conversion involve?"
- "Map these Mesop constructs to Material Web."
- "Scaffold the FastAPI + Lit target."

The skill has **two halves** you can use independently:

- **ASSESS** — run a deterministic analyzer over the app and produce a written conversion
  assessment (scope, component plan, endpoint surface, state plan, serve/deploy delta). Safe,
  read-only, no changes to the app.
- **ASSIST** — perform the conversion using that assessment: scaffold the target, derive
  endpoints, build components, stand up tests.

**Do not use it** to *add behavior* during a port. The skill is explicit that there is **no LLM
token streaming** to carry over in these apps (generator `yield`s are spinner updates, not token
streams); adding SSE/WebSocket streaming is a feature, not a port. Likewise it is not a general
"rewrite my Python app" tool — it assumes a request/response UI over some service logic, which is
what nearly all Mesop apps are.

---

## 2. Install / invoke

The skill is a **plain skill directory** — no packaging step. It lives at
`skill/mesop-to-lit/` and is discovered and invoked by Claude Code automatically from its
`SKILL.md` frontmatter (`name: mesop-to-lit` + the `description`) when your request matches one of
the triggers above. You don't "install" it beyond having the directory on the skill path; just ask
for the assessment or conversion in natural language.

The one executable is the analyzer, which the skill runs via Bash (it is **not** read into
context):

```
python3 ${CLAUDE_SKILL_DIR}/scripts/analyze_mesop_app.py <app_dir> [--json out.json] [--md out.md]
```

- **Python 3 standard library only** — no `pip install`, no dependencies, no network.
- With no `--json`/`--md`, it prints the markdown report to stdout.
- Point it at an **app directory** or a **repo root**. At a repo root that vendors several apps it
  excludes `experiments/` and `archive/` by default; pass `--include-nested` to override.
- It is robust: it has run over a ~28k-LOC repo (GMCS) without crashing and never hard-fails on an
  unparseable file (it records `parse_errors` and moves on). It is read-only and hardened — it
  skips symlinked files/dirs and caps per-file reads at 5 MB.

---

## 3. The ASSESS workflow

### Step 1 — Run the analyzer

```
python3 ${CLAUDE_SKILL_DIR}/scripts/analyze_mesop_app.py path/to/app --json assess.json --md assess.md
```

### Step 2 — Read the assessment

The report surfaces the signals that decide how mechanical the port will be:

- **Serve model** — `plain-wsgi` (`app:me`/`main:me`) vs `fastapi-hybrid` (`main:app` +
  `WSGIMiddleware`), with evidence. A hybrid app is already partway to the target.
- **Routes** — distinct count, registrations, **double-registered** and **routed-but-hidden**
  pages (collapse these deliberately in the new router table).
- **State classes** — per-field classification: **UI-only** / **derived-display** /
  **secret-config**. This drives transport (see §4).
- **The seam** — `services_mesop_free` / `models_mesop_free`, plus **in-view LLM calls** (the
  logic-in-view red flag). The seam is the backbone of the whole conversion.
- **Duplicated components** — copy-paste constructs that the DRY gate will promote to one shared
  component.
- **Construct inventory** (presence + line counts) and **hard topics** — streaming, upload
  (native + custom GCS signed-URL), IAP/auth, Firestore, Cloud Tasks, legacy vertexai.
- **Per-page difficulty** — trivial / mechanical / needs-design / hard, for sequencing.
- **Stack facts** — including requirements-vs-lockfile drift.

### Step 3 — Interpret the key judgments

- **Difficulty bands** order your work: do **trivial → mechanical → needs-design → hard**, and
  pick the smallest representative vertical slice first.
- **The seam** is the leverage. A clean Mesop-free `services/`+`models/` seam means the backend is
  "almost verbatim." **No seam → that is the first task**: lift LLM/business calls out of the view
  handlers before anything else (`references/hard-topics.md`).
- **The construct map** (`references/construct-map.md`): map every construct Mesop → Lit + Material
  Web → FastAPI. **Re-confirm the Material Web column against live docs** each time.
- **The component decision** (`references/component-decisions.md`), Q1–Q5:
  - Q1 pure layout → **HTML/CSS**
  - Q2 a stable MWC component maps 1:1 → **stock**
  - Q3 2–3 MWC + glue → **compose**
  - Q4 an MWC gap → **custom Lit**
  - Q5 bespoke domain UI → **custom Lit**
  - **DRY gate:** a duplicated construct promotes to **one shared component**.
  - **MWC maintenance-mode rule:** `@material/web` (v2.5.0) is in **maintenance mode** — "stock"
    means a *stable shipped* component; **treat labs as absent and never adopt them** (they will
    not graduate). Build custom Lit for the known gaps: **tooltip, accordion/expansion-panel,
    navigation-drawer**. The analyzer pre-computes these calls; override only with cause.

---

## 4. The DECIDE step (defaults — override only with cause)

Classify state (`references/state-and-transport.md`) and apply the defaults:

| Decision | Default | Override when |
|---|---|---|
| Session state | **stateless backend** | genuinely shared/cross-session state exists |
| Streaming | **keep non-streaming** | the app streams tokens today |
| Serve model | **single-service** (FastAPI serves the Vite bundle) | a CDN/static split is justified |
| Component gaps (tooltip/accordion/nav-drawer) | **custom Lit** | a stable MWC component appears |
| Labs components | **never** | MWC leaves maintenance mode |

Transport follows the classification: **UI-only** → browser reactive state; **derived-display** →
response bodies; **secret-config** → server-side only. Generator-`yield` spinner → a `loading`
flag. Delete the `on_blur`+`key++` remount hack (native two-way binding replaces it). A
"serialize-to-JSON-string-in-state" Mesop workaround becomes a normal typed response body.

The **two serve models**: `plain-wsgi` and `fastapi-hybrid`. Both converge on a single-service
FastAPI target; a hybrid app is already closer.

---

## 5. The ASSIST workflow

Drive this from the ASSESS output and **work one vertical slice at a time**: scaffold → one
endpoint → its custom component → its tests, all green, before widening. The slice is the proof —
a conversion is not "done" until `pytest` + `vitest run` + `vite build` all pass.

### Step 1 — Scaffold the target (`references/assist-scaffold.md`)

Create the single-service tree: FastAPI `main.py` + `api/`, and the Vite/Lit `web/`. **Copy** the
app's `services/`/`models/`/`config/` **verbatim** — but grep them for `mesop` first; an import
there is a "no seam" task to do before anything else. Pin **lit 3.3.3**, **`@material/web` 2.5.0**,
**`@vaadin/router` 2.0.1**. Verify the backend with `pytest` *before* the frontend exists (guard
the static mount with `isdir(dist)`); verify the frontend shell with `vite build` *before*
building components.

### Step 2 — Derive endpoints + pydantic schemas (`references/assist-endpoints.md`)

**One route per real service method.** Method params → request model; return type → a clean typed
response model **plus a `from_parsed(...)` adapter** (the internal/parsed type is often lossy —
see G4 in §6). Keep routes thin: validate → call the unchanged service → adapt → return.
Construct the service behind a `Depends(...)` provider so tests can inject a mocked client. Reshape
every failure to the `{"error": {"code", "message"}}` envelope (422 validation reshaped, 500
catch-all). The parse-**fallback** is a **200** with `raw`, not an error.

### Step 3 — Build the components (`references/assist-components.md`)

Build **leaves → composites**:
`theme` → `md-markdown` (marked + **DOMPurify**, mandatory) → `prompt-input` (native textarea,
deletes the `on_blur`+`key++` hack) → `app-accordion` (`<details>`) → the bespoke
`checklist-results` → `app-header`/`app-sidenav` → pages → `app-root` shell.

Keep every unit-tested component **MWC-free** and register stable MWC **only in `main.ts`** (see
G1–G3 in §6 — this is where the real footguns live).

### Step 4 — Stand up the tests (`references/assist-testing.md`)

The pyramid, LLM mocked at the client boundary (**no real Vertex/Gemini calls**):

- **Backend** — FastAPI `TestClient`: happy path, 422 validation, error-envelope, parse-fallback,
  CSP. Use `TestClient(app, raise_server_exceptions=False)` (see G5). Carry over the parser/service
  unit tests.
- **Frontend** — Vitest + `@open-wc/testing-helpers` for the custom components.
- **Optional** — Playwright e2e mirroring the Mesop smoke test (stub the API route; never a real
  LLM). It is the only layer that exercises real MWC rendering and full-fidelity markdown URL
  sanitization.
- **Gate:** `pytest` + `vitest run` + `vite build` all green.

### Step 5 — Wire the single-service deploy (`references/serve-and-deploy.md`)

Multi-stage Dockerfile (node build → python runtime), WSGI → ASGI (uvicorn worker, preserve the
long LLM timeout + port), CSP/`frame-ancestors`, drop `mesop` from deps. A scratch proof may stop
at the passing slice; a real conversion finishes the deploy.

---

## 6. The gotchas that actually bit (pitfalls & fixes)

These are distilled from the Promptlandia pilot (G1–G7 in `scratch/RESULTS.md`) and the three
quality-gate reviews. They are the difference between "the method looks right" and "the slice
actually goes green."

### G1 — Lit templates break under happy-dom when a nested template sits at the template ROOT
A `TemplateResult` placed directly at a template's root with no enclosing element — e.g.
`` html`${cond ? html`...` : nothing}` `` — is **mis-parsed by happy-dom**: it commits as literal
`<?>` text **and shifts every binding after it**, so a later `.text=${str}` silently receives an
object. The component renders fine in a browser but its test shadow root is empty/garbled.
**Fix:** wrap every `html` body (and every helper's returned fragment, at every nesting level) in a
**static container element** so no bare `${nested-template}` is a root child.

### G2 — `@material/web` cannot be imported under happy-dom
Importing any `@material/web` component in a test (or any module a test imports) throws
`this.attachInternals is not a function`. "Stable MWC only" also means MWC is **untestable** in the
unit layer.
**Fix:** keep every unit-tested component **MWC-free** (native elements + bare
`<md-icon>glyph</md-icon>`) and register stable MWC **only in `main.ts`**, which tests never import.

### G3 — interpolated adjacent expressions inject the template's own whitespace
`` html`Checklist found ${n}\n  ${plural}` `` renders `"Checklist found 1\n  issue"`, so a
`textContent.includes("Checklist found 1 issue")` assertion fails on invisible whitespace.
**Fix:** build such phrases as a **single JS string**: `` `Checklist found ${n} ${plural}` ``.

### G4 — the service return type is lossy; the wire schema needs an explicit adapter
"Mirror the service signatures" is not literal when the return type comes from a lossy parser
(e.g. one that reshapes raw per-issue JSON into markdown and drops `issue_name`/`severity`).
**Fix:** write a `Response.from_parsed(parsed, raw)` classmethod that maps what survives, orders
sensibly, and returns `raw` on parse failure — and **document the lossiness in the schema
docstring**.

### G5 — `TestClient` re-raises server exceptions, hiding the error envelope
The error-envelope test fails unless the client is `TestClient(app, raise_server_exceptions=False)`
— otherwise the exception propagates before the 500 handler shapes the body. Also: the
parse-**fallback** is a **200** (degrade gracefully), easily conflated with the 500 case.

### G6 — config reads env at import time
If `config/default.py` reads e.g. `PROJECT_ID` at import, tests fail to import without it.
**Fix:** `os.environ.setdefault("PROJECT_ID", "test-project")` in `conftest.py` (no network, LLM
still mocked).

### G7 — the service needs an injectable client for mocking
`app.dependency_overrides` can only inject a mocked `LLMClient` if the service accepts one. Adding
an optional `client=None` is a legitimate minimal seam fix.

### Quality-gate findings (merge-blocking) — the security traps

- **SPA-fallback path traversal (CRITICAL).** A naïve SPA fallback that serves the requested path
  is an arbitrary-file-read: `../../main.py` / `%2e%2e%2f` / `/etc/passwd` bypass client-side URL
  normalization and the handler reads the file. **Safe pattern:** resolve the candidate with
  `os.path.realpath` and serve it **only if it is contained in `WEB_DIST`**
  (`candidate == real_dist or candidate.startswith(real_dist + os.sep)`); otherwise fall through to
  `index.html`/404. `StaticFiles(html=True)` is a safe alternative. Add a regression test with
  several encoded variants.
- **Error envelope must not leak `str(exc)` (MEDIUM/HIGH).** The 500 handler returns a generic
  `"Internal server error"`; the detail goes to `logger.exception(...)` server-side only. And use
  `JSONResponse(status_code=..., content=...)` — the two traps are swapped positional args and
  leaking `str(exc)`.
- **happy-dom markdown/MWC test caveats.** happy-dom's DOM is not a faithful browser DOM: DOMPurify's
  protocol-based URL filtering (e.g. `javascript:` hrefs) is **not reproduced reliably** under
  happy-dom. Assert only on payloads that strip deterministically (dangerous tags/attributes); push
  full-fidelity URL-scheme coverage to the Playwright layer. (This pairs with G2: MWC itself is
  untestable under happy-dom.)

---

## 7. Evidence

The skill is proven, not aspirational:

- **The Promptlandia checklist slice** was converted end-to-end with the skill (source in
  `experiments/.../examples/promptlandia-checklist-slice/`). Observed, reproducible outcomes:
  - **Backend:** `pytest` → **15 passed** (happy path, 422 ×2, error-envelope, parse-fallback,
    CSP, 3 path-traversal variants, carried-over parser/service unit tests).
  - **Frontend:** `vitest run` → **16 passed** (`checklist-results`, `prompt-input`,
    `app-accordion`, markdown sanitization).
  - **Build:** `vite build` → **clean** (94 modules, no errors).
  - **No mesop:** `grep` for mesop imports across `main.py`/`api`/`services`/`models`/`config`
    → none.
- **ASSESS validated at range:** the analyzer produced clean assessments for **babel** (small) and
  **GMCS** (~28k-LOC, routes=42, `fastapi-hybrid`, only 2 parse errors) without crashing. See
  `validation/*-assessment.md` and the `assess-validation-*.md` write-ups
  (Promptlandia 9/9 + 20/20; the "harder" re-validation).
- **All three quality gates APPROVED** — code, security, and test review (two code/security
  rounds) returned APPROVE after the merge-blocking findings in §6 were fixed in both the slice and
  the propagating skill references. See `reviews/` and `evidence/`.

---

## 8. Where to go deeper

| You need… | Open |
|---|---|
| The full method behind this guide | `playbook-draft.md` |
| Each analyzer field's detection method | `references/analysis-method.md` |
| Mesop → Lit → FastAPI construct table | `references/construct-map.md` |
| The stock/compose/custom procedure | `references/component-decisions.md` |
| State classification + transport | `references/state-and-transport.md` |
| Serve-model detection + Dockerfile + CSP | `references/serve-and-deploy.md` |
| Upload/auth/Firestore/Cloud Tasks/no-seam | `references/hard-topics.md` |
| Scaffold tree, pins, recipes, pitfalls | `references/assist-scaffold.md` |
| Endpoint derivation + lossy adapter + envelope | `references/assist-endpoints.md` |
| Component build order + happy-dom rules | `references/assist-components.md` |
| The test pyramid + green-gate commands | `references/assist-testing.md` |
