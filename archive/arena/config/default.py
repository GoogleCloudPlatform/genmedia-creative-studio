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
""" Default Configuration for GenMedia Arena """

import json
import os
from dataclasses import asdict, dataclass, field
from dotenv import load_dotenv

load_dotenv(override=True)

@dataclass
class GeminiModelConfig:
    """Configuration specific to Gemini models"""


@dataclass
class Default:
    """All configuration variables for this application are managed here."""

    # pylint: disable=invalid-name
    PROJECT_ID: str = os.environ.get("PROJECT_ID")
    LOCATION: str = os.environ.get("LOCATION", "us-central1")
    MODEL_ID: str = os.environ.get("MODEL_ID", "gemini-3.5-flash")
    INIT_VERTEX: bool = os.environ.get("INIT_VERTEX", "True").lower() in ("true", "1")

    GENMEDIA_BUCKET: str = os.environ.get("GENMEDIA_BUCKET")
    PUBLIC_BUCKET: bool = os.environ.get("PUBLIC_BUCKET", "False").lower() in ("true", "1")
    SHOW_RESULTS_PAUSE_TIME: int = int(os.environ.get("SHOW_RESULTS_PAUSE_TIME", "1"))
    IMAGE_FIREBASE_DB: str = os.environ.get("IMAGE_FIREBASE_DB")
    IMAGE_COLLECTION_NAME = os.environ.get("IMAGE_COLLECTION_NAME")
    STUDY_COLLECTION_NAME: str = os.environ.get("STUDY_COLLECTION_NAME", "arena_study")
    IMAGE_RATINGS_COLLECTION_NAME: str = os.environ.get("IMAGE_RATINGS_COLLECTION_NAME", "arena_elo")
    STABLE_DIFFUSION_DB_PROMPTS: str = os.environ.get("STABLE_DIFFUSION_DB_PROMPTS", "prompts/stable_diffusion_prompts.json")
    DEFAULT_PROMPTS: str = os.environ.get("DEFAULT_PROMPTS", "prompts/imagen_prompts.json")
    DEFAULT_STUDY_NAME: str = os.environ.get("DEFAULT_STUDY_NAME", "live")
    ELO_K_FACTOR: int = int(os.environ.get("ELO_K_FACTOR", 32))

    # Comma-separated allowlist of admin emails authorized to perform destructive
    # operations (e.g. resetting a study's ELO leaderboard). Empty by default so
    # the destructive purge fails closed. Consumed by common.authz (which reads
    # the ARENA_ADMIN_EMAILS environment variable directly). See common/authz.py.
    ARENA_ADMIN_EMAILS: str = os.environ.get("ARENA_ADMIN_EMAILS", "")

    # image models
    MODEL_IMAGEN2: str = "imagen-4.0-generate-001"
    MODEL_IMAGEN3_FAST: str = "imagen-4.0-fast-generate-001"
    MODEL_IMAGEN3: str = "imagen-4.0-generate-001"
    MODEL_IMAGEN32: str = "imagen-4.0-generate-001"

    MODEL_GEMINI2: str = "gemini-3.5-flash"

    # model garden image models
    MODEL_FLUX1: str = "black-forest-labs/flux1-schnell"
    MODEL_FLUX1_ENDPOINT_ID: str = os.environ.get("MODEL_FLUX1_ENDPOINT_ID")
    MODEL_STABLE_DIFFUSION: str = "stability-ai/stable-diffusion-2-1"
    MODEL_STABLE_DIFFUSION_ENDPOINT_ID: str = os.environ.get("MODEL_STABLE_DIFFUSION_ENDPOINT_ID")

    # Spanner related variables
    SPANNER_INSTANCE_ID: str = os.environ.get("SPANNER_INSTANCE_ID", "arena")
    SPANNER_DATABASE_ID: str = os.environ.get("SPANNER_DATABASE_ID", "study")
    SPANNER_TIMEOUT: int = int(os.environ.get("SPANNER_TIMEOUT", 300))  # seconds

    def __post_init__(self):
        """Validates the configuration variables after initialization."""

        if not self.PROJECT_ID:
            raise ValueError("PROJECT_ID environment variable is not set.")
        
        if not self.GENMEDIA_BUCKET:
            raise ValueError("GENMEDIA_BUCKET environment variable is not set.")

        if not self.MODEL_FLUX1_ENDPOINT_ID:
            print("MODEL_FLUX1_ENDPOINT_ID environment variable is not set. List of models will exclude flux1") # Optional: List of models will exclude flux1
        
        if not self.MODEL_STABLE_DIFFUSION_ENDPOINT_ID:
            print("MODEL_STABLE_DIFFUSION_ENDPOINT_ID environment variable is not set. List of models will exclude stable diffusion")

        if self.ELO_K_FACTOR <= 0:
            raise ValueError("ELO_K_FACTOR must be a positive integer.")

        if not self.IMAGE_FIREBASE_DB:
            raise ValueError("IMAGE_FIREBASE_DB environment variable is not set. Default will be used") 

        if not self.IMAGE_COLLECTION_NAME:
            raise ValueError("IMAGE_COLLECTION_NAME environment variable is not set.")

        valid_locations = ["us-central1", "us-east4", "europe-west4", "asia-east1"]  # example locations
        if self.LOCATION not in valid_locations:
            print(f"Warning: LOCATION {self.LOCATION} may not be valid.")
        print("Configuration validated successfully.")
    
    def __repr__(self):
        return f"Default({json.dumps(asdict(self), indent=4)})"

    # pylint: disable=invalid-name
