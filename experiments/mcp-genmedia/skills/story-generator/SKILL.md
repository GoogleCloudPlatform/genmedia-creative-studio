---
name: story-generator
description: Expert in generating full multi-scene multimedia storybooks (image, video, voice, and music) with dynamic duration probing, conversational tempo guardrails, a dedicated self-correcting Editor's QC Room, and pipeline flowcharts embedded in interactive reports.
metadata:
  version: "1.3.0"
  design_system: "Material 3 Tonal (Emerald-Meadow & Cosmic-Science)"
---

# Story Generator Skill (v1.3.0)

This skill allows an agent to design, generate, and composite a multi-scene storybook video using direct, native MCP tool calls. It implements a feedback-driven cognitive media engine. By combining upfront voiceover duration probing with dynamic video length selection, tempo clamping, and a dedicated quality-assurance audit ("The Editor's QC Room"), it guarantees studio-grade pacing and prevents typical AI audio-video desyncs.

## Directory Structure
Conforming to the [Agent Skills Specification](https://agentskills.io/specification.md):
```
story-generator/
├── SKILL.md            # Main metadata, co-creation instructions & FFmpeg blueprints
├── scripts/            # Executable orchestration & compilation utilities
│   ├── generate_scene.py # Generates individual scenes with speed-fit and mixing
│   ├── assemble_story.py # Normalizes codecs and concatenates scenes without desync
│   ├── editors_quality_room.py # Evaluates and audits scene/master quality and speech rates
│   ├── generate_pipeline_diagram.py # Compiles custom Graphviz DOT pipeline flowcharts
│   ├── generate_report.py # Compiles interactive HTML report
│   └── package_report.py # Packages report into a standalone zip file
└── assets/             # Reusable design tokens & static assets
    ├── index.css       # Premium Material 3 stylesheet (Emerald/Cosmic)
    └── fonts/          # Font files (GoogleSansFlex.ttf)
```

---

## 1. The Writers Room Interrogation (Co-Creation Phase)

Before generating any media, the agent must assume the persona of an **expert showrunner and creative co-director** and host an interactive co-creation session with the user. The goal is to draft a comprehensive **Story Bible** before generating any files.

### 1.1 The Interrogation Process
The agent must present a structured inquiry covering **The Four Pillars of Media Interrogation**. Instead of just asking dry questions, the agent should propose imaginative style elements, plot quirks, or color schemes to inspire the user.

#### Pillar 1: Narrative Scope & Custom Length
*   **Narrative Scene Count**: Ask the user exactly how many scenes they want in their narrative (e.g., a short 3-scene story, a standard 5-scene story, or an epic 10+ scene odyssey). Do NOT constrain the length.
*   **Arc Structure**: Let the user select the dramatic format:
    1.  *Classic Hero's Journey*: Hook, call to adventure, trials, climax, and resolution.
    2.  *Short-Form Arc*: Focused problem, quick struggle, and fast solution.
    3.  *Tragic Fall*: Rise to prominence, pride/error, rapid failure, and moral warning.
    4.  *Rags to Riches*: Struggle against adversity, discovery, triumph, and giving back.
    5.  *Custom / Freestyle*: User-provided structural sequence.

#### Pillar 2: Character Consistency Framework
*   **Primary Character Portrait Prompt**: Co-create a detailed description of the protagonist to maintain visual consistency.
    *   *Formula*: `[Species/Role] + [Age/Mood] + [Distinct Costume] + [Defining Physical Features]`.
    *   *Example*: "A fluffy white Angora bunny wearing miniature round science safety goggles, a tiny leather tool belt, and an emerald-green vest. Extremely curious, bright pink twitching nose."
*   **Supporting Cast**: Describe secondary characters and their visual relationship to the protagonist.

#### Pillar 3: Multimedia & Production Aesthetics
*   **Visual Art Medium**: (e.g., *3D Claymation / Stop-Motion* [recommended for charming consistency], *Realistic Sci-Fi Cinematic*, or *Watercolor Sketch*).
*   **Color Palette & Mood**: (e.g., "Vibrant pasture greens and soft gold sunlight" or "Desaturated charcoal and glowing bioluminescent cyan").
*   **Soundtrack Genre & Tone**: (e.g., "Whimsical acoustic guitar and playful tuba" or "Ethereal synth pads and slow, soft chimes").
*   **Voice Actor Cast**: (Prefer *Callirrhoe* for warm/soothing female narration, *Fenrir* for resonant/deep sci-fi narration, or *Kore* for playful/bright stories. With the default Gemini 3.8 TTS you can also cast an Extended Voice Library narrator, e.g. `list_gemini_voices` with `search: "storyteller"`. Keep the voice prompt to a short delivery style such as "soothing, gentle"; the voice itself carries gender and accent).

#### Pillar 4: Audio Speed-Fitting Preference
*   Confirm if the user wants the system to automatically speed-fit the narrator voice-over using the FFmpeg `atempo` filter if it runs longer than the video scene (recommended to avoid video stalling/looping).
*   *Warning*: Inform the user that the showrunner will strictly clamp voiceover speedups at $1.25\times$ to preserve natural speaker cadence. If a script is too wordy, the pipeline will instead loop the video or recommend text cuts in the Editor's QC Room.

### 1.2 Interactive Loop
1.  **Draft Proposed Story Bible**: Synthesize the user's answers and your creative suggestions into a formal Story Bible block.
2.  **Await Explicit User Approval**: Present the story bible and scene-by-scene script. **Do NOT proceed to media generation until the user has explicitly approved the story bible.**

---

## 2. Scripting & Story Bible Schema

Once the user approves the story bible, format the scene-by-scene scripts in a structured `scenes.json` file. For each scene (1 to N), specify:
*   **id**: Sequential scene index (1-indexed).
*   **title**: Concise scene name.
*   **narrator**: Text for the voice-over: only the words to be spoken, with no stage directions (Gemini 3.8 TTS reads it verbatim). Keep it under 800 characters, both to fit the scene and so it works on every Gemini TTS model; 3.8 itself accepts up to 4,000. Vocal events may use `<sigh>`, `<laugh>`, `<short pause>`.
*   **music_prompt**: Specific background music prompt for Lyria.
    *   *Rule*: Music prompts must automatically append the strict instrumental negative filter: `, strictly instrumental, no vocals, no voice, no singing, ambient background score` to avoid synthetic vocal artifacts.
*   **image_prompt**: Nano Banana visual prompt incorporating the character descriptions and visual medium.
*   **motion_prompt**: Veo 3.1 motion prompt describing camera movement and subject action.

---

## 3. Double-Engine Media Assembly Pipeline

This skill provides a **Double-Engine** media assembly pipeline. Any coding agent can either run the automated Python scripts or perform the exact manual FFmpeg commands directly in the shell if they want to override the pipeline.

### Engine A: Manual Agent Command Blueprint (Raw FFmpeg)
If you are an agent executing these steps manually in the command line, use this step-by-step FFmpeg blueprint to compile individual scenes and concatenate them robustly:

#### 1. Generate Voiceover & Probe Duration
Always run TTS generation first and retrieve the exact duration of the voice file:
```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 voice.wav
```

#### 2. Query Veo Video with Optimal Sizing
Compare the voice duration ($D_{voice}$) and request a matching video length from Veo (either 4, 6, or 8 seconds):
*   $D_{voice} \le 4.2\text{s} \rightarrow$ Generate a **4-second** video clip.
*   $D_{voice} \le 6.2\text{s} \rightarrow$ Generate a **6-second** video clip.
*   $D_{voice} > 6.2\text{s} \rightarrow$ Generate an **8-second** video clip.

Retrieve the resulting video clip's exact duration:
```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 video.mp4
```

#### 3. Calculate Speed-Fit Tempo and Determine Looping
If `voice_duration` ($D_{voice}$) is longer than `video_duration` ($D_{vid}$), calculate the required tempo ratio:
$$\text{tempo} = \frac{D_{voice}}{D_{vid} - 0.5}$$
*   **Tempo Guardrail**: If $\text{tempo} \le 1.25$, apply the `atempo` filter.
*   **Tempo Clamp**: If $\text{tempo} > 1.25$, drop the tempo back to `1.0` (natural speaking speed) and **loop** the background video clip indefinitely to fit.

#### 4. Determine if Video has a Native Audio Track
To prevent FFmpeg filter crashes, check if the video has an audio stream:
```bash
ffprobe -v error -select_streams a -show_entries stream=codec_type -of csv=p=0 video.mp4
```

#### 5. Mix Audio Streams with Volume Ducking & Mathematical Capping
Calculate the exact target output duration:
$$\text{out\_duration} = \frac{D_{voice}}{\text{tempo}}$$

Run the appropriate mixing command. *CRITICAL: We append `-stream_loop -1` to loop the video in case tempo clamping is active, and enforce the output duration strictly with `-t {out_duration}` to prevent blank trailing frames.*

*   **Case A (Video has ambient sound)**: Duck video audio to 25%, apply speed-fit and boost to narration, duck music to 15%, and mix them:
    ```bash
    ffmpeg -y -stream_loop -1 -i video.mp4 -i voice.wav -i music.wav \
      -filter_complex "[0:a]volume=0.25[bgv]; [1:a]atempo=1.20,volume=1.5[vo]; [2:a]volume=0.15[bgm]; [vo][bgv][bgm]amix=inputs=3:duration=first:dropout_transition=0[aout]" \
      -map 0:v -map "[aout]" -t 7.345 -c:v libx264 -preset fast -pix_fmt yuv420p -c:a aac -ar 44100 scene_mixed.mp4
    ```
*   **Case B (Video is silent)**: Mix only the speed-fitted narration and the ducked background music:
    ```bash
    ffmpeg -y -stream_loop -1 -i video.mp4 -i voice.wav -i music.wav \
      -filter_complex "[1:a]atempo=1.20,volume=1.5[vo]; [2:a]volume=0.15[bgm]; [vo][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]" \
      -map 0:v -map "[aout]" -t 7.345 -c:v libx264 -preset fast -pix_fmt yuv420p -c:a aac -ar 44100 scene_mixed.mp4
    ```

#### 6. Pre-flight Normalization for Concat Desync Prevention
Before concatenating multiple video files, you **MUST** normalize their audio parameters to prevent audio drift, blank screens, or concatenation failures.
*   **Normalize Segment WITH Native Audio**: Re-encode to standard `libx264` and `aac` at `44100Hz`:
    ```bash
    ffmpeg -i scene_mixed.mp4 -c:v libx264 -preset fast -c:a aac -ar 44100 -y norm_scene.mp4
    ```
*   **Normalize Segment WITHOUT Audio (Silent clips)**: Force-inject a silent mono track and re-encode:
    ```bash
    ffmpeg -i scene_mixed.mp4 -f lavfi -i anullsrc=cl=mono:r=44100 \
      -map 0:v -map 1:a -c:v libx264 -preset fast -c:a aac -shortest -y norm_scene.mp4
    ```

#### 7. Concatenate Normalized Segments Instantly
Since all segments are perfectly normalized to the same video/audio codec configurations, stitch them instantly without re-encoding:
```bash
# Create concat_list.txt containing file paths:
# file 'norm_scene_1.mp4'
# file 'norm_scene_2.mp4'
ffmpeg -y -f concat -safe 0 -i concat_list.txt -c copy final_story.mp4
```

---

### Engine B: Automated Scripting Blueprint
For fully automated and robust end-to-end execution, use the provided Python scripts in the `scripts/` directory:

#### 1. Generate Individual Scene Assets
Run `generate_scene.py` for each scene (this can be executed concurrently in parallel subagents to maximize throughput):
```bash
python3 story-generator/scripts/generate_scene.py \
  --scene_id 1 \
  --narrator "Barnaby the bunny woke up in his cozy earthy burrow..." \
  --voice "Callirrhoe" \
  --music "Gentle acoustic guitar theme" \
  --image "3D claymation, cartoon bunny with safety goggles..." \
  --video "The bunny stretches lazily, ears twitching" \
  --out_dir /path/to/project_dir
```
*(This script automatically handles the voiceover-first ffprobe checks, dynamic video duration mapping, speed-clamping at 1.25x with auto-looping, vocal negative filtering, and explicit mathematical duration capping).*

#### 2. Assemble and Stitch the Final Storybook
Run `assemble_story.py` to normalize the generated clips and stitch them into the final storybook:
```bash
python3 story-generator/scripts/assemble_story.py \
  --project_dir /path/to/project_dir \
  --output_name final_story.mp4
```

---

## 4. The Editor's Quality Control Room Stage

To ensure broadcast-quality narrative pacing and format adherence, the agent must run the QC stage immediately after stitching the master video.

```bash
python3 story-generator/scripts/editors_quality_room.py --project_dir /path/to/project_dir
```

### 4.1 Audits Conducted
1.  **Format Verification**: Confirms that all scene files and the final master video are standard H.264 video with AAC, 44100Hz stereo audio.
2.  **Narrator Speech Density Audit**: Computes the estimated speech-tempo ratio. If a scene requires a compression factor $> 1.50\times$, it flags a `TEMPO` warning.
3.  **A/V Drift Detection**: Audits the compiled master video duration against the mathematical sum of the individual scene files. If the drift exceeds 0.5 seconds, it flags a `DRIFT` warning.
4.  **Actionable Quality Report**: Outputs `quality_report.json` and a human-readable `quality_report.md` specifying actionable editorial feedback.

### 4.2 Self-Correcting Feedback Loop
If the QC Room outputs `TEMPO` warnings, the agent should intercept this, present the actionable editorial notes to the user, and offer to automatically shorten the narration script for those specific scenes (aiming for under 12–14 words per 6-second segment) to maintain a natural, calm cadence.

---

## 5. Visual Pipeline Flowcharts

Every compiled project report includes a high-fidelity rendering of the Double-Engine media pipeline, visualized via Graphviz DOT.

```bash
python3 story-generator/scripts/generate_pipeline_diagram.py --project_dir /path/to/project_dir
```

This command parses the workflow blocks and compiles `/path/to/project_dir/report/pipeline_diagram.dot` to an optimized `/path/to/project_dir/report/pipeline_diagram.webp` file, which is then embedded directly as a premium architecture dashboard card inside the compiled Material 3 HTML reports.
