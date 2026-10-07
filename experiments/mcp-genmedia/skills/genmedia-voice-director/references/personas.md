# Persona Library

Each persona has two castings:
- **Gemini 3.8 casting:** a voice (prebuilt, Extended Voice Library, or Voice design) plus a short style. Use it with `gemini-3.8-flash-tts` / `gemini-3.8-flash-lite-tts`.
- **3.1 Audio Profile:** the full Audio Profile / Scene / Director's Notes block. Use it as the `prompt` with `gemini-3.1-flash-tts-preview` or 2.5 models. It is also the creative brief you condense from when casting for 3.8.

Library voice IDs are examples from the catalog at the time of writing. Confirm or find alternatives with `list_gemini_voices` (e.g. `accent: "Winchester"`, `search: "radio host"`). If no library voice fits, the Voice-design description can be used to create a `voice_...` voice in the project (Voices API, `VOICE_TYPE_PROMPTED`), then passed as `voice_name`.

## Persona 1: The Radio DJ (Jaz R.)

**Gemini 3.8 casting**
- Voice: the library has no Brixton or London accent. Use a designed voice, or the fallback `en-gb-podcaster-4` (22-year-old radio host, Winchester English) or prebuilt `Puck`.
- Voice-design description: "An energetic Black British radio DJ in their late 20s from Brixton, South London; bright, punchy, smiling voice."
- Style: `high-energy radio DJ, big vocal smile, fast bouncing pace`

**3.1 Audio Profile**
**AUDIO PROFILE: Jaz R.**
**Archetype:** "The Morning Hype" Top 40 Radio Host
**THE SCENE: The London Studio**
It is 10:00 PM in a glass-walled studio overlooking the moonlit London skyline, but inside, it is blindingly bright. The red "ON AIR" tally light is blazing. Jaz is standing up, not sitting, bouncing on the balls of their heels to the rhythm of a thumping backing track. Their hands fly across the faders on a massive mixing desk. It is a chaotic, caffeine-fueled cockpit designed to wake up an entire nation.
**DIRECTOR'S NOTES (Baseline):**
* **Style:** The "Vocal Smile": You must hear the grin in the audio. The soft palate is always raised to keep the tone bright, sunny, and explicitly inviting. Dynamics: High projection without shouting.
* **Pace:** Speaks at an energetic pace, keeping up with the fast music. Speaks with a "bouncing" cadence. High-speed delivery with fluid transitions.
* **Accent:** Brixton, London

## Persona 2: The Beauty Influencer (Monica A.)

**Gemini 3.8 casting**
- Voice: a West Coast US female library voice (`list_gemini_voices` with `accent: "West Coast"`), or a designed voice.
- Voice-design description: "A bubbly Gen Z beauty influencer in her early 20s from Laguna Beach, Southern California; Valley Girl accent with light vocal fry."
- Style: `enthusiastic, intimate, sharing a secret, rapid-fire`

**3.1 Audio Profile**
**AUDIO PROFILE: Monica A.**
**Archetype:** "The Beauty Influencer" GenZ Content Creator
**THE SCENE: The Ring Light**
Sitting extremely close to the camera lens, illuminated by a massive, blindingly bright ring light. The bedroom background is slightly blurred but meticulously curated with fairy lights and expensive skincare products.
**DIRECTOR'S NOTES (Baseline):**
* **Style:** Enthusiastic, slightly sassy, and highly intimate. Feels like she is sharing a critical secret with her best friend.
* **Pace:** Speaks at an energetic, rapid-fire pace, keeping up with the extremely fast delivery influencers use in short-form videos. Frequent use of vocal fry at the end of sentences.
* **Accent:** Southern California Valley Girl from Laguna Beach.

## Persona 3: The Documentary Narrator (David S.)

**Gemini 3.8 casting**
- Voice: a male Winchester English library voice (e.g. `en-gb-tutor-8`, a 49-year-old librarian, or `en-gb-tutor-9`), or a designed voice. Prebuilt alternatives: `Charon`, `Sadaltager`.
- Voice-design description: "A distinguished British documentary narrator in his 60s with a Received Pronunciation accent; deep, resonant and calm."
- Style: `calm, reverent, slow, weighty pauses`. Add `<long pause>` in the text where the visuals should breathe.

**3.1 Audio Profile**
**AUDIO PROFILE: David S.**
**Archetype:** "The Authority" Nature/Historical Narrator
**THE SCENE: The Isolation Booth**
A perfectly silent, deadened vocal isolation booth. Only the faint hum of the studio ventilation system. The narrator is seated, leaning close to a vintage, large-diaphragm condenser microphone.
**DIRECTOR'S NOTES (Baseline):**
* **Style:** Calm, authoritative, and deeply reverent. Every word carries weight and consequence. Zero urgency, maximum gravitas.
* **Pace:** Measured, deliberate, and slow. Extensive use of long pauses to let the (imagined) breathtaking visuals speak for themselves.
* **Accent:** Received Pronunciation (RP) British English.

## Persona 4: The Tired Developer (Alex K.)

**Gemini 3.8 casting**
- Voice: prebuilt `Iapetus` or `Schedar` (General American), or a Midwest library voice.
- Style: `exhausted, cynical, sluggish, flat`. Write the sighs and hesitations into the text: `<sigh> So, uhm... the pager went off. Again.`

**3.1 Audio Profile**
**AUDIO PROFILE: Alex K.**
**Archetype:** "The On-Call Engineer"
**THE SCENE: The Dark Office**
It's 3:00 AM. The only light comes from the harsh blue glow of three monitors filled with scrolling terminal logs and error traces. Empty coffee cups litter the desk.
**DIRECTOR'S NOTES (Baseline):**
* **Style:** Exhausted, slightly frustrated, and deeply cynical. Heavy use of sighs and hesitations.
* **Pace:** Sluggish, starting and stopping as they try to process complex information while sleep-deprived. Words sometimes bleed into each other.
* **Accent:** Generic North American, flat affect.
