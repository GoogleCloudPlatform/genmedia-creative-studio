# Security Review — mesop-to-lit skill + checklist-slice conversion

**Auditor:** `mesop-lit-rev-sec` (security-auditor)
**Date:** 2026-10-07
**Scope:** `scratch/promptlandia-lit/` (backend + frontend), `skill/mesop-to-lit/scripts/analyze_mesop_app.py`, `skill/mesop-to-lit/references/*`
**Method:** static read + local dynamic proof-of-concept (no cloud/network calls). Files were not modified.

---

## Verdict: **REQUEST CHANGES**

The primary XSS surface the brief worried about — untrusted LLM/markdown rendered in the browser — **is handled correctly and is safe** (marked → DOMPurify default config → `unsafeHTML`, consistently, with no un-sanitized `unsafeHTML` anywhere). Good.

However the audit found **one Critical, exploitable, confirmed vulnerability**: the single-service SPA fallback in `main.py` is an arbitrary-file-read (path traversal) that serves any file on the server (verified: `GET /..%2F..%2Fetc%2Fpasswd` → `/etc/passwd`). **Crucially, this insecure pattern is taught verbatim by the skill** (`assist-scaffold.md`, `serve-and-deploy.md`), so every future conversion inherits it. That alone blocks the PR. A Medium information-disclosure issue (raw exception text leaked to clients) is likewise both implemented *and* taught by the skill.

The manager (`mesop-lit-em`) was messaged with the Critical the moment it was confirmed.

### Summary of counts
- **Critical:** 1
- **High:** 0
- **Medium:** 1
- **Low:** 3
- **Info:** 2

---

## Must-fix before PR

| # | Sev | Finding | Location |
|---|-----|---------|----------|
| F1 | **Critical** | Path traversal → arbitrary file read in SPA fallback (also in skill recipe) | `main.py:76-84`; `references/assist-scaffold.md` §main.py; `references/serve-and-deploy.md` |
| F2 | **Medium** | 500 error envelope leaks raw `str(exc)` to the client (also in skill recipe) | `api/errors.py:59-65`; `references/assist-endpoints.md:86` |

## Follow-up (not blocking, schedule)

| # | Sev | Finding | Location |
|---|-----|---------|----------|
| F3 | Low | CSP hardening: `style-src 'unsafe-inline'`, broad `img-src https:`, missing `base-uri`/`object-src`/`form-action` | `main.py:40-47` |
| F4 | Low | No HSTS header for the HTTPS/Cloud Run deploy | `main.py:54-60`; `references/serve-and-deploy.md` |
| F5 | Low | Analyzer: unbounded file read + symlink-following walk on hostile input | `scripts/analyze_mesop_app.py:148-168` |

---

## Findings

### [CRITICAL] F1 — Path traversal / arbitrary file read in the SPA fallback

- **Location:** `scratch/promptlandia-lit/main.py:76-84` (the `spa_fallback` handler). Taught identically in `skill/mesop-to-lit/references/assist-scaffold.md` (the `main.py` recipe, `@app.get("/{full_path:path}")`) and `references/serve-and-deploy.md` ("unmatched non-API paths → `index.html`").
- **Description:** The catch-all route builds a filesystem path by joining user-controlled input directly onto the web-root and serves it with no containment check:
  ```python
  @app.get("/{full_path:path}")
  async def spa_fallback(full_path: str):
      candidate = os.path.join(WEB_DIST, full_path)
      if full_path and os.path.isfile(candidate):
          return FileResponse(candidate)      # <-- serves ANY file
  ```
  `os.path.join(WEB_DIST, "../../etc/passwd")` normalizes *out* of `WEB_DIST`. Starlette percent-decodes the path **before** routing and does not collapse `..`, so encoded traversal reaches the handler intact.
