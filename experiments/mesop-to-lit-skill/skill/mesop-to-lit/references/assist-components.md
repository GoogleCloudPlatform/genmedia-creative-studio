# Assist: build the Lit components (order + recipes)

The `component-decisions.md` framework decided *what* to build (stock / compose / custom).
This is *how* — the build order and concrete recipes for components using **Web Awesome (default)**
or **Material Web (opt-in)**.

## Build order (dependencies first)
Build leaves before the things that compose them so each is testable on arrival:
```
theme.ts  →  md-markdown  →  prompt-input  →  app-accordion (WA: stock <wa-details>)
          →  checklist-results (bespoke)    →  app-header / app-sidenav (WA: stock <wa-drawer>)
          →  pages (page-checklist)         →  app-root (shell + router)
```

---

## 1. Theming

### Web Awesome (Default)
Import the Web Awesome theme stylesheet in `main.ts` or `index.html`:
```ts
import '@awesome.me/webawesome/dist/styles/themes/default.css';
```
Web Awesome supports dark mode natively by adding `class="wa-theme-default-dark"` (or toggling `.dark` with CSS variables) to `<html>` or container elements.

### Material Web (Opt-in)
Mesop's `theme_var`/`set_theme_mode` → M3 `--md-sys-color-*` custom properties set on `<html>`. Persisted via `localStorage` + system color-scheme detection.

---

## 2. Markdown (`md-markdown`)
Replaces Mesop's `me.markdown`. In Web Awesome, `<wa-markdown>` is available stock, or use the standard `marked` + `DOMPurify` helper:
```ts
DOMPurify.sanitize(marked.parse(text, { async: false }))
```
DOMPurify is **mandatory** when rendering model-generated text.

---

## 3. Shared Prompt Input (`prompt-input`)
The 4× copy-pasted `gemini_prompt_input` → one shared element.
- **Web Awesome:** Use `<wa-textarea>` and `<wa-button>` or `<wa-icon-button>`. Two-way binding via `@wa-input` or native `@input` deletes the Mesop `on_blur` + `key++` remount hack.
- **Material Web:** Native `<textarea>` or `<md-outlined-text-field type="textarea">` with clear/send buttons.

---

## 4. Accordion / Expansion Panels
- **Web Awesome (Stock):**
  Use `<wa-details summary="...">` or `<wa-accordion>` with `<wa-accordion-item>`.
  ```html
  <wa-details summary="Issues found (3)">
    <div class="content">...</div>
  </wa-details>
  ```
  Zero custom code required.
- **Material Web (Custom):**
  MWC has no accordion. Build custom `<app-accordion>` wrapping native `<details>/<summary>` with M3 token styling.

---

## 5. Navigation Drawer / Sidenav
- **Web Awesome (Stock):**
  Use `<wa-drawer placement="start" label="Menu">` with `<wa-button>` or navigation links. Light-dismiss, open/close animations, and focus management are built in.
- **Material Web (Custom):**
  MWC nav-drawer is labs-only. Build custom `<app-sidenav>` using CSS transitions over `<aside>` / `md-list`.

---

## 6. Tooltips & Copy Button
- **Web Awesome (Stock):**
  `<wa-tooltip content="Copy prompt"><wa-copy-button value=${text}></wa-copy-button></wa-tooltip>`
- **Material Web (Custom):**
  Custom Lit directive / HTML `title`, manual `navigator.clipboard.writeText(...)`.

---

## Lit-under-test quirks (happy-dom) — Key Lessons

### 1. Element Internals in happy-dom
- **Web Awesome:** Form-associated custom elements require `element-internals-polyfill`.
  Import `import 'element-internals-polyfill';` in your test setup (`test/setup.ts` or top of tests).
  Once imported, Web Awesome components render and test cleanly under happy-dom.
- **Material Web:** MWC custom elements crash happy-dom if imported directly into unit tests (`attachInternals is not a function`).
  When targeting MWC, keep unit-tested components MWC-free and register MWC exclusively in `main.ts`.

### 2. A nested template at the template ROOT mis-parses → renders as `<?>`
A `TemplateResult` placed directly at a template's root with no enclosing element commits as the literal text `<?>` under happy-dom and shifts sibling bindings.
**Rule:** Every `html` fragment must begin with a static element:
```ts
// GOOD — wrapped in a container:
render() {
  return html`<div class="results">${a ? html`...` : nothing}</div>`;
}
```

### 3. Interpolated adjacent expressions inject template whitespace
Build multi-part phrases as a single JavaScript string template:
```ts
`Checklist found ${n} ${plural}`
```
instead of interpolating adjacent variables separated by template newlines.

### 4. Property binding for complex data
Pass objects/arrays via `.data=${obj}` declared `@property({attribute: false})`.
