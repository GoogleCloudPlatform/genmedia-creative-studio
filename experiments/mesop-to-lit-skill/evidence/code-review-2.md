# mesop-lit-rev-code2 — RE-REVIEW of fixes to the `mesop-to-lit` Skill + checklist slice

## Executive Summary
All prior merge-blocking findings (C1 Critical, H1 High) and all follow-ups (M1 Medium,
L1–L4 Low, plus security hardening F3/F4/F5) are genuinely resolved in both the converted
slice **and** the propagating skill recipes — verified by reading the actual code and by
running the gates (backend 15/15, frontend 16/16, build clean, analyzer clean). Risk level:
**LOW**. Verdict: **APPROVE**.

---

## Per-finding disposition

### C1 [CRITICAL] — Path traversal / arbitrary file read in SPA fallback — **RESOLVED**
`scratch/promptlandia-lit/main.py:104-114`. The handler now resolves the candidate with
`os.path.realpath(os.path.join(real_dist, full_path))` and serves it only if
`candidate == real_dist or candidate.startswith(real_dist + os.sep)` **and** it is a file;
otherwise it falls through to `index.html` (or a 404 envelope). `realpath` collapses `..`
before the containment test, so `../../main.py` resolves outside `WEB_DIST` and is rejected.
The containment logic is correct and I found no off-by-one:
- Root `index.html` — `/` gives `full_path=""`, skips the guarded block, serves index. ✔
- `/assets/*` — served by the `StaticFiles` mount (registered *before* the catch-all), which
  has its own traversal guard; unaffected. ✔
- Sibling-prefix escape (e.g. `web/dist-evil`) — blocked by the `+ os.sep` in `startswith`. ✔

**Regression test is real, not vacuous.** `tests/test_api_checklist.py:144-169`
(`test_spa_fallback_rejects_path_traversal`, 3 encoded params) runs against a live route —
`web/dist/index.html` exists, so the `if os.path.isdir(WEB_DIST)` route *is* registered. I
reconstructed the OLD vulnerable handler in a throwaway app and hit it with the same three
params: `/..%2F..%2Fmain.py` and `/%2e%2e%2f%2e%2e%2fmain.py` both returned **200 with the
backend source leaked** (`register_error_handlers`/`spa_fallback` present) — i.e. the test
would FAIL against the pre-fix code. The fixed code returns index.html for all three. (Minor
note under New Findings on the `/etc/passwd` param.)

**Both skill recipes fixed:** `references/assist-scaffold.md:80-106` ships the containment-
checked `main.py` recipe plus an explicit CWE-22 warning and the `StaticFiles(html=True)`
alternative; `references/serve-and-deploy.md:22-31` carries a matching SECURITY note.

### H1 [HIGH] — Inverted `JSONResponse` args in error-handler recipe — **RESOLVED**
`references/assist-endpoints.md:82-93`: all three handlers (`_v`/`_h`/`_u`) now use
`JSONResponse(status_code=..., content=...)` keyword args, with a "two must-get-right traps"
callout (lines 98-107) teaching both keyword-args and the `str(exc)` ban. The implemented
`api/errors.py:47-69` was already correct and remains so.