- **Impact:** Unauthenticated (the app has no auth in code; design §3.6 makes IAP *optional*) arbitrary file read of anything the service account can read: application source, a `.env` loaded by `load_dotenv` (PROJECT_ID and any other secrets), mounted secret volumes, GCP service-account key files, `/proc/self/environ`. That is a direct path to **credential theft / full compromise**, matching the Critical bar. Because the pattern ships in the skill, every converted app is born with this hole.
- **Proof of concept (verified locally with FastAPI TestClient, no network):**
  ```
  GET /..%2fsecret.txt            -> 200  "TOPSECRET"      (file outside web root)
  GET /%2e%2e%2fsecret.txt        -> 200  "TOPSECRET"
  GET /..%2F..%2Fetc%2Fpasswd     -> 200  "root:x:0:0:root:/root:/bin/bash..."
  ```
  (Plain `/../secret.txt` is normalized by the client and returns `index.html`; the percent-encoded variants bypass normalization and succeed.)
- **Recommendation:** Never serve a path derived from user input without verifying the *resolved* path stays inside the web root. Prefer delegating to `StaticFiles` (which has traversal protection) and reserve the custom handler for the index-only fallback:
  ```python
  from pathlib import Path

  WEB_DIST_PATH = Path(WEB_DIST).resolve()

  @app.get("/{full_path:path}")
  async def spa_fallback(full_path: str):
      index = WEB_DIST_PATH / "index.html"
      if full_path:
          candidate = (WEB_DIST_PATH / full_path).resolve()
          # containment check: candidate must be inside WEB_DIST
          if candidate.is_file() and WEB_DIST_PATH in candidate.parents:
              return FileResponse(candidate)
      if index.is_file():
          return FileResponse(index)
      return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "Not found"}})
  ```
  (`Path.resolve()` + the `WEB_DIST_PATH in candidate.parents` check is the load-bearing fix; `os.path.commonpath([WEB_DIST_PATH, candidate]) == str(WEB_DIST_PATH)` is an equivalent guard.) Even simpler and safer: mount the whole bundle with `app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="spa")` as the last mount and drop the hand-rolled handler. **The skill references MUST be corrected in the same change** so the fix propagates to future conversions.

---

### [MEDIUM] F2 — Internal exception text leaked to the client in the 500 envelope

- **Location:** `scratch/promptlandia-lit/api/errors.py:59-65`. Taught in `skill/mesop-to-lit/references/assist-endpoints.md:86` (`_envelope("internal_error", str(exc))`).
- **Description:** The catch-all exception handler returns the raw exception string to the client:
  ```python
  @app.exception_handler(Exception)
  async def _unhandled_handler(request, exc):
      logger.exception(...)
      return JSONResponse(status_code=500,
          content=_envelope("internal_error", str(exc) or "Internal server error"))
  ```
  Any unhandled service/LLM/SDK failure flows here. `google-genai` / Vertex exceptions routinely embed the GCP project ID, region, model ID, backend endpoint URLs, and quota/permission detail in their message; a bug could surface file paths or config values. The frontend then renders it verbatim (`page-checklist.ts:77` → `${e.code}: ${e.message}`).
- **Impact:** Information disclosure of server internals/infrastructure to the client — useful for reconnaissance and, depending on the exception, leaking config/identifiers. Not full compromise (no stack trace object is sent, and it is text only), hence Medium, but it is a bad default that the skill multiplies across every conversion.
- **Proof of concept:** Trigger any server-side failure (e.g. invalid `PROJECT_ID`/permissions so the Vertex client raises). Response body: `{"error":{"code":"internal_error","message":"<raw provider error incl. project/location/endpoint>"}}`.
- **Recommendation:** Log the detail server-side (already done via `logger.exception`) but return a generic message to the client; keep specific, safe messages only for exceptions you explicitly map:
  ```python
  @app.exception_handler(Exception)
  async def _unhandled_handler(request, exc):
      logger.exception("Unhandled error on %s", request.url.path)
      return JSONResponse(status_code=500,
          content=_envelope("internal_error", "Internal server error"))
  ```
  The validation (422) and `HTTPException` handlers are fine — their messages are intentionally client-facing. Fix `assist-endpoints.md:86` to show the generic message so the recipe teaches the secure default.

---

### [LOW] F3 — CSP hardening opportunities

