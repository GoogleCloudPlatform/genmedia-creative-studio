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

"""Pydantic models for the prompt health checklist."""

from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field, ValidationError


class ChecklistItemDetail(BaseModel):
    """Represents the details of a single checklist item."""

    score: bool
    explanation: Optional[str] = None


class IssueDetail(BaseModel):
    """Represents the structured details of an identified issue."""

    issue_name: str
    location_in_prompt: str
    rationale: str


class CategoryData(BaseModel):
    """Represents the data for a single category in the checklist."""

    items: Dict[str, bool] = Field(default_factory=dict)
    details: Optional[Dict[str, Union[IssueDetail, str]]] = (
        None  # Can hold structured issue details or simple string explanations
    )
    explanation: Optional[str] = None  # For overall category explanation

    @classmethod
    def parse_category_data(cls, data: Dict[str, Any]) -> "CategoryData":
        """Parses a dictionary into a CategoryData object.

        Args:
            data: The dictionary to parse.

        Returns:
            A CategoryData object.
        """
        items = {}
        details_dict = {}  # Initialize as an empty dict
        category_explanation_str = None

        if isinstance(data, dict):
            # Correctly parse nested items
            raw_items = data.get("items")
            if isinstance(raw_items, dict):
                for key, value in raw_items.items():
                    if isinstance(value, bool):
                        items[key] = value

            raw_details = data.get("details")
            if isinstance(raw_details, dict):
                for key, value in raw_details.items():
                    if isinstance(value, dict):
                        try:
                            # Attempt to parse as a structured IssueDetail
                            details_dict[key] = IssueDetail(**value)
                        except ValidationError:
                            # If it fails, treat it as a plain string (or handle error appropriately)
                            details_dict[key] = str(value)
                    else:
                        # Keep it as a string if it's not a dictionary
                        details_dict[key] = str(value)

            category_explanation_str = data.get("explanation")
            if not isinstance(category_explanation_str, str):
                category_explanation_str = None

        return cls(
            items=items,
            details=details_dict if details_dict else None,
            explanation=category_explanation_str,
        )


class ParsedChecklistResponse(BaseModel):
    """Represents the entire checklist response."""

    categories: Dict[str, CategoryData] = Field(default_factory=dict)

    @classmethod
    def from_json_dict(cls, json_dict: Dict[str, Any]) -> "ParsedChecklistResponse":
        """Creates a ParsedChecklistResponse from a JSON dictionary.

        Args:
            json_dict: The JSON dictionary to parse.

        Returns:
            A ParsedChecklistResponse object.
        """
        parsed_categories = {}
        for cat_name, cat_data in json_dict.items():
            if isinstance(cat_data, dict):
                parsed_categories[cat_name] = CategoryData.parse_category_data(cat_data)
            else:
                # Handle cases where a category might not be a dict as expected
                # We might want to log this warning in a real app
                parsed_categories[cat_name] = CategoryData()  # empty category
        return cls(categories=parsed_categories)
