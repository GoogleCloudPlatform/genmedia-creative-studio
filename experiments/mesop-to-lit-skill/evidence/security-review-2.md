# Security Re-Audit (Gate 2) — mesop-to-lit skill + checklist slice

**Auditor:** `mesop-lit-rev-sec2` (security-auditor)
**Date:** 2026-10-07
**Scope:** Focused re-audit of the fixes applied after `reviews/security-review.md`
(F1 Critical, F2 Medium, F3/F4/F5 Low) — confirm each is genuinely remediated, not
bypassable, with no new weakness and no regression to the XSS path.
**Method:** static read + local dynamic PoC (FastAPI TestClient, `raise_server_exceptions=False`).
No cloud/network calls. No files modified.

---

## Verdict: **APPROVE**

All five prior findings are **REMEDIATED** in both the converted slice *and* the
propagating skill recipes. The Critical path-traversal fix is non-bypassable under
every bypass class I tried (encoded dot-segments, mixed `%2F`, prefix-collision,
symlink, absolute `full_path`). The previously-SAFE XSS/sanitization path is
**unchanged and still safe**. No new findings at or above Low; one Info-level
residual noted. Nothing blocks the PR.

### Summary of counts (new issues this pass)
- Critical: 0
- High: 0
- Medium: 0
- Low: 0
- Info: 1 (residual, non-blocking)

---

## Per-finding verdicts

### F1 [CRITICAL] Path traversal / arbitrary file read — **REMEDIATED**

**Code:** `scratch/promptlandia-lit/main.py:104-111`. The handler now computes
`real_dist = os.path.realpath(WEB_DIST)`, resolves the candidate
`os.path.realpath(os.path.join(real_dist, full_path))`, and serves it only when
`candidate == real_dist or candidate.startswith(real_dist + os.sep)` **and**
`os.path.isfile(candidate)`; otherwise it falls through to `index.html` / a 404
envelope. This is the load-bearing containment pattern recommended in the prior review.

**Bypass attempts (all defeated — live TestClient PoC, handler confirmed active;
`web/dist/{index.html,assets}` exists so the route is registered):**
| Attack | Result |
|--------|--------|
| `/..%2F..%2Fmain.py` (encoded `../../`) | 200 → `index.html` (no `spa_fallback` in body) |
| `/%2e%2e%2f%2e%2e%2fetc%2fpasswd` (fully encoded dot-segments) | 200 → `index.html` (no `root:x:0:0`) |
| `/..%2F..%2F..%2Fetc%2Fpasswd` | 200 → `index.html` |
| `/index.html` (legit) | 200 → `index.html` (functionality intact) |

- **Encoded/mixed `%2e`/`%2F`:** `realpath` collapses `..` after Starlette decodes → escapes `real_dist` → rejected.
- **Prefix collision:** a sibling such as `web/dist-attacker/secret` does *not* satisfy `startswith(real_dist + os.sep)` because the separator is required (`/app/web/dist-attacker/...` ∌ `/app/web/dist/`). Correct.
- **Symlink:** `candidate` is realpath'd, so a symlink inside `dist` pointing outside resolves outside `real_dist` → rejected.
- **Absolute `full_path`:** `os.path.join(real_dist, "/etc/passwd")` discards the base → `/etc/passwd` → fails containment → rejected.

**Regression test:** `tests/test_api_checklist.py:144-169`
(`test_spa_fallback_rejects_path_traversal`, 3 encoded params incl. `/etc/passwd`)
asserts `spa_fallback`/`register_error_handlers`/`root:x:0:0` never appear in the body
and the response is `index.html` or a 404 envelope. It is **meaningful against the old
code**: the old `os.path.join(WEB_DIST, full_path)` + `FileResponse` would serve
`main.py`, so `assert "spa_fallback" not in resp.text` would fail. Backend suite:
**9 passed** (`tests/test_api_checklist.py`).

**Skill recipes — both fixed:**
- `references/assist-scaffold.md:80-106` — safe recipe with `realpath` + `startswith(real_dist + os.sep)` containment, an explicit CWE-22 warning, equivalent-guard notes (`commonpath`, `pathlib parents`), and the `StaticFiles(html=True)` alternative.
- `references/serve-and-deploy.md:22-30` — "the SPA fallback is a path-traversal trap" SECURITY callout pointing at the containment check and the full recipe.

### F2 [MEDIUM] Exception text leaked to client — **REMEDIATED**

**Code:** `api/errors.py:59-69`. The catch-all `_unhandled_handler` now logs detail
server-side (`logger.exception("Unhandled error on %s", request.url.path)`) and returns
a fixed `_envelope("internal_error", "Internal server error")`. No `str(exc)` reaches
the client. The `RequestValidationError` (422) and `StarletteHTTPException` handlers
retain intentionally client-facing messages (`str(exc.detail)`), which is correct — not a leak.

**Test:** `test_checklist_service_error_envelope` (`tests/test_api_checklist.py:90-105`)
asserts the body message equals `"Internal server error"` **and** that `"Gemini exploded"`
(the raised text) is absent. Passes.

**Skill recipe:** `references/assist-endpoints.md:91-105` — the 500 handler returns the
generic message, with a "two traps" callout: (1) keyword `status_code=`/`content=`,
(2) "Never echo `str(exc)` to the client."

### F3 [LOW] CSP hardening — **REMEDIATED**

