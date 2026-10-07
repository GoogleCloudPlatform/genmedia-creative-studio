# Gemini TTS Model Differences: 3.1 vs 3.8

Gemini 3.8 TTS (`gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`) uses a different control model from the earlier Gemini TTS models (`gemini-3.1-flash-tts-preview`, `gemini-2.5-*-tts`). Pick the model first, then write the prompt for that family.

## Choosing a model

| Need | Model |
|---|---|
| Everyday narration, read-aloud, voice agents, volume, low latency | `gemini-3.8-flash-lite-tts` (tool default; recommended replacement for 3.1) |
| Acting nuance, frequent vocal sounds, regional dialects, audiobooks, two-speaker dialogue | `gemini-3.8-flash-tts` |
| Reproduce an existing 3.1 / 2.5 prompt exactly, or the user asks for it | `gemini-3.1-flash-tts-preview`, `gemini-2.5-pro-tts`, `gemini-2.5-flash-tts` |

## What goes where

| | Gemini 3.8 | Gemini 3.1 / 2.5 |
|---|---|---|
| `text` | **Verbatim transcript only.** Every word may be spoken, including headings, `Speaker:` names, `Take 1` markers and "Say the following...". | Transcript. The tool sends it to the Cloud TTS API. |
| `prompt` | **Short turn-level style**, e.g. `whispered, nervous`, `warm and unhurried`, `speaking rapidly, excited`. Sent as `speechMetadata.style`. | Natural-language direction. The full Audio Profile / Scene / Director's Notes framework works here. |
| Inline tags | **Angle brackets, human sounds only:** `<sigh>`, `<laugh>`, `<chuckle>`, `<gasp>`, `<breath>`, `<cough>`, `<throat-clearing>`, `<short pause>`, `<long pause>` (full list in `audio-tags.md`). | Square brackets: `[sigh]`, `[laughing]`, `[short pause]`, `[medium pause]`, plus emotion tags like `[sarcasm]`, `[excitement]`. |
| Emotion, tone, pace | In `prompt` (style). If the emotion changes mid-line, split into separate calls (or turns). | Emotion tags inline, or in the prompt. |
| Accent, age, gender, timbre | **In the voice**: pick an Extended Voice Library voice (`list_gemini_voices` with `accent`, `search`, `language_code`) or a designed voice (`voice_...`). Don't put them in style. | In the prompt (Director's Notes: Accent). |
| Voices | 30 prebuilt + ~2,000 library voices + designed/replicated `voice_...` IDs. | 30 prebuilt voices only. |
| Two speakers | `turns` + `speakers` (exactly two speakers). Backchannels: wrap listener reactions in pipes inside the active turn, e.g. `So it ships Thursday |oh hmm| are we ready?` | Not supported by the tool. |
| Emphasis | CAPITALISE the stressed word: `This is a VERY important point.` | `*asterisks*` or CAPS. |
| Disfluencies | Write them as words: `uhm`, `hm`, `I mean...`. | `[uhm]` tag. |
| Length | Up to 4,000 characters per call. | Up to 800 characters per call. |
| Encodings | LINEAR16 (WAV), PCM, MULAW, ALAW. | LINEAR16, MP3, OGG_OPUS, MULAW, ALAW, PCM, M4A. |

## Translating a 3.1 prompt to 3.8

1. **Strip structure from the text.** Remove `# AUDIO PROFILE`, `## THE SCENE`, `### DIRECTOR'S NOTES`, `#### TRANSCRIPT`, `INSTRUCTIONS:`, "Say the following...:" and `Take N` lines. Keep only the words to be spoken.
2. **Move permanent traits to the voice.** Accent, age, gender and timbre become a library voice or a Voice-design description.
3. **Condense the rest into a short style**, under about 15 words: Style + Pace + the scene's energy. Example: the Jaz R. block becomes `high-energy radio DJ, big vocal smile, fast bouncing pace`.
4. **Convert the tags:**

| 3.1 tag | 3.8 |
|---|---|
| `[sigh]`, `[sighs]` | `<sigh>` |
| `[laughs]`, `[laughing]` | `<laugh>` (or `<chuckle>`) |
| `[gasp]`, `[giggles]`, `[crying]` | `<gasp>`, `<giggle>`, `<cry>` |
| `[clears throat]` | `<throat-clearing>` |
| `[short pause]` / `[medium pause]` / `[long pause]` | `<short pause>` / `<short pause>` or `...` / `<long pause>` |
| `[uhm]` | `uhm` (plain word) |
| `[whispering]`, `[whispers]` | style: `whispering` |
| `[shouting]` | style: `shouting` (or `<shout>` for a single burst) |
| `[extremely fast]`, `[fast]`, `[slow]` | style: `speaking rapidly` / `speaking slowly` |
| `[robotic]` | style: `robotic, monotone` |
| `[sarcasm]`, `[enthusiasm]`, `[awe]`, other emotions | style words; split the line where the emotion changes |

The tool returns **prompt advisories** when a request uses a pattern that misbehaves on the selected model. Act on them and regenerate.

## Observed behavior (live probe, Oct 2026)

- On 3.8, inline `[whispering]` was spoken as a word in 3 of 3 runs. "Say the following cheerfully:" was spoken in 1 of 3 runs. "Take one, the direct read..." markers were always spoken. `Joe:` prefixes were spoken.
- 3.8 still performs legacy `[sigh]` / `[short pause]` tags, but angle brackets are the documented form.
- A style that contradicts the words (e.g. `shouting angrily` on a cheerful line) may lose to the text. Write text and style that agree, or make the style specific and physical.
- 3.1 ignores 3.8-style `speechMetadata` without any error. The tool sends `prompt` correctly for each family.
