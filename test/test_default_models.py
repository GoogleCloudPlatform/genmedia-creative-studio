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

"""Tests for the default-model review (gmcs-2b7)."""

# ruff: noqa: D103, S101

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("PROJECT_ID", "test-project")
os.environ.setdefault("LOCATION", "us-central1")

for _mod in ("parselmouth", "parselmouth.praat"):
    if _mod not in sys.modules:
        try:  # pragma: no cover - import side effect
            __import__(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()

from config import default as config_default  # noqa: E402
from config.gemini_image_models import GEMINI_IMAGE_MODELS  # noqa: E402
from pages import gemini_writers_workshop as ww  # noqa: E402

DEFAULTS = config_default.Default()


def test_csv_env_parses_trims_and_falls_back(monkeypatch):
    monkeypatch.setenv("X_MODELS", " a , b,,c ")
    assert config_default._csv_env("X_MODELS", ("z",)) == ("a", "b", "c")

    monkeypatch.setenv("X_MODELS", " , ")
    assert config_default._csv_env("X_MODELS", ("z",)) == ("z",)

    monkeypatch.delenv("X_MODELS")
    assert config_default._csv_env("X_MODELS", ("z",)) == ("z",)


def test_writers_workshop_defaults_to_argon_with_two_models():
    assert DEFAULTS.GEMINI_WRITERS_WORKSHOP_MODELS == (
        "gemini-4-argon",
        "gemini-3.8-flash",
    )
    assert DEFAULTS.GEMINI_WRITERS_WORKSHOP_MODEL_ID == "gemini-4-argon"


def test_interior_design_and_object_rotation_use_nano_banana_2_1():
    assert DEFAULTS.INTERIOR_DESIGN_IMAGE_MODEL == "gemini-nano-banana-2.1"
    assert DEFAULTS.OBJECT_ROTATION_IMAGE_MODEL == "gemini-nano-banana-2.1"


def test_image_defaults_are_registered_models():
    registered = {m.model_name for m in GEMINI_IMAGE_MODELS}

    assert DEFAULTS.INTERIOR_DESIGN_IMAGE_MODEL in registered
    assert DEFAULTS.OBJECT_ROTATION_IMAGE_MODEL in registered


def _with_cfg(monkeypatch, models, default):
    monkeypatch.setattr(
        ww,
        "cfg",
        lambda: SimpleNamespace(
            GEMINI_WRITERS_WORKSHOP_MODELS=models,
            GEMINI_WRITERS_WORKSHOP_MODEL_ID=default,
        ),
    )


def test_picker_offers_exactly_the_configured_models(monkeypatch):
    _with_cfg(monkeypatch, ("gemini-4-argon", "gemini-3.8-flash"), "gemini-4-argon")

    assert ww.workshop_model_options() == ["gemini-4-argon", "gemini-3.8-flash"]
    assert ww.default_workshop_model() == "gemini-4-argon"


def test_default_not_listed_is_added_first(monkeypatch):
    _with_cfg(monkeypatch, ("gemini-3.8-flash",), "gemini-4-argon")

    assert ww.workshop_model_options() == ["gemini-4-argon", "gemini-3.8-flash"]
    assert ww.default_workshop_model() == "gemini-4-argon"


@pytest.mark.parametrize("default", ["gemini-3.8-flash", "gemini-4-argon"])
def test_default_is_selectable_from_either_model(monkeypatch, default):
    _with_cfg(monkeypatch, ("gemini-4-argon", "gemini-3.8-flash"), default)

    assert ww.default_workshop_model() == default
