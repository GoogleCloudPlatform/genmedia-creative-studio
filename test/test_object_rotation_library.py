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

"""Tests for the Object Rotation library chooser wiring and chooser hygiene."""

import json
import unittest
from unittest.mock import patch

from common.metadata import MediaItem
from components.library import library_chooser_button as chooser
from pages import object_rotation as page


class ApplyLibrarySelectionTest(unittest.TestCase):
    def test_main_image_creates_project_for_owner(self):
        project = page.apply_library_selection(
            {}, page.MAIN_IMAGE_CHOOSER_ID, "gs://b/a.png", "me@example.com"
        )
        self.assertEqual(project["main_product_image_uri"], "gs://b/a.png")
        self.assertEqual(project["user_email"], "me@example.com")
        self.assertIn("timestamp", project)

    def test_main_image_keeps_existing_project(self):
        existing = {"user_email": "me@example.com", "product_description": "mug"}
        project = page.apply_library_selection(
            existing, page.MAIN_IMAGE_CHOOSER_ID, "gs://b/a.png", "other@example.com"
        )
        self.assertEqual(project["user_email"], "me@example.com")
        self.assertEqual(project["product_description"], "mug")

    def test_each_view_chooser_sets_only_its_view(self):
        project = {}
        for view, chooser_id in page.VIEW_CHOOSER_IDS.items():
            project = page.apply_library_selection(
                project, chooser_id, f"gs://b/{view}.png", "me@example.com"
            )
        self.assertEqual(
            project["product_views"],
            {v: f"gs://b/{v}.png" for v in page.VIEW_CHOOSER_IDS},
        )

    def test_empty_uri_is_ignored(self):
        self.assertIsNone(
            page.apply_library_selection(
                {}, page.MAIN_IMAGE_CHOOSER_ID, "", "me@example.com"
            )
        )

    def test_unknown_chooser_is_ignored(self):
        self.assertIsNone(
            page.apply_library_selection(
                {}, "step1_library_chooser", "gs://b/a.png", "me@example.com"
            )
        )


class PageWiringTest(unittest.TestCase):
    def test_chooser_ids_are_unique(self):
        ids = [page.MAIN_IMAGE_CHOOSER_ID, *page.VIEW_CHOOSER_IDS.values()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_state_has_no_media_item_list(self):
        # A bare ``list`` field holding MediaItems crashed Mesop state
        # deserialization ("'list' object has no attribute 'args'").
        fields = page.PageState.__dataclass_fields__
        self.assertNotIn("library_items", fields)
        self.assertNotIn("show_library", fields)


def _item(**kwargs) -> MediaItem:
    return MediaItem(**kwargs)


class ChooserItemsTest(unittest.TestCase):
    def test_selectable_gcs_uri(self):
        self.assertEqual(
            chooser.selectable_gcs_uri(_item(gcsuri="gs://b/a.png")), "gs://b/a.png"
        )
        self.assertEqual(
            chooser.selectable_gcs_uri(_item(gcs_uris=["gs://b/x.png"])),
            "gs://b/x.png",
        )
        self.assertIsNone(chooser.selectable_gcs_uri(_item()))
        self.assertIsNone(
            chooser.selectable_gcs_uri(
                _item(gcsuri="gs://b/a.png", error_message="boom")
            )
        )

    def test_load_filters_failed_items_and_warms_urls_once(self):
        items = [
            _item(id="ok1", gcsuri="gs://b/1.png"),
            _item(id="failed", error_message="boom"),
            _item(id="nouri"),
            _item(id="ok2", gcs_uris=["gs://b/2.png"]),
        ]
        with (
            patch.object(
                chooser, "get_media_for_page_optimized", return_value=(items, None)
            ) as fetch,
            patch.object(chooser, "warm_display_urls") as warm,
        ):
            result = chooser.load_chooser_items_json(["images"], None)

        fetch.assert_called_once()
        warm.assert_called_once_with(["gs://b/1.png", "gs://b/2.png"])
        self.assertEqual([d["id"] for d in json.loads(result)], ["ok1", "ok2"])


if __name__ == "__main__":
    unittest.main()
