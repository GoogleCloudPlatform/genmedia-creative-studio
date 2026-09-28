# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Schema-validated shot plans for the profile-driven creative-studio engine.

This module defines the two planner `output_schema`s the engine ships:
  * `AdPlan` — the `ad` profile (Veo clips, duration-budgeted). Default.
  * `StoryboardPlan` — the `storyboard` profile (nanobanana stills, board-paced,
    NO duration budget). See the note above `StoryboardShot` below.

It also defines `QCVerdict` — the `output_schema` of the PR-7 "Editor's QC Room"
critic (both profiles). The critic MEASURES the assembled cut and writes a
`QCVerdict` to `state["qc_verdict"]`; the `LoopAgent` stops on escalate (an
acceptable cut) or the `max_iterations` cap. See `QCVerdict` at the end of this
module and `_build_critic` in agent.py.

`AdPlan` is the planner's `output_schema`. Giving the planner an `output_schema`
turns its reply into a schema-validated JSON spine that lands in session state
(`state["ad_plan"]`) instead of free text — every downstream stage reads a
guaranteed shape rather than parsing prose.

ADK 2.8.0 write path (source-verified against the installed 2.8.0 —
tag v2.8.0 of github.com/google/adk-python):
  - `LlmAgent.output_schema` field: agents/llm_agent.py:404 (docstring :415).
  - On the final response ADK runs `validate_schema(output_schema, text)` and
    stores the result under `output_key`:
    agents/llm_agent.py:1044-1045.
  - For a Pydantic `type[BaseModel]`, `validate_schema` returns a **dict**
    (`schema.model_validate_json(json_text).model_dump(exclude_none=True)`):
    utils/_schema_utils.py:141-142. So `state["ad_plan"]` is a dict, and the
    `{ad_plan}` instruction template renders it via `str(value)`
    (utils/instructions_utils.py:162-165).

