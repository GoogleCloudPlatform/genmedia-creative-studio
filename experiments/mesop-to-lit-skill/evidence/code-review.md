# mesop-lit-rev-code — Review of the `mesop-to-lit` Skill + the checklist-slice conversion

## Overall verdict: **REQUEST CHANGES**

Per-area:

| Area | Verdict |
|---|---|
| The Skill (SKILL.md + references) | **REQUEST CHANGES** (one must-fix recipe bug + doc accuracy) |
| Analyzer script | **APPROVE** (low-severity dead code only) |
| Converted backend | **REQUEST CHANGES** (one Critical security bug) |
| Converted frontend | **APPROVE** (low-severity nits only) |

**Summary.** This is strong, carefully-reasoned work: the ASSESS references encode the design
with high fidelity (construct map, Q1–Q5 + DRY gate, stateless default, no-streaming, two serve
models, MWC maintenance-mode/never-labs), the ASSIST references genuinely capture all seven
conversion gaps G1–G7, the analyzer is robust (AST + regex fallback, graceful parse-error
handling), and the converted app builds and passes every gate (backend 12/12, frontend 13/13,
`vite build` clean). Two defects block merge: (1) a **Critical path-traversal / arbitrary-file-read**
in the converted `main.py` SPA fallback, which I reproduced serving `/etc/passwd` and the app's own
source; and (2) a **must-fix inverted-argument bug** in the error-handler recipe in
`assist-endpoints.md` — a skill recipe that produces broken code if copied. Everything else is
nits/follow-ups.

Severity labels below follow the brief's requested scale (**Critical / High / Medium / Low**).
Critical and High are must-fix-before-PR (merge-blocking); Medium/Low are nice-to-have / follow-up.

---

## MUST-FIX BEFORE PR

### Critical

**C1 — Path traversal / arbitrary file read in the SPA fallback.**
`scratch/promptlandia-lit/main.py:76-84`
```python
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    candidate = os.path.join(WEB_DIST, full_path)
    if full_path and os.path.isfile(candidate):
        return FileResponse(candidate)         # <-- no containment check
    ...
```
`full_path` is attacker-controlled and joined straight into a filesystem path, then served if it
resolves to any existing file — with no check that the result stays inside `WEB_DIST`. I verified
this is genuinely exploitable (not theoretical):

```
../../main.py            -> SERVE_FILE .../promptlandia-lit/main.py
../../config/default.py  -> SERVE_FILE .../promptlandia-lit/config/default.py
<enough ../>etc/passwd   -> SERVE_FILE /etc/passwd
```

