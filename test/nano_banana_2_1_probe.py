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

"""Independent probe script to validate Gemini Nano Banana 2.1 capabilities against the live API.

Mirrors ``nano_banana_2_lite_probe.py`` for ``gemini-nano-banana-2.1``. Unlike
the Lite model, Nano Banana 2.1 supports 1K/2K/4K resolutions and grounding
(Google/image search), so 4K is expected to SUCCEED. The literal model id was
validated on the default Vertex ``global`` endpoint (spike 2026-10-06); no
custom base_url is required.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google import genai
from google.genai import types
import pytest

from config.default import Default

cfg = Default()
MODEL_NAME = "gemini-nano-banana-2.1"


@pytest.fixture(scope="module")
def client() -> genai.Client:
    """Initialize Vertex AI GenAI SDK Client."""
    http_options = None
    if cfg.GEMINI_IMAGE_GEN_API_BASE_URL:
        http_options = {"base_url": cfg.GEMINI_IMAGE_GEN_API_BASE_URL}

    return genai.Client(
        vertexai=True,
        project=cfg.PROJECT_ID,
        location=cfg.GEMINI_IMAGE_GEN_LOCATION,
        http_options=http_options,
    )


@pytest.mark.integration
def test_probe_1k_image_size_success(client: genai.Client) -> None:
    """Verify that generating an image with 1K size succeeds."""
    print(f"\n[PROBE] Testing {MODEL_NAME} with 1K image_size...")
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents="A simple red circle on a white background.",
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=types.ImageConfig(aspect_ratio="1:1", image_size="1K"),
        ),
    )
    assert response.candidates, "No candidates returned for 1K generation."
    has_image = any(
        part.inline_data
        for candidate in response.candidates
        for part in candidate.content.parts
        if candidate.content and candidate.content.parts
    )
    assert has_image, "Response did not contain an inline image part."
    print("[PROBE] 1K image generation SUCCESS.")


@pytest.mark.integration
def test_probe_4k_image_size_success(client: genai.Client) -> None:
    """Verify that 4K generation succeeds (NB2.1 supports 1K/2K/4K)."""
    print(f"\n[PROBE] Testing {MODEL_NAME} with 4K image_size...")
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents="A simple red circle on a white background.",
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=types.ImageConfig(aspect_ratio="1:1", image_size="4K"),
        ),
    )
    assert response.candidates, "No candidates returned for 4K generation."
    print("[PROBE] 4K image generation SUCCESS.")


@pytest.mark.integration
def test_probe_portrait_9_21_aspect_ratio(client: genai.Client) -> None:
    """Verify the doc-only 9:21 portrait aspect ratio is accepted."""
    print(f"\n[PROBE] Testing {MODEL_NAME} with 9:21 aspect ratio...")
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents="A tall waterfall in a lush canyon.",
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=types.ImageConfig(aspect_ratio="9:21", image_size="1K"),
        ),
    )
    assert response.candidates, "No candidates returned for 9:21 generation."
    print("[PROBE] 9:21 aspect ratio SUCCESS.")


@pytest.mark.integration
def test_probe_thinking_support(client: genai.Client) -> None:
    """Verify that thinking_config is supported by Nano Banana 2.1."""
    print(f"\n[PROBE] Testing {MODEL_NAME} with ThinkingConfig...")
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents="A futuristic cityscape at dusk, detailed architectural drawing.",
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=types.ImageConfig(aspect_ratio="16:9", image_size="1K"),
            thinking_config=types.ThinkingConfig(
                include_thoughts=True,
                thinking_budget=-1,
            ),
        ),
    )
    assert response.candidates, "No candidates returned for thinking generation."
    print("[PROBE] Thinking generation SUCCESS.")


if __name__ == "__main__":
    c = genai.Client(
        vertexai=True,
        project=cfg.PROJECT_ID,
        location=cfg.GEMINI_IMAGE_GEN_LOCATION,
    )
    try:
        test_probe_1k_image_size_success(c)
        test_probe_4k_image_size_success(c)
        test_probe_portrait_9_21_aspect_ratio(c)
        test_probe_thinking_support(c)
    except Exception as e:
        print(f"Probe execution failed: {e}")
