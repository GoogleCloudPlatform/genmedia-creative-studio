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

"""The profile seam — a plain-Python dataclass + factory input.

The engine is built behind `build_root_agent(profile)` (see agent.py) so the
same graph serves two audiences without reworking it. It ships TWO profiles:
  * `AD_PROFILE` — the ad creative-director capstone (Veo clips, single final
    file). It is the DEFAULT: `root_agent = build_root_agent(AD_PROFILE)`, so
    `adk web` shows the ad capstone unchanged.
  * `STORYBOARD_PROFILE` — the editorial "Creative Studio" storyboard profile
    (nanobanana stills, board-paced animatic, package + manifest). It is reached
    through the headless `package` CLI (see package.py) — the dogfood tool.

DESIGN CONSTRAINT (deliberate): profiles are a **frozen dataclass + factory**,
using only stable ADK constructor APIs. We do NOT use ADK's `from_config` /
`AgentConfig` YAML loader: in ADK 2.8.0 `agents/config_agent_utils.py:from_config`
is decorated BOTH `@deprecated` AND `@experimental(FeatureName.AGENT_CONFIG)`, so
building the engine on it would schedule a removal into the series.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from .schemas import AdPlan, StoryboardPlan


@dataclass(frozen=True)
class Profile:
    """Selects what the one engine produces for a given audience.

    Attributes:
      name: short profile id, used in the root agent's name ("ad" |
        "storyboard").
      planner_persona: tone/audience prose appended to the profile's planner
        instruction base (see agent.py).
      plan_schema: the planner's `output_schema` (AdPlan | StoryboardPlan).
      shot_media: what each per-shot slot produces —
        "clips": photoshoot still -> Veo clip (director); the ad path.
        "stills": photoshoot still ONLY (no director, no Veo); the storyboard
        path (cheaper/faster/deterministic docs tool).
      assembler_recipe: which assembly the assembler runs —
        "video_ad_concat": concat clips + mix music/VO + trim + combine (ad).
        "stills_animatic": stills -> silent slideshow + mix music/narration +
        trim + combine into animatic.mp4 (storyboard).
      emit_package: False (ad: single final file) | True (storyboard: a package
        directory + a machine-readable manifest.json, produced by the headless
        `package` CLI's deterministic packager — see package.py).
      plan_state_key: the session-state key the planner writes its schema-
        validated plan to and every downstream stage reads via `{key}`
        templating. "ad_plan" for the ad profile (unchanged from PR-5), "plan"
        for the storyboard profile (the key the packager reads).
      enable_qc: when True, the 4th (assembler) stage is wrapped in a `LoopAgent`
        — the "Editor's QC Room" (PR-7). The assembler runs FIRST each iteration
        (builds/rebuilds the cut) and a critic runs SECOND: it MEASURES the cut
        (ffprobe) and either escalates to stop the loop (cut acceptable) or writes
        correction notes the assembler reads on the next iteration. False (the
        default) preserves the pre-PR-7 behavior exactly — a bare assembler as the
        4th stage, no loop. Both shipped profiles set it True.
      qc_max_iterations: the LoopAgent's hard `max_iterations` cap — the guarantee
        against an infinite loop even if the critic never escalates
        (google-adk loop_agent.py:95-97). Small on purpose (2): one pass to build
        + catch, one to fix + accept. Only consulted when enable_qc is True.
    """

    name: str
    planner_persona: str
    plan_schema: type[BaseModel]
    shot_media: str
    assembler_recipe: str
    # Additive fields (defaults preserve the PR-5 AD_PROFILE behavior exactly).
    emit_package: bool = False
    plan_state_key: str = "ad_plan"
    # PR-7 QC LoopAgent ("Editor's QC Room"). Defaults (enable_qc=False) preserve
    # the pre-PR-7 behavior; both shipped profiles below set enable_qc=True.
    enable_qc: bool = False
    qc_max_iterations: int = 2


# The tone/audience half of the planner instruction for the ad profile. The
# construct-level half (schema fields, duration budget, shot cap) lives in
# PLANNER_BASE in agent.py so it is shared across any future profile.
_AD_PLANNER_PERSONA = """\

# Your brief and voice (ad creative director)
You are an ad creative director. The user gives you a brand brief and a target
duration; you turn it into a tight, persuasive short video ad. Think like an
advertiser: a clear through-line, a hero product/benefit, an emotional beat, and
a crisp call-to-action in the final shot's voiceover. Keep the brand voice
consistent across shots and make every second earn its place.
"""


AD_PROFILE = Profile(
    name="ad",
    planner_persona=_AD_PLANNER_PERSONA,
    plan_schema=AdPlan,
    shot_media="clips",
    assembler_recipe="video_ad_concat",
    # emit_package / plan_state_key left at their defaults (False / "ad_plan"),
    # so the ad clip/plan pipeline is byte-for-byte the PR-5 behavior.
    # PR-7: the QC LoopAgent applies to BOTH profiles (profile-agnostic on the
    # engine), so the ad capstone / `adk web` now runs the Editor's QC Room too.
    enable_qc=True,
)


# The tone/audience half of the planner instruction for the storyboard profile.
# The construct-level half (author the beats by REUSING PR-4's scriptwriter, then
# emit a schema-valid StoryboardPlan) lives in STORYBOARD_PLANNER_BASE in
# agent.py so any future editorial audience can share it.
_STORYBOARD_PLANNER_PERSONA = """\

# Your brief and voice (editorial storyboard director)
You are an editorial/documentary storyboard director for a journalist, marketer,
or devrel writer (including THIS series, which uses you to illustrate its own
posts). Your register is explanatory and neutral — you inform, you do not sell.
There is NO ad duration budget: the board is paced by the story, and the
narration reads as explainer voiceover, not a brand CTA. Give each panel a clear
editorial beat, an art-directed still prompt, and one neutral narration line.
"""


STORYBOARD_PROFILE = Profile(
    name="storyboard",
    planner_persona=_STORYBOARD_PLANNER_PERSONA,
    plan_schema=StoryboardPlan,
    shot_media="stills",
    assembler_recipe="stills_animatic",
    emit_package=True,
    plan_state_key="plan",
    # PR-7: the storyboard animatic also gets the Editor's QC Room (profile-
    # agnostic). Its critic uses NO duration budget — only existence + audio/video
    # sync — because the storyboard is board-paced.
    enable_qc=True,
)
