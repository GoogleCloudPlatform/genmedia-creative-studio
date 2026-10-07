# RESULTS — Promptlandia checklist slice conversion (mesop → FastAPI + Lit + Vite + M3)

Converted the Promptlandia **checklist vertical slice** end-to-end into
`scratch/promptlandia-lit/` using the `mesop-to-lit` skill, and authored the skill's
ASSIST half from what the conversion actually required. This note records the exact
build/test commands + outcomes, the skill gaps found and how they were fixed, and the
deviations/limitations.

## 1. Build & test commands + outcomes (all PASS)

### Backend — pytest (LLM mocked, no network)
```
$ cd scratch/promptlandia-lit && source .venv/bin/activate && python -m pytest -q
............                                                              [100%]
12 passed, 1 warning in 0.95s
```
(The one warning is a Starlette `anyio` deprecation notice, not from our code.)
Covers: happy path, empty-prompt 422, missing-field 422, service-error envelope (500),
parse-fallback (200 + `raw`), CSP `frame-ancestors` header, plus carried-over parser and
service unit tests.

### Frontend components — Vitest + @open-wc (happy-dom)
```
$ cd scratch/promptlandia-lit/web && npm run test
 Test Files  3 passed (3)
      Tests  13 passed (13)
```
`checklist-results` (4: issue section, no-issue section, pluralization, parse-fallback),
`prompt-input` (5), `app-accordion` (4).

### Frontend build — vite build
```
$ cd scratch/promptlandia-lit/web && npm run build
✓ 94 modules transformed.
dist/index.html                   0.65 kB │ gzip:  0.41 kB
dist/assets/index-Ds8whooQ.css    0.61 kB │ gzip:  0.36 kB
dist/assets/index-D-9bTRCo.js   194.98 kB │ gzip: 59.40 kB
✓ built in 713ms
```

### No mesop
```
$ grep -rnE "import mesop|from mesop" api main.py services models config tests
NO mesop imports anywhere
```

**Acceptance: `vite build` succeeds AND pytest passes AND Lit component tests pass. ✅**

## 2. What the skill got WRONG or left unclear — and how I fixed it

The ASSESS half was accurate for *deciding* the conversion; it simply had no ASSIST half
(it was a stub). Beyond "author the missing references", the conversion surfaced concrete
gaps that the new ASSIST references now encode. Frank list:

### G1 — (biggest) Lit templates break under happy-dom when a nested template sits at the template ROOT
**Nothing in the skill warned about this, and it cost the most time.** A `TemplateResult`
placed directly at a template's root (no enclosing element) — e.g.
`render() { return html\`${a ? html\`...\` : nothing}\`; }` — is **mis-parsed by
happy-dom**: it commits as the literal text `<?>` (`&lt;?&gt;`) instead of the template,
**and shifts every binding after it**, so a later `.text=${str}` silently received an
object (→ `marked(): input ... [object Object]`). The component rendered perfectly in the
browser but its test shadow root was empty/garbled. The fallback branch happened to work
only because it was already wrapped in `<div class="fallback">`.
**Fix:** wrap every `html` body (and every helper's returned fragment, at every nesting
level) in a static container element so no bare `${nested-template}` is a root child.
Added as the central rule in `assist-components.md` §"Lit-under-test quirks" #2 and
cross-referenced from `assist-testing.md`.

