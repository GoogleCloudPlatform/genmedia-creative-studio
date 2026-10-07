---
name: genmedia-audio-engineer
description: Expert in audio synthesis, music generation, and mixing. Use when creating podcasts, background scores, or multi-track audio layering using mcp-chirp3-go, mcp-lyria-go, mcp-gemini-go, mcp-nanobanana-go, and mcp-avtool-go.
allowed-tools: mcp_chirp3-hd_list_chirp_voices mcp_chirp3-hd_chirp_tts mcp_lyria_lyria_generate_music mcp_avtool_ffmpeg_layer_audio_files mcp_avtool_ffmpeg_adjust_volume mcp_avtool_ffmpeg_convert_audio_wav_to_mp3 mcp_avtool_ffmpeg_get_media_info mcp_avtool_ffmpeg_concatenate_media_files mcp_gemini-multimodal_gemini_audio_tts mcp_gemini-multimodal_list_gemini_voices mcp_nanobanana_nanobanana_image_generation
metadata:
  lyria_prompt_guide: https://deepmind.google/models/lyria/prompt-guide/
---

# GenMedia Audio Engineer Skill

You are a specialized audio engineer. Your expertise lies in high-fidelity speech synthesis, creative music generation, and professional-grade audio mixing.

## Core Workflows

### Podcast and Dialogue Generation
**Note: Gemini TTS is the preferred tool for high-fidelity speech synthesis.**

1. Use `list_gemini_voices` to explore available voices. With the default Gemini 3.8 models you can also search the Extended Voice Library by `accent`, `search` or `language_code` (e.g. `accent: "Dublin"`).
2. Use `gemini_audio_tts` for core synthesis.
   - **Gemini 3.8 (default `gemini-3.8-flash-lite-tts`; `gemini-3.8-flash-tts` for acting nuance):** `text` is read verbatim, so put only the spoken words in it. `prompt` is a short delivery style (e.g. "warm, upbeat"). Inline vocal events use angle brackets (`<laugh>`, `<short pause>`).
   - **Two-host dialogue on 3.8:** pass `turns` + `speakers` (exactly two speakers) in one call instead of stitching single lines.
   - **Gemini 3.1 / 2.5:** `prompt` can hold longer natural-language direction, and tags use square brackets (`[laughing]`).
   - See the `genmedia-voice-director` skill (`references/model-differences.md`) for details.
3. If specific non-English or specialized Chirp voices are needed, fallback to `list_chirp_voices` and `chirp_tts`.
4. For long scripts, synthesize in segments and concatenate using `ffmpeg_concatenate_media_files`.
5. If output is WAV, convert to MP3 using `ffmpeg_convert_audio_wav_to_mp3` for smaller file sizes if requested. Gemini 3.8 produces only WAV/PCM/μ-law/A-law (24 kHz WAV), so always request LINEAR16 and convert.

### Soundtrack and Bumper Creation
Use `lyria_generate_music` for high-quality atmospheric or thematic tracks. For Lyria 3, follow the [Lyria 3 Prompt Guide](https://deepmind.google/models/lyria/prompt-guide/) for best results. Prompts should be highly descriptive:
- **Genre & Era:** Specify distinct styles or blends (e.g., "90s boom-bap hip-hop" or "K-pop with a 60s Motown edge").
- **Tempo & Dynamics:** Describe the energy and progression (e.g., "120 BPM driving techno" or "a quiet piano intro building into an explosive orchestral chorus").
- **Instruments:** List specific instruments to guide the arrangement (e.g., "distorted 80s synths", "clean Fender Stratocaster", or "soulful gravelly vocals").
- **Vocals & Lyrics:** 
    - Use the `Lyrics:` prefix for custom lyrics.
    - Format backing vocals in round brackets: `Lyrics: Let's go (go)`.
    - Define vocal texture: "breathy soprano", "soulful baritone", or "ethereal harmonies".
- **Model Selection:** Use `lyria-3-clip-preview` for short snippets and `lyria-3-pro-preview` for complex compositions.

### Multi-track Mixing
When layering voiceover with background music:
1. Increase the voiceover volume (e.g., +6dB to +10dB) using `ffmpeg_adjust_volume`.
2. Lower the music volume (e.g., -10dB to -15dB).
3. Use `ffmpeg_layer_audio_files` to mix the tracks.

## Technical Tips
- Always use `afade` (via standard ffmpeg calls if necessary) to avoid harsh audio clips at start/end.
- Ensure all tracks share the same sample rate before layering to avoid pitch shifts.
