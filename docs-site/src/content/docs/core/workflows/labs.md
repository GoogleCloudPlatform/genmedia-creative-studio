---
title: "Labs & Experimental Workflows"
description: "Incubator hub (/labs) and experimental domain workflows in GenMedia Creative Studio."
---

The **Labs** workspace (`/labs`, implemented in `pages/test_index.py` and `main.py`) serves as GenMedia Creative Studio's experimental incubator. New domain workflows, evaluation harnesses, and UI component prototypes are built and validated here before graduating to the main Studio navigation bar.

:::note[Graduation Lifecycle]
Labs workflows are functional prototypes designed for rapid iteration and customer experimentation. Once a workflow stabilizes its prompt schemas, model adapters, and UI ergonomics, it graduates into a primary [Creative Workflow](/genmedia-creative-studio/core/workflows/) with dedicated navigation and architectural diagrams.
:::

## Incubating Creative & Evaluation Workflows

| Workflow | Route | Source Files | Capabilities & Models Orchestrated |
| :--- | :--- | :--- | :--- |
| **Retro Games** | `/retro_games` | `pages/retro_games.py`, `models/retro_games.py`, `config/retro_styles.py` | Generates 8-bit/16-bit pixel-art video game character cards, sprite sheets, and playable retro arcade intro animations by chaining **Gemini** character concept expansion, **Nano Banana** pixel-art image synthesis, and **Veo** retro gameplay video generation (`16:9` / `9:16`). |
| **Brand Adherence** | `/brand_adherence` | `pages/brand_adherence.py`, `state/brand_adherence_state.py`, `components/brand_adherence/` | Upload a **Brand Guidelines PDF** (`application/pdf`) + optional product reference image. **Gemini** extracts a structured `BrandBrief` (`color_palette`, `typography_style`, `photography_direction`, `logo_usage_rules`, `brand_voice`), synthesizes a brand-aligned prompt, generates candidate campaign imagery with **Nano Banana**, and scores each generated image with a multimodal **Brand Critic (`EvaluationResult`)** across color, typography, composition, and brand voice criteria (`0–10` rubric). |
| **Character Asset Sheet** | `/character_sheet` | `pages/character_sheet.py`, `state/character_sheet_state.py`, `components/character_sheet/` | Converts a single character description or reference image into a comprehensive production **Turnaround & Expression Asset Sheet** using **Nano Banana (`gemini-2.5-flash-image` / `gemini-3.1-flash-image-preview`)**: multi-angle orthographic views (*Front*, *Left Profile*, *Right Profile*, *Back*) plus a grid of emotional facial expressions (*Happy*, *Angry*, *Surprised*, *Thoughtful*) for downstream animation and 3D modeling. |
| **Guideline Analysis** | `/guideline-analysis` | `pages/guideline_analysis.py` | Multimodal creative QA auditor (`GUIDELINE_CRITERIA_TEMPLATE`). Evaluates existing or generated images against custom creative, safety, and brand guideline checklists using **Gemini** structured rubrics. |
| **Object Rotation** | `/object-rotation` | `pages/object_rotation.py` | Generates 360-degree rotating product showcase videos from a single e-commerce product photograph using **Veo**. |
| **Banana Studio** | `/banana-studio` | `pages/banana_studio.py` | Preset-driven quick-launch gallery for **Nano Banana** (`config/banana_presets.json`), allowing users to apply curated visual transformations and multi-image composition recipes in one click. |
| **VTO Composite Card Generator** | `/test_vto_prompt_generator` | `pages/test_vto_prompt_generator.py` | Batch utility that uses `VirtualModelGenerator` to synthesize multi-pose fashion model composite cards for Virtual Try-On testing. |

## UI & Infrastructure Test Harnesses (`/labs`)

The `/labs` index (`pages/test_index.py`) also exposes developer harnesses used to test custom Lit WebComponents and storage integrations in isolation:

* **Media Chooser Test (`/test_media_chooser`):** `pages/test_media_chooser.py` — Tests the unified Firestore Library / GCS media picker dialog (`components/media_chooser/`).
* **Pixie Timeline Test (`/test_pixie_timeline`):** `pages/test_pixie_timeline.py` — Tests the custom Lit multi-track timeline WebComponent (`components/pixie_timeline/`).
* **Uploader Test (`/test_uploader`):** `pages/test_uploader.py` — Tests multi-slot drag-and-drop GCS uploaders and Library chooser bindings.
* **SVG & Character Consistency Harness (`/test_svg`, `/test_character_consistency`):** `pages/test_svg.py`, `pages/test_character_consistency.py` — Component sandboxes for vector rendering and step-by-step state inspection.
