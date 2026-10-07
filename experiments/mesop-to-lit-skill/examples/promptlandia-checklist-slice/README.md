# Example: Promptlandia checklist slice (converted)

This is the **source** of the converted Promptlandia **checklist vertical slice** — the proof that
the `mesop-to-lit` skill works. It is the original Mesop app's checklist feature ported to the
target stack: a **FastAPI** JSON backend (`main.py` + `api/`, reusing the Mesop-free
`services/`/`models/`/`config/` seam) and a **Lit + Material 3 + Vite** frontend (`web/`).

> **Source only — build artifacts are intentionally excluded.** No `.venv/`, `node_modules/`,
> `web/dist/`, `__pycache__/`, `*.pyc`, or `.pytest_cache`. Recreate them with the commands below.

## What's here

```
promptlandia-checklist-slice/
  main.py                 # FastAPI app: static mount + safe SPA fallback + CSP/security headers
  api/                    # routes, pydantic schemas, DI providers, error-envelope handlers
  services/               # copied Mesop-free seam (checklist, improver, trimmer, llm_client)
  models/                 # domain models, parsers, prompts (copied verbatim from the Mesop app)
  config/                 # config/default.py (reads PROJECT_ID at import — see conftest)
  tests/                  # pytest: api, parsers, services (LLM mocked, no network)
  requirements.txt        # backend runtime + test deps (NO mesop)
  pyproject.toml          # requires-python >=3.11
  web/                    # Vite + Lit + Material 3 frontend (src/ + test/)
```

Only the **checklist** endpoint is wired; the other pages are router stubs and the extra copied
services (`improver`, `trimmer`) are present but not endpoint-wired — this is the mandated scope of
the scratch proof (see `../../evidence/RESULTS.md` §3).

## Reproduce the build & tests

### Backend — pytest (LLM mocked, no network)
```
cd promptlandia-checklist-slice
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PROJECT_ID=test-project python -m pytest -q
```
**Observed: 15 passed** (happy path, empty-prompt 422, missing-field 422, service-error envelope
500, parse-fallback 200 + `raw`, CSP `frame-ancestors`, 3 SPA path-traversal variants, plus
carried-over parser/service unit tests). `PROJECT_ID` is required because `config/default.py` reads
it at import (the test suite's `conftest.py` also sets a default).

### Frontend — Vitest components (happy-dom)
```
cd web
npm install
npm run test          # vitest run
```
**Observed: 16 passed** across `checklist-results`, `prompt-input`, `app-accordion`, and the
`md-markdown` sanitization test.

### Frontend — production build
```
cd web
npm run build         # vite build
```
**Observed: clean** — 94 modules transformed, no errors.

### Confirm no Mesop remains
```
grep -rnE "import mesop|from mesop" main.py api services models config tests
# -> no matches
```

**Acceptance gate (all green):** `pytest` passes **and** `vitest run` passes **and** `vite build`
succeeds. See `../../evidence/RESULTS.md` for the full outcome log and the G1–G7 gotchas this
conversion surfaced.