MAX_SHOTS is intentionally small and FIXED. ADK's `ParallelAgent` has a STATIC
`sub_agents` list (agents/parallel_agent.py:266 iterates `self.sub_agents`; it
does not fan out to a runtime shot count), so the shot stage builds exactly
MAX_SHOTS sub-agents and each reads `shots[i]` if present / no-ops if absent.
The budget math for MAX_SHOTS is justified in agent.py and the README.
"""

from pydantic import BaseModel, Field, field_validator, model_validator

# The only clip durations Veo-3 supports (see the Director persona + agent.py
# budget note). Enforced in-schema below so a bad plan fails at validation time.
VALID_SHOT_DURATIONS = (4, 6, 8)

# The finished-ad duration envelope (15s-2m). `total_duration_seconds` is bounded
# to this per-field (ge/le below), and — closing PR-5 review FYI-1 — the SUM of
# the per-shot `duration_seconds` is bounded to the same envelope by an AdPlan
# cross-field validator, because per-field bounds alone did not guarantee the
# aggregate (three legal 8s shots sum to 24s — fine — but three legal 4s shots
# sum to 12s, which is below the 15s floor even though each shot is valid).
MIN_TOTAL_DURATION_SECONDS = 15
MAX_TOTAL_DURATION_SECONDS = 120

# Fixed number of per-shot slots the ParallelAgent fans out to. Veo-3 clips are
# 4, 6, or 8 seconds each (see the Director persona + agent.py budget note), so
# MAX_SHOTS=3 gives 3 x {4,6,8}s = 12-24s of distinct hero footage — squarely a
# short-form / bumper ad and comfortably inside the 15s-2m budget ceiling.
MAX_SHOTS = 3


class Shot(BaseModel):
    """One hero shot: a still (look) that is then animated into a clip (motion)."""

    look: str = Field(
        description=(
            "Art-direction for the still: subject, composition, lens, light, "
            "and mood. This drives the Photoshoot (nanobanana) still."
        )
    )
    motion: str = Field(
        description=(
            "Camera and subject motion for the clip: e.g. 'slow dolly-in, "
            "low-angle'. This drives the Director (Veo) clip from the still."
        )
    )
    vo_line: str = Field(
        description="The single voiceover line spoken over this shot."
    )
    duration_seconds: int = Field(
        description=(
            "Length of this shot's clip in seconds. MUST be one of 4, 6, or 8 "
            "(the durations Veo-3 supports)."
        )
    )

    @field_validator("duration_seconds")
    @classmethod
    def _duration_must_be_veo3_supported(cls, v: int) -> int:
        # Fail-loud at model_validate time: the prose above steers generation,
        # but this guarantees an out-of-grid duration never reaches Veo. (We
        # use a validator rather than Literal[4, 6, 8] because integer-enum
        # response-schema translation is not confirmed honored by the pinned
        # ADK/genai; the validator is guaranteed to fire.)
        if v not in VALID_SHOT_DURATIONS:
            raise ValueError(
                f"duration_seconds must be one of {VALID_SHOT_DURATIONS} "
                f"(Veo-3 supported), got {v}"
            )
        return v


class AdPlan(BaseModel):
    """A duration-budgeted plan for one short video ad.

    The sum of `shots[*].duration_seconds` is the assembled ad's hero-footage
    length; it must respect `total_duration_seconds` and the 15s-2m envelope.
    """

    brand: str = Field(description="The brand or product the ad is for.")
    total_duration_seconds: int = Field(
        ge=15,
        le=120,
        description=(
            "Target length of the finished ad in seconds. Must be within the "
            "15-120s (15s-2m) budget. The per-shot durations should sum to "
            "approximately this value, up to the hero-footage ceiling "
            "(MAX_SHOTS x 8s)."
        ),
    )
    music_mood: str = Field(
        description=(
            "The mood/genre for the music bed (e.g. 'upbeat indie-pop, warm, "
            "optimistic'), handed to the Music Producer (lyria) persona."
        )
    )
    shots: list[Shot] = Field(
        description=(
            f"The hero shots, in order. AT MOST {MAX_SHOTS} shots — the shot "
            "stage has a fixed number of parallel slots."
        ),
        max_length=MAX_SHOTS,
    )

    @model_validator(mode="after")
    def _sum_of_shot_durations_in_envelope(self) -> "AdPlan":
        # Cross-field invariant (closes PR-5 review FYI-1). Each shot's
        # `duration_seconds` is individually valid (one of 4/6/8) and
        # `total_duration_seconds` is individually in [15, 120], but neither
        # guarantees the ASSEMBLED hero-footage length — the sum of the per-shot
        # durations — lands in the 15s-2m envelope. Enforce it here so a plan
        # whose shots are each legal but sum out of range fails LOUD at
        # validation time rather than producing an out-of-budget ad. Runs after
        # the per-field validators, so `shots` are already grid-valid here.
        total = sum(shot.duration_seconds for shot in self.shots)
        if not (
            MIN_TOTAL_DURATION_SECONDS <= total <= MAX_TOTAL_DURATION_SECONDS
        ):
            raise ValueError(
                "the sum of the per-shot duration_seconds must be within "
                f"[{MIN_TOTAL_DURATION_SECONDS}, {MAX_TOTAL_DURATION_SECONDS}] "
                f"seconds (the 15s-2m ad envelope), got {total}s from "
                f"{[shot.duration_seconds for shot in self.shots]}. Adjust the "
                "shot durations (each still one of 4/6/8) so they sum into range."
            )
        return self


# ============================================================================
# StoryboardPlan — the `storyboard` (journalism/marketing) profile's plan
# ============================================================================
# The storyboard profile is a SECOND audience for the same engine (see
# profiles.py / agent.py). It is board-paced and narration-driven, NOT ad-
# budgeted: there is deliberately NO veo, NO clip, and — because the duration
# model is board-paced, narration length driving it rather than a hard ad
# budget — NO hard duration budget. Consequences for this schema:
#   * StoryboardShot carries NO `duration_seconds` (stills, not Veo clips), so
#     the Veo-3 duration grid is irrelevant here.
#   * StoryboardPlan carries NO total-duration field, so the AdPlan aggregate
#     sum-in-[15,120] invariant above DOES NOT APPLY to StoryboardPlan (N/A by
#     design — the animatic length is driven by the narration at assembly time).
# The only shared constraint is the fixed shot-slot cap: the shot stage reuses
# the same MAX_SHOTS ParallelAgent, so `shots` is bounded to [1, MAX_SHOTS].


class StoryboardShot(BaseModel):
    """One storyboard panel: an editorial beat, its still, and its narration."""

    beat: str = Field(
        description=(
            "The editorial beat this panel covers — what this moment of the "
            "story explains or shows (e.g. 'establish the problem')."
        )
    )
    prompt: str = Field(
        description=(
            "Art-direction for the still: subject, composition, lens, light, "
            "and mood. This drives the Photoshoot (nanobanana) still — there is "
            "no motion/clip in the storyboard profile."
        )
    )
    narration_line: str = Field(
        description=(
            "The explainer voiceover line spoken over this panel (editorial, "
            "neutral register). Concatenated in order into the narration track."
        )
    )


class StoryboardPlan(BaseModel):
    """A board-paced, narration-driven editorial storyboard plan.

    The planner's `output_schema` for the `storyboard` profile. Unlike `AdPlan`
    there is NO duration budget (see the note above): the animatic's length is
    set by the narration at assembly time, so this schema has no total-duration
    field and the AdPlan aggregate-duration invariant does not apply.
    """

    subject: str = Field(
        description=(
            "The brand, product, story, or subject the storyboard is about "
            "(editorial framing, not necessarily an advertiser)."
        )
    )
    music_mood: str = Field(
        description=(
            "The mood/genre for the music bed (e.g. 'calm, contemplative "
            "documentary underscore'), handed to the Music Producer (lyria) "
            "persona."
        )
    )
    shots: list[StoryboardShot] = Field(
        description=(
            f"The storyboard panels, in order. Between 1 and {MAX_SHOTS} shots "
            "— the shot stage has a fixed number of parallel slots, and an "
            "empty plan must not yield a zero-shot package."
        ),
        min_length=1,
        max_length=MAX_SHOTS,
    )


# ============================================================================
# QCVerdict — the "Editor's QC Room" critic's output_schema (PR-7, both profiles)
# ============================================================================
# The critic (an LlmAgent with output_schema=QCVerdict, output_key="qc_verdict")
# runs SECOND inside the editor_qc LoopAgent, after the assembler. It MEASURES the
# just-assembled cut (ffprobe) and emits this structured verdict into session
# state. The LoopAgent stops when the critic escalates (an acceptable cut, via the
# exit_loop tool) OR when the max_iterations cap is hit. On a non-acceptable
# verdict the assembler reads `correction_notes` via the optional `{qc_verdict?}`
# template on the next iteration and re-assembles. `acceptable` is REQUIRED (no
# default) so a malformed verdict fails LOUD at validation time rather than being
# silently treated as a pass.


class QCVerdict(BaseModel):
    """The QC critic's objective pass/fail verdict on one assembled cut."""

    acceptable: bool = Field(
        description=(
            "True IFF the assembled cut passes every objective QC check: the final "
            "file EXISTS, the audio/video durations are in sync (the final cut is "
            "not more than the sync tolerance longer than the video-only track), "
            "and — for the ad profile ONLY — the total duration is within the "
            "15-120s budget. When True the critic also calls the `exit_loop` tool "
            "to stop the QC loop; when False it does NOT escalate."
        )
    )
    issues: list[str] = Field(
        default_factory=list,
        description=(
            "The concrete, MEASURED problems found (empty when acceptable). Each "
            "is an objective, reproducible fact, e.g. 'final 30.10s exceeds video "
            "20.00s by 10.10s (> 1.0s sync tolerance)'."
        ),
    )
    correction_notes: str = Field(
        default="",
        description=(
            "Actionable instructions the assembler applies on the next iteration "
            "to fix the issues (empty when acceptable), e.g. 're-run "
            "trim_audio_to_video_length on the mixed audio against the video, then "
            "re-combine and re-verify'."
        ),
    )
