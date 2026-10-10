# Component decisions: stock vs compose vs custom (+ the DRY gate)

Given one Mesop construct, decide: **(a)** use a stable UI library component as-is (stock),
**(b)** compose 2–3 stable components with light glue, or **(c)** build a custom Lit
element — and where to draw the boundary.

## Framework Context: Web Awesome (Default) vs. Material Web (Opt-in)

* **Web Awesome (`@awesome.me/webawesome` 3.14.0, MIT) — DEFAULT:**
  * Fully featured, actively maintained, Lit-native.
  * Off-the-shelf stock components cover the known MWC gaps:
    * Accordion: `<wa-details>` / `<wa-accordion>` + `<wa-accordion-item>` (**stock**)
    * Drawer: `<wa-drawer>` (**stock**)
    * Tooltip: `<wa-tooltip>` (**stock**)
    * Copy button: `<wa-copy-button>` (**stock**)
    * Dialog: `<wa-dialog>` (**stock**)
* **Material Web (`@material/web` 2.5.0) — OPT-IN ONLY:**
  * In **maintenance mode**.
  * Labs treated as absent.
  * Custom Lit elements must be built for accordion, nav-drawer, and tooltip.

---

## The Q1–Q5 Procedure

```
START with one construct.
├─ Q1. Pure layout (me.box/grid/flex, styling only)?
│      YES → NOT a component. Plain HTML + CSS in the parent template.
├─ Q2. Does a STABLE component in the chosen library match 1:1?
│      YES → (a) USE STOCK. Wrap only to set attributes/events.
│            (Under Web Awesome, drawer, details/accordion, tooltip, copy-button all pass here!)
├─ Q3. Can 2–3 stable components + light glue express it?
│      YES → (b) COMPOSE. Thin Lit element arranging stock parts, owning only glue state.
├─ Q4. Gap because the chosen library lacks it?
│      YES → (c) BUILD CUSTOM over a native primitive (<details>, <dialog>, ARIA) + design tokens.
└─ Q5. Bespoke domain UI with no general equivalent (e.g. a results view)?
       YES → (c) BUILD CUSTOM, domain-named, owns its render logic + the API shape it displays.
```

---

## The DRY gate (cross-cutting, overrides a/b/c)
Independent of the Q-path: **if a construct is duplicated across pages, promote it to
ONE shared component at its first reuse.** Duplication is the strongest boundary
signal — stronger than visual complexity. The analyzer surfaces this directly: any
function name defined in ≥2 modules is reported under **duplicate_components**, and each
mesop-component duplicate is emitted as a **promote-shared** decision.

---

## Comparison: Promptlandia-shaped Decisions

| Construct (detected) | Web Awesome (Default) | Material Web (Opt-in) |
|---|---|---|
| `me.button` / `content_button` | **stock** `<wa-button>` / `<wa-icon-button>` | **stock** `md-*-button` / `md-icon-button` |
| `native_textarea` + `on_blur` + `key++` | **stock** `<wa-textarea>` | **stock** `<md-outlined-text-field type=textarea>` |
| `me.select` / `me.slider` | **stock** `<wa-select>` / `<wa-range>` | **stock** `md-outlined-select` / `md-slider` |
| `me.expansion_panel` | **stock** `<wa-details>` / `<wa-accordion>` | **custom** `app-accordion` over `<details>` |
| `me.tooltip` | **stock** `<wa-tooltip>` | **custom** tooltip / `title=` |
| `me.sidenav` (drawer) | **stock** `<wa-drawer>` | **custom** `app-sidenav` |
| `copy_button` | **stock** `<wa-copy-button>` | **custom** copy button |
| `modal_or_dialog` | **stock** `<wa-dialog>` | **stock** `md-dialog` |
| `gemini_prompt_input` ×4 (DRY) | **promote-shared** `prompt-input` | **promote-shared** `prompt-input` |
| `checklist-results` | **custom (Q5)** `checklist-results` | **custom (Q5)** `checklist-results` |
| `page_scaffold` + `slot` | **compose** `app-root` | **compose** `app-root` |

**Conclusion:** Using Web Awesome turns 4 custom component builds into off-the-shelf stock usage, dramatically reducing lines of code and maintenance burden.
