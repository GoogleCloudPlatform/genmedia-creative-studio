# Construct map: Mesop → Lit + Web Awesome (default) / Material Web (opt-in) → FastAPI

The reusable translation table.

## Two Target UI Libraries

1. **Web Awesome (`@awesome.me/webawesome` 3.14.0, MIT) — DEFAULT:**
   - Actively maintained by Font Awesome / Cory LaViska; built directly in Lit.
   - Provides **stock off-the-shelf components** for all common application needs: `<wa-details>` / `<wa-accordion>` (accordion),
     `<wa-drawer>` (navigation drawer), `<wa-tooltip>` (tooltips), `<wa-copy-button>` (copy button), `<wa-dialog>` (dialogs).
   - No custom Lit elements required for accordion, drawer, or tooltip gaps.

2. **Material 3 (`@material/web` 2.5.0) — OPT-IN ONLY (when explicitly requested):**
   - **Caveat:** `@material/web` is in **MAINTENANCE MODE**. No new features planned.
   - **"Stock" means a *stable*, shipped component.** Treat **labs** components as **absent**.
   - Known **gaps** requiring custom Lit elements: **tooltip, accordion/expansion-panel, navigation-drawer**.

Baselines for both: **lit 3.3.3**, router **`@vaadin/router` 2.0.1** (stable).

---

## The Construct Translation Table

| Mesop construct | Web Awesome (Default) | Material Web (Opt-in M3) | FastAPI / server | Outcome (WA / MWC) |
|---|---|---|---|---|
| `@me.stateclass` (server-held) | Reactive `@state()`/`@property` on the element | Reactive `@state()`/`@property` on the element | **none** — becomes browser state | client |
| `me.state(X)` read/mutate in handler | `this.foo = ...` (auto re-render) | `this.foo = ...` (auto re-render) | n/a | client |
| `on_click`/`on_blur`/`on_input` | `@click=`/`@input=`/`@change=` | `@click=`/`@input=`/`@change=` | only LLM calls become `fetch` | client |
| generator handler `yield` (spinner) | `async` method + `loading` flag | `async` method + `loading` flag | plain `async def` JSON route | mechanical |
| `me.box(style=me.Style(...))` layout | plain `<div>` + CSS (flex/grid) | plain `<div>` + CSS (flex/grid) | n/a | **not a component** |
| `me.text(...)` typography | HTML + CSS / utility tokens | HTML + M3 typescale tokens | n/a | not a component |
| `me.markdown(...)` | `<wa-markdown>` or `marked`+`DOMPurify` | `md-markdown` (marked+DOMPurify) | server may return pre-rendered HTML | stock / helper |
| `me.input` | `<wa-input>` | `<md-outlined-text-field>` | — | **stock** |
| `me.native_textarea` (+`on_blur`+`key++`) | `<wa-textarea>` | `<md-outlined-text-field type="textarea">` | — | **stock** (2-way bind deletes hack) |
| `me.button` (flat/stroked/raised) | `<wa-button>` | `<md-filled/outlined/elevated/text-button>` | — | **stock** |
| `me.content_button(type="icon")` | `<wa-icon-button>` | `<md-icon-button>` | — | **stock** |
| `me.icon(...)` | `<wa-icon>` | `<md-icon>name</md-icon>` | — | **stock** |
| `me.select` + `me.SelectOption` | `<wa-select>` + `<wa-option>` | `<md-outlined-select>` + `<md-select-option>` | — | **stock** |
| `me.slider` | `<wa-range>` / `<wa-slider>` | `<md-slider>` | — | **stock** |
| `me.progress_spinner` | `<wa-spinner>` | `<md-circular-progress indeterminate>` | — | **stock** |
| `me.divider` | `<wa-divider>` | `<md-divider>` | — | **stock** |
| chips / tags | `<wa-tag>` / `<wa-badge>` | `<md-chip-set>` + `<md-input-chip>` | — | **stock** |
| custom `modal` content-component | `<wa-dialog>` | `<md-dialog>` | — | **stock** |
| `me.tabs` / collapsible `tab_box` | `<wa-tab-group>` + `<wa-tab>` + `<wa-tab-panel>` | `<md-tabs>` + `<md-primary-tab>` | — | **stock** |
| `me.expansion_panel` | **`<wa-details>` / `<wa-accordion>` (stock)** | **No M3 element** → custom `app-accordion` over `<details>` | — | **stock** (WA) / **custom** (M3) |
| `me.tooltip` | **`<wa-tooltip>` (stock)** | **No stable M3 tooltip** → custom tooltip / `title=` | — | **stock** (WA) / **custom** (M3) |
| `me.sidenav` (collapsible) | **`<wa-drawer>` (stock)** | **nav-drawer is labs** → custom `app-sidenav` | — | **stock** (WA) / **custom** (M3) |
| copy to clipboard (`copy_button`) | **`<wa-copy-button>` (stock)** | custom Lit button with navigator.clipboard | — | **stock** (WA) / **custom** (M3) |
| `me.content_component` + `me.slot()` | Lit `<slot>` projection | Lit `<slot>` projection | — | compose |
| `page_scaffold`/`page_frame` | `app-root` shell with `<slot>` / router outlet | `app-root` shell with `<slot>` / router outlet | — | compose |
| navigation `me.navigate` (index-keyed) | client router (`@vaadin/router`) | client router (`@vaadin/router`) | FastAPI serves SPA fallback | compose |
| routing `@me.page(path=...)` | client route table | client route table | `APIRouter` for data endpoints | — |
| theming `theme_var`/`set_theme_mode` | Web Awesome theme tokens + light/dark | M3 CSS custom properties (`--md-sys-color-*`) | — | not a component |
| `me.SecurityPolicy(...)` | FastAPI header middleware (CSP) | FastAPI header middleware (CSP) | FastAPI middleware | server |
| bespoke result view (checklist, etc.) | **custom Lit element** | **custom Lit element** | returns typed JSON | **custom (Q5)** |
| `google.genai` / `LLMClient` call | stays server-side | stays server-side | unchanged in FastAPI services | server |

---

## How the Analyzer Feeds This Table
`analyze_mesop_app.py` pre-maps constructs based on `--target-ui webawesome` (default) or `--target-ui material-web`.
In Web Awesome mode, accordions, tooltips, and drawers map to stock components, saving substantial engineering time.
