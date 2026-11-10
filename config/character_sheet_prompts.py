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
"""Prompt presets for the Character Sheet page.

The page builds its preset chooser from ``CHARACTER_SHEET_PRESETS`` so that
adding a new sheet type is a one-entry change here (no UI edits).
"""

from dataclasses import dataclass

CUSTOM_PRESET_ID = "custom"
DEFAULT_PRESET_ID = "turnaround"

CAMERA_SHOTS = (
    "Extreme Close-Up (ECU): Focuses tightly on a specific detail, such as eyes or a hand.",
    "Close-Up (CU): Frames a subject's face to emphasize emotion.",
    "Medium Shot (MS): Frames the subject from the waist up.",
    "Cowboy Shot (CS): Frames the subject from mid-thigh up, popular in Westerns.",
    "Full Shot (FS): Captures the subject's entire body.",
    "Long Shot (LS)/Wide Shot (WS): Shows the subject within their environment, establishing context.",
    "Over-the-Shoulder (OTS): Shot from behind a person, looking at another, commonly used in dialogues.",
)


@dataclass(frozen=True)
class CharacterSheetPreset:
    """A selectable character sheet prompt.

    Attributes:
        id: Stable identifier stored in page state and the library comment.
        label: Text shown on the toggle button.
        description: One-line help text shown under the chooser.
        template: Prompt text. May contain ``{description}`` which is replaced
            by the optional character description clause.
        aspect_ratio: Aspect ratio requested from the image model.
        uses_description: Whether the optional character description field is
            shown and substituted into ``template``.

    """

    id: str
    label: str
    description: str
    template: str
    aspect_ratio: str = "16:9"
    uses_description: bool = False


CHARACTER_SHEET_PRESETS: tuple[CharacterSheetPreset, ...] = (
    CharacterSheetPreset(
        id="turnaround",
        label="Turnaround",
        description=(
            "Design reference sheet: front, back, side, three-quarter and a "
            "face close-up on a white background."
        ),
        template=(
            "Character sheet of this character, white background, multiple "
            "views: front, back, side, three-quarter, close-up face. "
            "Consistent style. High quality, detailed. Retain realism of "
            "original image."
        ),
    ),
    CharacterSheetPreset(
        id="camera_coverage",
        label="Camera Coverage",
        description=(
            "Cinematography multipanel: ECU, CU, MS, CS, FS, LS and OTS "
            "shots of the same character."
        ),
        template=(
            "Give me a multipanel of this character{description}\n\n"
            "with these camera shots:\n\n"
            + "\n".join(CAMERA_SHOTS)
            + "\n\nConsistent style and character across every panel. "
            "Retain realism of original image."
        ),
        uses_description=True,
    ),
)

_PRESETS_BY_ID = {p.id: p for p in CHARACTER_SHEET_PRESETS}


def get_preset(preset_id: str) -> CharacterSheetPreset | None:
    """Return the preset with the given id, or None (e.g. for custom)."""
    return _PRESETS_BY_ID.get(preset_id)


def get_default_aspect_ratio(preset_id: str) -> str:
    """Aspect ratio for a preset; custom and unknown ids use 16:9."""
    preset = get_preset(preset_id)
    return preset.aspect_ratio if preset else "16:9"


def build_prompt(
    preset_id: str, character_description: str = "", custom_prompt: str = "",
) -> str:
    """Build the final prompt for a preset.

    Args:
        preset_id: A preset id, or ``CUSTOM_PRESET_ID``.
        character_description: Optional description, used only by presets with
            ``uses_description``.
        custom_prompt: The user-edited prompt, used only for the custom id.

    Returns:
        The prompt string, stripped of surrounding whitespace. Empty for an
        empty custom prompt.

    """
    if preset_id == CUSTOM_PRESET_ID:
        return custom_prompt.strip()
    preset = get_preset(preset_id) or _PRESETS_BY_ID[DEFAULT_PRESET_ID]
    description = character_description.strip()
    clause = ""
    if preset.uses_description and description:
        clause = f"\n\n{description}"
    return preset.template.format(description=clause).strip()
