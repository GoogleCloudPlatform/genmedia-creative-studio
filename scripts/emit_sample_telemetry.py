#!/usr/bin/env python3
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

"""Sample telemetry generator for testing the smoke analyzer offline.

Emits structured JSON log lines for each instrumented model directly to stderr
or a log file.
"""

import os
import sys
import time

# Ensure repository root is in sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from common.analytics import track_model_call
from common.error_handling import ErrorCategory, GenerationError


def emit_samples():
    print("Emitting sample telemetry lines to stderr...", file=sys.stderr)

    # 1. Gemini Image / Nano Banana
    with track_model_call(
        "gemini-3.1-flash-image",
        billing_units={"aspect_ratio": "16:9", "input_asset_count": 1},
    ) as ctx:
        time.sleep(0.05)
        ctx["billing_units"].update(
            {"prompt_tokens": 120, "candidates_tokens": 512, "total_tokens": 632},
        )

    # 2. Lyria Music Generation
    with track_model_call(
        "lyria-3-clip-preview",
        billing_units={
            "sample_count": 1,
            "has_lyrics": True,
            "has_image_conditioning": False,
        },
    ):
        time.sleep(0.04)

    # 3. Gemini TTS
    with track_model_call(
        "gemini-tts",
        billing_units={
            "characters_synthesized": 85,
            "voice_name": "en-US-Standard-A",
            "language_code": "en-US",
            "audio_bytes": 16400,
        },
    ):
        time.sleep(0.02)

    # 4. Chirp 3 HD
    with track_model_call(
        "chirp-3-hd",
        billing_units={
            "characters_synthesized": 110,
            "voice_name": "en-US-Chirp3-HD-Orus",
            "speaking_rate": 1.0,
            "audio_bytes": 22000,
        },
    ):
        time.sleep(0.03)

    # 5. Virtual Try-On
    with track_model_call(
        "vto-1",
        billing_units={
            "sample_count": 2,
            "base_steps": 32,
            "safety_filter_level": "block_low_and_above",
            "images_generated": 2,
        },
    ):
        time.sleep(0.06)

    # 6. Imagen 4 Fast
    with track_model_call(
        "imagen-4.0-fast",
        billing_units={"sample_count": 1, "aspect_ratio": "1:1", "images_generated": 1},
    ):
        time.sleep(0.03)

    # 7. Veo 3.1 Fast
    with track_model_call(
        "veo-3.1-fast-generate-001",
        billing_units={
            "video_seconds_generated": 8,
            "sample_count": 1,
            "resolution": "1080p",
            "aspect_ratio": "16:9",
            "generate_audio": True,
            "videos_generated": 1,
        },
    ):
        time.sleep(0.08)

    # 8. Gemini Omni
    with track_model_call(
        "gemini-omni-1.2-flash",
        billing_units={
            "video_seconds_generated": 10,
            "sample_count": 1,
            "aspect_ratio": "16:9",
            "omni_mode": "text2video",
            "is_multiturn": False,
        },
    ) as ctx:
        time.sleep(0.07)
        ctx["details"]["interaction_id"] = "int-sample-99"

    # 9. Classified Failure: Capacity Exhausted
    try:
        with track_model_call(
            "veo-3.1-generate-001", billing_units={"video_seconds_generated": 8},
        ):
            raise GenerationError(
                "ResourceExhausted: 429 Rate limit exceeded",
                category=ErrorCategory.CAPACITY_EXHAUSTED,
                code=429,
                retryable=True,
            )
    except Exception:
        pass

    # 10. Classified Failure: Safety Filter
    try:
        with track_model_call(
            "imagen-4.0-generate-001", billing_units={"sample_count": 1},
        ):
            raise GenerationError(
                "Content Filtered: Prompt triggered safety filter",
                category=ErrorCategory.SAFETY_FILTER,
                code=None,
                retryable=False,
            )
    except Exception:
        pass

    print("Sample telemetry emitted successfully.", file=sys.stderr)


if __name__ == "__main__":
    emit_samples()