- **Location:** `scratch/promptlandia-lit/main.py:40-47`.
- **Description:** The CSP is a solid baseline — `default-src 'self'`, `script-src 'self'` (no `unsafe-inline`/`unsafe-eval`), `connect-src 'self'` (limits exfiltration even under XSS), and a scoped `frame-ancestors 'self' https://google.github.io`. Residual weaknesses:
  - `style-src 'self' 'unsafe-inline'` — `unsafe-inline` for styles permits CSS injection (data exfil via CSS, UI redress). Lit shadow-DOM styles use constructable stylesheets and `theme.ts` uses the CSSOM (`style.setProperty`), neither of which needs `'unsafe-inline'`; DOMPurify also permits inline `style` attributes on sanitized markdown.
  - `img-src 'self' data: https:` allows images from *any* HTTPS host, so attacker-influenced markdown image URLs can beacon arbitrary third parties.
  - No `base-uri` (not covered by `default-src`; `<base>` injection can repoint relative URLs), no `object-src 'none'` (explicit), no `form-action 'self'`.
- **Impact:** Defense-in-depth only; no direct exploit given F1/XSS are the real risks and sanitization holds.
- **Recommendation:** Tighten to:
  ```
  default-src 'self'; base-uri 'self'; object-src 'none'; form-action 'self';
  img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self';
  connect-src 'self'; frame-ancestors 'self' https://google.github.io
  ```
  Drop `'unsafe-inline'` from `style-src` if feasible after confirming no inline `<style>`/style-attribute reliance (sanitized markdown may need `DOMPurify` configured to strip `style`). Keep `connect-src 'self'` — it is a genuine strength.

### [LOW] F4 — No HSTS header

- **Location:** `scratch/promptlandia-lit/main.py:54-60` (security-headers middleware); `references/serve-and-deploy.md` CSP section.
- **Description:** The middleware sets CSP, `X-Content-Type-Options`, and `Referrer-Policy`, but no `Strict-Transport-Security`. The target is Cloud Run (HTTPS).
- **Impact:** Minor; TLS downgrade / first-request-over-HTTP exposure. Defense-in-depth.
- **Recommendation:** Add `response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"` (and document it in the skill). Only emit when served over HTTPS.

### [LOW] F5 — Analyzer resource/symlink handling on hostile input

- **Location:** `skill/mesop-to-lit/scripts/analyze_mesop_app.py:148-168` (`collect_py_files`/`read_text`), and the many `rglob` walks.
- **Description:** The script is correctly **read-only** (uses `ast.parse`, never `eval`/`exec`/`compile`/shell; no `subprocess`; arguments are a directory path and output file paths only — confirmed across the file). On hostile input, however, it reads whole files into memory (`p.read_text()`) with no size cap and walks with `Path.rglob`, which can follow directory symlinks into unintended trees / loops, and regex-scans every line. This is a local developer tool pointed at a repo the operator already trusts, so impact is low (DoS/time via a crafted giant or symlink-looped tree).
- **Impact:** Low — local, self-inflicted; no code execution, no write, no traversal beyond what the operator points it at.
- **Recommendation:** Skip symlinked directories during the walk and cap per-file reads (e.g. read the first N MB, skip files above a threshold) so a pathological target cannot exhaust memory/time. Not required for merge.

---

## Explicit XSS / sanitization determination (brief's primary question)

**The XSS/sanitization path is SAFE.** Verified end-to-end:

