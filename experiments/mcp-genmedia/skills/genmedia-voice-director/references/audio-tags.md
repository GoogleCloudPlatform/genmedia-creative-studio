# Inline Audio Tags Reference

Tag syntax depends on the model family. See `model-differences.md`.

## Gemini 3.8 (`gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`)

Use **angle brackets** and only **momentary human vocal sounds and pauses**. Put each tag exactly where the sound happens. Anything that lasts (emotion, tone, whispering, pace) goes in the `prompt` (style), not in a tag.

| Category | Tags |
|---|---|
| Breath and air | `<breath>`, `<heavy breath>`, `<exhales>`, `<pant>`, `<phew>`, `<pff>`, `<yawn>` |
| Laughter | `<laugh>`, `<laughter>`, `<chuckle>`, `<chuckles>`, `<giggle>`, `<snicker>`, `<cackle>` |
| Distress | `<sigh>`, `<sighs>`, `<groan>`, `<moan>`, `<cry>`, `<sob>`, `<whimper>`, `<gasp>` |
| Loud bursts | `<shout>`, `<scream>`, `<shriek>`, `<cheer>`, `<argh>` |
| Throat and nose | `<cough>`, `<throat-clearing>`, `<sneeze>`, `<snort>` |
| Other vocal | `<growl>`, `<grr>`, `<grunt>`, `<hiss>`, `<tsk>`, `<whispers>`, `<whispering>` (documented, but the word was spoken aloud in 2 of 3 test runs; use style `whispering` instead) |
| Pauses | `<short pause>`, `<long pause>` (there is no medium pause; use `...` or punctuation) |

Rules:
- Keep tags in English even when the transcript is in another language.
- Use human sounds, not sound effects (no `<applause>`, `<door slam>`).
- Emphasis: CAPITALISE the word (`It was a VERY long day <sigh> ...`).
- Disfluencies are words, not tags: `uhm`, `hm`, `uh`.
- Pacing also comes from punctuation: commas, `--` and `...`.
- In two-speaker turns, put listener reactions in pipes inside the active speaker's turn: `Ready enough |oh really?| the last blocker cleared.`

Example (style = `whispered, nervous`):
```
Wait... <short pause> did you hear that? <gasp> Someone's at the door.
```

## Gemini 3.1 / 2.5 (`gemini-3.1-flash-tts-preview`, `gemini-2.5-*-tts`)

Use **square brackets**. The tags are suggestions, not an exhaustive list. Tags must be in English, but can be combined with text in other languages (e.g. `[anger] Je ne sais pas!`).

**Non-speech sounds and modifiers:** `[sigh]`, `[laughing]`, `[laughs]`, `[uhm]`, `[whispering]`, `[whispers]`, `[shouting]`, `[robotic]`, `[sarcasm]`, `[extremely fast]`, `[fast]`, `[slow]`

**Pauses:** `[short pause]` (~250ms), `[medium pause]` (~500ms), `[long pause]` (~1000ms+)

**Emotion and delivery tags** (some adjective-style tags may be spoken as words, so test before relying on them):

`[acceptance]`, `[accomplishment]`, `[achievement]`, `[active]`, `[admiration]`, `[admonition]`, `[adoration]`, `[affection]`, `[aggression]`, `[agitation]`, `[alarm]`, `[amazement]`, `[ambivalence]`, `[amused]`, `[amusement]`, `[analysis]`, `[anger]`, `[animation]`, `[annoyance]`, `[anticipation]`, `[anxiety]`, `[apology]`, `[appreciation]`, `[apprehension]`, `[approval]`, `[arrogance]`, `[assertion]`, `[assertive]`, `[assertiveness]`, `[assurance]`, `[astonishment]`, `[aversion]`, `[awareness]`, `[awe]`, `[awkwardness]`, `[bargaining]`, `[boredom]`, `[caring]`, `[caution]`, `[cautious]`, `[certainty]`, `[challenging]`, `[comfort]`, `[compassion]`, `[concentration]`, `[concern]`, `[confidence]`, `[confident]`, `[confusion]`, `[contemplative]`, `[contempt]`, `[contentment]`, `[conviction]`, `[courage]`, `[craving]`, `[critical]`, `[criticism]`, `[curiosity]`, `[decision]`, `[defiance]`, `[demonstration]`, `[description]`, `[descriptive]`, `[desire]`, `[despair]`, `[desperation]`, `[despondency]`, `[determination]`, `[determined]`, `[devotion]`, `[directness]`, `[disagreement]`, `[disappointment]`, `[disapproval]`, `[disbelief]`, `[discernment]`, `[discomfort]`, `[disdain]`, `[disgust]`, `[disillusionment]`, `[dislike]`, `[dismissive]`, `[distress]`, `[doubt]`, `[dread]`, `[eagerness]`, `[effervescence]`, `[embarrassment]`, `[embitterment]`, `[embracement]`, `[empathy]`, `[emphasis]`, `[enchantment]`, `[encouraging]`, `[energetic]`, `[enjoyment]`, `[enthusiasm]`, `[enthusiastic]`, `[excitement]`, `[exhaustion]`, `[explaining]`, `[fascination]`, `[fast]`, `[fear]`, `[focus]`, `[fondness]`, `[friendly]`, `[frustration]`, `[gratification]`, `[gratitude]`, `[grief]`, `[guilt]`, `[happy]`, `[high energy]`, `[hope]`, `[horror]`, `[humor]`, `[hurt]`, `[incredulity]`, `[indifference]`, `[indignation]`, `[informative]`, `[instruction]`, `[interest]`, `[intrigue]`, `[invitation]`, `[joy]`, `[laughs]`, `[logical reasoning]`, `[long pause]`, `[love]`, `[low energy]`, `[melancholy]`, `[mixed]`, `[negative]`, `[negative surprise]`, `[nervousness]`, `[neutral]`, `[nostalgia]`, `[observation]`, `[offense]`, `[optimism]`, `[pain]`, `[panic]`, `[passion]`, `[passive]`, `[pensive]`, `[pessimism]`, `[pity]`, `[planning]`, `[playful]`, `[pleading]`, `[pleased]`, `[positive]`, `[positive surprise]`, `[praise]`, `[pride]`, `[realization]`, `[recognition]`, `[reflection]`, `[regret]`, `[relaxation]`, `[relief]`, `[reminiscence]`, `[resignation]`, `[sadness]`, `[sarcasm]`, `[satisfaction]`, `[self-deprecation]`, `[self-satisfaction]`, `[sentimentality]`, `[serenity]`, `[seriousness]`, `[shame]`, `[shock]`, `[short pause]`, `[skepticism]`, `[slight relief]`, `[smitten]`, `[solemnity]`, `[speculation]`, `[slow]`, `[strategizing]`, `[stress]`, `[struggle]`, `[success]`, `[suffering]`, `[suggestion]`, `[summary]`, `[surprise]`, `[suspicion]`, `[sympathy]`, `[tension]`, `[terror]`, `[thanks]`, `[thinking]`, `[thrill]`, `[tiredness]`, `[triumph]`, `[uncertainty]`, `[unclear]`, `[understanding]`, `[unease]`, `[urgency]`, `[victory]`, `[warning]`, `[weariness]`, `[whispers]`, `[wisdom]`, `[wistful]`, `[worry]`, `[yearning]`

Converting these to 3.8: see the translation table in `model-differences.md`.
