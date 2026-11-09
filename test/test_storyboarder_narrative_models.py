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

"""Tests for the Storyboarder Narrative Writer model defaults (gmcs-71i)."""

# ruff: noqa: D103, ANN001, ANN201

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("PROJECT_ID", "test-project")
os.environ.setdefault("LOCATION", "us-central1")

for _mod in ("parselmouth", "parselmouth.praat"):
    if _mod not in sys.modules:
        try:  # pragma: no cover - import side effect
            __import__(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()

from config import default as config_default  # noqa: E402
from pages import storyboarder  # noqa: E402
from state.storyboarder_state import PageState  # noqa: E402

DEFAULTS = config_default.Default()


def test_config_defaults():
    assert DEFAULTS.GEMINI_STORYBOARDER_NARRATIVE_MODELS == (
        "gemini-3.8-flash",
        "gemini-4-argon",
        "gemini-3.5-flash-lite",
    )
    assert DEFAULTS.GEMINI_STORYBOARDER_NARRATIVE_MODEL_ID == "gemini-3.8-flash"


def test_state_default_matches_config():
    assert (
        PageState().selected_narrative_model
        == DEFAULTS.GEMINI_STORYBOARDER_NARRATIVE_MODEL_ID
    )


def test_picker_offers_configured_models_with_default_label():
    assert storyboarder.narrative_model_options() == [
        ("Gemini 3.8 Flash (Default)", "gemini-3.8-flash"),
        ("Gemini 4 Argon", "gemini-4-argon"),
        ("Gemini 3.5 Flash Lite", "gemini-3.5-flash-lite"),
    ]


def test_picker_never_offers_retired_models():
    values = [value for _, value in storyboarder.narrative_model_options()]
    assert "gemini-3.0-pro" not in values


def test_default_not_listed_is_added_first(monkeypatch):
    monkeypatch.setattr(
        storyboarder,
        "cfg",
        SimpleNamespace(
            GEMINI_STORYBOARDER_NARRATIVE_MODELS=("gemini-4-argon",),
            GEMINI_STORYBOARDER_NARRATIVE_MODEL_ID="gemini-3.8-flash",
        ),
    )

    assert storyboarder.narrative_model_options() == [
        ("Gemini 3.8 Flash (Default)", "gemini-3.8-flash"),
        ("Gemini 4 Argon", "gemini-4-argon"),
    ]


def test_unknown_model_falls_back_to_its_id_as_label(monkeypatch):
    monkeypatch.setattr(
        storyboarder,
        "cfg",
        SimpleNamespace(
            GEMINI_STORYBOARDER_NARRATIVE_MODELS=("gemini-9-future",),
            GEMINI_STORYBOARDER_NARRATIVE_MODEL_ID="gemini-9-future",
        ),
    )

    assert storyboarder.narrative_model_options() == [
        ("gemini-9-future (Default)", "gemini-9-future"),
    ]
