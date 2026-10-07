# Construct map: Mesop → Lit + Material Web (M3) → FastAPI

The reusable translation table. **Re-confirm the Material Web column against live docs
each time** — `@material/web` is in **maintenance mode** (see the caveat below), so its
stable set is unlikely to grow but must still be verified.

## Fixed caveat — `@material/web` 2.5.0 is in MAINTENANCE MODE
No new components or features are planned (bug-fixes case-by-case). Practical rules:
- **"Stock" means a *stable*, shipped component.** Treat **labs** components as
  **absent** — they will never graduate, so adopting one is a permanent liability.
- Known **gaps** you must build custom for: **tooltip, accordion/expansion-panel,
  navigation-drawer** (nav-drawer is labs-only; tooltip/accordion are unbuilt).
- Baselines at time of writing: **lit 3.3.3**, router **`@vaadin/router` 2.0.1** (stable).

## Stable Material Web components (the "stock" set)
button, checkbox, chips, dialog, divider, elevation, fab, field, focus-ring, icon,
icon-button, list, menu, progress, radio, ripple, select, slider, switch, tabs,
text-field; plus theming via color/tokens/typography. These cover the bulk of a
typical Mesop app's primitives.

## The table

| Mesop construct | Lit + Material Web (M3) | FastAPI / server | Outcome |
|---|---|---|---|
| `@me.stateclass` (server-held) | Reactive `@state()`/`@property` on the element, or a small shared store | **none** — becomes browser state; only genuinely shared/secret state needs an endpoint | client |
| `me.state(X)` read/mutate in handler | `this.foo = ...` (auto re-render) | n/a | client |
| `on_click`/`on_blur`/`on_input`/`on_selection_change` | `@click=`/`@input=`/`@change=` DOM listeners | only handlers that call the LLM become `fetch` → route | client |
| generator handler `yield` (spinner/status) | `async` method + a `loading`/`status` reactive flag; `await fetch()` | plain `async def` route returning JSON (no stream needed) | mechanical |
| `me.box(style=me.Style(...))` layout | plain `<div>` + CSS (flex/grid) in `static styles` | n/a | **not a component** |
| `me.text(type="headline-5")` typography | HTML + M3 typescale tokens (`--md-sys-typescale-*`) | n/a | not a component |
| `me.markdown(...)` | a markdown→HTML render (`marked`) + **sanitizer (DOMPurify)** | server *may* return pre-rendered HTML instead | not a component (helper) |
| `me.input` | `md-outlined-text-field` / `md-filled-text-field` | — | **stock** |
| `me.native_textarea` / `me.textarea` (+`on_blur`+`key++`) | `md-outlined-text-field type="textarea"` (or native `<textarea>` for full style) | — | **stock** — native 2-way binding deletes the `on_blur`+`key++` remount hack |
| `me.button` (flat/stroked/raised) | `md-filled-/outlined-/elevated-/text-button` | — | stock |
| `me.content_button(type="icon")` | `md-icon-button` | — | stock |
| `me.icon(...)` (Material Symbols) | `<md-icon>name</md-icon>` + Symbols font | — | stock |
| `me.select` + `me.SelectOption` | `md-outlined-select` + `md-select-option` | — | stock |
| `me.slider` | `md-slider` | — | stock |
| `me.progress_spinner` | `md-circular-progress indeterminate` | — | stock |
| `me.divider` | `md-divider` | — | stock |
| chips (e.g. stop-sequences) | `md-chip-set` + `md-input-chip` | — | stock |
| custom `modal` content-component | `md-dialog` | — | stock |
| `me.tabs` / collapsible `tab_box` | `md-tabs` + `md-primary-tab` | — | stock (tiny custom wrapper only if collapse is required) |
| `me.expansion_panel` | **no M3 element** → native `<details>/<summary>` + M3 tokens, or tiny custom `app-accordion` | — | **custom** |
| `me.tooltip` | **no stable M3 tooltip** → `title=` attr or tiny ARIA element | — | **custom** |
| `me.sidenav` (collapsible) + theme toggle | **nav-drawer is labs** → custom `app-sidenav` composing `md-list`/`md-list-item` + `md-icon-button` | — | **custom** (compose stable parts) |
| `me.content_component` + `me.slot()` | Lit `<slot>` projection | — | compose |
| `page_scaffold`/`page_frame` | `app-root` shell with `<slot>` / router outlet | — | compose |
| navigation `me.navigate` (index-keyed) | client router (`@vaadin/router`); declarative route table | FastAPI serves SPA; deep links fall through to `index.html` | compose |
| routing `@me.page(path=...)` | client route table | `APIRouter` for **data** endpoints only (not pages) | — |
| theming `me.theme_var`/`set_theme_mode`/`theme_brightness` | M3 CSS custom properties (`--md-sys-color-*`) + light/dark (prefers-color-scheme / `data-theme`) | — | not a component |
| `me.SecurityPolicy(...)` / `allowed_iframe_parents` | — | FastAPI header middleware: CSP + `frame-ancestors` | server |
| bespoke result view (e.g. checklist grid) | **custom Lit element** named for the domain; owns one API type | returns the typed JSON it renders | **custom (Q5)** |
| `google.genai` / `LLMClient` call | — (stays server-side) | **unchanged** inside FastAPI (already Mesop-free if seam exists) | server |
| markdown→pydantic parse pipeline | — | **reused as-is**; becomes the JSON the API returns | server |

## How the analyzer feeds this table
`analyze_mesop_app.py` emits a **construct inventory** (presence + line counts) and a
**construct → component decisions** block. Each present construct is pre-mapped to its
stock/compose/custom/not-a-component outcome here; duplicated constructs are flagged
**promote-shared** (see `component-decisions.md`). Use the analyzer output as the input
to the decision procedure — do not hand-inventory what the script already found.