**Code:** `main.py:46-56`. CSP now includes `base-uri 'self'`, `object-src 'none'`,
`form-action 'self'`, and narrowed `img-src 'self' data:` (wildcard `https:` dropped).
`script-src 'self'` and `connect-src 'self'` retained (strong exfil/injection limits);
`frame-ancestors 'self' https://google.github.io` preserved per design §8. The retained
`style-src 'unsafe-inline'` tradeoff is **reasonable and documented** (code comment
lines 42-45 + RESULTS.md §5): Lit/MWC constructable styles and DOMPurify-left inline
`style` attributes need a browser/e2e pass this env cannot run; with `script-src 'self'`
backstopping, residual CSS-injection risk is defense-in-depth only. Asserted by
`test_csp_frame_ancestors_header` (lines 130-138: `base-uri`, `object-src`, no wildcard
`https:` in `img-src`). Mirrored in `serve-and-deploy.md:73-83`.

### F4 [LOW] HSTS — **REMEDIATED**

**Code:** `main.py:69-76`. `Strict-Transport-Security: max-age=63072000; includeSubDomains`
is emitted, **HTTPS-gated** via `x-forwarded-proto`/`url.scheme == "https"` so it is never
pinned on plain-HTTP dev/test. `max-age` (2y) and `includeSubDomains` are sane; no
`preload` (appropriately conservative). Documented in `serve-and-deploy.md:85-87`.

### F5 [LOW] Analyzer hardening — **REMEDIATED**

**Code:** `scripts/analyze_mesop_app.py:154-199`.
- `collect_py_files` (the primary walk) skips symlinked files and any file under a
  symlinked parent (`p.is_symlink() or _has_symlink_parent(p, root)`) — prevents
  traversal/loops out of the operator-chosen tree.
- `read_text` caps reads at `MAX_READ_BYTES = 5 MB` (returns `""` above cap, `OSError`
  fail-safe) — prevents memory exhaustion. The cap applies to **all** `read_text`
  callers (Procfile/requirements/json/pyproject/etc.).
- Still read-only (`ast.parse`, regex; no `eval`/`exec`/`subprocess`/writes). No new issue.

`_has_symlink_parent` is fail-safe: if `root` is never matched it stops at the filesystem
root and returns `False` (no over-report, no crash).

---

## XSS path — still SAFE (explicit statement)

`web/src/components/md-markdown.ts` is **unchanged** and remains the single sink:
`marked.parse(...)` → `DOMPurify.sanitize(...)` (default config — no `ADD_TAGS`/`ADD_ATTR`,
no `ALLOW_UNKNOWN_PROTOCOLS`, no `RETURN_TRUSTED_TYPE`) → `unsafeHTML` (`md-markdown.ts:36-42`).
A repo-wide grep confirms `unsafeHTML` appears **only** in `md-markdown.ts`; there is no
`innerHTML`, `unsafeSVG`, or dynamic `unsafeCSS`. The new
`web/test/md-markdown.test.ts` **does not weaken** the boundary — it feeds hostile
`<script>` and `<img onerror>` payloads and asserts they are stripped from the shadow DOM,
with an honest documented happy-dom caveat that protocol-based (`javascript:`) URL filtering
is deferred to the Playwright layer (the behaviour under test is unchanged; the test is
additive). The XSS/sanitization path is safe.

---

## New findings

**None** at Low or above. One Info-level residual:

#### [INFO] Analyzer: symlinked-dir skip is only on the `.py` walk
- **Location:** `scripts/analyze_mesop_app.py` — `collect_py_files` skips symlinked
  parents, but the auxiliary `rglob` walks (Procfile:497, requirements.txt:543,
  uv.lock:557, pyproject.toml:573, `*.json`:628) can still descend symlinked
  directories.
- **Impact:** Negligible — those reads are size-capped by `read_text` (5 MB), the tool
  is read-only and local, pointed at a repo the operator already trusts. No traversal
  escape of consequence, no exhaustion.
- **Recommendation (optional, next sprint):** factor the `_has_symlink_parent` guard into
  a shared walk helper so every `rglob` consistently skips symlinked trees. Not required
  for merge.

---

## Positive observations

- F1 fix is implemented with the exact resolved-path containment the prior review
  prescribed, carries an explanatory CWE-22 comment, and is **propagated to both skill
  recipes** — future conversions inherit the safe pattern, closing the "insecure pattern
  taught verbatim" systemic risk that drove the Critical.
- Each fix ships with a regression test that is meaningful against the old code
  (traversal returns `index.html`, not source; envelope asserts the raw text is absent).
- HSTS is correctly HTTPS-gated rather than unconditionally pinned — a common footgun avoided.
- Tradeoffs that could not be fully closed in this environment (`style-src 'unsafe-inline'`,
  full-fidelity URL-scheme sanitization) are explicitly documented and tracked rather than
  silently accepted.

## Recommendations (proactive, non-blocking)

1. When `uv.lock` / `package-lock` are generated for the real deploy, gate releases on
   `pip-audit` / `npm audit` against the pinned set (carried over from the prior review).
2. Consider the Info-level shared symlink-walk helper above.
3. Keep the Playwright e2e job that covers `javascript:`-URL sanitization and real MWC
   rendering on the must-have list for the ship PR (already tracked in RESULTS.md).

---

*No files were modified. Dynamic checks were local only (FastAPI TestClient); no cloud or
network calls were made. Backend suite re-run: 9 passed.*