### M1 [MEDIUM] — 500 envelope leaked `str(exc)` — **RESOLVED**
`api/errors.py:60-69`: `_unhandled_handler` logs full detail via `logger.exception(...)`
server-side and returns a generic `"Internal server error"` to the client. Test updated —
`tests/test_api_checklist.py:104-105` asserts the message **equals** `"Internal server
error"` AND that `"Gemini exploded"` is **not** present. Skill recipe fixed identically
(`assist-endpoints.md:88-92`, trap #2).

### L1 [LOW] — Analyzer "key-bump" over-promise — **RESOLVED**
`scripts/analyze_mesop_app.py:60`: real detector added —
`CONSTRUCT_PATTERNS["key_bump_remount"] = r"_textarea_key|_key\s*\+\+"`. Docs now accurate:
`references/state-and-transport.md:60` and `references/analysis-method.md:46` describe the
key-bump flag, which the analyzer now actually emits.

### L2 [LOW] — Scratch workflow leaked into reusable reference — **RESOLVED**
`references/assist-testing.md:112,123`: "record the skip in RESULTS" / "paste into
RESULTS.md" generalized to "your conversion notes". No `RESULTS` references remain in the ref.

### L3 [LOW] — Dead code in analyzer — **RESOLVED**
`grep` finds no `_first_dir` and no `if ... in ("os","re","json"): pass` branch remaining;
both the overwritten `mods` comprehension and the no-op branch are gone. Analyzer still runs
clean (23 files, 0 parse errors) on the converted app.

### L4 [LOW] — `app-sidenav` md-list/ul redundancy + inaccurate comment — **RESOLVED**
`web/src/components/app-sidenav.ts:103-118` renders a plain native `<ul><li><a>` with no
`<md-list>` wrapper. Header comment (`:1-7`) now states the nav is built "from a plain native
<ul>/<a> list … (md-list wrapping a <ul> is redundant nested-list semantics, so it is not
used.)" — code and comment now agree.

---

## Regression checks (fixes introducing new defects)

- **F3 (CSP hardening) / frame-ancestors contract — intact.** `main.py:46-56` keeps
  `frame-ancestors 'self' https://google.github.io`; adds `base-uri 'self'`,
  `object-src 'none'`, `form-action 'self'`, narrows `img-src` to `'self' data:`.
  `test_csp_frame_ancestors_header` (now also asserting the new directives and the absence of
  wildcard `https:` in `img-src`) passes. The `img-src` assertion correctly isolates the
  directive (`split("img-src")[-1].split(";",1)[0]`) so the `https://` in `frame-ancestors`
  does not false-trip it.
- **F4 (HSTS) — safe.** `main.py:72-76` emits HSTS only when `x-forwarded-proto == "https"`,
  so plain-http dev/test requests are never pinned. No header test broken.
- **F5 (analyzer hardening) — no detection regression.** Symlink skip
  (`collect_py_files:178-182` + `_has_symlink_parent:157-166`) only drops symlinked paths —
  a normal app has none. Size cap (`read_text:187-192`, 5 MB) only skips pathological files —
  source is tiny. Confirmed by running the analyzer end-to-end on the converted app: clean,
  0 parse errors.
- **Containment off-by-one** — checked explicitly (see C1); none found.

## New Findings
- **FYI — one traversal test param cannot reach its stated target.** The
  `/..%2F..%2F..%2F..%2Fetc%2Fpasswd` param has only four `../` segments; `web/dist` sits far
  deeper than four levels above `/etc`, so even the *old* vulnerable code could never have
  served `/etc/passwd` from this param (my repro: `LEAKED=False` on old code for that one).
  The test's teeth come entirely from the two `main.py` params, which DO leak on old code —
  so the test is non-vacuous overall. No action required; if desired, deepen that param's
  `../` count so it is a genuine escape attempt rather than a defense-in-depth assertion.

## Test Coverage
Adequate and behavioral. The two prior gaps the earlier review named are closed: the SPA
fallback now has a negative traversal test, and the 500-envelope test now asserts a generic
message instead of locking in the leak. Playwright e2e remains intentionally skipped (brief-
permitted; style-src `'unsafe-inline'` drop and full-fidelity URL-scheme sanitization are
tracked as must-haves for the ship PR, per RESULTS.md §3/F3).

## Backward Compatibility
N/A — scratch app, no production wire contract. The 500-envelope message change is a
hardening of an internal/IAP-gated tool, not a breaking wire change (shape `{code, message}`
unchanged).

## Positive Feedback
- C1 fix is the minimal-correct one (realpath + containment) and is mirrored faithfully into
  both propagating recipes with a clear CWE-22 rationale and a safer `StaticFiles(html=True)`
  alternative — the lesson, not just the patch, propagates.
- The regression test uses percent-encoded variants that bypass client-side normalization,
  which is the actual attack vector; I verified it fails against the pre-fix code.
- M1/H1 recipe fixes include a "two traps" callout that teaches *why*, reducing recurrence.

## Final Verdict
**APPROVE.**

Gates run here (shared-plain workspace; project at
`/scion-volumes/scratchpad/projects/mesop-lit`):
- Backend `pytest` (`PROJECT_ID=test-project`, LLM mocked, no network) — **15 passed**, 1
  unrelated anyio deprecation warning.
- Frontend `npm run test` (Vitest + happy-dom) — **16 passed (4 files)**.
- Frontend `npm run build` (vite) — **clean, 94 modules**.
- Analyzer — runs clean on the converted app (23 files, 0 parse errors).
- Independent repro of the OLD handler confirming the traversal regression test is
  non-vacuous.

Gates not run: no `tsc` type-check gate is wired beyond `vite build` (esbuild transpiles
without full type-check); no linter configured in the project; no Docker/deploy gate exists.
No real cloud/network calls made. No files modified (regenerated `web/dist` is a build
artifact of the permitted build command).
