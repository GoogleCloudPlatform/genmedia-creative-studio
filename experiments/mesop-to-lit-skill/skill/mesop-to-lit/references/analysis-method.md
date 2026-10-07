# Analysis method: the STEP-1 inventory checklist

`scripts/analyze_mesop_app.py` automates this inventory. This file documents **what** it
inventories and the **detection method** for each item, so a human or agent can reproduce
or audit the analysis by hand, and so you understand what each field of the report means.

Run it first:
```
python3 ${CLAUDE_SKILL_DIR}/scripts/analyze_mesop_app.py <app_dir> --json out.json --md out.md
```
Pointed at a repo **root** that vendors multiple apps, it excludes `experiments/` and
`archive/` by default (they are separate apps); pass `--include-nested` to override.

## What to inventory (and how the script detects it)

1. **Pages / routes** — every `@me.page(path=...)` decorator **and** imperative
   `me.page(...)` call.
   - *Method:* AST walk of decorator lists + `Call` nodes; extract the `path=` kwarg and the
     decorated/wrapped content fn; group by path.
   - *Flags:* **double-registration** (same path registered >1×) and **routed-but-hidden**
     (a registered path not referenced by any nav source — `*nav*.py` uncommented lines +
     `*nav*.json`). → `routes[]`, `summary.double_registered_routes`, `summary.hidden_routes`.

2. **Components** — shared `@me.component`/`@me.content_component` **and in-page duplicated**
   ones (copy-paste).
   - *Method:* AST decorator detection for shared components; **duplicate detection** =
     any function name defined in ≥2 modules (`duplicate_components[]`), with
     `is_mesop_component` set when the name is a detected component. This catches the classic
     `gemini_prompt_input ×4`.

3. **State** — every `@me.stateclass`, global vs per-page/per-feature, with per-field
   classification.
   - *Method:* AST `ClassDef` with a `stateclass` decorator; fields from `AnnAssign`/`Assign`;
     scope inferred from the module path (`state/` → global/feature, `pages/` → per-page);
     each field name classified **UI-only / derived-display / secret-config** by keyword
     heuristic (confirm by reading usage). → `stateclasses[]`.

4. **Services / models seam** — which modules import mesop vs not; is there a Mesop-free
   `services/`+`models/` seam; are there in-view LLM calls (logic-in-view red flag).
   - *Method:* AST import scan per module; `services_mesop_free`/`models_mesop_free` =
     no mesop import under those dirs (`None` if the dir is absent). **In-view LLM calls** =
     `LLMClient(`/`genai.Client(`/`.generate_content`/`GenerativeModel(`/`ImageGenerationModel(`
     found in a module that imports mesop. → `seam{}`, headline `in_view_llm_count`.

5. **Construct / pattern presence + counts** — stateclass, generator `yield`, `me.navigate`,
   `native_textarea`/`on_blur`(+key-bump), `me.slot`/content_component, theming
   (`theme_var`/`set_theme`/`theme_brightness`), `SecurityPolicy`/`allowed_iframe_parents`,
   select, slider, tabs, modal/dialog, expansion_panel, markdown, `me.box`.
   - *Method:* **line-count heuristic** — per pattern, number of `.py` lines containing a
     match (grep -c semantics), reproducing the Phase-0 construct-usage matrix. **Presence
     (count > 0) is the load-bearing signal**; exact counts can be inflated by comments/
     strings and are labelled heuristic. → `construct_counts{}`.

6. **Hard topics** — streaming, upload (native + custom `@me.web_component` signed-URL),
   websocket, auth/IAP, Firestore, Cloud Tasks/BackgroundTasks, legacy `vertexai`.
   - *Method:* targeted regex (see `hard-topics.md`). `legacy_vertexai` deliberately excludes
     `vertexai=True` (that is the new `google.genai` SDK). → `hard_topics{}`.

7. **Serve model** — plain-WSGI vs FastAPI-hybrid.
   - *Method:* parse `Procfile`/`Dockerfile` for the entrypoint (`app:me`/`main:me` →
     plain-wsgi; `main:app` + `FastAPI`/`WSGIMiddleware` in code → fastapi-hybrid). →
     `serve_model{}`.

8. **Stack facts** — python version, declared deps, requirements-vs-lock drift.
   - *Method:* read `.python-version`, `pyproject.toml` (`requires-python`, `dependencies`),
     `requirements.txt` pins, `uv.lock` resolution; compare mesop/google-genai pins between
     requirements and lock. → `stack{}`.

9. **Per-page difficulty** — trivial / mechanical / needs-design / hard.
   - *Method:* transparent additive score over the page's resolved content module (the
     registrar's wrapper is followed through its import to the real `pages/*` module):
     `+1` per distinct rich primitive (select/slider/tabs/modal-dialog/chips/expansion_panel);
     `+2` in-view LLM call; `+1` generator yield; `+1` state size >5 fields (`+1` more >12);
     `+1` layout density ≥30 `me.box` (`+1` more ≥80); `+3` upload component; `+1` per bespoke
     in-page component (cap 2). Bands: trivial <2, mechanical 2–4, needs-design 5–7, hard >7.
     **Heuristic** — it flags where human judgement is needed, not a substitute for it. →
     `page_assessments[]`.

10. **Construct → component decisions** — stock / compose / custom / promote-shared per
    present construct, by applying the framework programmatically; duplicated components →
    promote-shared. → `component_decisions[]`. (See `component-decisions.md` for the Q1–Q5
    procedure behind these calls, and where human judgement must override.)

## Robustness notes
- The script **never hard-fails** on an unparseable file: on `SyntaxError`/`ValueError` it
  falls back to a line-based regex extractor (so routes/stateclasses/components are still
  detected even when the app uses newer Python syntax than the interpreter running the
  script, e.g. PEP 701 f-strings). Unparsed files are listed under `parse_errors`.
- Everything is deterministic (sorted file walk, stable counts) and stdlib-only.

## The assess → decide pipeline
1. **Run** the analyzer on the target app → JSON + markdown.
2. **Read** the report: serve model, seam, routes (double/hidden), duplicates, construct
   presence, hard topics, per-page difficulty.
3. **Apply** `construct-map.md` + `component-decisions.md` (Q1–Q5 + DRY gate), re-confirming
   the Material Web stable set against live docs.
4. **Emit** a conversion assessment: scope/sequence (difficulty order), the component list
   (stock/compose/custom/promote-shared), the endpoint surface (from the action handlers),
   the state plan (field classification), the serve/deploy delta, and the hard-topic tasks.
