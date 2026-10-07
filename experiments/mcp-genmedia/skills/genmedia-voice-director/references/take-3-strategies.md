# "Take 3 on the Bounce" Strategies

In voiceover work, "doing it on the bounce" means performing several takes of the same line back-to-back, each with a different delivery. The **words stay identical** across takes; only the performance changes.

How you build the takes depends on the model family (see `model-differences.md`).

## Gemini 3.8: one call per take (recommended)

3.8 reads `text` verbatim, so **never** put "Take 1 / Take 2" labels or direction lines in the transcript; they will be spoken. Instead, make **three `gemini_audio_tts` calls** with the same voice and the same words. Give each call its own short `prompt` (style) and its own inline vocal tags, and name the files so the takes stay ordered (`output_filename`: `line_take1`, `line_take2`, `line_take3`).

Separate files are what a VO session delivers anyway. Each take can be auditioned, retried or swapped on its own. If the user wants one continuous file, concatenate the three WAVs with the avtool server (`ffmpeg_concatenate_media_files`).

For contrast, change the **style** first, then the **vocal tags and punctuation**. Use CAPITALS for emphasis.

### Approach 1: The "Safety" Set
Same core emotion, small variations in polish or emphasis.

| Take | `prompt` (style) | `text` |
|---|---|---|
| 1. Direct read | `clear, warm, natural pace` | `Welcome to the future of cloud computing. We are excited to have you here.` |
| 2. The tweak | `warm, leaning on the key word` | `Welcome to the FUTURE of cloud computing. <short pause> We are excited to have you here.` |
| 3. The safe option | `polished, measured, slightly slower` | `Welcome to the future of cloud computing... We are excited to have you here.` |

### Approach 2: The Character/Emotional Shift
Three distinct readings of the character's reaction.

| Take | `prompt` (style) | `text` |
|---|---|---|
| 1. Initial idea | `frustrated, clipped` | `<sigh> I can't believe the build failed again.` |
| 2. The contrast | `defeated, quiet, almost whispering` | `I can't believe... <short pause> the build failed again.` |
| 3. The wild card | `dry sarcasm, amused` | `<chuckle> Oh great. I can't believe the build failed AGAIN. Fantastic.` |

### Approach 3: The Pacing/Emphasis Variation
For commercial reads and marketing copy, where rhythm matters.

| Take | `prompt` (style) | `text` |
|---|---|---|
| 1. Upbeat | `high energy, speaking rapidly` | `Get yours today before they're entirely sold out!` |
| 2. Relaxed | `relaxed, conversational, speaking slowly` | `Get yours today... <short pause> before they're entirely sold out.` |
| 3. Punchy | `punchy, confident, short and firm` | `Get yours TODAY! <short pause> Before they're sold out!` |

Tips:
- Keep the voice identical across takes; it carries identity. Don't describe the voice in the style.
- Keep each style under about 15 words. If a take needs a mid-line emotional turn, split that take into two calls.
- Write text and style that agree. A style that fights the words (e.g. angry delivery of cheerful copy) may lose to the text.

## Gemini 3.1 / 2.5: one call, takes in the transcript

Older models tolerate take markers and direction inside a single request. Structure the Transcript with explicit "Take" markers, use square-bracket tags, and use `[short pause]` or `[medium pause]` between takes for separation. Put the Audio Profile / Scene / Director's Notes in `prompt` and this block in `text`.

### Approach 1: The "Safety" Set
```markdown
[short pause]
Take 1. The Direct Read.
[short pause]
Welcome to the future of cloud computing. We are excited to have you here.
[medium pause]

Take 2. Emphasize "future".
[short pause]
Welcome to the *future* of cloud computing. [short pause] We are excited to have you here.
[medium pause]

Take 3. The Safe Option. Slower and polished.
[short pause]
Welcome to the future of cloud computing. We are excited to have you here.
```

### Approach 2: The Character/Emotional Shift
```markdown
[short pause]
Take 1. The Initial Idea. Frustrated.
[short pause]
[sigh] I can't believe the build failed again.
[medium pause]

Take 2. The Contrast. Defeated and sad.
[short pause]
[whispering] I can't believe the build failed again.
[medium pause]

Take 3. The Wild Card. Sarcastic amusement.
[short pause]
[laughing] Oh great, I can't believe the build failed *again*. Fantastic.
```

### Approach 3: The Pacing/Emphasis Variation
```markdown
[short pause]
Take 1. Upbeat and Fast.
[short pause]
[extremely fast] Get yours today before they're entirely sold out!
[medium pause]

Take 2. Relaxed and Slow.
[short pause]
Get yours today... [short pause] before they're entirely sold out.
[medium pause]

Take 3. Punchy.
[short pause]
Get yours *today*! [short pause] Before they're sold out!
```

The take labels may be voiced on these models too. If the user needs clean takes, use the 3.8 one-call-per-take method with any model.
