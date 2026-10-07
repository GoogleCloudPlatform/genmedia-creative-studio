# ASSESS validation — Promptlandia (point-by-point vs ground truth)

**Method (assert on EFFECTS).** The analyzer was run on the real app tree
(`/workspace/genmedia-creative-studio/experiments/promptlandia`, read-only) and its output
(`validation/promptlandia-assessment.{json,md}`) is compared **line-by-line** against the
investigator ground truth in `findings/promptlandia-anatomy.md` (Sections A1–A6, C12) and the
construct-usage matrix in `findings/mesop-app-inventory.md`. Each row is **MATCH** (analyzer
agrees with ground truth) or **MISS** (disagreement), with the evidence that proves it.

Command:
```
python3 skill/mesop-to-lit/scripts/analyze_mesop_app.py \
  /workspace/genmedia-creative-studio/experiments/promptlandia --json promptlandia-assessment.json --md promptlandia-assessment.md
```
Result: ran clean, `parse_errors: 0`, 38 py files.

---

## A. Brief acceptance checklist (the required matches)

| # | Acceptance criterion | Ground truth | Analyzer output | Verdict |
|---|---|---|---|---|
| 1 | **Route count** | 7 routes (A1 table) | `distinct_routes: 7` (`route_registrations: 8`) | **MATCH** |
| 2 | **Double-registered route** | `/video_checklist` registered twice (A5#10: app.py:137 + video_checklist.py:546) | `double_registered_routes: ["/video_checklist"]`; regs_detail lists app.py:137 **and** pages/video_checklist.py:546 | **MATCH** |
| 3 | **Routed-but-hidden route** | `/playground` routed but hidden from nav (A1.4, side_nav.py:37) | `hidden_routes: ["/playground"]` | **MATCH** |
| 4 | **Mesop-free seam** | `services/` + `models/` have zero mesop imports (A4 "seam proof") | `services_mesop_free: true`, `models_mesop_free: true` | **MATCH** |
| 5 | **×4 duplicated component** | 4 near-identical `gemini_prompt_input` defs (A2) | `duplicate_components`: `gemini_prompt_input` count **4** in checklist/generate/promptlandia/video_checklist, `is_mesop_component: true` | **MATCH** |
| 6 | **No streaming** | NONE — 0 matches for `generate_content_stream`/`stream=True` (A3) | `streaming_present: false`, `hard_topics.streaming.present: false` (0 lines) | **MATCH** |
| 7 | **No upload** | no file upload anywhere (summary, A-level) | `upload_present: false`; `upload_native/web_component/signed_url` all false; `custom_gcs_uploader_files: []` | **MATCH** |
| 8 | **3 in-view LLM calls** | 3 pages call `LLMClient` directly in the view (A5#12: generate.py:202, video_checklist.py:482, playground.py:402) | `in_view_llm_count: 3` → generate.py, playground.py, video_checklist.py; sites include generate.py:202, video_checklist.py:482, playground.py:402 | **MATCH** (incl. exact line numbers) |
| 9 | **Construct presence set** | matrix column "promptlandia" (presence of stateclass, page, navigate, yield, native_textarea, on_blur, slot, theme_var, set_theme, SecurityPolicy, iframe, select, slider, tabs, modal, expansion, markdown, box; streaming absent) | every present construct present, streaming absent (see §C) | **MATCH** |

All 9 required acceptance items **MATCH**.

---

## B. Construct-count matrix (exact line counts vs `mesop-app-inventory.md`)

The inventory matrix is grep-line counts; the analyzer uses the same grep-`-c` semantics. The
"promptlandia" column is reproduced **exactly**:

| pattern | matrix (promptlandia) | analyzer `construct_counts` | verdict |
|---|---|---|---|
| `@me.stateclass` | 7 | 7 | MATCH |
| `@me.page`/`me.page(` | 8 | 8 | MATCH |
| `me.navigate` | 1 | 1 | MATCH |
| generator `yield` | 21 | 21 | MATCH |
| `native_textarea` | 7 | 7 | MATCH |
| `on_blur` | 15 | 15 | MATCH |
| `me.slot`/content_component | 8 | 8 | MATCH |
| `theme_var` | 34 | 34 | MATCH |
| `set_theme`/`theme_brightness` | 7 | 7 | MATCH |
| `SecurityPolicy` | 3 | 3 | MATCH |
| `allowed_iframe_parents` | 1 | 1 | MATCH |
| `me.select` | 2 | 2 | MATCH |
| `me.slider` | 2 | 2 | MATCH |
| tabs | 8 | 8 | MATCH |
| modal/dialog | 25 | 25 | MATCH |
| `expansion_panel` | 9 | 9 | MATCH |
| `me.markdown` | 28 | 28 | MATCH |
| streaming | 0 | 0 | MATCH |
| upload (any token) | 5 | `upload_any_token` 5 | MATCH |
| `me.box` | 152 | 152 | MATCH |

**20/20 construct counts match exactly.** Note on "upload (any token) = 5": this is the loose
`upload` substring (appears in generate.py/promptlandia.py, e.g. `upload`-named identifiers/strings),
**not** a real upload mechanism — the matrix carries the same 5 and the specific upload detectors
(`me.uploader`, `@me.web_component`, signed-URL) are all 0, so "no upload" (A7) still holds.

---

## C. Structural detail (A1–A6) — point by point

| Ground-truth claim | Analyzer output | Verdict |
|---|---|---|
| A1: 7 pages over a shared scaffold, registered in app.py | 7 routes, all registered in `app.py` (regs_detail module=app.py); each route resolved to its real `pages/*.py` content module in `page_assessments` | **MATCH** |
| A1 route→module map (`/`→promptlandia.py, `/prompt`→generate.py, `/settings`→settings.py, `/playground`→playground.py, `/checklist`→checklist.py, `/video_checklist`→video_checklist.py, `/trimmer`→trimmer.py) | `page_assessments[].module` resolves each route to exactly these modules | **MATCH** |
| A2: in-page components copy-pasted, incl. `render_pydantic_response` duplicated (checklist + video_checklist) | bonus find: `render_pydantic_response` count **2** across checklist.py/video_checklist.py, `is_mesop_component: true` | **MATCH (+bonus)** |
| A3: global `AppState` + 6 per-page `PageState`; settings empty | 7 stateclasses: `AppState` (global, state/state.py) + 6 `PageState`; settings.py PageState `fields: []` | **MATCH** |
| A3: trimmer state lives in global `AppState`, not a PageState | `AppState` fields include `trimmer_input/output/analysis/loading/duration`; trimmer PageState absent | **MATCH** |
| A3: JSON-in-state workaround (`parsed_response_json_str`) | field `parsed_response_json_str` present, classified `derived-display` | **MATCH** |
| A4: `services/` + `models/` Mesop-free, CLI-driven | `seam.services_mesop_free/models_mesop_free: true`; services/* and models/* in `logic_modules`, cli/* in `logic_modules` | **MATCH** |
| A5#9: SecurityPolicy on settings/trimmer; iframe parents on video page | `security_policy` 3, `allowed_iframe_parents` 1 (present) | **MATCH** |
| A6: Procfile `gunicorn … app:me` (plain Mesop WSGI) | `serve_model: plain-wsgi`, entrypoint `app:me`, evidence quotes the Procfile line | **MATCH** |
| A6: requirements vs uv.lock DISCREPANCY on mesop (1.3.5 vs 1.3.6) and google-genai (2.22.0 vs 1.50.1) | `requirements_vs_lock_drift`: mesop 1.3.5→1.3.6, google-genai 2.22.0→1.50.1 | **MATCH** |
| A6: `requires-python >=3.14`, `.python-version` 3.14 | `stack.requires_python: ">=3.14"`, `python_version_file: "3.14"` | **MATCH** |
| A6: pydantic not declared though used (transitive via mesop) | `dependencies` list has no pydantic; drift/`requirements_pins` shows pydantic resolved — surfaces the gap | **MATCH** |

---

## D. Per-page difficulty vs C12 ratings

C12 is a human rating; the analyzer's additive rubric is a **heuristic that flags where judgement
is needed**, so exact-band agreement is the goal but one-band drift is acceptable when defensible.

| Page | C12 human | Analyzer (score→band) | Verdict |
|---|---|---|---|
| `/settings` | trivial | 1 → **trivial** | MATCH |
| `/trimmer` | mechanical→needs-design | 3 → **mechanical** | MATCH (within stated range) |
| `/` (improver) | needs-design | 6 → **needs-design** | MATCH |
| `/checklist` | needs-design | 5 → **needs-design** | MATCH |
| `/playground` | hard | 12 → **hard** | MATCH |
| `/prompt` (generate) | mechanical | 6 → **needs-design** | **MISS (+1 band)** |
| `/video_checklist` | needs-design | 8 → **hard** | **MISS (+1 band)** |

**5/7 exact, 2 one-band overshoots.** Both misses are **conservative and defensible**: the rubric
adds +2 for an in-view LLM call, and both `/prompt` and `/video_checklist` are among the three pages
the ground truth itself flags as calling `LLMClient` directly in the view (A5#12) — a genuine
conversion red flag (logic must be lifted to a service first). The heuristic therefore rates the
risk slightly higher than the pure-UI-complexity human rating; it never *under*-rates. This is
documented as a known limitation of the difficulty heuristic (see `project-log/assess-dev.md`), not
a detection error.

---

## E. Summary

- **Acceptance checklist: 9/9 MATCH.** Route count, double route, hidden route, Mesop-free seam,
  ×4 duplicated component, no streaming, no upload, 3 in-view LLM calls, construct presence set.
- **Construct counts: 20/20 exact MATCH** against the inventory matrix.
- **Structural detail (A1–A6): all MATCH**, plus one correct bonus duplicate find
  (`render_pydantic_response` ×2).
- **Per-page difficulty: 5/7 exact, 2 defensible one-band overshoots**, both driven by the
  in-view-LLM red flag the ground truth independently calls out — documented, not fixed (the
  heuristic is intentionally risk-conservative).

**No MISSes among the required acceptance items.** The only deviations are two intentional,
documented one-band difficulty overshoots.
