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

import mesop as me

@me.stateclass
class PageState:
    """Character Sheet Page State"""
    
    # Input
    original_image_gcs_uri: str = ""
    original_image_display_url: str = ""
    scenario_prompt: str = ""
    
    # Asset Sheet Generation
    sheet_preset_id: str = "turnaround"
    character_description: str = ""
    custom_prompt: str = ""
    is_generating_sheet: bool = False
    asset_sheet_gcs_uri: str = ""
    asset_sheet_display_url: str = ""
    
    # Scenario Generation
    is_generating_scenario: bool = False
    scenario_image_gcs_uri: str = ""
    scenario_image_display_url: str = ""
    
    # UI
    show_snackbar: bool = False
    snackbar_message: str = ""
    info_dialog_open: bool = False
