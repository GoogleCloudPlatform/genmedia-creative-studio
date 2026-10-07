---
title: "Using GenMedia Creative Studio"
---

GenMedia Creative Studio provides a centralized interface for experimenting with Google Cloud's generative media models. The application is organized into three primary areas: Foundation models, Creative Workflows, and Studio management tools.

## 1. Navigating the Studio

*   **The Library:** A centralized repository to browse, manage, and download all your generated media.
*   **Settings & Configuration:** Manage your application settings, API configurations, and experimental feature flags.

## 2. Foundation Models (Direct Generation)

Interact directly with the raw generative models to create single-modality outputs.

*   **Image Generation:** 
    *   **Gemini Image Generation:** Generate high-quality images from text prompts using Gemini (Nano Banana), including Gemini 3.1 Flash-Lite for rapid creation and iteration at 1K resolution.
    *   **Imagen (deprecated):** Imagen image generation, editing, and upscaling — all Imagen models — were shut down across Google, including Vertex AI, around August 17, 2026. Use **Gemini Image Generation (Nano Banana, `gemini-nano-banana-2.1`)** instead. See the [Imagen models migration guide](https://firebase.google.com/docs/ai-logic/imagen-models-migration?api=dev) for the model replacement mapping.
*   **Video Generation:** 
    *   **Gemini Omni:** Create, animate, reference, and iteratively edit video in a multi-turn chat workspace using Gemini Omni Flash.
    *   **Veo:** Create high-fidelity videos from text or image prompts using Veo 3 and Veo 3.1.
*   **Audio & Speech Generation:** 
    *   **Lyria:** Generate complex music tracks and thematic scores from text prompts.
    *   **Gemini TTS:** Synthesize expressive and highly-controllable text-to-speech.
    *   **Chirp 3 HD:** Generate high-definition speech from text.
*   **Text & Ideation:** 
    *   **Gemini (Writer's Workshop):** Collaborate with Gemini to brainstorm, refine, and structure your creative prompts.

## 3. Creative Workflows

Workflows are opinionated pipelines that chain multiple generative models together to accomplish specific, complex tasks.

*   **Virtual Try-On:** A dedicated interface for virtually trying on clothing items across different generated models.
*   **Character Consistency:** Maintain character identity across multiple video generations and image prompts.
*   **Shop the Look:** Generate shoppable product imagery by combining product extraction and generated lifestyle scenes.
*   **Starter Pack:** Quickly generate a cohesive visual moodboard (a "starter pack") from a single central concept.
*   **Interior Design:** Re-imagine interior spaces by generating 3D views from basic floor plans.
*   **Motion Portraits:** Create animated, breathing portraits from a single still image.
*   **Object Rotation:** Create 360-degree product videos from a single image.
*   **Storyboarder:** Create coherent multi-scene narrative storyboards using Gemini 3.5 Flash to write the narrative, Gemini to generate scene frames, and Veo to animate the sequence inline.

## 4. Advanced Tools

*   **Pixie Compositor:** A canvas to help you visually combine and arrange your generative media.
*   **Labs:** A sneak peek at experimental features and odd things currently bubbling up in development.