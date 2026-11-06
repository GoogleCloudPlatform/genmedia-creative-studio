# Copyright 2024 Google LLC
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

"""Python wrapper for the Media Detail Viewer Lit component."""

import mesop as me
import typing


@me.web_component(path="./media_detail_viewer.js")
def media_detail_viewer(
    *,
    media_type: str | None,
    primary_urls_json: str,
    source_urls_json: str,
    metadata_json: str,
    id: str,
    raw_metadata_json: str,
    on_edit_click: typing.Callable[[me.WebEvent], None] | None = None,
    on_veo_click: typing.Callable[[me.WebEvent], None] | None = None,
    on_omni_click: typing.Callable[[me.WebEvent], None] | None = None,
    on_extend_click: typing.Callable[[me.WebEvent], None] | None = None,
    key: str | None = None,
):
    """Defines the API for the media_detail_viewer web component."""
    return me.insert_web_component(
        key=key,
        name="media-detail-viewer",
        properties={
            "mediaType": media_type or "",
            "primaryUrlsJson": primary_urls_json,
            "sourceUrlsJson": source_urls_json,
            "metadataJson": metadata_json,
            "id": id,
            "rawMetadataJson": raw_metadata_json,
        },
        events={
            "editClickEvent": on_edit_click,
            "veoClickEvent": on_veo_click,
            "omniClickEvent": on_omni_click,
            "extendClickEvent": on_extend_click,
        },
    )


