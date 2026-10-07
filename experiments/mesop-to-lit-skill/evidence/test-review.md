# Test/QA Review — mesop-to-lit Skill + checklist-slice conversion

**Reviewer:** Test Engineer (QA)
**Date:** 2026-10-07
**Scope reviewed:** backend `tests/`, frontend `web/test/`, the analyzer validation in
`validation/`, and the skill's test guidance `references/assist-testing.md`.

---

## Overall verdict: **APPROVE** (for a reference/scratch PoC)

The three acceptance gates all pass on a clean run (reproduced below). The backend suite
correctly covers all six contracts the plan and `assist-testing.md` call for, with correct
mocking (LLM mocked at the client boundary, no network). The frontend component tests
meaningfully exercise `checklist-results`, `prompt-input`, and `app-accordion`, and the
G1/G2 happy-dom quirks are handled honestly (components are genuinely MWC-free — verified
`@material/web` is imported only in `main.ts`, which no test imports). The analyzer
validation methodology is sound and reproducible.

The approval is **scoped to a reference/scratch PoC**. Three real coverage gaps
(`page-checklist.ts`, `api/client.ts`, `md-markdown.ts` sanitization) are currently
**undocumented**. They are acceptable as *documented* limitations for this scratch proof,
but each becomes a **must-fix before the pattern fans out to other pages or a ship PR** —
and the one security-relevant gap (markdown sanitization) is cheap enough that I recommend
adding it now. Condition of approval: record the undocumented gaps in `RESULTS.md §3`.

---

## Confirmed test results (observed, this run)

