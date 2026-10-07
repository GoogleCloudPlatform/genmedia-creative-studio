# Component decisions: stock vs compose vs custom (+ the DRY gate)

Given one Mesop construct, decide: **(a)** use a stable Material Web component as-is,
**(b)** compose 2–3 stable components with light glue, or **(c)** build a custom Lit
element — and where to draw the boundary. Stays correct under one live fact:
**`@material/web` 2.5.0 is in maintenance mode**, so "stock" = *stable* and **labs = absent**.

## Inputs the decision needs
1. The construct's **behavior** (what it renders + does on interaction).
2. How often it **recurs** (once / per-page-duplicated / app-wide).
3. Whether a **stable** MWC component covers it — checked against live docs, not memory.
4. How much bespoke layout/logic **wraps** it (a stock element inside heavy custom
   structure is still a custom component *at the boundary*).

The analyzer supplies #1–#2 (construct inventory + duplicate detection); you supply the
live-docs check for #3.

## The Q1–Q5 procedure
```
START with one construct.
├─ Q1. Pure layout (me.box/grid/flex, styling only)?
│      YES → NOT a component. Plain HTML + CSS in the parent template.
├─ Q2. Does a STABLE @material/web component match 1:1?        [LIVE check]
│      YES → (a) USE STOCK. Wrap only to set attributes/events. Do not subclass.
├─ Q3. Can 2–3 stable MWC components + light glue express it?
│      YES → (b) COMPOSE. Thin Lit element arranging stock parts, owning only glue state.
├─ Q4. Gap because MWC lacks it (absent or labs-only)?         [LIVE check]
│      YES → (c) BUILD CUSTOM over a native primitive (<details>, <dialog>, ARIA) + M3 tokens.
└─ Q5. Bespoke domain UI with no general equivalent (e.g. a results view)?
       YES → (c) BUILD CUSTOM, domain-named, owns its render logic + the API shape it displays.
```

## The DRY gate (cross-cutting, overrides a/b/c)
Independent of the Q-path: **if a construct is duplicated across pages, promote it to
ONE shared component at its first reuse.** Duplication is the strongest boundary
signal — stronger than visual complexity. The analyzer surfaces this directly: any
function name defined in ≥2 modules is reported under **duplicate_components**, and each
mesop-component duplicate is emitted as a **promote-shared** decision.

## Tie-breakers
- Prefer **stock > compose > custom** (least code to own; inherits M3 a11y).
- Prefer **native-primitive-based custom** over from-scratch (`<details>` not a
  hand-built accordion; `md-dialog` not a hand-built modal).
- **Never adopt a labs component** in maintenance mode — treat labs as "absent" in Q4.
- A stock element buried in heavy custom layout is still (c) **at the page level** —
  name the boundary by the *reused unit*, not the leaf element.

## Worked examples (Promptlandia — what the analyzer detects → decision)
| Construct (detected) | Q-path | Decision | Why |
|---|---|---|---|
| `me.button`/`me.content_button` | Q2 | **stock** `md-*-button`/`md-icon-button` | 1:1, a11y for free |
| `native_textarea`+`on_blur`+`key++` | Q2 | **stock** `md-outlined-text-field type=textarea` | native 2-way binding deletes the remount hack |
| `me.select`/`me.slider`/`me.divider`/`me.progress_spinner`/`me.icon` | Q2 | **stock** | all stable |
| stop-sequence chips | Q2 | **stock** `md-chip-set`+`md-input-chip` | dynamic add/remove is local state |
| custom `modal` | Q2 | **stock** `md-dialog` | slot content in |
| `me.markdown` (×28) | — | **not a component** — `md-markdown` helper (marked + **DOMPurify**) | rendering concern; sanitize mandatory |
| **`gemini_prompt_input` ×4** (analyzer: duplicate, 4 modules) | DRY+Q2 | **promote-shared** `prompt-input` | textbook copy-paste → one component |
| `me.expansion_panel` (×9) | Q4 | **custom** `app-accordion` over `<details>` | MWC has no accordion |
| `me.tooltip` (×5) | Q4 | **custom** `app-tooltip` (ARIA) / `title=` | MWC has no tooltip |
| `me.sidenav` collapsible + theme toggle + index-nav | Q3/Q4 | **custom** `app-sidenav` composing `md-list`+`md-icon-button` | nav-drawer labs-only; collapse is bespoke |
| `page_scaffold` + `me.slot()` | Q3 | **compose** `app-root` shell + router outlet | `me.slot` → `<slot>`; drop unused `page_frame` |
| `header(title, icon)` | Q2/Q3 | **thin** `app-header` | every page uses it |
| **checklist results view** (grid, nested detail, flag/check icons) | Q5 | **custom** `checklist-results` | bespoke domain UI; no M3 equivalent; **one component serves `/checklist` + `/video-checklist`** (dedup) |
| collapsible `tab_box` | Q2/Q4 | **stock** `md-tabs`; tiny custom only for the collapse | don't rebuild tabs |
| gradient brand text | Q1 | **not a component** — CSS class | pure CSS |

## Resolved component list for a Promptlandia-shaped app
- **Stock (wiring only):** buttons, icon-button, icon, text-field, select, slider,
  dialog, chips, tabs, progress, divider, list, menu.
- **Composed/shared custom:** `app-root`, `app-sidenav`, `app-header`, `prompt-input`,
  `app-accordion`, `app-tooltip`, `md-markdown` (helper).
- **Bespoke custom:** `checklist-results` (design-heavy), per-page page elements.

## Generalizing
Run Q1–Q5 over the analyzer's construct inventory for any app. The procedure is
framework-stable; only the **Q2/Q4 live-docs check moves** — re-confirm MWC's stable set
at conversion time (maintenance mode means a construct that is custom today stays custom).
