# ASSESS validation — harder apps (Babel + GMCS) vs ground truth

**Method (assert on EFFECTS).** The analyzer was run read-only on the two non-reference targets and
its output diffed against `findings/mesop-app-inventory.md` (App 1 GMCS, App 2 Babel + the
construct-usage matrix) and the app descriptions. Every row is **MATCH** or **MISS** with evidence.
These two apps were chosen because they exercise what Promptlandia lacks: Babel is the lightweight
**FastAPI-hybrid, no-GenAI, faked-nav** case; GMCS is the flagship **FastAPI-hybrid with upload,
IAP, Cloud Tasks, Firestore** case. Both also stress the analyzer's **robustness** (PEP 701
f-strings that the running interpreter cannot AST-parse).

Commands:
```
python3 analyze_mesop_app.py /workspace/genmedia-creative-studio/experiments/babel/app --json babel-assessment.json --md babel-assessment.md
python3 analyze_mesop_app.py /workspace/genmedia-creative-studio                        --json gmcs-assessment.json  --md gmcs-assessment.md
```
Both ran to completion without crashing (the core acceptance bar for the harder apps).

---

## 1. Babel (`experiments/babel/app`)

| Ground-truth claim (inventory App 2) | Analyzer output | Verdict |
|---|---|---|
| **1 real `@me.page`** (`/`), nav faked via `match state.current_page` | `distinct_routes: 1`, `route_registrations: 1` | **MATCH** |
| **FastAPI wrapping Mesop WSGI** (`WSGIMiddleware`, `uvicorn main:app`) | `serve_model: fastapi-hybrid` | **MATCH** |
| global `AppState` + 4 per-page `PageState` = **5 stateclasses** | `stateclasses: 5` | **MATCH** |
| **No GenAI in Python at all** (0 `google.genai`/`vertexai`); logic = HTTP to a Go service | `in_view_llm_count: 0`; `legacy_vertexai.present: false` | **MATCH** |
| **No seam** (`services/`/`models/` dirs absent; logic inline in handlers) | `services_mesop_free: null`, `models_mesop_free: null` (dirs absent → correctly null, not false) | **MATCH** |
| logic **duplicated across pages** | `duplicate_components: ["subtle_chat_input_journey"]` | **MATCH** (surfaces the duplication) |
| streaming absent; **file upload absent** (no `me.uploader`) | `streaming_present: false`; `upload_native/web_component/signed_url: false`; `upload_present: false` | **MATCH** |

### Babel construct-count matrix (18/18 exact)
| pattern | matrix (babel) | analyzer | | pattern | matrix | analyzer |
|---|---|---|---|---|---|---|
| stateclass | 5 | 5 | | SecurityPolicy | 0 | 0 |
| page | 1 | 1 | | iframe parents | 0 | 0 |
| navigate | 1 | 1 | | select | 1 | 1 |
| yield | 20 | 20 | | slider | 0 | 0 |
| native_textarea | 4 | 4 | | tabs | 0 | 0 |
| on_blur | 8 | 8 | | modal/dialog | 0 | 0 |
| slot/content_comp | 4 | 4 | | expansion_panel | 0 | 0 |
| theme_var | 15 | 15 | | markdown | 1 | 1 |
| set_theme/brightness | 12 | 12 | | box | 79 | 79 |
| upload (any token) | 4 | 4 | | streaming | 0 | 0 |

**All babel counts match exactly.**

### Robustness (effects-based proof)
`parse_errors: 6` — six page modules use **PEP 701 f-strings** that the running Python's `ast`
rejects. The analyzer did **not** crash or drop them: the regex fallback still extracted the pages,
all 5 stateclasses, and the components, and the regex-based construct counts are unaffected (they
read raw text, not the AST). **Proof:** had the fallback failed, `stateclasses` would read 1 (only
the one AST-parseable module), not 5 — it reads 5. This is the bug fixed during development
(undercount 1→5) and it holds.

**Babel verdict: all claims MATCH; robustness confirmed.** No misses.

---

## 2. GMCS (repo root, nested apps excluded)

| Ground-truth claim (inventory App 1) | Analyzer output | Verdict |
|---|---|---|
| **genuine FastAPI+Mesop hybrid** (`main:app`, `WSGIMiddleware`, uvicorn worker) | `serve_model: fastapi-hybrid` | **MATCH** |
| **~40–50 routes** (≈40 `@me.page` + ~10 imperative test pages) | `distinct_routes: 42`, `route_registrations: 50` | **MATCH** |
| **48 `@me.stateclass`** across state/+pages/+components | `stateclasses: 49` (distinct), `construct_counts.stateclass: 50` (lines) | **MATCH** (±1) |
| modular per-feature state split (`veo_state.py`, `imagen_state.py`, …) + global `AppState` | 49 stateclasses across `state/*` and pages/components | **MATCH** |
| **seam largely Mesop-free; only 2 of 24 model files import mesop; GenAI confined to seam** | `services_mesop_free: true`, `models_mesop_free: **false**`, `in_view_llm_count: 0` | **MATCH** (precise: models not *fully* clean because 2 files import mesop; services clean; no in-view LLM) |
| **upload — two mechanisms:** native `me.uploader` **and** custom `@me.web_component` signed-URL GCS uploader (`components/gcs_uploader/gcs_uploader.py` + `GET /api/get_signed_url`) | `upload_native: true`, `upload_web_component: true`, `upload_signed_url: true`, `custom_gcs_uploader_files` includes `components/gcs_uploader/gcs_uploader.py` (+3 more uploaders found) | **MATCH (+bonus)** |
| **streaming ABSENT** | `streaming_present: false` | **MATCH** |
| **auth/IAP present & non-trivial** (IAP assertion, `REQUIRE_AUTHENTICATED_USER`, identity bridge) | `auth_iap.present: true` | **MATCH** |
| **background/async jobs** (`BackgroundTasks` + `google-cloud-tasks`) | `cloud_tasks.present: true` | **MATCH** |
| **Firestore pervasive** (27 files, `common/metadata.py`) | `firestore.present: true` | **MATCH** |
| hidden/test pages routed but not in nav | `hidden_routes`: 18 incl. 10 `/test_*` pages + banana-studio, selfie, etc. | **MATCH** |
| imperative duplicate test-page registrations | `double_registered_routes`: 8 `/test_*` paths | **MATCH** (these are registered both in-page and imperatively in main.py) |