### G2 — `@material/web` cannot be imported under happy-dom
Importing any `@material/web` component in a test (or any module a test imports) throws
`this.attachInternals is not a function` (happy-dom doesn't implement `attachInternals`).
The skill said "stable MWC only" but never said this makes MWC **untestable** in the unit
layer.
**Fix:** keep every unit-tested component **MWC-free** (native elements + bare
`<md-icon>glyph</md-icon>` tags) and register stable MWC **only in `main.ts`**, which tests
never import. Documented in `assist-scaffold.md` (pitfalls), `assist-components.md` (#1),
`assist-testing.md`.

### G3 — interpolated adjacent expressions inject the template's own whitespace
`Checklist found ${n}\n  ${plural}` renders `"Checklist found 1\n  issue"`; a
`textContent.includes("Checklist found 1 issue")` assertion then fails on invisible
whitespace. The skill's "no streaming → loading flag" guidance was right, but nothing
covered this rendering-text footgun.
**Fix:** build such phrases as a single JS string (`` `Checklist found ${n} ${plural}` ``).
Documented in `assist-components.md` #3.

### G4 — the service return type is lossy; the wire schema needs an explicit adapter
The skill said "mirror the service method signatures" but the checklist service returns
`ParsedChecklistResponse`, whose shape comes from a **lossy** markdown parser
(`parse_evaluation_markdown` reshapes raw per-issue JSON into markdown strings and **drops
`issue_name`/`severity`**). Mirroring it 1:1 would leak the loss and the JSON-in-state
shape. The design's §3.3 `ChecklistResponse` is the clean body.
**Fix:** write a `ChecklistResponse.from_parsed(parsed, raw)` classmethod that maps what
survives, sorts issues-first, and returns `raw` on parse failure — and **document the
lossiness in the schema docstring**. Generalized in `assist-endpoints.md` §"Schemas: adapt
at the boundary".

### G5 — `TestClient` re-raises server exceptions, hiding the error envelope
The error-envelope test (service raises → expect 500 envelope) fails unless the client is
`TestClient(app, raise_server_exceptions=False)`; otherwise the exception propagates before
the 500 handler shapes the body. Also: the parse-*fallback* is a **200** (model gave junk,
degrade gracefully), not an error — easy to conflate with the 500 case.
**Fix:** both documented in `assist-testing.md` (the two "subtleties that bite").

### G6 — config reads env at import time
`config/default.py` constructs `Default()` which reads `PROJECT_ID` from the environment at
import, so tests fail to import without it.
**Fix:** `os.environ.setdefault("PROJECT_ID", "test-project")` in `conftest.py` (no
network, LLM still mocked). Documented in `assist-scaffold.md` pitfalls + `assist-testing.md`.

### G7 — service needed an injectable client for mocking
`PromptChecklist` had to accept `client=None` so `app.dependency_overrides` could inject a
mocked `LLMClient`. The skill's state/transport ref implied a clean seam but didn't call
out the DI requirement.
**Fix:** `assist-endpoints.md` §"DI so tests can mock the LLM" states the service must take
an injectable client, and that adding an optional `client=None` is a legitimate minimal
seam fix (Promptlandia's already did).

### Minor / confirmations (no skill change needed, recorded for honesty)
- `tsconfig` must set `useDefineForClassFields: false` or Lit `@property` breaks — now in
  `assist-scaffold.md`.
- The ASSESS component decisions (checklist-results = Q5 custom; prompt-input = DRY-promote;
  app-accordion = `<details>`; sidenav = compose stable list, nav-drawer is labs→rejected)
  were **all correct** and were followed verbatim.

## 3. Deviations from the design docs + limitations

- **Python 3.11, not 3.14.** Per the brief (container has ≈3.11). `pyproject.toml` sets
  `requires-python = ">=3.11"`; the `serve-and-deploy.md` Dockerfile still shows 3.14 for
  the real deploy. The copied `services/`/`models/` run unchanged under 3.11 +
  google-genai 1.9.0.
- **Playwright e2e skipped.** Optional per the brief; the TestClient + component tests
  already cover the contracts (loading flag, error envelope, parse-fallback, markdown
  sanitization, theme tokens). `assist-testing.md` records how to add it (stub the API
  route with `page.route`, never a real LLM).
- **Deploy not built.** This is a scratch proof; no Dockerfile/Cloud Run wiring. The
  single-service `main.py` (static mount + SPA fallback + CSP) is in place and the deploy
  recipe is in `serve-and-deploy.md` + ASSIST step 5.
- **Scope = checklist slice only** (the mandatory scope). Other pages are `page-stub`s
  behind the real router table; the extra copied services (`improver`, `trimmer`) are
  present but not wired to endpoints — only the checklist endpoint was built.
- **`raw` typing.** Design §3.3 uses `raw` for the parse-fallback; the typed success path
  sets `raw: null`. The frontend `checklist-results` renders the fallback via `md-markdown`.

### Documented frontend coverage gaps (test-gate condition — acceptable for the scratch PoC, must-fix before fan-out)
The test review flagged three undocumented coverage gaps as "acceptable-for-scratch-but-
must-fix-before-fan-out." Recorded here plainly:
1. **`page-checklist.ts` (orchestration page) — untested.** The loading-flag toggle, the
   empty/loading send-guard, `onClear` reset, and the §3.5 error-envelope render
   (`${code}: ${message}`) have no unit coverage. It is unit-testable (mock the `client`
   module) and is the template every fan-out page reuses → **must-fix before fan-out.**
2. **`api/client.ts` envelope normalization — untested.** `request()` is the frontend half
   of the §3.5 contract (`ApiClientError`, the `network_error` catch, and the
   `unknown_error` fallback when a non-OK response has no `{error}` body). Zero coverage;
   stub `fetch` to cover all four paths → **must-fix before fan-out** (shared client).
3. **`md-markdown.ts` sanitization boundary — now partially closed.** A new Vitest test
   (`web/test/md-markdown.test.ts`) feeds hostile `<script>` / `<img onerror>` payloads and
   asserts the dangerous tag/attribute is stripped from the rendered shadow DOM. **Caveat:**
   happy-dom's DOM is not a faithful browser DOM, so DOMPurify's protocol-based URL filtering
   (e.g. `javascript:` hrefs) is not reproduced reliably under happy-dom — the test asserts
   only on the payloads that strip deterministically; full-fidelity URL-scheme coverage is
   left to the Playwright layer. The security review verified the real-browser path is SAFE.
- **Playwright e2e is skipped for the scratch PoC** (also noted above). It is the only layer
  that would exercise real MWC rendering, real-browser templates, the full
  fill→send→loading→result flow, and the full-fidelity markdown-sanitization URL filtering —
  tracked as a must-have for the real conversion / ship PR.

## 5. Quality-gate fixes (post-review pass, 2026-10-07)

Three quality-gate reviews (code, security, test) returned REQUEST CHANGES. All four MUST-FIX
items, all four LOW items, and the three security follow-ups were addressed in **both** the
converted slice **and** the propagating skill references.

### MUST-FIX (merge-blocking)
- **C1/F1 [CRITICAL] Path traversal / arbitrary-file-read in the SPA fallback.**
  `main.py` `spa_fallback` now resolves the candidate with `os.path.realpath` and serves it
  only if it is contained in `WEB_DIST` (`candidate == real_dist or candidate.startswith(
  real_dist + os.sep)`); otherwise it falls through to `index.html`/404. Verified the handler
  receives `../../main.py` intact (encoded `%2F`/`%2e` bypass client normalization) and the
  fix returns `index.html`, not the source. Regression test:
  `tests/test_api_checklist.py::test_spa_fallback_rejects_path_traversal` (3 encoded variants,
  incl. `/etc/passwd`). Skill recipes fixed: `references/assist-scaffold.md` (safe `main.py`
  recipe + explicit warning + the `StaticFiles(html=True)` alternative) and
  `references/serve-and-deploy.md` (SECURITY note on the fallback trap).
- **H1 [HIGH] Inverted `JSONResponse` args in the error-handler recipe.**
  `references/assist-endpoints.md` now uses `JSONResponse(status_code=..., content=...)` in all
  three handlers, with a "two traps" callout (keyword args + no `str(exc)`). (`api/errors.py`
  was already correct.)
- **M1/F2 [MEDIUM] 500 envelope leaked `str(exc)` to the client.**
  `api/errors.py` `_unhandled_handler` now returns a generic `"Internal server error"`; the
  full detail stays server-side via `logger.exception(...)`. Test updated
  (`test_checklist_service_error_envelope`) to assert the generic message AND that
  `"Gemini exploded"` is NOT present. Skill recipe `assist-endpoints.md` fixed the same way.
- **[TEST] Markdown-sanitization regression test + documented gaps.** New
  `web/test/md-markdown.test.ts` (3 tests, verified to FAIL when DOMPurify is bypassed).
  Coverage gaps documented in §3 above. `references/assist-testing.md` extended to tell future
  users to test the orchestration page, `api/client.ts` envelope normalization, and the
  markdown-sanitization boundary (with the happy-dom caveat).

### ALSO-FIX (LOW)
- **L1** Analyzer "key-bump" over-promise: added a real detector
  `CONSTRUCT_PATTERNS["key_bump_remount"] = r"_textarea_key|_key\s*\+\+"` (script + docs now
  consistent; verified it fires on GMCS → 12 matches).
- **L2** `references/assist-testing.md` generalized "record in RESULTS" / "paste into
  RESULTS.md" → "your conversion notes".
- **L3** Deleted dead code in `scripts/analyze_mesop_app.py`: the overwritten first `mods`
  comprehension (and the now-unused `_first_dir`) in `_dir_is_mesop_free`, and the no-op
  `if ... in ("os","re","json"): pass` branch in `_regex_extract`.
- **L4** `web/src/components/app-sidenav.ts`: dropped the redundant `<md-list>` wrapper around
  the native `<ul>` and corrected the header comment to match.

### SECURITY FOLLOW-UPS
- **F3** Hardened the CSP in `main.py` + `serve-and-deploy.md`: added `base-uri 'self'`,
  `object-src 'none'`, `form-action 'self'`; narrowed `img-src` to `'self' data:` (dropped the
  wildcard `https:`). Kept `frame-ancestors 'self' https://google.github.io` (design §8 — CSP
  test still passes). **Tradeoff tracked:** kept `style-src 'unsafe-inline'` — dropping it
  needs a browser/e2e pass (Lit/MWC constructable styles, DOMPurify-left inline `style` attrs)
  that this scratch env cannot run.
- **F4** Added HSTS (`Strict-Transport-Security: max-age=63072000; includeSubDomains`) to the
  security-headers middleware + the recipe, emitted only on HTTPS (`x-forwarded-proto`).
- **F5** Analyzer read-only hardening in `scripts/analyze_mesop_app.py`: skip symlinked files
  and files reached through symlinked dirs (`_has_symlink_parent`), and cap per-file reads at
  5 MB (`MAX_READ_BYTES`). Stdlib-only, still read-only; verified it still runs end-to-end on
  GMCS (routes=42, serve=fastapi-hybrid, parse_errors=2).

### Re-run acceptance (all green)
```
$ cd scratch/promptlandia-lit && PROJECT_ID=test-project .venv/bin/python -m pytest -q
15 passed, 1 warning in 0.95s        # 12 existing + 3 traversal params; envelope test updated

$ cd scratch/promptlandia-lit/web && npm run test
 Test Files  4 passed (4)
      Tests  16 passed (16)           # 13 existing + 3 md-markdown sanitization

$ cd scratch/promptlandia-lit/web && npm run build
✓ 94 modules transformed.
✓ built in 657ms

$ grep -rnE "import mesop|from mesop" scratch/promptlandia-lit/{main.py,api,services,models,config}
NONE (good)
```
The CSP `frame-ancestors` header test (`test_csp_frame_ancestors_header`) still passes after F3
(extended to also assert `base-uri 'self'`, `object-src 'none'`, and no wildcard `https:` in
`img-src`).

## 4. Where everything lives
- Converted app: `scratch/promptlandia-lit/` (backend root + `web/`).
- ASSIST skill refs: `skill/mesop-to-lit/references/assist-{scaffold,endpoints,components,testing}.md`
  + the filled ASSIST section in `skill/mesop-to-lit/SKILL.md`.
- Project log: `project-log/conv-dev.md`.
