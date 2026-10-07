# Assist: scaffold the FastAPI `api/` + Vite/Lit `web/` target

The concrete directory + file recipe for the converted app, in the order you create
it. Produces a **single-service** layout (FastAPI serves `/api/*` and the built Vite
bundle — see `serve-and-deploy.md`). Everything here was executed converting
Promptlandia's checklist slice; the pins and quirks are the ones that actually worked.

## Pins (do not drift)
- Frontend: **lit 3.3.3**, **`@material/web` 2.5.0** (maintenance mode — stable only),
  **`@vaadin/router` 2.0.1**, `marked` + `dompurify` for the markdown helper.
- Dev/test: `vite ^5`, `vitest ^2`, `happy-dom`, `@open-wc/testing-helpers`,
  `typescript ^5`.
- Backend: `fastapi`, `uvicorn[standard]`, `gunicorn`, `pydantic`, plus the app's own
  LLM deps (`google-genai`, `tenacity`, `python-dotenv`). **No `mesop`.**
- Toolchain reality: target the Python you actually have (3.11 is fine for a proof;
  do not hard-require 3.14). Node 20+.

## Target tree
```
<app>/
  main.py                 # ASGI entrypoint (replaces app:me)
  pyproject.toml          # pytest pythonpath=["."], testpaths=["tests"]
  requirements.txt        # pinned; NO mesop
  api/
    __init__.py
    schemas.py            # pydantic request/response (§3.3)
    deps.py               # DI: constructs services with an injectable client
    errors.py             # register_error_handlers(app) -> uniform envelope
    routes_actions.py     # POST /api/<action> per service method
    routes_config.py      # GET /api/healthz (+ /api/config if needed)
  services/  models/  config/   # COPIED verbatim from the Mesop app (unchanged)
  tests/
    conftest.py           # canned LLM output + mock_client fixture
    test_api_*.py         # FastAPI TestClient
    test_services_*.py test_parsers_*.py   # carried-over unit tests
  web/
    index.html  vite.config.ts  tsconfig.json  package.json
    src/
      main.ts             # browser entry: register MWC + applyTheme + components
      app-root.ts         # shell: sidenav + <main> router outlet
      router.ts  theme.ts  global.css
      api/ client.ts types.ts
      components/ ...      # custom + shared Lit elements
      pages/ page-*.ts
    test/ *.test.ts       # Vitest + @open-wc
```

## Step order (each step independently verifiable)
1. **Copy the seam.** `cp -r` the app's `services/`, `models/`, `config/` into the new
   tree. Grep them for `import mesop` / `me\.` — if clean (Promptlandia's are), they run
   as-is. If not, that is a "no seam" task (see `hard-topics.md`), do it first.
2. **Backend shell.** `main.py` + `api/`. Verify with `pytest` before any frontend work.
3. **Frontend shell.** `package.json` → `npm install` → `index.html` + `vite.config.ts`
   + `tsconfig.json` + `src/main.ts` + `app-root.ts` + `router.ts` + `theme.ts`. Verify
   with `vite build` (empty pages are fine).
4. **Components + pages** in build order (see `assist-components.md`).
5. **Tests** alongside each component (see `assist-testing.md`).

## `main.py` (single-service entrypoint)
Order is load-bearing: **register error handlers → middleware → API routers → static
mount + SPA fallback LAST**. Guard the static mount with `os.path.isdir(dist)` so the
backend tests run before any frontend build exists.
```python
app = FastAPI(...)
register_error_handlers(app)

@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = _CSP   # incl. frame-ancestors (§8)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp

app.include_router(config_router)     # /api/healthz first
app.include_router(actions_router)    # /api/<action>

if os.path.isdir(WEB_DIST):           # guard: tests run with no dist yet
    app.mount("/assets", StaticFiles(directory=f"{WEB_DIST}/assets"), name="assets")

    @app.get("/{full_path:path}")     # SPA deep-link fallback, LAST
    async def spa_fallback(full_path: str):
        # SECURITY (CWE-22): full_path is attacker-controlled and Starlette's
        # :path convertor does NOT collapse `..` (uvicorn percent-decodes first),
        # so a bare os.path.join(WEB_DIST, full_path) + FileResponse is an
        # arbitrary-file-read (serves /etc/passwd, your own source, a .env).
        # Resolve the candidate and confirm it stays INSIDE WEB_DIST before serving.
        real_dist = os.path.realpath(WEB_DIST)
        if full_path:
            candidate = os.path.realpath(os.path.join(real_dist, full_path))
            if (candidate == real_dist or candidate.startswith(real_dist + os.sep)) \
                    and os.path.isfile(candidate):
                return FileResponse(candidate)
        index = os.path.join(real_dist, "index.html")
        return FileResponse(index) if os.path.isfile(index) else JSONResponse(
            status_code=404, content={"error": {"code": "not_found", "message": "Not found"}})
```
`WEB_DIST` must be an **absolute** path (`os.path.dirname(os.path.abspath(__file__))`)
so it resolves regardless of the process CWD.

> **NEVER** serve a path derived from user input without a resolved-path containment check.
> The naive `candidate = os.path.join(WEB_DIST, full_path); return FileResponse(candidate)`
> pattern is a confirmed path-traversal hole. Equivalent guards: `os.path.commonpath([real_dist,
> candidate]) == real_dist`, or `pathlib`'s `WEB_DIST_PATH in candidate.resolve().parents`.
> **Even simpler and safe:** mount the whole bundle with
> `app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="spa")` as the LAST mount
> (StaticFiles has its own traversal guard) and drop the hand-rolled handler entirely.

## `pyproject.toml` (the pytest config that avoids import pain)
The copied `services/`/`models/` use **absolute imports** (`from models.x import ...`).
Make the app root importable in tests without an editable install:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

## `vite.config.ts` (build output + dev proxy + test env in one file)
```ts
export default defineConfig({
  build: { outDir: 'dist', emptyOutDir: true },     // FastAPI serves web/dist
  server: { proxy: { '/api': 'http://localhost:8080' } },
  test: { environment: 'happy-dom', globals: true, include: ['test/**/*.test.ts'] },
});
```
One config serves build, dev, and unit test — no separate `vitest.config`.

## `tsconfig.json` (the decorator settings Lit needs)
Lit's `@customElement`/`@property` decorators require these exactly:
```jsonc
"experimentalDecorators": true,
"useDefineForClassFields": false,   // MUST be false or @property breaks
"target": "ES2021"
```

## Scaffold pitfalls found during the conversion
- **Don't register MWC in `app-root`/components** — register the stable MWC imports
  **only in `main.ts`** (the browser entry). MWC custom elements call
  `attachInternals()`, which happy-dom does not implement, so any test that imports a
  module which imports MWC crashes with `this.attachInternals is not a function`. Keep
  unit-tested components MWC-free and load MWC from the one entry that tests never import.
- **`config/default.py` reads env at import time.** Set a dummy (`PROJECT_ID`) in
  `conftest.py` via `os.environ.setdefault(...)` so `Default()` constructs under test.
- The SPA fallback must be the **last** route and must not shadow `/api/*` (register API
  routers first); otherwise deep links or API calls get swallowed by `index.html`.
