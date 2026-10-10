# Example: Promptlandia checklist slice (Web Awesome spike)

This is the **Web Awesome reference spike** of the converted Promptlandia **checklist vertical slice** — demonstrating and validating the Web Awesome default option for the `mesop-to-lit` conversion skill. It converts the original Mesop app's checklist feature to:
- A **FastAPI** JSON backend (`main.py` + `api/`, reusing the Mesop-free `services/`/`models/`/`config/` seam).
- A **Lit + Web Awesome (`@awesome.me/webawesome` 3.14.0) + Vite** frontend (`web/`).

> **Source only — build artifacts are intentionally excluded.** No `.venv/`, `node_modules/`,
> `web/dist/`, `__pycache__/`, `*.pyc`, or `.pytest_cache`. Recreate them with the commands below.

## Why Web Awesome

1. **Active Maintenance:** `@material/web` 2.5.0 is in maintenance mode with missing stable components. Web Awesome is actively maintained, MIT licensed, and built on Lit.
2. **Stock Accordion & Drawer:** Replaces custom expansion panels and nav drawers with stock `<wa-details>` / `<wa-accordion>` and `<wa-drawer>`.
3. **Happy-dom Compatibility:** Form-associated Web Awesome components test cleanly with `@open-wc/testing-helpers` and `happy-dom` when using `element-internals-polyfill`.

## What's here

```
promptlandia-checklist-slice-webawesome/
  main.py                 # FastAPI app: static mount + safe SPA fallback + CSP/security headers
  api/                    # routes, pydantic schemas, DI providers, error-envelope handlers
  services/               # copied Mesop-free seam (checklist, improver, trimmer, llm_client)
  models/                 # domain models, parsers, prompts (copied verbatim from the Mesop app)
  config/                 # config/default.py (reads PROJECT_ID at import — see conftest)
  tests/                  # pytest: api, parsers, services (LLM mocked, no network)
  requirements.txt        # backend runtime + test deps (NO mesop)
  pyproject.toml          # requires-python >=3.11
  web/                    # Vite + Lit + Web Awesome frontend (src/ + test/)
```

## Reproduce the build & tests

### Backend — pytest (LLM mocked, no network)
```bash
cd promptlandia-checklist-slice-webawesome
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PROJECT_ID=test-project python -m pytest -q
```
**Observed: 15 passed** (happy path, empty-prompt 422, missing-field 422, service-error envelope
500, parse-fallback 200 + `raw`, CSP `frame-ancestors`, 3 SPA path-traversal variants, plus
carried-over parser/service unit tests).

### Frontend — Vitest components (happy-dom)
```bash
cd web
npm install
npm run test          # vitest run
```
**Observed: 19 passed** across `checklist-results`, `prompt-input`, `app-accordion`, `wa-details` (Web Awesome native accordion), and `md-markdown`.

### Frontend — production build
```bash
cd web
npm run build         # vite build
```
**Observed: clean** — 108 modules transformed, 0 errors, gzip JS 82.27 kB.

### Confirm no Mesop remains
```bash
grep -rnE "import mesop|from mesop" main.py api services models config tests
# -> no matches
```

**Acceptance gate (all green):** `pytest` passes **and** `vitest run` passes **and** `vite build` succeeds.
