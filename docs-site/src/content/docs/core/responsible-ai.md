---
title: "Responsible AI & Safety Alignment"
description: "How GenMedia Creative Studio implements inclusive representation (Monk Skin Tone Scale), model safety controls, and media provenance (SynthID and C2PA)."
---

GenMedia Creative Studio pairs Vertex AI generative media models with application-level practices for **inclusive representation**, **model safety alignment**, and **cryptographic media provenance**. This page documents the current implementation across the Core Application and serves as the reference guide for contributors adding new generative workflows.

---

## 1. Inclusive Virtual Model Generation & the Monk Skin Tone Scale

Workflows that synthesize human models for apparel or merchandising (**Virtual Try-On**, **Starter Pack**, and the **VTO Composite Card Generator**) use a shared, data-driven taxonomy defined in `config/virtual_model_options.json` and assembled by `models/virtual_model_generator.py` (`VirtualModelGenerator`).

### Monk Skin Tone (MST) Scale

To avoid homogeneous default outputs and represent a broad spectrum of complexions, `config/virtual_model_options.json` incorporates the 10-point **Monk Skin Tone Scale**:

> **Citation & License:** Monk, Ellis. *"Monk Skin Tone Scale,"* 2019 ([https://skintone.google](https://skintone.google)). Licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). See [Monk Skin Tone Recommended Practices](https://skintone.google/recommended-practices).

| Scale Point | Hex Swatch | Prompt Fragment (`config/virtual_model_options.json`) |
| :--- | :--- | :--- |
| **MST-1** | `#f6ede4` | `a very light skin tone with balanced undertones (#f6ede4)` |
| **MST-2** | `#f3e7db` | `a light skin tone with warm, yellow undertones (#f3e7db)` |
| **MST-3** | `#f7ead0` | `a light-medium skin tone with golden undertones (#f7ead0)` |
| **MST-4** | `#eadaba` | `a medium skin tone with olive undertones (#eadaba)` |
| **MST-5** | `#d7bd96` | `a medium-tan skin tone with warm, caramel undertones (#d7bd96)` |
| **MST-6** | `#a07e56` | `a tan-brown skin tone with neutral undertones (#a07e56)` |
| **MST-7** | `#825c43` | `a medium-dark brown skin tone with reddish undertones (#825c43)` |
| **MST-8** | `#604134` | `a dark brown skin tone with cool, espresso undertones (#604134)` |
| **MST-9** | `#3a312a` | `a very dark brown skin tone with neutral undertones (#3a312a)` |
| **MST-10** | `#292420` | `the deepest brown-black skin tone with cool undertones (#292420)` |

### Inclusive Representation Axes

Alongside MST, `config/virtual_model_options.json` structures two additional attributes deliberately:

- **Presentation-Based Gender Terms (`genders`):** Uses `Feminine-presenting`, `Masculine-presenting`, and `Androgynous` rather than identity labels. A synthetic model has a visual appearance rather than a personal identity; presentation-based wording accurately describes visual traits without mislabeling.
- **Neutral Geometric Silhouettes (`silhouette_presets`):** Uses descriptive, non-judgmental geometric language (`Linear & Balanced`, `Tapered & Grounded`, `Inverted Triangle`, `Classic Hourglass`) so every body form is treated as an equal starting point rather than a "default" or "deviation."

### Where MST Is Wired in the Application

| Surface | File Path | Behavior |
| :--- | :--- | :--- |
| **Taxonomy & Prompt Builder** | `config/virtual_model_options.json`, `models/virtual_model_generator.py` | Stores the CC-BY-4.0 citation, MST-1..10 fragments, gender presentation, silhouette presets, and pose variants; validates that custom prompt templates retain all four placeholders (`{gender}`, `{MST}`, `{silhouette}`, `{variant}`). |
| **Virtual Try-On (`/vto`)** | `pages/vto.py` (`on_click_generate_person`) | Randomly samples across all four axes (including uniform sampling across `MST-1`–`MST-10`) and generates a studio portrait via `models/image_models.py` (`generate_virtual_models` → Gemini Image / Nano Banana). |
| **Starter Pack (`/starter-pack`)** | `models/starter_pack.py` (`generate_virtual_model`) | Randomly samples across all four axes using `VirtualModelGenerator` to synthesize a virtual model before dressing it in the Starter Pack items. |
| **VTO Composite Card Generator (`/test_vto_prompt_generator`)** | `pages/test_vto_prompt_generator.py` | Interactive matrix UI allowing explicit selection or randomization of gender presentation, MST-1..10 (with live visual orb previews from `https://google-ai-skin-tone-research.imgix.net/orbs/monk-XX.png`, allowlisted in `main.py` CSP `img-src`), and silhouette presets. |

---

## 2. Generated-Model Safety Alignment Controls

GenMedia Creative Studio relies on Vertex AI's built-in Responsible AI (RAI) filters and configures explicit policy controls per modality and workflow.

### `person_generation` Policies

| Workflow / Adapter | File Path | Default | Configurable Options |
| :--- | :--- | :--- | :--- |
| **Veo Video Generation (`/veo`)** | `state/veo_state.py`, `models/veo.py`, `components/veo/generation_controls.py` | `Allow (Adults only)` (`allow_adult`) | `Allow (All ages)` (`allow_all`), `Allow (Adults only)` (`allow_adult`), `Don't Allow` (`dont_allow`) |
| **Character Consistency** | `models/character_consistency.py` | `allow_adult` | Hardcoded in Veo step |
| **Motion Portraits** | `pages/portraits.py` | `allow_adult` | Hardcoded in Veo step |
| **Storyboarder** | `models/storyboard_video.py` | `Allow (Adults only)` (`allow_adult`) | Hardcoded in Veo step |
| **Interior Design** | `models/workflow_video.py` | `dont_allow` | Hardcoded (architectural / room walkthroughs) |
| **Virtual Try-On (`/vto`)** | `pages/vto.py`, `models/vto.py` | UI: `allow_all` / Adapter: `allow_all` | `Allow (All ages)` (`allow_all`), `Allow (Adults only)` (`allow_adult`) |

### Safety Filter Thresholds & `BLOCK_NONE` Policy

- **Virtual Try-On (`safety_filter_level`):** `pages/vto.py` exposes a **Safety Filter** selector (`Block most` → `block_low_and_above`, `Block some` → `block_medium_and_above`, `Block few` → `block_only_high`). `models/vto.py` defaults to `block_low_and_above` when called programmatically.
- **Imagen RAI Transparency:** `models/image_models.py` (`generate_images`) passes `include_rai_reason=True` so any server-side RAI moderation decision is logged and surfaced clearly instead of failing silently.
- **Gemini `safety_settings` Scoping Rule:**
  - User-facing generative endpoints (`models/gemini.py` image generation, text rewriters, Veo prompt enhancers) **retain Vertex AI default safety thresholds**.
  - Explicit `HarmBlockThreshold.BLOCK_NONE` overrides are restricted solely to internal evaluation/inspection helpers (`models/gemini.py` `analyze_audio` and `critique_images`) so the automated critic can inspect and score already-generated assets without spurious self-refusals. Do **not** copy `BLOCK_NONE` onto user-facing generation calls.

### RAI Error Classification & Telemetry

`common/error_handling.py` (`classify_error`) detects Vertex AI moderation and recitation blocks (`rai`, `recitation`, `harmful`, `content policy`, `finish_reason`, `safety_filter_exceeded`, `safety violation`) and classifies them as `ErrorCategory.SAFETY_FILTER` with `retryable: False`. This ensures:
- Safety blocks are never blindly retried in automated loops.
- Structured analytics logs record `SAFETY_FILTER` counts separately from transient capacity (`429`) or timeout (`504`) errors.

### Prompt Safety Rewriting (MCP Skills & Experiments)

- **Clinical Rewrite Guidance:** The GenMedia MCP skills (`experiments/mcp-genmedia/mcp-genmedia-go/GEMINI.md` and `genmedia-image-artist`) document the **Clinical Rewrite** technique for legitimate creative/cinematic prompts that trip false-positive safety filters: replace emotionally charged labels (e.g., *"terror"*, *"horror"*) with objective physical descriptions (e.g., *"eyes widening"*, *"sharp intake of breath"*).
- **Child-Reference Sanitization (Experiment):** `experiments/veo-genetic-prompt-optimizer/veo_genetic_prompt_optimizer/rewrite_prompt_for_safety.py` provides an automated pre-flight sanitizer that removes minor/child references from benchmark prompts before calling `allow_adult`-scoped Veo endpoints.

---

## 3. Media Provenance: SynthID & C2PA Content Credentials

Transparency and provenance verification are built directly into the Studio UI and backend:

- **SynthID Digital Watermarking:** Imagen generation (`components/imagen/advanced_controls.py`, `components/imagen/image_output.py`) keeps `state.imagen_watermark = True` locked on (disabled checkbox) and renders a visible **Images watermarked by SynthID (Google)** badge beneath generated galleries.
- **C2PA Content Credentials Inspection:**
  - **Backend (`services/c2pa_service.py`):** Uses `c2pa-python` (`c2pa.Reader`) to extract signed C2PA manifests from generated local files or GCS assets.
  - **UI (`components/content_credentials/`):** Renders the `<content-credentials>` Lit web component on generated media cards in **Gemini Image (`/gemini_image_generation`)**, **Lyria 3 (`/lyria`)**, **Veo**, and the **Library (`/library`)**, displaying claim generator, signing issuer, and `c2pa.actions` provenance assertions.

---

## 4. Contributor & Agent Guidelines

When adding a new generative model, page, or creative workflow to GenMedia Creative Studio:

1. **Reuse `VirtualModelGenerator` for synthetic people:** Load options from `config/virtual_model_options.json` so new apparel, portrait, or character workflows inherit the full `MST-1`–`MST-10` skin tone scale, neutral silhouettes, and presentation-based gender wording.
2. **Preserve the MST CC-BY-4.0 attribution:** Keep the `_citation` entry in `config/virtual_model_options.json` and link to `https://skintone.google/recommended-practices` in any UI displaying the scale.
3. **Default `person_generation` conservatively:** Use `allow_adult` for human-capable video workflows and `dont_allow` for architectural or product-only scenes unless the workflow explicitly requires `allow_all`.
4. **Never disable safety filters on user-facing generation:** Keep Vertex AI's default safety settings on generation paths; reserve `BLOCK_NONE` strictly for internal evaluation/audit helpers.
5. **Preserve provenance metadata:** Persist C2PA manifests and avoid lossy re-encoding steps that strip embedded Content Credentials or SynthID watermarks.