### Backend — `PROJECT_ID=test-project .venv/bin/python -m pytest -q`
```
............                                                              [100%]
12 passed, 1 warning in 1.06s
```
(The single warning is Starlette's `anyio.abc.BlockingPortal` deprecation — not from app code.)

### Frontend components — `npm run test`
```
 ✓ test/prompt-input.test.ts    (5 tests)
 ✓ test/app-accordion.test.ts   (4 tests)
 ✓ test/checklist-results.test.ts (4 tests)
 Test Files  3 passed (3)
      Tests  13 passed (13)
```

### Frontend build — `npm run build`
```
✓ 94 modules transformed.
dist/assets/index-D-9bTRCo.js  194.98 kB │ gzip: 59.40 kB
✓ built in 848ms
```

**All three gates green — matches the counts claimed in `RESULTS.md §1`.**

---

## What the backend tests actually cover (verified against the source)

All six contracts from `assist-testing.md` are present and correct:

| Contract | Test | Correct? |
|---|---|---|
| Happy path | `test_checklist_happy_path` | ✅ Uses the **real** `PromptChecklist(client=mock_client)`, so it exercises the real parse pipeline end-to-end. Asserts flagged category + nested item, no-issue category, issues-sorted-first, and `generate_content` called exactly once. |
| Empty-prompt 422 | `test_checklist_empty_prompt_422` | ✅ Asserts `error.code == "validation_error"` **and** that the LLM was never called. |
| Missing-field 422 | `test_checklist_missing_field_422` | ✅ (Does not assert LLM-never-called — minor.) |
| Service-error envelope 500 | `test_checklist_service_error_envelope` | ✅ Correctly uses `TestClient(app, raise_server_exceptions=False)` (G5) so the 500 handler shapes the envelope. |
| Parse-fallback 200 + raw | `test_checklist_parse_fallback` | ✅ Asserted **separately** from the 500 case (G5) — 200, `categories == []`, `raw` carried. |
| CSP header | `test_csp_frame_ancestors_header` | ✅ `frame-ancestors 'self' https://google.github.io` present on `/api/healthz`. |

Plus carried-over unit tests: `test_parsers.py` (2) guards the unchanged parse pipeline, and
`test_services_checklist.py` (4) covers the service + the `ChecklistResponse.from_parsed`
adapter (incl. the lossy/fallback paths, G4). **Mocks are correct**: LLM mocked via
`MagicMock(spec=GenerateContentResponse)` injected through `app.dependency_overrides` or
direct constructor injection (G7); `PROJECT_ID` set in `conftest.py` (G6). No network.

**No false confidence found in the backend layer.** The one minor note: the 500 and
fallback tests use hand-written stub services (`BoomService`, `FallbackService`) rather than
driving the real `PromptChecklist`, so the route's handling is proven but the real service's
own exception path to the envelope is not exercised end-to-end. Acceptable.

## What the component tests cover

- **`checklist-results`** (4): issue section (humanized name, `flag` icon, nested item),
  no-issue section (`check_circle`), pluralization (1 issue vs 2 issues, the G3 whitespace
  footgun), and the parse-fallback path (renders `raw` via `md-markdown`). Meaningful.
- **`prompt-input`** (5): placeholder parity, `value-changed`, `send` with value, `clear`,
  and the `disabled` guard (no `send` when disabled). Meaningful.
- **`app-accordion`** (4): heading + slot, closed-by-default, `open` reflection, `toggle`
  emission. Meaningful.

**Documented false-confidence limits (inherent to the happy-dom layer, G1/G2):** because
`@material/web` is untestable under happy-dom, the components are MWC-free and the tests
assert on bare `<md-icon>glyph</md-icon>` *text* — they confirm the correct glyph name is
emitted, but **not** that the real MWC element renders. Likewise the G1 static-container
workaround means the tested DOM shape is the test-harness shape, not necessarily the
browser's natural render. Both push "does it actually render in a browser" out of the unit
layer and onto the (skipped) Playwright layer. This is honest and documented in
`assist-components.md`/`assist-testing.md`, but it means the e2e layer is doing more
load-bearing work here than in a typical pyramid.

---

## Coverage gaps (ranked)

### 🔴 High — `page-checklist.ts` is entirely untested
The orchestration component implements two contracts the plan says must be frozen before
fan-out (acceptance #5): the **loading-state flag** and the **§3.5 error-envelope
rendering**. None of it is covered — the empty/loading `onSend` guard, `onClear` reset,
error string formatting (`${code}: ${message}`), and the `result → checklist-results`
wiring. Its only possible coverage is the skipped Playwright e2e.
- **Recommendation:** add a `page-checklist` component test (mock the `client` module) for
  loading toggles, error render from an `ApiClientError`, and the send-guard. It is
  unit-testable without a browser.
- **Disposition:** acceptable as a *documented* limitation for the scratch PoC; **must-fix
  before fan-out** (this is the page whose contracts every other page reuses).

### 🔴 High — `api/client.ts` error-envelope normalization is untested
`request()` is pure logic (mockable at the `fetch` boundary) and is the frontend half of the
§3.5 contract: `ApiClientError`, the `network_error` catch, and the `unknown_error` fallback
when a non-OK response has no `{error}` body. Zero coverage.
- **Recommendation:** unit-test with a stubbed `fetch` — one happy case, one enveloped-error
  case, one envelope-less non-OK (→ `unknown_error`), one thrown-fetch (→ `network_error`).
- **Disposition:** acceptable-documented for scratch; **must-fix before fan-out** (shared client).

### 🔴 High (security-relevant) — `md-markdown.ts` sanitization is untested
`marked` + `DOMPurify` is the XSS boundary that replaces Mesop's 28× `me.markdown` (§8). No
test proves DOMPurify actually strips a `<script>`/`onerror=` payload — the fallback test
only renders benign text.
- **Recommendation:** add one test feeding `md-markdown` a `<img src=x onerror=...>` /
  `<script>` string and asserting the dangerous attribute/tag is gone. Cheap, high value.
- **Disposition:** I recommend **adding this now** even for the scratch PoC — it is the only
  security-boundary with zero verification; at minimum it is a must-fix before ship.

### 🟡 Medium — Playwright e2e skipped
Documented in `RESULTS.md §3` and `assist-testing.md` (stub `POST /api/checklist` via
`page.route`, never a real LLM). The plan (P1.6, acceptance #4) wants all layers green in CI.
Given the G1/G2 limits above, e2e is the *only* layer that would exercise real MWC rendering,
real-browser template rendering, and the full fill→send→loading→result flow.
- **Disposition:** acceptable as a documented limitation for a scratch proof; **tracked
  must-have for the real conversion / ship PR** (it is the designed template for the fan-out).

### 🟡 Medium — serve integration / SPA deep-link fallback untested
`main.py`'s `spa_fallback` (static-file-or-index routing + the 404 envelope) and plan P1.3's
"prove deep link `/checklist` loads from a cold container" (acceptance #2) have no test.
- **Recommendation:** a `TestClient` test against a built `web/dist` asserting a deep link
  returns `index.html` and an unknown API path returns the 404 envelope.
- **Disposition:** acceptable-documented for scratch; recommended before ship.

### 🟢 Low — `theme.ts` (system-default + toggle) and `router.ts` untested
Theme is acceptance #3; low-risk, unit-coverable (matchMedia + toggle state). Router table is
mostly declarative. Acceptable as documented limitations.

### 🟢 Low — `GET /api/config` untested; CSP test is partial
`/api/config` is out of the slice scope (Settings is Phase 2) — fine. The CSP test checks
only `frame-ancestors`, not the `X-Content-Type-Options: nosniff` / `Referrer-Policy` headers
`main.py` also sets. Add two asserts for completeness. Low.

---

## Analyzer-validation methodology: **sound and reproducible**

The `validation/` method (run the analyzer read-only, diff its output **line-by-line**
against pre-existing investigator ground truth) is a legitimate validation design:

- **Independent mechanical oracle.** The 20/20 (promptlandia) and 18/18 (babel) construct
  counts are cross-checked against raw `grep -c` — an oracle independent of both the analyzer
  and the human inventory. The GMCS ROOT-column analysis even proves the *ground truth* wrong
  by reproducing both the excluded and un-excluded greps exactly. That is strong.
- **Difficulty spread.** Three apps of escalating hardness (promptlandia reference → babel
  no-GenAI FastAPI-hybrid → GMCS flagship with upload/IAP/Cloud Tasks/Firestore), not just
  the reference — this tests generalization, not just memorization.
- **Robustness proven by effects.** PEP 701 f-string parse-failures (babel 6, GMCS 2)
  recovered via regex fallback; the proof ("would read 1 stateclass not 5 if fallback
  failed") is a real falsifiable check, and it caught a genuine 1→5 undercount bug.
- **Honest about misses.** Self-reports the 2 one-band difficulty overshoots, the GMCS
  websocket soft-positive (a comment), and the ground-truth matrix mislabeling — none
  silently passed.
- **Reproducible.** Exact commands, read-only targets, `parse_errors` reported, artifacts
  checked in (`*-assessment.{json,md}`).

**Caveats (do not block, worth noting):**
1. *Not a blind oracle for the structural claims.* Ground truth and analyzer are from the same
   project; the mechanical `grep` cross-check mitigates this for counts, but the A1–A6
   structural verdicts rely on the same team's reading. Low risk, but it is confirmation-prone.
2. *No negative control.* All three targets are real Mesop apps — there is no test that the
   analyzer behaves on a non-Mesop/empty tree, and line-based detection has a documented
   soft-positive (presence reliable, interpretation needs a human glance).
3. *Point-in-time, not a regression test.* The diffs live in markdown; nothing re-runs them
   if the analyzer changes. Reproducible by hand, but not CI-gated.
4. *Validates ASSESS, not the ASSIST conversion.* The conversion's correctness rests on the
   test suite above, not on this analyzer validation — the two are separate and should not be
   conflated.

---

## `assist-testing.md` guidance: correct and near-complete

The pyramid it teaches is right: TestClient (happy/422/error-envelope/parse-fallback/CSP),
@open-wc component tests, optional Playwright. It correctly encodes the two subtleties that
bite (G5 `raise_server_exceptions=False`; parse-fallback = 200 ≠ 500) and the G1/G2/G3
happy-dom quirks. **Gap in the guidance itself:** it does not mention testing the
orchestration page (`page-checklist`), the `api/client.ts` envelope normalization, or the
`md-markdown` sanitization boundary — the same three High gaps found in the slice. Recommend
adding those three to the reference so the fan-out pages inherit them.

---

## Recommendations for the manager (surfaced, not actioned — outside test scope)

- **Error envelope leaks the raw exception string to the client.** `api/errors.py`
  `_unhandled_handler` returns `str(exc)` (test asserts `"Gemini exploded"` reaches the
  client body). This is an information-disclosure concern — worth a security-auditor glance
  before ship. Reported, not fixed.

---

## Bottom line

For a scratch/reference PoC whose primary deliverable is the skill references, the test work
is **solid and honest**: gates green, backend contracts fully and correctly covered, components
meaningfully tested, and the validation methodology sound. **APPROVE**, conditioned on
documenting the three currently-undocumented High gaps (`page-checklist`, `client.ts`,
`md-markdown` sanitization) in `RESULTS.md`, adding the markdown-sanitization test now, and
tracking all High/Medium gaps as must-fix before this pattern fans out or ships.
