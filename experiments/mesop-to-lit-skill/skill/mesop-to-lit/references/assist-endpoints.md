# Assist: derive endpoints + pydantic schemas from the services seam

One rule drives the API surface: **one route per real service method.** The Mesop event
handlers that called `services/` directly become HTTP POSTs; the service signatures become
the pydantic request/response shapes. This is where the Mesop "JSON-in-state" hacks die.

## The derivation
For each service method the Mesop pages call:

| From the service | Becomes |
|---|---|
| method name (`evaluate_prompt`) | a route (`POST /api/checklist`) |
| method params (`prompt: str`) | the **request** model fields |
| method return type | the **response** model (typed, not a JSON string) |
| the method itself | called unchanged behind a `Depends(...)` provider |
| a read-only config display | `GET /api/config` (optional) |
| liveness | `GET /api/healthz` |

**Actions are POST** (they call the LLM / mutate), **reads are GET**. Mirror the method
signature exactly — do not invent params the service does not take.

## Schemas: use the design's wire shapes, adapt at the boundary
The response model is the **wire contract**, authored to be clean for the client — it is
*not* required to equal the service's internal return type. When the two differ, write a
small `from_parsed(...)`/adapter classmethod on the response model. This is the single
most important endpoint lesson from the conversion.

Promptlandia's checklist service returns `(ParsedChecklistResponse | None, raw_text)`.
The internal `ParsedChecklistResponse` is shaped by a **lossy** markdown parser
(`parse_evaluation_markdown` → `from_json_dict`) that reshapes the model's raw per-issue
JSON into markdown strings and **drops `issue_name`/`severity`**. The design's §3.3
`ChecklistResponse` is the clean typed body. The adapter bridges them:
```python
class ChecklistResponse(BaseModel):
    categories: list[ChecklistCategory] = Field(default_factory=list)
    raw: str | None = None                      # parse-fallback text

    @classmethod
    def from_parsed(cls, parsed, raw):
        if parsed is None:                       # parser failed -> raw fallback
            return cls(categories=[], raw=raw)
        cats = []
        for name, cat in parsed.categories.items():
            has_issue = any(bool(s) for s in cat.items.values())
            items = [...]                        # only score=True items -> issue items
            cats.append(ChecklistCategory(name=name, has_issue=has_issue,
                                          explanation=cat.explanation or "", items=items))
        cats.sort(key=lambda c: not c.has_issue) # issues first (Mesop ordering parity)
        return cls(categories=cats, raw=None)
```
Document the lossiness in the schema docstring (where a field is empty because the parser
dropped it) so the next person does not assume the gap is a bug.

## The route: thin, typed, no business logic
```python
@router.post("/checklist", response_model=ChecklistResponse)
def checklist(req: ChecklistRequest,
              service: PromptChecklist = Depends(get_checklist_service)):
    parsed, raw_text = service.evaluate_prompt(req.prompt)
    return ChecklistResponse.from_parsed(parsed, raw_text)
```
The route only: validates (pydantic), calls the unchanged service, adapts, returns. No
parsing, no LLM wiring — that all stays in `services/`.

## DI so tests can mock the LLM (`deps.py`)
Construct the service behind a dependency whose only job is to be overridable:
```python
def get_checklist_service() -> PromptChecklist:
    return PromptChecklist()          # real client in prod
```
Tests swap it with `app.dependency_overrides[get_checklist_service] = lambda: svc`, where
`svc` wraps a mocked client — **no network LLM calls** (see `assist-testing.md`). This
requires the service to accept an **injectable client** (`PromptChecklist(client=...)`).
If the copied service hard-codes its client, add an optional `client=None` param — that is
a legitimate, minimal seam fix, not a behavior change.

## Error envelope (§3.5) — one handler module, three handlers
Every failure the client can hit becomes `{"error": {"code", "message"}}`:
```python
def register_error_handlers(app):
    @app.exception_handler(RequestValidationError)   # 422, reshaped from FastAPI default
    async def _v(req, exc):
        return JSONResponse(status_code=422, content=_envelope("validation_error", msg))
    @app.exception_handler(StarletteHTTPException)    # preserve status
    async def _h(req, exc):
        return JSONResponse(status_code=exc.status_code, content=_envelope("http_error", ...))
    @app.exception_handler(Exception)                 # 500 catch-all (LLM/service blew up)
    async def _u(req, exc):
        # Log the detail server-side; return a GENERIC client message.
        logger.exception("Unhandled error on %s", req.url.path)
        return JSONResponse(status_code=500,
                            content=_envelope("internal_error", "Internal server error"))
```
Reshape FastAPI's verbose 422 body into the same two-field envelope so the client has
**one** error shape to parse. The parse-*fallback* (model output unparseable) is **not**
an error — it is a 200 with `raw` set; only infra/validation failures use the envelope.

> **Two must-get-right traps in this recipe:**
> 1. **Keyword args, always.** Starlette's signature is `JSONResponse(content, status_code=200, ...)`.
>    Writing `JSONResponse(422, _envelope(...))` binds `content=422` and `status_code=<dict>` —
>    backwards (body becomes the integer `422`, status becomes a dict → runtime error). Pass
>    `status_code=` and `content=` by keyword in every handler.
> 2. **Never echo `str(exc)` to the client.** Raw exception text leaks prompt content, internal
>    paths, and provider/config identifiers (CWE-209 info disclosure). Log the full detail with
>    `logger.exception(...)` server-side and return a fixed `"Internal server error"` to the
>    client. The 422 and `HTTPException` messages are intentionally client-facing; the 500
>    catch-all message must not be.

## Generalizing
Walk the service layer, list its public methods, and emit one POST each with a
request model = params and a response model = a clean wire shape + an adapter from the
return type. Add `/api/healthz`; add `/api/config` only if a Settings page reads config.
Keep routes thin; keep all parsing/LLM logic in the copied `services/`.
