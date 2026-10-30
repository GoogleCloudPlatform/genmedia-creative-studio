---
title: "Using GenMedia Creative Studio"
---

GenMedia Creative Studio provides a centralized interface for experimenting with Google Cloud's generative media models. The application is organized into three primary areas: [Foundation Model Workspaces](/genmedia-creative-studio/core/foundation-models/), [Creative Workflows](/genmedia-creative-studio/core/workflows/), and Studio management tools.

## 1. Navigating the Studio

*   **The Library (`/library`):** A centralized repository to browse, filter by media type, inspect C2PA Content Credentials, and download or reuse all your generated media.
*   **Settings & Configuration (`/config`):** Manage your application settings, API configurations, and experimental feature flags.

## 2. Foundation Models (Direct Generation)

Interact directly with the underlying generative media models to test prompts, compare model variants, and create single- or interleaved-modality outputs. See the **[Foundation Model Workspaces Overview](/genmedia-creative-studio/core/foundation-models/)** for the shared request lifecycle diagram.

*   **Image Generation:**
    *   **[Gemini Image Generation (Nano Banana)](/genmedia-creative-studio/core/foundation-models/nano-banana/):** Generate and conversationally edit high-resolution (`1K`–`4K`) images with up to 14 reference images and Google Search grounding using Nano Banana 2 (`gemini-3.1-flash-image-preview`), Nano Banana 2 Lite (`gemini-3.1-flash-image-lite-preview`), and Nano Banana Pro (`gemini-3-pro-image-preview`).
    *   **Imagen (Deprecated):** Legacy Imagen 3 and Imagen 4 models are being deprecated across Vertex AI. Use **[Gemini Image Generation (Nano Banana)](/genmedia-creative-studio/core/foundation-models/nano-banana/)** instead. See the [Imagen models migration guide](https://firebase.google.com/docs/ai-logic/imagen-models-migration?api=dev) for the replacement mapping.
*   **Multimodal & Video Generation:**
    *   **[Gemini Omni](/genmedia-creative-studio/core/foundation-models/gemini-omni/):** Generate interleaved text, image, and audio turns in a single workspace using `gemini-omni-1.1-flash-preview` via the Vertex AI Interactions API.
    *   **[Veo Video Generation](/genmedia-creative-studio/core/foundation-models/veo/):** Create high-fidelity videos across Text-to-Video, Image-to-Video, First/Last Frame Interpolation, Reference-to-Video (`ASSET` & `STYLE`), and Video Extension using Veo 3.1, Veo 3, and Veo 2.
*   **Audio, Music & Speech Generation:**
    *   **[Lyria Music Generation](/genmedia-creative-studio/core/foundation-models/lyria/):** Generate instrumental and vocal music tracks from text prompts, custom lyrics, and reference images using Lyria 2 (`lyria-002`) and Lyria 3 (`lyria-3-clip-preview`, `lyria-3-pro-preview`) with C2PA provenance preservation.
    *   **[Gemini TTS](/genmedia-creative-studio/core/foundation-models/gemini-tts/):** Synthesize expressive single- and multi-speaker speech with natural-language style direction, inline vocal tags, and integrated Praat/Librosa acoustic telemetry (`gemini-3.8-flash-tts`, `gemini-2.5-flash-tts`).
    *   **[Chirp 3 HD](/genmedia-creative-studio/core/foundation-models/chirp-3hd/):** Generate high-definition speech across 30+ locales with speaking rate controls and custom `IPA` / `X-SAMPA` phonetic pronunciations.
*   **Text & Prompt Ideation:**
    *   **[Gemini Writers Workshop](/genmedia-creative-studio/core/foundation-models/writers-workshop/):** Collaborate with Gemini on multimodal prompts, customize system instructions, and save reusable `PromptTemplate` records to Firestore.

## 3. Creative Workflows

Creative Workflows are opinionated, multi-step pipelines that chain Gemini reasoning, Nano Banana image generation, Virtual Try-On, Veo video synthesis, and MoviePy post-processing. See the **[Creative Workflows Overview](/genmedia-creative-studio/core/workflows/)** for a full comparison matrix.

*   **[Storyboarder](/genmedia-creative-studio/core/workflows/storyboarder/):** Expand a story concept and character reference into a multi-scene script with Gemini, synthesize character-consistent keyframes with Nano Banana, animate every scene with Veo, and stitch a master MP4 movie.
*   **[Shop the Look](/genmedia-creative-studio/core/workflows/shop-the-look/):** Dress a fashion model sequentially across multiple apparel items using Vertex AI Virtual Try-On, verify every step with a Gemini visual critic (`select_best_image` & `final_image_critic`), and generate a Veo runway clip.
*   **[Character Consistency](/genmedia-creative-studio/core/workflows/character-consistency/):** Extract a structured `FacialCompositeProfile` from reference photos, synthesize candidate scenes, select the best likeness via Gemini, outpaint to `16:9`, and animate with Veo.
*   **[Interior Design](/genmedia-creative-studio/core/workflows/interior-design/):** Convert a 2D floor plan into a 3D isometric visualization, zoom into individual rooms, iteratively restyle finishes in the Design Studio, and assemble a guided Veo walkthrough tour.
*   **[Virtual Try-On (VTO)](/genmedia-creative-studio/core/workflows/virtual-try-on/):** Combine real or synthetically generated (`VirtualModelGenerator`) model portraits with product garments and animate the result with Veo.
*   **[Starter Pack](/genmedia-creative-studio/core/workflows/starter-pack/):** Bi-directionally convert between lifestyle outfit photographs and flat-lay "Starter Pack" product moodboard collages.
*   **[Motion Portraits](/genmedia-creative-studio/core/workflows/motion-portraits/):** Animate still portraits or live webcam selfies using curated cinematography styles (`PORTRAIT_STYLES`), Gemini scene direction, Veo Image-to-Video, and automatic GIF conversion.

## 4. Post-Production & Experimental Labs

*   **[Pixie Compositor](/genmedia-creative-studio/core/workflows/pixie-compositor/):** Stitch multiple Veo video clips with transitions (`concat`, `crossfade`, `wipe`), layer Lyria or TTS audio tracks onto video, and export looping GIFs.
*   **[Labs & Experimental Workflows](/genmedia-creative-studio/core/workflows/labs/):** Explore incubating workflows at `/labs`—including **Retro Games**, **Brand Adherence**, **Character Asset Sheet**, **Guideline Analysis**, **Object Rotation**, and **Banana Studio**.