Browsers normalize `..`, but an attacker does not need a browser: `curl --path-as-is` or
percent-encoded `GET /%2e%2e/%2e%2e/etc/passwd` reach the handler with `..` intact (uvicorn decodes,
Starlette's `:path` convertor does not collapse dot-segments). In the single-service deploy model
(§7) the app serves `/api/*` and the SPA from one container, so this reads any file the process can
read: backend source, `config/default.py`, and a `.env`/secret if present. CWE-22.

Note the `/assets` `StaticFiles` mount (main.py:70-74) is *not* affected — Starlette's `StaticFiles`
has its own traversal guard. The vulnerability is exclusively in the hand-rolled fallback.

**Fix:** contain the resolved path before serving. Minimal:
```python
real_dist = os.path.realpath(WEB_DIST)
candidate = os.path.realpath(os.path.join(WEB_DIST, full_path))
if full_path and candidate.startswith(real_dist + os.sep) and os.path.isfile(candidate):
    return FileResponse(candidate)
# else fall through to index.html
```
(or equivalently guard with `os.path.commonpath([candidate, real_dist]) == real_dist`). Preferably
serve the bundle via `StaticFiles(directory=WEB_DIST, html=True)` mounted last and keep only a
guarded index fallback for deep links. Add a regression test asserting
`GET /../../main.py` (path-as-is) does **not** return file contents.

### High

**H1 — Error-handler recipe has inverted `JSONResponse` arguments (skill recipe propagates broken code).**
`skill/mesop-to-lit/references/assist-endpoints.md:81-86`
```python
async def _v(req, exc): return JSONResponse(422, _envelope("validation_error", msg))
async def _h(req, exc): return JSONResponse(exc.status_code, _envelope("http_error", ...))
async def _u(req, exc): return JSONResponse(500, _envelope("internal_error", str(exc)))
```
Starlette/FastAPI's signature is `JSONResponse(content, status_code=200, ...)`. As written,
`JSONResponse(422, _envelope(...))` binds `content=422` and `status_code=<the envelope dict>` —
backwards. A user who copies this recipe gets a response whose **body is the integer `422`** and
whose **status code is a dict** (a runtime error when Starlette tries to use it). The *implemented*
`api/errors.py` is correct (`JSONResponse(status_code=422, content=...)`), so this is a recipe-only
defect — but this is a Skill whose recipes propagate, and the error envelope is one of its headline
deliverables. **Fix:** use keyword args in all three handlers, e.g.
`JSONResponse(status_code=422, content=_envelope(...))`. (It is abbreviated pseudocode — `msg`/`...`
are placeholders — but the argument *order* is the thing being taught and it is wrong.)

---

## NICE-TO-HAVE / FOLLOW-UP

### Medium

**M1 — 500 envelope leaks the raw exception message to the client.**
`scratch/promptlandia-lit/api/errors.py:60-65` returns `str(exc)` as `message`; the behavior is
enshrined by `tests/test_api_checklist.py:102` (`assert "Gemini exploded" in body["error"]["message"]`).
Raw exception text can carry prompt content, internal paths, or library internals. Design §3.5 only
requires a uniform `{code, message}` envelope — it does not require echoing the exception. The detail
is already captured server-side via `logger.exception(...)`. **Recommend:** return a generic
`"Internal server error"` in the body, keep the full detail in the log, and update the test to assert
the generic message. The same `str(exc)` appears in the skill recipe (assist-endpoints.md:86) — fix
both so the pattern does not propagate. (Medium, not High: the target is an internal/IAP-gated tool.)

### Low

**L1 — Docs overpromise analyzer "key-bump" detection.**
`skill/.../references/state-and-transport.md:61` ("The analyzer flags `native_textarea`, `on_blur`,
and the key-bump pattern") and `analysis-method.md:46` (`native_textarea`/`on_blur`(+key-bump))
claim the analyzer detects the `*_textarea_key++` remount hack. It does not: `CONSTRUCT_PATTERNS`
(`scripts/analyze_mesop_app.py:55-56`) contains only `native_textarea` and `on_blur`; the only
"key++" string in the script (line 119) is descriptive text in a decision message, not a detector.
**Fix:** either add a pattern (e.g. `_textarea_key|_key\s*\+\+`) or correct both docs. A user who
trusts the doc will expect auto-flagged sites and find none.

**L2 — Author's scratch workflow leaks into a reusable reference.**
`skill/.../references/assist-testing.md:95,106` instruct the reader to "record the skip in RESULTS"
/ "paste the summaries into RESULTS.md". `RESULTS.md` is the dev's own scratch deliverable; a future
skill user has no such file. **Fix:** generalize the wording ("your conversion notes").

**L3 — Dead code in the analyzer.**
`scripts/analyze_mesop_app.py:949-950` — the first `mods = [...]` comprehension in
`_dir_is_mesop_free` is immediately overwritten by the second on line 951 (and `_first_dir` is only
referenced by the dead line). `analyze_mesop_app.py:275-277` — a no-op `if ... in ("os","re","json"):
pass` branch in `_regex_extract`. Harmless but should be deleted for maintainability.

**L4 — `app-sidenav` nests a raw `<ul>` inside `<md-list>`; comment is inaccurate.**
`scratch/promptlandia-lit/web/src/components/app-sidenav.ts:101-118`. The header comment says it
"composes the STABLE md-list / md-list-item", but the render wraps `<ul><li><a>` inside `<md-list>`
rather than using `md-list-item`. `md-list` around a `ul` is semantically redundant (nested list
roles) and the comment misdescribes the code. **Fix:** either use `md-list-item type="link"` as the
comment claims, or drop the `<md-list>` wrapper and keep the plain `<ul>`. Not unit-tested; cosmetic
+ minor a11y. (Follows G2 correctly either way — it is registered only in `main.ts`.)

### FYI

**F1 — Router catch-all maps unknown paths to the checklist page.**
`web/src/router.ts:33` (`{ path: '(.*)', component: 'page-checklist' }`). Unknown deep links render
the checklist rather than a not-found page. Fine for the scratch slice; revisit for the real build.

**F2 — API client has no request timeout/AbortController.** `web/src/api/client.ts`. Consistent with
design §3.5 (AbortController is for user-initiated cancel only, explicitly "not built" for the slice).
No action for the slice.

---

## Positive feedback (specific)

- **`ChecklistResponse.from_parsed`** (`api/schemas.py:79-129`) correctly handles the lossy parser:
  it maps the surviving `IssueDetail` fields, falls back to the formatted-string path when the
  parser stored a string, filters passed checks out of `items`, sorts issues-first
  (`sort(key=lambda c: not c.has_issue)`), and returns `raw` on the `parsed is None` fallback — and
  the lossiness is documented in the module + method docstrings (G4 captured faithfully).
- **DI seam is genuinely mockable** (`api/deps.py` + `services/checklist.py:34` `client=None`): the
  tests inject a mocked `LLMClient` via `app.dependency_overrides` with zero network (G7).
- **Backend test coverage is honest and behavioral**: happy path, empty-prompt 422, missing-field
  422, service-error 500 envelope, parse-fallback 200+raw, and the CSP `frame-ancestors` header —
  with `TestClient(..., raise_server_exceptions=False)` correctly applied (G5).
- **Frontend G1–G3 lessons are applied in the code, not just documented**: the static wrapper `<div
  class="results">` around dynamic parts (checklist-results.ts:189), MWC-free unit-tested components
  (prompt-input/checklist-results/app-accordion use native elements + bare `<md-icon>` glyphs; MWC
  registered only in `main.ts`), and the single-string `issueHeading` (checklist-results.ts:180).
- **`md-markdown`** sanitizes correctly: `marked.parse(...)` → `DOMPurify.sanitize(...)` →
  `unsafeHTML(...)` (md-markdown.ts:36-43), and the parse-fallback raw text is routed through the
  same sanitizer.
- **Analyzer robustness**: `ast.parse` wrapped with a regex fallback for newer-than-interpreter
  syntax, `read_text` with utf-8→latin-1→"" degradation, deterministic sorted walks, and a
  transparent, self-documenting difficulty rubric (`RUBRIC_NOTES`).

## Test coverage

Adequate for the pilot slice and genuinely behavioral. Gaps: (a) no negative test for the SPA
fallback traversal — add one with C1's fix (`spa_fallback` is currently untested entirely); (b) the
500-envelope test currently *locks in* the exception-message leak (M1) and should be changed to
assert a generic message; (c) Playwright e2e is skipped, which the brief permits. Frontend covers
checklist-results (issue/no-issue/pluralization/fallback), prompt-input, and app-accordion.

## Backward compatibility

N/A — new scratch app, no wire contract in production. The wire schema matches design §3.3:
`ChecklistItem` declares all six fields; `from_parsed` fills only the three that survive the parser,
with the loss documented. Frontend `api/types.ts` mirrors the backend shapes.

---

## What I verified vs. what I only read

**Verified (ran / executed / reproduced):**
- Backend `pytest` — **12 passed** (ran in the provided `.venv`, LLM mocked, no network).
- Frontend `npm run test` (Vitest + happy-dom) — **13 passed**; `npm run build` — **clean**
  (94 modules, matches RESULTS.md).
- **C1 reproduced** by executing the exact `spa_fallback` logic against crafted `../` paths; confirmed
  it serves `/etc/passwd` and the app's own backend source outside `WEB_DIST`.
- **H1 and L1 independently confirmed** by reading the cited lines (inverted `JSONResponse` args;
  absence of any key-bump pattern in `CONSTRUCT_PATTERNS`).
- No `mesop` import in the backend (consistent with RESULTS.md; design acceptance criterion).

**Read closely (not executed):**
- All backend source: `main.py`, `api/{schemas,errors,routes_actions,routes_config,deps}.py`,
  `services/{checklist,llm_client}.py`, `models/{checklist_models,parsers}.py`, `config/default.py`,
  `tests/*`.
- All reviewed frontend source: `web/src/{app-root,router,theme,main}.ts`, `api/{client,types}.ts`,
  `components/{checklist-results,md-markdown,prompt-input,app-accordion,app-sidenav}.ts`,
  `pages/page-checklist.ts`, `web/test/checklist-results.test.ts`, `vite.config.ts`, `tsconfig.json`.
- The analyzer script in full.
- SKILL.md + all 10 references cross-checked against `design/target-architecture.md`,
  `design/component-decision-framework.md`, and `scratch/RESULTS.md` (G1–G7).

**Not reviewed (out of delta / out of scope):** carried-over `services/{improver,trimmer}.py`,
`models/{domain,prompts}.py`, and the bulk of `services/llm_client.py` / `config/default.py` are
imported largely unchanged per design §3.1/§3.4; `web/test/{prompt-input,app-accordion}.test.ts`
were executed (passing) but not line-read; `page-stub.ts`/`app-header.ts` are trivial. No Dockerfile
/ Cloud Run wiring exists (scratch proof, per RESULTS.md §3).

**Gates I could not run:** no TypeScript `tsc` type-check gate is wired beyond `vite build`
(esbuild transpiles without full type-checking); I relied on the clean build + reading for type
correctness. No linter is configured in the project. No deploy/Docker gate exists to run.
