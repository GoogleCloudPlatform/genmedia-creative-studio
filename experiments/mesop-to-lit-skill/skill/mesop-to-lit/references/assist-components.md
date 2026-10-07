# Assist: build the Lit components (order + recipes)

The `component-decisions.md` framework decided *what* to build (stock / compose / custom).
This is *how* — the build order and the concrete recipes for the components the conversion
actually required, plus the Lit-under-test quirks that cost real time.

## Build order (dependencies first)
Build leaves before the things that compose them so each is testable on arrival:
```
theme.ts  →  md-markdown  →  prompt-input  →  app-accordion
          →  checklist-results (bespoke)    →  app-header / app-sidenav
          →  pages (page-checklist)         →  app-root (shell + router)
```
`theme.ts`, `md-markdown`, `prompt-input`, `app-accordion`, `checklist-results` have **no
MWC dependency** and are unit-tested. `app-sidenav`/`app-header`/`app-root`/`main.ts` use
stable MWC and are browser-only (see the MWC/happy-dom rule below).

## Theming (`theme.ts`)
Mesop's `theme_var`/`set_theme_mode` → M3 `--md-sys-color-*` custom properties set on
`<html>`. Default to **system** (`matchMedia('(prefers-color-scheme: dark)')`), allow a
persisted override (`localStorage`) + a toggle. Components read tokens via
`var(--md-sys-color-*, <fallback>)` — the fallback keeps them rendering in tests where the
theme is not applied.

## `md-markdown` — sanitize, always
Replaces Mesop's `me.markdown` (×28). `marked.parse(text, { async: false })` →
`DOMPurify.sanitize(...)` → `unsafeHTML(...)` inside a wrapper `<div class="md">`.
DOMPurify is **mandatory** — we render model output; Trusted Types is not needed because
we control rendering (drop Mesop's `dangerously_disable_trusted_types`). Keep the
component MWC-free.

## `prompt-input` — the shared input (DRY promotion)
The 4× copy-pasted `gemini_prompt_input` → one shared element. A native `<textarea>` with
`.value=${this.value}` + `@input` gives real two-way binding, which **deletes the Mesop
`on_blur` + `key++` remount hack**. Clear/send are native `<button aria-label=...>` with
an `<md-icon>` glyph; emit `value-changed` / `send` / `clear` as
`composed: true, bubbles: true` CustomEvents. Guard `send` on `disabled`.

## `app-accordion` — custom over a native primitive
MWC has no accordion (confirmed absent). Build on `<details>/<summary>` — a11y + open
state for free. `@property({reflect:true}) open`, style `summary::after` with a Material
Symbols chevron, and re-emit the native `toggle` as a CustomEvent carrying `{open}`.
Prefer native primitives (`<details>`, `<dialog>`) over hand-built widgets for every MWC
gap.

## `checklist-results` — the bespoke domain component (Q5)
Consumes the typed `ChecklistResponse`. Renders two sections: a **grid of issue
categories** (flag icon, humanized category + issue names, per-item detail via nested
`md-markdown`, dividers, a category "explanation") and a **passed-checks list** (check
icon). The parse-fallback branch (`categories:[]`, `raw` set) renders the raw text through
`md-markdown`. A `humanize()` helper turns `snake_case` keys into `Title Case`.

This is the component that exercised every Lit-under-test quirk below — read them before
writing any component whose template branches or loops.

## Lit-under-test quirks (happy-dom) — the expensive lessons
These cost the most time in the conversion. They are **test-environment** quirks
(happy-dom's HTML parser), not Lit bugs, but they dictate how you must write templates if
you want component tests to pass.

### 1. MWC crashes happy-dom on import
Importing any `@material/web` component under happy-dom throws
`this.attachInternals is not a function`. **Keep every unit-tested component MWC-free** —
use native elements + bare `<md-icon>glyph</md-icon>` tags (an unregistered `<md-icon>` is
an inert unknown element in tests and the real font glyph in the browser). Register the
stable MWC imports **only in `main.ts`**, which tests never import.

### 2. A nested template at the template ROOT mis-parses → renders as `<?>`
This is the big one. A `TemplateResult` placed **directly at a template's root**, with no
enclosing element, is mis-parsed by happy-dom and commits as the literal text `&lt;?&gt;`
instead of the template — and it **shifts every binding after it**, so sibling `.prop`
bindings receive the *wrong value* (we saw `md-markdown.text` get an object → `marked():
input ... [object Object]`). Symptom: the component renders empty/garbled only in tests,
fine in the browser.

**Rule: every `html\`...\`` fragment must begin with a static element and must not place a
bare `${nested-template-or-conditional}` as a root child.** Wrap the whole render body in a
container:
```ts
// BAD — root-level child parts (mis-parses under happy-dom):
render() { return html`${a ? html`...` : nothing} ${b ? html`...` : nothing}`; }
// GOOD — wrapped; child parts live inside a static element:
render() { return html`<div class="results">
  ${a ? html`...` : nothing} ${b ? html`...` : nothing}
</div>`; }
```
Apply it at **every** nesting level: a helper like `renderItem()` that returns
`html\`<div>..</div> ${trailing}\`` should wrap its whole output in one element; a
conditional sub-template that *starts* with `${x ? ... : nothing}` should start with a
static element instead. Arrays from `.map()` are fine as long as they sit **inside** a
container element (`<div class="grid">${items.map(...)}</div>`).

### 3. Interpolated adjacent expressions inject template whitespace
`Checklist found ${n}\n  ${plural}` renders as `"Checklist found 1\n  issue"` — the
template's own newline/indentation lands between the values, so a
`textContent.includes("Checklist found 1 issue")` assertion fails on invisible whitespace.
Build such phrases as a **single JS string** (`` `Checklist found ${n} ${plural}` ``) and
interpolate once, or assert against normalized whitespace.

### 4. `@property({attribute: false})` for object/array props
Pass structured data (`ChecklistResponse`) via a property binding (`.data=${obj}`) declared
`@property({attribute: false})` — never an attribute. (The empty-render symptom here was
actually quirk #2, not the property type, but object props must still be `attribute:false`.)

## Pages + shell
- `page-*`: own `@state() loading/result/error`; on send set `loading=true`, `await
  client.<action>()`, render `checklist-results` on success, the envelope `code: message`
  on error, a CSS spinner while loading. The generator-yield spinner → this `loading` flag.
- `app-root`: `<app-sidenav>` + `<main>` outlet; `initRouter(outlet)` in `firstUpdated`;
  track `vaadin-router-location-changed` to keep the active nav item in sync.
- `main.ts`: the ONLY place that imports MWC registrations + calls `applyTheme()`.

## Generalizing
Build leaves→composites; keep anything you want to unit-test MWC-free; wrap every template
body in a static container; build phrase strings in JS. These four rules make Lit
components pass under happy-dom on the first run.
