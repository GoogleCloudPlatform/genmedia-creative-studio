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

"""This module provides a client for interacting with the Google GenAI API.

It handles client initialization, authentication, and provides a wrapper for
content generation with automatic retries and logging.
"""

import base64
import logging
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai
from google.genai.types import GenerateContentConfig
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.default import Default

logger = logging.getLogger(__name__)
load_dotenv(override=True)


class LLMClient:
    """A wrapper around the Google GenAI client with retry logic and logging."""

    def __init__(self, project_id: Optional[str] = None, location: Optional[str] = None):
        """Initializes the LLMClient.

        Args:
            project_id: The Google Cloud project ID. If None, loads from config.
            location: The Google Cloud location. If None, loads from config.
        """
        config = Default()
        self.project_id = project_id or config.PROJECT_ID
        # Gemini calls use the dedicated GEMINI_LOCATION (default "global"),
        # decoupled from the Cloud Run / deployment region (LOCATION).
        self.location = location or config.GEMINI_LOCATION
        self.init_vertex = config.INIT_VERTEX

        if not self.project_id or not self.location:
            raise ValueError("Project ID and Location must be set in environment or passed explicitly.")

        logger.info(f"Initiating GenAI client with {self.project_id} in {self.location}")
        self.client = genai.Client(
            vertexai=self.init_vertex,
            project=self.project_id,
            location=self.location,
        )

    def _log_non_text_parts(self, response):
        """Logs any non-text parts (like thoughts) found in the Gemini response."""
        try:
            if not response.candidates:
                return
            for i, candidate in enumerate(response.candidates):
                if not candidate.content or not candidate.content.parts:
                    continue
                for j, part in enumerate(candidate.content.parts):
                    # Check for known non-text attributes that might be interesting
                    if hasattr(part, "thought") and part.thought:
                        logger.info(
                            f"Response Candidate {i}, Part {j} [THOUGHT]: {part.thought}"
                        )
                    elif hasattr(part, "thought_signature") and part.thought_signature:
                        signature = part.thought_signature
                        if isinstance(signature, bytes):
                            signature = base64.b64encode(signature).decode("utf-8")
                        logger.info(
                            f"Response Candidate {i}, Part {j} [THOUGHT_SIGNATURE]: {signature[:100]}..."
                        )
                    elif not part.text:
                        # Fallback for other non-text parts (function calls, etc.)
                        logger.info(f"Response Candidate {i}, Part {j} [NON-TEXT]: {part}")
        except Exception as e:
            logger.warning(f"Error logging non-text parts: {e}")

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def generate_content(
        self,
        model: str,
        contents: str,
        config: GenerateContentConfig,
        log_success_msg: str = "Gemini content generation successful",
    ) -> Any:
        """Generates content using the GenAI client with retry logic.

        Args:
            model: The model ID to use.
            contents: The prompt content.
            config: The generation configuration.
            log_success_msg: Message to log upon success.

        Returns:
            The response from the model.
        """
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            self._log_non_text_parts(response)
            # Log a snippet of the text if available
            text_snippet = response.text[:100] if response.text else "(no text)"
            logger.info(f"{log_success_msg}: {text_snippet}...")
            return response
        except Exception as e:
            logger.error(f"Error during Gemini call ({log_success_msg}): {e}")
            raise
