# Serve & deploy: detect the serve model, target single-service

## Two serve models exist in the wild — detect which
The analyzer parses `Procfile`/`Dockerfile` + scans code and reports `serve_model`:

| Model | Signature | Examples |
|---|---|---|
| **plain-wsgi** | `Procfile` runs `gunicorn ... app:me` / `main:me` — the entrypoint object is Mesop's WSGI app `me`; no FastAPI | Promptlandia (`app:me`), creative-genmedia-workflow, arena, imagen-cs (`main:me`) |
| **fastapi-hybrid** | entrypoint `main:app` is a `FastAPI()` instance; Mesop mounted as a catch-all WSGI sub-app via `WSGIMiddleware(me.create_wsgi_app(...))`; Procfile uses a uvicorn worker | GMCS (`-k uvicorn.workers.UvicornWorker main:app`), babel (`uvicorn main:app`) |

**Why it matters:** a **fastapi-hybrid** app is *already partway to the target* — it has a
FastAPI shell, middleware, and (often) `/api/*` routes you keep. A **plain-wsgi** app needs
the FastAPI shell created from scratch. The analyzer's `serve_model.evidence` lists the
Procfile line and whether `WSGIMiddleware`/`FastAPI` appear in code.

## Target: single-service (FastAPI serves the Vite bundle)
Default to **one service, one container** — closest to a typical single Cloud Run deploy,
no CORS, minimal infra delta:
- `main.py` is an ASGI `FastAPI()` app. Register `/api/*` routers **first**, then mount the
  built frontend via `StaticFiles`, then an SPA fallback last (unmatched non-API paths →
  `index.html`, so client-router deep links work).
- **SECURITY — the SPA fallback is a path-traversal trap.** Do **not** serve a file whose path
  is built by joining user input onto the web root without a containment check — Starlette's
  `:path` convertor does not collapse `..` (uvicorn percent-decodes first), so
  `os.path.join(WEB_DIST, full_path)` + `FileResponse` is an arbitrary-file-read (CWE-22:
  serves `/etc/passwd`, your source, a `.env`). Either mount the bundle with
  `StaticFiles(directory=WEB_DIST, html=True)` as the last mount (it has a built-in traversal
  guard) and keep only a guarded index fallback, **or** resolve the candidate with
  `os.path.realpath` and verify it stays inside `WEB_DIST`
  (`candidate.startswith(real_dist + os.sep)`) before serving. See the full recipe in
  `assist-scaffold.md`.
- The Mesop `app.py` WSGI module is **deleted**; `main.py` replaces it. No `mesop` import
  should remain in the shipped app.
- Split frontend/backend (CDN + separate API) only if static traffic justifies it — it
  adds CORS, a second deploy target, and more infra for marginal benefit at small scale.

## WSGI → ASGI
Process manager changes from gunicorn(WSGI) to **gunicorn + uvicorn workers (ASGI)** (or
plain uvicorn). **Preserve the worker count, the port, and especially the long timeout**
(LLM calls are slow — e.g. Promptlandia's `--timeout 360`). Example CMD:
```
gunicorn -k uvicorn.workers.UvicornWorker --workers 3 --timeout 360 --bind :8080 main:app
```

## Multi-stage Dockerfile (single-service)
```
# stage 1: build the frontend
FROM node:22-slim AS web
WORKDIR /web ; COPY web/ . ; RUN npm ci && npm run build        # -> /web/dist

# stage 2: python runtime
FROM python:3.14-slim
WORKDIR /app ; COPY . . ; COPY --from=web /web/dist ./static
RUN pip install uv && uv sync --frozen
CMD ["gunicorn","-k","uvicorn.workers.UvicornWorker","--workers","3","--timeout","360","--bind",":8080","main:app"]
```
For a **fastapi-hybrid** source app, reuse the existing Dockerfile base/python version and
add the node build stage. Keep env vars, service-account roles, and platform gating (IAP)
unchanged — on single-service, only the *build* changes, not the topology.

## Security headers / CSP (replaces `me.SecurityPolicy`)
Set response headers in FastAPI middleware:
- **Trusted Types:** Mesop's `dangerously_disable_trusted_types=True` is a **Mesop
  workaround**, not a requirement. In Lit you control rendering and sanitize markdown with
  DOMPurify, so **drop the flag** and set a conservative CSP instead.
- **iframe-embed (`frame-ancestors`):** if the source set `allowed_iframe_parents=[...]`
  (the analyzer reports `allowed_iframe_parents` presence) and embedding must survive, set
  `Content-Security-Policy: frame-ancestors 'self' https://<parent>`. Otherwise
  `frame-ancestors 'self'`. One middleware line — designed as a config toggle.

A hardened baseline CSP (lock down the lesser-known directives too):
```
default-src 'self'; base-uri 'self'; object-src 'none'; form-action 'self';
img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self';
connect-src 'self'; frame-ancestors 'self' https://<parent>
```
- `base-uri 'self'` and `object-src 'none'` are **not** covered by `default-src` in practice —
  set them explicitly (`<base>` injection / plugin content).
- Narrow `img-src` to `'self' data:` (no wildcard `https:`) so attacker-influenced markdown
  image URLs cannot beacon arbitrary third parties.
- Keep `script-src 'self'` and `connect-src 'self'` — no `unsafe-inline`/`unsafe-eval`; these
  limit the blast radius if sanitization ever slips. Drop `'unsafe-inline'` from `style-src`
  too if a browser/e2e pass confirms nothing (Lit/MWC constructable styles, DOMPurify-left
  inline `style` attrs) relies on it; otherwise keep it and note the tradeoff.
- **HSTS:** add `Strict-Transport-Security: max-age=63072000; includeSubDomains` for the
  HTTPS/Cloud Run deploy. Emit it only when the request is HTTPS (check
  `x-forwarded-proto == "https"` behind the Cloud Run TLS terminator) so you never pin HSTS on
  a plain-http dev request.

## Dependency baseline
- **Lockfile is authoritative** when `requirements.txt` and `uv.lock` disagree (the
  analyzer reports `requirements_vs_lock_drift` for mesop/google-genai).
- **Drop** `mesop`; **add** `fastapi`, `uvicorn`, `gunicorn` (uvicorn worker). **Declare**
  anything that was transitive via mesop (commonly `pydantic`).

## Dev workflow
- Terminal 1: `uvicorn main:app --reload --port 8080`.
- Terminal 2: `npm run dev` (Vite) with `vite.config.ts` proxying `/api` → `:8080`.
- Any existing CLI keeps running against `services/` with no server.
