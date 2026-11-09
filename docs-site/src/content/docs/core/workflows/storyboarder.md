---
title: "Storyboarder"
description: "Multi-scene narrative planning, character-consistent keyframe synthesis, Gemini Omni or Veo scene animation, and MoviePy master film assembly."
---

The **Storyboarder** workflow (`/storyboarder`) transforms a single story premise and optional character reference photo into a multi-scene short film. It chains **Gemini structured narrative planning**, **Nano Banana sequential keyframe generation**, **Gemini Omni (default) or Veo Image-to-Video (I2V) animation**, and **MoviePy timeline assembly**.

![Storyboarder Workflow Architecture](../assets/diagrams/workflow-storyboarder-light.webp)

## Source Architecture

| Layer | File Path | Responsibility |
| :--- | :--- | :--- |
| **Mesop Page & Orchestrator** | `pages/storyboarder.py` (`PageState`, `NarrativeStructure`, `SceneDetail`) | End-to-end 4-stage pipeline UI, per-scene prompt & keyframe editor, individual scene regeneration, scene video loop, and final MoviePy compilation. |
| **Image Synthesis** | `models/gemini.py` (`generate_image_from_prompt_and_images`) | Synthesizes 16:9 scene keyframes conditioned on the character asset and previous scene frames. |
| **Video Model Routing** | `models/storyboard_video.py` (`video_model_options`, `supported_aspect_ratios`, `generate_storyboard_clip`) | Builds the video-model dropdown from the Omni and Veo registries and routes each keyframe to the right model. |
| **Video Synthesis** | `models/omni.py` (`generate_omni_video`) and `models/veo.py` (`generate_video`) | Animates each scene keyframe into a `4s` `720p` clip with native audio, using Gemini Omni (default) or Veo. |
| **Video Assembly** | `models/video_processing.py` (`process_and_concatenate_videos`) | Concatenates all scene clips into a single master MP4 and uploads it to Cloud Storage. |

## Step-by-Step Pipeline

### Step 1: Story Concept & Structured Script Generation (`NarrativeStructure`)
1. The user enters a **Story Concept** (or clicks **Random Prompt** to have Gemini invent one), selects a visual style (e.g., *Cinematic*, *Anime*, *Claymation*, *Noir*) and aspect ratio (`16:9` or `9:16`), and optionally uploads or selects a **Character Reference Image**. The **Narrative Writer Model** picker defaults to **Gemini 3.8 Flash** and also offers **Gemini 4 Argon** and **Gemini 3.5 Flash Lite**; the list and default are configurable via `GEMINI_STORYBOARDER_NARRATIVE_MODELS` and `GEMINI_STORYBOARDER_NARRATIVE_MODEL_ID`.
2. `pages/storyboarder.py` calls `client.models.generate_content()` with `response_schema=NarrativeStructure`:
   ```python
   class SceneDetail(BaseModel):
       title: str
       image_prompt: str
       video_prompt: str

   class NarrativeStructure(BaseModel):
       overall_style: str
       scenes: list[SceneDetail]
   ```
3. Gemini outputs a 3-to-5 scene breakdown where each scene has both a static composition prompt (`image_prompt`) and a camera/motion prompt (`video_prompt`).

### Step 2: Sequential Character-Aware Keyframe Synthesis
To maintain visual continuity from scene to scene, Storyboarder generates keyframes sequentially using **Nano Banana** (`gemini-2.5-flash-image` / `gemini-3.1-flash-image-preview`):
* **Scene 1:** Conditioned on `scene[0].image_prompt` + the user's `character_image_gcs` (if provided).
* **Scene $k$ ($k > 1$):** Conditioned on `scene[k].image_prompt` + `character_image_gcs` + the generated keyframe from Scene $k-1$ (`previous_scene_image`) so lighting, environment, and character wardrobe carry forward.
* Users can inspect the storyboard grid, edit any individual `image_prompt`, and click **Regenerate Image** on any single scene before proceeding to video generation.

### Step 3: Scene-by-Scene Video Animation
* The **Video Model** setting defaults to **Gemini Omni 1.2 Flash**. The dropdown lists every Omni model that supports image-to-video, followed by the Veo models, and is built from the model registries (`config/omni_models.py`, `config/veo_models.py`).
* Clicking **Generate Videos for All Scenes** iterates through every storyboard card and animates the scene's keyframe (`reference_image_gcs`) with its `video_prompt` through `generate_storyboard_clip`. Omni models receive an `i2v` `OmniVideoGenerationRequest`; Veo models receive an `i2v` `VideoGenerationRequest`. Every clip is `4s` at `720p` with native audio so clips from either model stitch together.
* Gemini Omni animates `16:9` and `9:16` only. Selecting an Omni model snaps a `1:1` storyboard back to `16:9`, and the aspect-ratio selector lists only the ratios the chosen model supports.
* Users can also regenerate any individual scene's video clip independently if they tweak its `video_prompt`.

### Step 4: MoviePy Master Video Assembly
* Once all scenes have rendered their video clips, clicking **Create Final Movie** downloads the scene MP4s from GCS, concatenates them in sequence via `models/video_processing.py` (clips of a different size are letterboxed to the first clip's size), uploads the stitched master film to `gs://<GENMEDIA_BUCKET>/storyboarder_movies/`, and logs a complete `MediaItem` in Firestore.
