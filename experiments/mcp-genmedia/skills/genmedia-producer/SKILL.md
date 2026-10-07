---
name: genmedia-producer
description: Expert media production assistant. Use when requested to help with storyboarding, podcast creation, audio assembly, or complex multi-step media workflows using the GenMedia MCP servers (Veo, Lyria, Gemini TTS, NanoBanana).
allowed-tools: mcp_veo_veo_t2v mcp_veo_veo_i2v mcp_veo_veo_extend_video mcp_veo_veo_first_last_to_video mcp_veo_veo_ingredients_to_video mcp_lyria_lyria_generate_music mcp_gemini-multimodal_gemini_audio_tts mcp_nanobanana_nanobanana_image_generation mcp_avtool_ffmpeg_concatenate_media_files mcp_avtool_ffmpeg_get_media_info mcp_avtool_ffmpeg_combine_audio_and_video
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
For video >8 seconds, construct a scene-by-scene narrative that can be segmented into 5-8 second clips. Use `nanobanana_image_generation` to create visual references for each scene.

## Veo Video Generation (Veo 3.1)
- Use the **Five-Part Formula** for prompts: Cinematography, Subject, Action, Context, and Style.
- **Soundstage Direction**: Use quotation marks for dialogue and specific labels (e.g., `[loud thunder]`) for sound effects.
- **Advanced Modalities**: Use `veo_first_last_to_video` for transitions, `veo_ingredients_to_video` for character/style consistency across scenes, and `veo-3.1-lite-generate-001` for faster, 720p/1080p generation.
- If a request times out, retry once. If it fails again, reduce the `duration` parameter and inform the user.
- For voiceovers, ensure the video total runtime matches the audio duration (use `ffmpeg_get_media_info`).
- The `bucket` parameter must be a full GCS URI (`gs://...`).