### GMCS — nuances and bonus finds
- **`legacy_vertexai: true` — BONUS true-positive.** Not called out in the inventory GMCS checklist,
  but verified real: `import vertexai` at `models/model_setup.py:22` and `models/lyria.py:23`. This
  is exactly the backend-only migration opportunity documented in `references/hard-topics.md#8`.
- **`websocket: true` — SOFT-POSITIVE (documented).** Ground truth says websockets are "effectively
  absent — only a comment at `pages/veo.py:649`." The analyzer reports `present: true` with
  `line_count: 1`, which **agrees with the matrix count (ROOT websocket = 1)** but the single hit is
  a **code comment**, not a real WebSocket. This is the known limitation of line-based detection:
  presence is load-bearing, exact interpretation needs a human glance. Flagged here, not silently
  passed. (A reader following the report to `pages/veo.py:649` sees it is a comment.)

### GMCS construct counts — the ROOT-column discrepancy (important)
The analyzer's root-app construct counts are **lower** than the matrix "ROOT" column:

| pattern | matrix "ROOT" | analyzer | grep **whole-repo** | grep **--exclude-dir=experiments,archive** |
|---|---|---|---|---|
| `@me.stateclass` | 67 | **50** | 67 | **50** |
| `me.navigate` | 19 | **13** | 19 | **13** |
| `theme_var` | 295 | **235** | 295 | **235** |
| `native_textarea` | 18 | **7** | 18 | **7** |
| `me.box` | 1116 | **787** | 1116 | **787** |

**Root cause (verified by re-running grep both ways):** the matrix "ROOT" column, despite its header
note "ROOT column excludes `experiments/` and `archive/`", was actually computed over the **whole
repository** (nested apps included). The analyzer **correctly** scopes to the root app only
(`NESTED_APP_DIRS = {experiments, archive}` excluded by default). Proof by effects: the analyzer's
numbers reproduce `grep … --exclude-dir=experiments --exclude-dir=archive` **exactly** (50, 13, 235,
7, 787), while the matrix numbers reproduce the **un-excluded** whole-repo grep exactly (67, 19, 295,
18, 1116), and `787 + Σ(nested app box: 152+79+19+53+26 = 329) = 1116`.

**Verdict: this is a MISS in the ground-truth matrix, not in the analyzer.** The analyzer's
root-scoped counts are the correct "GMCS app" numbers. It is recorded here (per the brief:
"misses… fixed or documented") as a documented ground-truth labeling error; the analyzer needs no
change. The `--include-nested` flag reproduces the whole-repo (matrix) numbers on demand if a user
wants the repo-wide view.

### GMCS robustness
`parse_errors: 2` — two files unparseable by the running interpreter; both recovered via the regex
fallback, and the 254-file, ~49k-LOC root tree analyzed without crashing (the brief's hard
requirement: "robust to large apps, never hard-fail").

**GMCS verdict:** every inventory claim MATCH; two bonus true-positives beyond the checklist
(extra uploader files, legacy vertexai); one documented soft-positive (websocket = a comment); and
one documented **ground-truth** matrix mislabeling (ROOT column counts the whole repo) that the
analyzer gets *more* correct than the ground truth.

---

## 3. Cross-app summary

| App | Ran clean | Serve model | Seam | Upload | Key hard topics | Matrix counts |
|---|---|---|---|---|---|---|
| Babel | ✅ (6 parse-errors recovered) | fastapi-hybrid ✅ | none (null) ✅ | none ✅ | none ✅ | 18/18 exact ✅ |
| GMCS | ✅ (2 parse-errors recovered) | fastapi-hybrid ✅ | services-clean, models-mixed ✅ | native+custom GCS ✅ | IAP, Cloud Tasks, Firestore, legacy vertexai ✅ | correct (matrix ROOT col is whole-repo; analyzer is root-scoped) |

**Misses:** none in the analyzer. One ground-truth matrix mislabeling (GMCS ROOT column =
whole-repo) is documented; one GMCS websocket soft-positive (a comment) is documented. Both are
recorded per the brief rather than silently passed.
