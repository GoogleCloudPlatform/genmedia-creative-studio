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

"""Python wrapper for the Worsfold Encoder Lit component."""

import mesop as me
import typing

@me.web_component(path="./worsfold_encoder.js")
def worsfold_encoder(
    *,
    # --- Properties ---
    video_url: str = "",
    config: dict | None = None,
    start_encode: bool = False,

    # --- Events ---
    on_encode_complete: typing.Callable[[me.WebEvent], None] = None,
    on_progress: typing.Callable[[me.WebEvent], None] = None,
    on_log: typing.Callable[[me.WebEvent], None] = None,
    on_load_complete: typing.Callable[[me.WebEvent], None] = None,

    key: str | None = None,
):
    """Defines the API for the Worsfold Encoder web component."""
    if config is None:
        config = {}
    return me.insert_web_component(
        key=key,
        name="worsfold-encoder",
        properties={
            "videoUrl": video_url,
            "config": config,
            "startEncode": start_encode,
        },
        events={
            "encodeCompleteEvent": on_encode_complete,
            "progressEvent": on_progress,
            "logEvent": on_log,
            "loadCompleteEvent": on_load_complete,
        },
    )
