# Assist: the test pyramid (TestClient + @open-wc + Playwright)

The tests that prove the conversion, at the lowest level that captures each behavior.
**Mock the LLM at the client boundary — never a real Vertex/Gemini call anywhere.** The
conversion stood up: backend pytest (FastAPI `TestClient` + carried-over unit tests) and
frontend Vitest (`@open-wc/testing-helpers`, happy-dom). Playwright is optional.

## Backend: FastAPI `TestClient`, LLM mocked
Mock at the **client boundary** (`generate_content`), inject via `dependency_overrides`.
The canned LLM output is a markdown string the **unchanged** parser turns into one
with-issue + one no-issue category — so the test exercises the real parse pipeline, not a
stub of it.

`conftest.py`:
```python
os.environ.setdefault("PROJECT_ID", "test-project")   # config reads env at import

CANNED_CHECKLIST_MD = """# Prompt analysis for Clarity
```json
{"issue_name": "...", "location_in_prompt": "...", "rationale": "...vague...", ...}
```
# Prompt analysis for Typos
Issue not present in the prompt.
"""

@pytest.fixture
def mock_client(...):
    client = MagicMock()
    resp = MagicMock(spec=GenerateContentResponse)   # match the existing Mesop test pattern
    resp.text = CANNED_CHECKLIST_MD
    client.generate_content.return_value = resp
    return client
```

`test_api_checklist.py`:
```python
@pytest.fixture
def client(): return TestClient(app, raise_server_exceptions=False)  # let 500 handler run
def _override(svc): app.dependency_overrides[get_checklist_service] = lambda: svc
def teardown_function(): app.dependency_overrides.clear()
```
The five cases that matter (one per contract):

| Test | Setup | Asserts |
|---|---|---|
| happy path | `PromptChecklist(client=mock_client)` | 200; issue category flagged + item; no-issue category; issues sorted first; `generate_content` called once |
| empty prompt | `prompt=""` | 422, `error.code == "validation_error"`; **LLM never called** |
| missing field | `{}` | 422 envelope |
| service error | service raises `RuntimeError` | 500, `error.code == "internal_error"`, message carried |
| parse-fallback | service returns `(None, raw)` | 200, `categories == []`, `raw == <text>` |
| CSP header | `GET /api/healthz` | `frame-ancestors 'self' https://google.github.io` present |

Two subtleties that bite:
- Use `raise_server_exceptions=False` or the `TestClient` re-raises before your 500 handler
  can shape the envelope — the error-envelope test fails without it.
- The parse-fallback is a **200**, not an error. Assert it separately from the envelope
  cases or you will conflate "model gave junk" (expected, degrade gracefully) with "server
  broke" (500).

Carry over the Mesop app's existing **parser/service unit tests** that apply to the slice
(`test_parsers.py`, `test_services_checklist.py`) — they run unchanged against the copied
`models/`/`services/` and guard the pipeline the API depends on.

## Frontend: Vitest + `@open-wc/testing-helpers` (happy-dom)
`vite.config.ts` carries the test env (`environment: 'happy-dom', globals: true`). Mount
with `fixture`, `await el.updateComplete`, assert on the shadow root.

### Testing with Web Awesome (Default)
When using Web Awesome, import `element-internals-polyfill` in your test files or test setup:
```ts
import 'element-internals-polyfill';
import { describe, it, expect } from 'vitest';
import { html, fixture } from '@open-wc/testing-helpers';
import '@awesome.me/webawesome/dist/components/button/button.js';
import '@awesome.me/webawesome/dist/components/details/details.js';
```
With the polyfill, Web Awesome form controls and elements render and pass directly in happy-dom.

### Testing with Material Web (Opt-in)
Do **not** import `@material/web` from any unit test (or any module a test imports) — it throws
`attachInternals is not a function` under happy-dom. Test MWC-free components; use bare
`<md-icon>` tags and register MWC exclusively in `main.ts`.
Cover per the design: `checklist-results` (issue + no-issue + parse-fallback),
`prompt-input` (emits `value-changed`/`send`/`clear`, respects `disabled`), `app-accordion`
(reflects `open`, emits `toggle`).

**Do not stop at the leaf components — these three carry the contracts every page reuses:**
- **The orchestration page** (`page-<feature>.ts`): mock the `client` module and test the
  loading-flag toggle (send → loading on → result → loading off), the empty/loading send-guard,
  `onClear` reset, and the §3.5 error render (`ApiClientError` → `${code}: ${message}`). It is
  unit-testable without a browser; it is the template the fan-out pages copy.
- **`api/client.ts` envelope normalization:** stub `fetch` and assert the four paths — a happy
  response, an enveloped error (`ApiClientError` with the server `{code, message}`), a non-OK
  response with **no** `{error}` body (→ `unknown_error`), and a thrown fetch (→ `network_error`).
- **The markdown-sanitization boundary** (`md-markdown.ts`): feed a hostile payload
  (`<script>…</script>`, `<img src=x onerror=…>`) and assert the dangerous tag/attribute is
  gone from the rendered shadow DOM. This is the XSS boundary that replaces Mesop's `me.markdown`
  — the only security-critical render path, so prove it. **Caveat:** happy-dom's DOM is not a
  faithful browser DOM, so DOMPurify's protocol-based URL filtering (e.g. `javascript:` hrefs)
  is not reproduced reliably under happy-dom; assert on the payloads that strip deterministically
  (`<script>`, event-handler attrs) and push full-fidelity URL-scheme coverage to the Playwright
  layer.

**The happy-dom quirks in `assist-components.md` are test-discovered — they surface here
first.** When a component renders fine in `npm run dev` but its test shadow root is empty,
`<!---->`, or contains `&lt;?&gt;`, it is the **root-level-nested-template** quirk, not a
test bug: wrap the component's template body in a static container element. When an
assertion fails on an invisible space in an interpolated phrase, it is the
**template-whitespace** quirk: build the phrase as one JS string. Debug by printing
`el.shadowRoot!.innerHTML` (and a minimal reproduction component) rather than trusting
`textContent`.

Do **not** import `@material/web` from any test (or any module a test imports) — it throws
`attachInternals is not a function` under happy-dom. Test MWC-free components; use bare
`<md-icon>` tags and assert on their text content.

## E2E: Playwright (optional)
Mirror the Mesop page's smoke test (`test_checklist_page`): load `/checklist`, type a
prompt, stub `POST /api/checklist` via `page.route(...)` (still no real LLM), click send,
assert `checklist-results` shows the categories and the loading spinner cleared. Skip if
the toolchain/time is tight — the TestClient + component tests already cover the contracts;
record the skip in your conversion notes.

## Verify-everything commands (the acceptance gate)
```
# backend
cd <app> && python -m pytest -q
# frontend
cd <app>/web && npm run test        # vitest run
cd <app>/web && npm run build       # vite build must succeed
```
All three green = the slice is proven. Run them before marking the task complete; paste the
summaries into your conversion notes.
