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
"""Tests for the Character Sheet prompt presets and page handlers."""

from types import SimpleNamespace

import pytest

from config import character_sheet_prompts as csp


def test_presets_are_well_formed_and_unique():
    ids = [p.id for p in csp.CHARACTER_SHEET_PRESETS]
    assert len(ids) == len(set(ids))
    assert csp.DEFAULT_PRESET_ID in ids
    assert csp.CUSTOM_PRESET_ID not in ids  # custom is added by the page
    for p in csp.CHARACTER_SHEET_PRESETS:
        assert p.label and p.description and p.template
        assert p.aspect_ratio
        # Every template must render without leftover placeholders.
        assert "{" not in csp.build_prompt(p.id)


def test_turnaround_is_the_original_prompt():
    prompt = csp.build_prompt("turnaround")
    assert prompt.startswith("Character sheet of this character, white background")
    assert "front, back, side, three-quarter, close-up face" in prompt


def test_camera_coverage_lists_all_shots():
    prompt = csp.build_prompt("camera_coverage")
    assert prompt.startswith("Give me a multipanel of this character")
    for shot in csp.CAMERA_SHOTS:
        assert shot in prompt
    assert len(csp.CAMERA_SHOTS) == 7


def test_camera_coverage_inserts_description_only_when_given():
    desc = "ALEX VANCE (Studio Anchor): Sharp, professional, energetic."
    with_desc = csp.build_prompt("camera_coverage", character_description=f"  {desc}  ")
    assert desc in with_desc
    assert with_desc.index(desc) < with_desc.index("with these camera shots")
    assert desc not in csp.build_prompt("camera_coverage")


def test_description_is_ignored_by_presets_that_do_not_use_it():
    assert csp.build_prompt("turnaround", character_description="XYZ") == (
        csp.build_prompt("turnaround")
    )


def test_custom_prompt_is_used_verbatim_and_not_formatted():
    custom = "  A {braced} sheet with only the face.  "
    assert csp.build_prompt(csp.CUSTOM_PRESET_ID, custom_prompt=custom) == (
        "A {braced} sheet with only the face."
    )
    assert csp.build_prompt(csp.CUSTOM_PRESET_ID) == ""


def test_unknown_preset_falls_back_to_default():
    assert csp.build_prompt("nope") == csp.build_prompt(csp.DEFAULT_PRESET_ID)
    assert csp.get_default_aspect_ratio("nope") == "16:9"
    assert csp.get_default_aspect_ratio(csp.CUSTOM_PRESET_ID) == "16:9"


@pytest.fixture
def page(monkeypatch):
    from pages import character_sheet as cs

    state = cs.PageState()
    monkeypatch.setattr(cs.me, "state", lambda cls: state)
    return cs, state


def test_switching_to_custom_seeds_prompt_from_previous_preset(page):
    cs, state = page
    state.sheet_preset_id = "camera_coverage"
    state.character_description = "A tired detective."
    list(cs.on_preset_change(SimpleNamespace(value=csp.CUSTOM_PRESET_ID)))
    assert state.sheet_preset_id == csp.CUSTOM_PRESET_ID
    assert "A tired detective." in state.custom_prompt
    assert "Extreme Close-Up (ECU)" in state.custom_prompt


def test_switching_to_custom_keeps_existing_edits(page):
    cs, state = page
    state.custom_prompt = "my edited prompt"
    list(cs.on_preset_change(SimpleNamespace(value=csp.CUSTOM_PRESET_ID)))
    assert state.custom_prompt == "my edited prompt"


def test_generate_uses_selected_preset_prompt(page, monkeypatch):
    cs, state = page
    state.sheet_preset_id = "camera_coverage"
    state.original_image_gcs_uri = "gs://b/original.png"
    calls = {}

    def fake_generate(prompt, images, aspect_ratio, gcs_folder):
        calls.update(prompt=prompt, images=images, aspect_ratio=aspect_ratio)
        return ["gs://b/sheet.png"], None, None, None, None

    monkeypatch.setattr(cs, "generate_image_from_prompt_and_images", fake_generate)
    monkeypatch.setattr(cs, "create_display_url", lambda uri: "https://x/" + uri)
    saved = []
    monkeypatch.setattr(cs, "add_media_item_to_firestore", saved.append)
    monkeypatch.setattr(cs.me, "state", lambda cls: state if cls is cs.PageState else SimpleNamespace(user_email="u@example.com"))

    list(cs.on_generate_sheet_click(None))

    assert calls["prompt"].startswith("Give me a multipanel of this character")
    assert calls["aspect_ratio"] == "16:9"
    assert saved and "camera_coverage" in saved[0].comment
    assert state.asset_sheet_gcs_uri == "gs://b/sheet.png"


def test_generate_blocks_empty_custom_prompt(page, monkeypatch):
    cs, state = page
    state.sheet_preset_id = csp.CUSTOM_PRESET_ID
    state.original_image_gcs_uri = "gs://b/original.png"
    called = []
    monkeypatch.setattr(
        cs, "generate_image_from_prompt_and_images", lambda **kw: called.append(kw)
    )
    monkeypatch.setattr(cs.me, "state", lambda cls: state if cls is cs.PageState else SimpleNamespace(user_email="u@example.com"))

    list(cs.on_generate_sheet_click(None))

    assert not called
    assert state.show_snackbar
    assert state.is_generating_sheet is False
