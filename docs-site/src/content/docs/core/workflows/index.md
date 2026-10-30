---
title: "Creative Workflows"
description: "Multi-step generative media orchestration pipelines in GenMedia Creative Studio."
---

Beyond single-model workspaces, GenMedia Creative Studio features **Creative Workflows**—opinionated, multi-stage pipelines that orchestrate Gemini reasoning, Nano Banana image synthesis, Virtual Try-On (VTO), Veo video generation, and MoviePy post-processing to solve end-to-end industry use cases.

## Graduated Creative Workflows

| Workflow | Route | Models & Tools Orchestrated | End-to-End Pipeline Summary |
| :--- | :--- | :--- | :--- |
| **[Storyboarder](/genmedia-creative-studio/core/workflows/storyboarder/)** | `/storyboarder` | Gemini 2.5/3.5 Flash (`NarrativeStructure` JSON) + Nano Banana + Veo + MoviePy | Expands a story concept and optional character reference into a structured multi-scene script, generates consistent scene keyframes, animates each scene with Veo, and stitches a final master MP4 movie. |
| **[Shop the Look](/genmedia-creative-studio/core/workflows/shop-the-look/)** | `/shop-the-look` | Gemini + Vertex AI VTO (`virtual-try-on-001`) + Gemini Critic + Veo | Enriches apparel catalog articles, sequentially dresses a virtual model item-by-item, uses a Gemini visual critic to select the best sample and retry failed garments, and generates a Veo runway video. |
| **[Character Consistency](/genmedia-creative-studio/core/workflows/character-consistency/)** | `/character-consistency` | Gemini (`FacialCompositeProfile` & `BestImage`) + Imagen 3 / Nano Banana + Veo | Extracts a structured facial profile from multi-angle character photos, synthesizes candidate scenes, uses Gemini to select the most likeness-faithful candidate, outpaints to 16:9, and animates with Veo. |
| **[Interior Design](/genmedia-creative-studio/core/workflows/interior-design/)** | `/interior-design` | Gemini + Nano Banana (`gemini-2.5-flash-image`) + Veo 3.1 + MoviePy | Converts a 2D floor plan into a 3D isometric visualization, extracts room names, generates zoomed first-person views per room, supports conversational material re-styling, and stitches a guided Veo video walkthrough. |
| **[Virtual Try-On (VTO)](/genmedia-creative-studio/core/workflows/virtual-try-on/)** | `/vto` | `VirtualModelGenerator` + Vertex AI VTO (`recontext_image`) + Veo | Combines a real or synthetically generated model portrait with up to 4 product garments for photorealistic try-on synthesis and one-click Veo motion animation. |
| **[Starter Pack](/genmedia-creative-studio/core/workflows/starter-pack/)** | `/starter-pack` | Nano Banana (`1:1`) + `VirtualModelGenerator` | Bi-directional retail moodboard pipeline: extracts a "Starter Pack" flat-lay product collage from a lifestyle look, or dresses a virtual model in all items from a Starter Pack collage. |
| **[Motion Portraits](/genmedia-creative-studio/core/workflows/motion-portraits/)** | `/motion-portraits` | Live `selfie_camera` / Library + Gemini (`create_scene_direction`) + Veo + MoviePy | Captures or imports a portrait, applies curated cinematic style modifiers (`PORTRAIT_STYLES`), optionally expands the motion direction via Gemini, and generates both a Veo MP4 clip and an animated GIF. |
| **[Pixie Compositor](/genmedia-creative-studio/core/workflows/pixie-compositor/)** | `/pixie-compositor` | MoviePy (`concatenate_videoclips`, `CompositeVideoClip`, `write_gif`) | Post-production assembly tool for concatenating multiple Veo clips with transitions (`concat`, `crossfade`, `wipe`), layering Lyria or TTS audio tracks onto video, and exporting looping GIFs. |

## Experimental & Labs Workflows

In addition to the graduated workflows in the main navigation bar, GenMedia Creative Studio includes an experimental **[Labs & Experimental Workflows](/genmedia-creative-studio/core/workflows/labs/)** hub (`/labs`) where domain-specific prototypes—such as **Retro Games** (`/retro_games`), **Brand Adherence** (`/brand_adherence`), **Character Asset Sheet** (`/character_sheet`), **Guideline Analysis** (`/guideline-analysis`), and **Object Rotation** (`/object-rotation`)—are incubated before graduating to the main navigation.

---

## Common Orchestration Patterns

Across all Creative Workflows, the studio uses four recurring architectural patterns:

1. **Structured Gemini Planning & Prompt Expansion (`response_schema`):** Workflows use Gemini with Pydantic schemas (`NarrativeStructure`, `FacialCompositeProfile`, `RoomNames`, `TryOnOrder`) to decompose a high-level user brief into deterministic downstream model calls.
2. **Multi-Turn Visual Context Carryover:** Workflows like Storyboarder, Shop the Look, and Interior Design feed the generated image from Step $N$ directly into Step $N+1$ as a reference image so characters, garments, and architectural layouts remain coherent.
3. **Agentic Visual Judge & Critic Loops:** Workflows like Shop the Look and Character Consistency generate $N$ candidate images in parallel and invoke a Gemini multimodal judge (`select_best_image()`, `final_image_critic()`) to score garment accuracy and facial likeness, automatically retrying failed steps.
4. **Streaming Generator Progress & Firestore Checkpoint Persistence:** Every workflow executes inside a Python generator (`yield`) that updates the Mesop UI after each sub-step and logs final `MediaItem` records to Firestore (`genmedia_library`).
