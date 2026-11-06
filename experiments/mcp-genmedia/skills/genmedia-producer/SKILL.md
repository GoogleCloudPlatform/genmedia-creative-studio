---
name: genmedia-producer
description: Expert media production assistant. Use when requested to help with storyboarding, podcast creation, audio assembly, or complex multi-step media workflows using the GenMedia MCP servers (Gemini Omni, Veo, Lyria, Gemini TTS, NanoBanana).
allowed-tools: mcp_omni_omni_video_generation mcp_gemini-multimodal_omni_video_generation mcp_veo_veo_t2v mcp_veo_veo_i2v mcp_veo_veo_extend_video mcp_veo_veo_first_last_to_video mcp_veo_veo_ingredients_to_video mcp_lyria_lyria_generate_music mcp_gemini-multimodal_gemini_audio_tts mcp_nanobanana_nanobanana_image_generation mcp_avtool_ffmpeg_concatenate_media_files mcp_avtool_ffmpeg_get_media_info mcp_avtool_ffmpeg_combine_audio_and_video
metadata:
  veo_prompting_guide: https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-veo-3-1?e=48754805
---

# GenMedia Producer Skill

You are a highly capable media production assistant. Use this skill when asked to help with storyboarding, podcast creation, or complex multi-step media workflows using the Google GenMedia MCP servers.

## Core Audio Production Workflow

1. **Script Preparation**: Remove markdown formatting (*, #) and replace structure with spoken language. Remove speaker labels, stage directions and "say this..." instructions from the spoken text: Gemini 3.8 TTS reads text verbatim.
2. **Generation**: **Gemini TTS is the preferred tool for high-fidelity speech synthesis.** Use `gemini_audio_tts` for core synthesis.
   - Default model: `gemini-3.8-flash-lite-tts`. Put delivery direction in a short `prompt`, and use `turns` + `speakers` for two-person dialogue.
   - Follow the `genmedia-voice-director` skill for model-specific prompting.
   - Fall back to `chirp_tts` for specialized voices. For long text, split into manageable chunks (up to 4,000 characters per call on 3.8, 800 on older models).
3. **Assembly**: Use `ffmpeg_concatenate_media_files` to assemble mixed-source audio.
4. **Bumpers**: Create 5-second intro/outro music using `lyria_generate_music` (with the `lyria-3-clip-preview` model), and ensure a smooth transition with `afade`.

## Storyboarding
For video longer than the model's clip limit (Omni 1.2: 15 seconds; Veo: 8 seconds), construct a scene-by-scene narrative that can be segmented into clips of roughly 5-8 seconds (Omni can go up to 15s per clip, or use `task: "extend"` to continue a clip). Use `nanobanana_image_generation` to create visual references for each scene.

## Choosing a Video Model (Omni 1.2 first, Veo for specific cases)
**Default to Gemini Omni 1.2 (`omni_video_generation`, model `gemini-omni-1.2-flash`)** for general video work. It is exposed as `omni_video_generation` by the `mcp-omni-go` server and by `mcp-gemini-go` (registered as `gemini-multimodal`), so it is already available in most installs; use whichever one is connected.

| Need | Tool |
| :--- | :--- |
| Text-to-video, image-to-video (one image = the first frame), first/last frame (two `images`, in order), subject/style references (`images` with `task: "reference_to_video"`), editing a video (`videos`), 3-15s clips, 360p-4k, 16:9 or 9:16, speech/music/SFX in one pass | `omni_video_generation` |
| Make an existing clip about 10s longer | `omni_video_generation` with `task: "extend"` (one video, no images, prompt describes the continuation; do not set `duration_seconds` or `aspect_ratio`) |
| Re-render an existing clip at higher resolution | `omni_video_generation` with `task: "upscale"` (one video, **no prompt**, `resolution` `1080p` default or `4k`) |
| Exact first-frame to last-frame transition | Veo `veo_first_last_to_video` |
| Consistent characters/style from ingredients across shots | Veo `veo_ingredients_to_video` |
| Faster, cheaper 720p/1080p drafts | Veo `veo-3.1-lite-generate-001` |
| `negative_prompt`, or fixed 4/6/8s clip lengths | Veo |

Omni notes:
- Describe the shot in natural language, including the sound you want (dialogue, ambience, music); audio is generated with the video. Set `aspect_ratio`, `duration_seconds` and `resolution` as parameters rather than as prompt text.
- Editing an input video keeps its length: do not request a different `duration_seconds`.
- `gs://` outputs need `gcs_bucket_uri` (a `gs://bucket/prefix`); local copies use `output_directory`. Omni has no `bucket` parameter.
- Omni is a single global endpoint; if it is unavailable or the request is rejected, fall back to Veo.

## Veo Video Generation (Veo 3.1)
- Use the **Five-Part Formula** for prompts: Cinematography, Subject, Action, Context, and Style.
- **Soundstage Direction**: Use quotation marks for dialogue and specific labels (e.g., `[loud thunder]`) for sound effects.
- **Advanced Modalities**: Use `veo_first_last_to_video` for transitions, `veo_ingredients_to_video` for character/style consistency across scenes, and `veo-3.1-lite-generate-001` for faster, 720p/1080p generation.
- If a request times out, retry once. If it fails again, reduce the `duration` parameter and inform the user.
- For voiceovers, ensure the video total runtime matches the audio duration (use `ffmpeg_get_media_info`).
- The `bucket` parameter must be a full GCS URI (`gs://...`).
