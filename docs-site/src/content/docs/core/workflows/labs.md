---
title: "Labs & Experimental Workflows"
description: "Incubator hub (/labs) and experimental domain workflows in GenMedia Creative Studio."
---

The **Labs** workspace (`/labs`, implemented in `pages/test_index.py` and `main.py`) serves as GenMedia Creative Studio's experimental incubator. New domain workflows, evaluation harnesses, and UI component prototypes are built and validated here before graduating to the main Studio navigation bar.

:::note[Graduation Lifecycle]
Labs workflows are functional prototypes designed for rapid iteration and customer experimentation. Once a workflow stabilizes its prompt schemas, model adapters, and UI ergonomics, it graduates into a primary [Creative Workflow](/genmedia-creative-studio/core/workflows/) with dedicated navigation and architectural diagrams.
:::

## Quick Reference Matrix

| Workflow | Route | Models Orchestrated |
| :--- | :--- | :--- |
| **[Retro Games](#retro-games)** | `/retro_games` | Gemini + Nano Banana + Veo (`16:9` / `9:16`) |
| **[Brand Adherence](#brand-adherence)** | `/brand_adherence` | Gemini (`BrandBrief` PDF parser & `EvaluationResult` critic) + Nano Banana |
| **[Character Asset Sheet](#character-asset-sheet)** | `/character_sheet` | Nano Banana (`gemini-2.5-flash-image` / `gemini-3.1-flash-image-preview`) |
| **[Guideline Analysis](#guideline-analysis)** | `/guideline-analysis` | Gemini (`GUIDELINE_CRITERIA_TEMPLATE` multimodal QA rubric) |
| **[Object Rotation](#object-rotation)** | `/object-rotation` | Veo (360° product showcase video) |
| **[Banana Studio](#banana-studio)** | `/banana-studio` | Nano Banana + `config/banana_presets.json` |
| **[VTO Composite Card Generator](#vto-composite-card-generator)** | `/test_vto_prompt_generator` | `VirtualModelGenerator` (Imagen / Nano Banana) |

---

## Incubating Creative & Evaluation Workflows

### Retro Games (`/retro_games`)
* **Source Files:** `pages/retro_games.py`, `models/retro_games.py`, `config/retro_styles.py`
* **Capabilities:** Generates 8-bit and 16-bit pixel-art video game character cards, sprite sheets, and playable retro arcade intro animations by chaining **Gemini** character concept expansion, **Nano Banana** pixel-art image synthesis, and **Veo** retro gameplay video generation (`16:9` or `9:16`).

### Brand Adherence (`/brand_adherence`)
* **Source Files:** `pages/brand_adherence.py`, `state/brand_adherence_state.py`, `components/brand_adherence/`
* **Capabilities:** Users upload a **Brand Guidelines PDF** (`application/pdf`) and an optional product reference image:
  1. **Gemini** extracts a structured `BrandBrief` (`color_palette`, `typography_style`, `photography_direction`, `logo_usage_rules`, `brand_voice`).
  2. Synthesizes a brand-aligned campaign prompt and generates candidate imagery with **Nano Banana**.
  3. Scores each generated image with a multimodal **Brand Critic (`EvaluationResult`)** across color, typography, composition, and brand voice criteria (`0–10` rubric).

### Character Asset Sheet (`/character_sheet`)
* **Source Files:** `pages/character_sheet.py`, `state/character_sheet_state.py`, `components/character_sheet/`
* **Capabilities:** Converts a single character description or reference image into a comprehensive production **Turnaround & Expression Asset Sheet** using **Nano Banana**:
  * **Multi-angle orthographic views:** *Front*, *Left Profile*, *Right Profile*, and *Back*.
  * **Facial expression grid:** *Happy*, *Angry*, *Surprised*, and *Thoughtful* character portraits for downstream animation and 3D modeling.

### Guideline Analysis (`/guideline-analysis`)
* **Source Files:** `pages/guideline_analysis.py`
* **Capabilities:** Multimodal creative QA auditor (`GUIDELINE_CRITERIA_TEMPLATE`) that evaluates existing or generated images against custom creative, safety, and brand guideline checklists using **Gemini** structured rubrics.

### Object Rotation (`/object-rotation`)
* **Source Files:** `pages/object_rotation.py`
* **Capabilities:** Generates 360-degree rotating product showcase videos from a single e-commerce product photograph using **Veo**.

### Banana Studio (`/banana-studio`)
* **Source Files:** `pages/banana_studio.py`, `config/banana_presets.json`
* **Capabilities:** Preset-driven quick-launch gallery for **Nano Banana**, allowing users to apply curated visual transformations and multi-image composition recipes in one click.

### VTO Composite Card Generator (`/test_vto_prompt_generator`)
* **Source Files:** `pages/test_vto_prompt_generator.py`, `models/virtual_model_generator.py`
* **Capabilities:** Batch utility that uses `VirtualModelGenerator` to synthesize multi-pose fashion model composite cards for Virtual Try-On testing.

---

## UI & Infrastructure Test Harnesses (`/labs`)

The `/labs` index (`pages/test_index.py`) also exposes developer harnesses used to test custom Lit WebComponents and storage integrations in isolation:

* **Media Chooser Test (`/test_media_chooser`):** `pages/test_media_chooser.py` — Tests the unified Firestore Library / GCS media picker dialog (`components/media_chooser/`).
* **Pixie Timeline Test (`/test_pixie_timeline`):** `pages/test_pixie_timeline.py` — Tests the custom Lit multi-track timeline WebComponent (`components/pixie_timeline/`).
* **Uploader Test (`/test_uploader`):** `pages/test_uploader.py` — Tests multi-slot drag-and-drop GCS uploaders and Library chooser bindings.
* **SVG & Character Consistency Harness (`/test_svg`, `/test_character_consistency`):** `pages/test_svg.py`, `pages/test_character_consistency.py` — Component sandboxes for vector rendering and step-by-step state inspection.