- `web/src/components/md-markdown.ts:36-43` — the *only* `unsafeHTML` in the codebase — always runs `DOMPurify.sanitize(marked.parse(text))` before `unsafeHTML`. DOMPurify uses its **default configuration** (no `ADD_TAGS`/`ADD_ATTR`, no `RETURN_TRUSTED_TYPE`, no `ALLOW_UNKNOWN_PROTOCOLS`, no `WHOLE_DOCUMENT`/`FORCE_BODY` bypass surface), so `<script>`, event-handler attributes, and `javascript:` URIs are stripped. The config is not bypassable as written.
- Every place that renders untrusted LLM text routes through `<md-markdown>`: `checklist-results.ts` per-item detail (`:129`), category explanation (`:152`), and the parse-fallback raw text (`:169`). There is no direct `innerHTML`, no bare `unsafeHTML`, no `unsafeSVG`, and no `unsafeCSS(<dynamic>)` elsewhere. The raw-fallback code-fence wrapping (`'```\n' + raw + '\n```'`) cannot defeat sanitization — even if `raw` breaks the fence, the output is still DOMPurify-sanitized.
- Structured fields rendered as text (`humanize(issue_name)`, category names) use Lit text bindings (`${...}`), which auto-escape.
- Dropping Mesop's Trusted Types (`dangerously_disable_trusted_types`) is correctly **compensated by render-time sanitization**, exactly as design §8 requires, and `script-src 'self'` (no `unsafe-inline`/`unsafe-eval`) backstops it.

Residual nit (Info, not a finding): DOMPurify default permits `<a target>` without forcing `rel="noopener"`; marked doesn't emit `target` by default, so there is no current tabnabbing vector. If link `target` is ever enabled, add a DOMPurify `afterSanitizeAttributes` hook to force `rel="noopener noreferrer"`.

---

## Positive observations

- **Markdown sanitization is correct, centralized, and mandatory** — the single `md-markdown` helper is the one render path and it never skips DOMPurify. The skill (`assist-components.md`, `component-decisions.md`) repeatedly and correctly states "sanitize, always / DOMPurify is mandatory."
- **Secrets stay server-side.** `GET /api/config` (`routes_config.py:31-39`) exposes only `model_id`, `alternative_model_id`, `gemini_location` — no `PROJECT_ID`, no credentials. `config/default.py` keeps `PROJECT_ID` server-side; Vertex auth stays in `LLMClient`. Matches design §3.6 / `state-and-transport.md`.
- **No committed secrets.** No `.env`, key, or credential files in the slice; `conftest.py` uses a dummy `PROJECT_ID` and a mocked LLM client (no network in tests).
- **Strong transport-isolation CSP defaults** — `connect-src 'self'` and `script-src 'self'` meaningfully limit exfiltration/injection blast radius.
- **Input validation** via pydantic (`prompt: str = Field(min_length=1)`) with a uniform 422 envelope; no SQL/DB, no OS command execution, no `exec.Command`-equivalent, no shell anywhere in backend or analyzer.
- **Analyzer is genuinely read-only** and uses `ast.parse` (not `eval`/`exec`) — the brief's explicit concern is satisfied.
- **Retry/timeout posture preserved** — tenacity retry in the service layer; design preserves the 360s long-call timeout.

---

## Recommendations (proactive)

1. **Fix F1 in the skill recipes, not just the slice.** The `main.py`/SPA-fallback pattern in `assist-scaffold.md` and `serve-and-deploy.md` is the authoritative source every future conversion copies; ship the containment-checked version (or `StaticFiles(html=True)`) there with a one-line note on *why*.
2. **Add a "secure defaults" subsection to the skill** covering the three recurring traps this audit surfaced: (a) never serve user-derived paths without a resolved-path containment check; (b) never return raw exception text to clients; (c) a hardened CSP/HSTS header template. These are the security equivalents of the "Lit-under-test quirks" the skill already documents.
3. **Regression test the traversal fix** — add a backend test asserting `GET /..%2F..%2Fetc%2Fpasswd` (and a few encoded variants) returns `index.html`/404, never file contents. (For the manager/test-engineer to consider — surfaced as a recommendation, not an escalation.)
4. When `uv.lock` is generated for the real deploy (B12-7), run the project's dependency audit (`pip-audit` / `npm audit`) against the pinned set; the current pins (`fastapi 0.115.6`, `pydantic 2.10.4`, `google-genai 1.9.0`; `marked ^15`, `dompurify ^3.2.3`, `lit 3.3.3`) had no obvious known-vuln at review time, but a lockfile audit should gate releases.

---

*No files were modified during this audit. Dynamic checks were local only (FastAPI TestClient); no cloud or network calls were made.*
