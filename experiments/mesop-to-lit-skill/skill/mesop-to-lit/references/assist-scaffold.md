# Assist: scaffold the FastAPI `api/` + Vite/Lit `web/` target

The concrete directory + file recipe for the converted app, in the order you create
it. Produces a **single-service** layout (FastAPI serves `/api/*` and the built Vite
bundle — see `serve-and-deploy.md`).

## Pins (do not drift)

### Default: Web Awesome
- Frontend: **lit 3.3.3**, **`@awesome.me/webawesome` 3.14.0** (MIT), **`@vaadin/router` 2.0.1**.
- Dev/test: `vite ^5`, `vitest ^2`, `happy-dom`, `element-internals-polyfill`, `@open-wc/testing-helpers`, `typescript ^5`.
  *(Note: `element-internals-polyfill` allows Web Awesome custom elements to test directly in happy-dom!)*
- Markdown helper: `marked` + `dompurify` (or built-in `<wa-markdown>`).

### Alternative: Material 3 (when explicitly requested)
- Frontend: **lit 3.3.3**, **`@material/web` 2.5.0** (maintenance mode — stable only), **`@vaadin/router` 2.0.1**.
- Dev/test: `vite ^5`, `vitest ^2`, `happy-dom`, `@open-wc/testing-helpers`, `typescript ^5`.
- Markdown helper: `marked` + `dompurify`.

### Backend
- `fastapi`, `uvicorn[standard]`, `gunicorn`, `pydantic`, plus the app's own LLM deps (`google-genai`, `tenacity`, `python-dotenv`). **No `mesop`.**
- Target Node 20+; Python 3.11+.

---

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
      main.ts             # browser entry: register components + theme + app
      app-root.ts         # shell: drawer/sidenav + <main> router outlet
      router.ts  theme.ts  global.css
      api/ client.ts types.ts
      components/ ...      # custom + shared Lit elements
      pages/ page-*.ts
    test/ *.test.ts       # Vitest + @open-wc
```

---

## Step order (each step independently verifiable)
1. **Copy the seam.** `cp -r` the app's `services/`, `models/`, `config/` into the new
   tree. Grep them for `import mesop` / `me\.` — if clean, they run as-is. If not, that is a "no seam" task (see `hard-topics.md`), do it first.
2. **Backend shell.** `main.py` + `api/`. Verify with `pytest` before any frontend work.
3. **Frontend shell.** `package.json` → `npm install` → `index.html` + `vite.config.ts`
   + `tsconfig.json` + `src/main.ts` + `app-root.ts` + `router.ts` + `theme.ts`. Verify
   with `vite build` (empty pages are fine).
4. **Components + pages** in build order (see `assist-components.md`).
5. **Tests** alongside each component (see `assist-testing.md`).

---

## `main.py` (single-service entrypoint)
Order is load-bearing: **register error handlers → middleware → API routers → static mount + SPA fallback LAST**. Guard the static mount with `os.path.isdir(dist)` so the backend tests run before any frontend build exists.

```python
app = FastAPI(...)
register_error_handlers(app)

@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = _CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp

app.include_router(config_router)     # /api/healthz first
app.include_router(actions_router)    # /api/<action>

if os.path.isdir(WEB_DIST):
    # Mount SPA dist safely
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="spa")
```

---

## `package.json` (Web Awesome default)
```json
{
  "name": "app-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@awesome.me/webawesome": "3.14.0",
    "@vaadin/router": "2.0.1",
    "dompurify": "^3.2.3",
    "lit": "3.3.3",
    "marked": "^15.0.4"
  },
  "devDependencies": {
    "@open-wc/testing-helpers": "^3.0.1",
    "element-internals-polyfill": "^1.3.11",
    "happy-dom": "^15.11.7",
    "typescript": "^5.7.2",
    "vite": "^5.4.11",
    "vitest": "^2.1.8"
  }
}
```

---

## `tsconfig.json` (the decorator settings Lit needs)
Lit's `@customElement`/`@property` decorators require these exactly:
```jsonc
"experimentalDecorators": true,
"useDefineForClassFields": false,   // MUST be false or @property breaks
"target": "ES2021"
```

---

## Scaffold pitfalls found during conversion
- **Testing Web Components with happy-dom:**
  - With **Web Awesome**: Install `element-internals-polyfill` and import it in your test setup. Web Awesome components can then be rendered and tested directly under happy-dom.
  - With **Material Web**: MWC calls `attachInternals()`, which crashes happy-dom if imported in unit tests. Unit-tested components must remain MWC-free and MWC components registered only in `main.ts`.
- **`config/default.py` reads env at import time.** Set a dummy (`PROJECT_ID`) in `conftest.py` via `os.environ.setdefault(...)` so `Default()` constructs under test.
- The SPA fallback must be the **last** route and must not shadow `/api/*`.
