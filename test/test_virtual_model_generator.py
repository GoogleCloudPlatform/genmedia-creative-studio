# Copyright 2026 Google LLC
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

"""Unit tests for VirtualModelGenerator and Monk Skin Tone Scale configuration."""

import json
import re
from pathlib import Path

from models.virtual_model_generator import DEFAULT_PROMPT, VirtualModelGenerator

OPTIONS_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "virtual_model_options.json"
)


def test_virtual_model_options_has_full_mst_scale_and_citation() -> None:
    """Verify config/virtual_model_options.json has MST-1..10 and CC-BY-4.0 citation."""
    with OPTIONS_PATH.open() as f:
        options = json.load(f)

    assert "Monk Skin Tone Scale" in options.get("_citation", "")
    assert "skintone.google" in options.get("_citation", "")

    mst_entries = options["MST"]
    assert [m["name"] for m in mst_entries] == [f"MST-{i}" for i in range(1, 11)]
    for entry in mst_entries:
        assert re.fullmatch(r"#[0-9a-f]{6}", entry["hex"])
        assert entry["hex"] in entry["prompt_fragment"]
        assert "skin tone" in entry["prompt_fragment"]


def test_randomize_all_builds_clean_fully_substituted_prompt() -> None:
    """Verify randomize_all() populates all four placeholders cleanly."""
    generator = VirtualModelGenerator(DEFAULT_PROMPT)
    generator.randomize_all()

    prompt = generator.build_prompt()

    assert "{" not in prompt
    assert "}" not in prompt
    assert "an a " not in prompt
    assert "skin tone skin tone" not in prompt


def test_every_mst_entry_renders_cleanly_in_default_prompt() -> None:
    """Verify every MST-1..10 fragment renders without duplicated articles or nouns."""
    generator = VirtualModelGenerator(DEFAULT_PROMPT)
    generator.set_value("gender", generator.options["genders"][0]["prompt_fragment"])
    generator.set_value(
        "silhouette",
        generator.options["silhouette_presets"][0]["prompt_fragment"],
    )
    generator.set_value("variant", generator.options["variants"][0]["prompt_fragment"])

    for mst in generator.options["MST"]:
        generator.set_value("MST", mst["prompt_fragment"])
        prompt = generator.build_prompt()
        assert mst["prompt_fragment"] in prompt
        assert "an a " not in prompt
        assert "an the " not in prompt
        assert "skin tone skin tone" not in prompt


def test_invalid_template_falls_back_to_default_prompt() -> None:
    """Verify templates missing required placeholders revert to DEFAULT_PROMPT."""
    generator = VirtualModelGenerator("Incomplete template missing placeholders")
    generator.randomize_all()

    prompt = generator.build_prompt()

    assert "{" not in prompt
    assert "}" not in prompt
    assert "virtual try-on application" in prompt
