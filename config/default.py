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

import json
import os
from dataclasses import dataclass, field
from typing import TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel

from common.identity import require_authenticated_user
from common.verified_identity import resolve_auth_mode, validate_identity_config

load_dotenv(override=True)


# Define ImageModel here
class ImageModel(TypedDict):
    """Defines Models For Image Generation."""

    display: str
    model_name: str


class NavItem(BaseModel):
    id: int
    display: str
    icon: str
    route: str | None = None
    group: str | None = None
    align: str | None = None
    feature_flag: str | None = None
    feature_flag_not: str | None = None
    description: str | None = None
    video_url: str | None = None
    video_object_position: str | None = None


class NavConfig(BaseModel):
    pages: list[NavItem]


@dataclass
class Default:
    """Defaults class."""

    VERSION: str = "1.13.1"  # Fallback if package metadata is missing
    BUILD_COMMIT: str = ""
    BUILD_DATE: str = ""

    APP_ENV: str = os.environ.get("APP_ENV", "")
    REQUIRE_AUTHENTICATED_USER: bool = require_authenticated_user(APP_ENV)
    # Identity source mode, derived from APP_ENV (not an operator boolean):
    # deployed envs verify the IAP assertion; local envs use a mock identity.
    AUTH_MODE: str = resolve_auth_mode(APP_ENV)
    # Per-env IAP JWT audience (opaque, infra-owned). Required in iap mode; the
    # literal value is never hardcoded. Startup validation enforces its presence.
    IAP_JWT_AUDIENCE: str = os.environ.get("IAP_JWT_AUDIENCE", "")
    API_BASE_URL: str = os.environ.get(
        "API_BASE_URL",
        f"http://localhost:{os.environ.get('PORT', '8080')}",
    )

    SERVICE_ACCOUNT_EMAIL: str = os.environ.get("SERVICE_ACCOUNT_EMAIL")
    # Gemini
    PROJECT_ID: str = os.environ.get("PROJECT_ID")
    LOCATION: str = os.environ.get("LOCATION", "us-central1")
    # Centralized Vertex AI API version for all google-genai client inits.
    # Defaults to "v1beta1" (the google-genai SDK default for Vertex AI) so the
    # effective behavior is unchanged; override via VERTEX_API_VERSION to switch
    # the API surface in one place.
    VERTEX_API_VERSION: str = os.environ.get("VERTEX_API_VERSION", "v1beta1")
    # Gemini 3.x models are not served from single regions such as us-central1 —
    # only from the global endpoint (and the us/eu multi-regions). LOCATION stays
    # regional because Veo/Imagen/Lyria/VTO and the Cloud Tasks queue need it.
    GEMINI_LOCATION: str = os.environ.get("GEMINI_LOCATION", "global")
    GEMINI_TTS_LOCATION: str = os.environ.get("GEMINI_TTS_LOCATION", "global")
    GA_MEASUREMENT_ID: str = os.environ.get("GA_MEASUREMENT_ID")
    MODEL_ID: str = os.environ.get("MODEL_ID", "gemini-3.5-flash")
    INIT_VERTEX: bool = True
    GEMINI_IMAGE_GEN_MODEL: str = os.environ.get(
        "GEMINI_IMAGE_GEN_MODEL",
        "gemini-nano-banana-2.1",
    )
    GEMINI_IMAGE_GEN_LOCATION: str = os.environ.get(
        "GEMINI_IMAGE_GEN_LOCATION",
        "global",
    )
    GEMINI_IMAGE_GEN_API_BASE_URL: str | None = os.environ.get(
        "GEMINI_IMAGE_GEN_API_BASE_URL",
    )

    GEMINI_AUDIO_ANALYSIS_MODEL_ID: str = os.environ.get(
        "GEMINI_AUDIO_ANALYSIS_MODEL_ID",
        "gemini-3.1-flash-lite",
    )
    GEMINI_WRITERS_WORKSHOP_MODEL_ID: str = os.environ.get(
        "GEMINI_WRITERS_WORKSHOP_MODEL_ID",
        MODEL_ID,
    )
    GEMINI_CRITIQUE_MODEL_ID: str = os.environ.get(
        "GEMINI_CRITIQUE_MODEL_ID",
        "gemini-3-flash-preview",
    )
    GEMINI_CRITIQUE_LOCATION: str = os.environ.get(
        "GEMINI_CRITIQUE_LOCATION",
        "global",
    )

    # Collections
    GENMEDIA_FIREBASE_DB: str = os.environ.get("GENMEDIA_FIREBASE_DB", "(default)")
    GENMEDIA_COLLECTION_NAME: str = os.environ.get(
        "GENMEDIA_COLLECTION_NAME",
        "genmedia",
    )
    SESSIONS_COLLECTION_NAME: str = os.environ.get(
        "SESSIONS_COLLECTION_NAME",
        "sessions",
    )

    # storage
    GENMEDIA_BUCKET: str = os.environ.get("GENMEDIA_BUCKET", f"{PROJECT_ID}-assets")
    VIDEO_BUCKET: str = os.environ.get("VIDEO_BUCKET", f"{PROJECT_ID}-assets/videos")
    IMAGE_BUCKET: str = os.environ.get("IMAGE_BUCKET", f"{PROJECT_ID}-assets/images")
    GCS_ASSETS_BUCKET: str = os.environ.get("GCS_ASSETS_BUCKET")

    # Library
    LIBRARY_MEDIA_PER_PAGE: int = int(os.environ.get("LIBRARY_MEDIA_PER_PAGE", 15))

    # Veo
    DEFAULT_VEO_MODEL_NAME: str = os.environ.get(
        "DEFAULT_VEO_MODEL_NAME",
        "veo-3.1-fast-generate-001",
    )
    VEO_LOCATION: str = os.environ.get("VEO_LOCATION", "us-central1")
    PREVIEW_LOCATION: str = os.environ.get("PREVIEW_LOCATION", "global")

    VEO_MODEL_ID: str = os.environ.get("VEO_MODEL_ID", "veo-3.1-fast-generate-001")
    VEO_PROJECT_ID: str = os.environ.get("VEO_PROJECT_ID", PROJECT_ID)

    VEO_EXP_MODEL_ID: str = os.environ.get(
        "VEO_EXP_MODEL_ID",
        "veo-3.1-generate-001",
    )
    VEO_EXP_FAST_MODEL_ID: str = os.environ.get(
        "VEO_EXP_FAST_MODEL_ID",
        "veo-3.1-fast-generate-001",
    )
    VEO_EXP_PROJECT_ID: str = os.environ.get("VEO_EXP_PROJECT_ID", PROJECT_ID)

    # Gemini Omni
    DEFAULT_OMNI_MODEL_NAME: str = os.environ.get(
        "DEFAULT_OMNI_MODEL_NAME",
        "gemini-omni-1.1-flash-preview",
    )
    OMNI_LOCATION: str = os.environ.get("OMNI_LOCATION", "global")
    OMNI_MODEL_ID: str = os.environ.get(
        "OMNI_MODEL_ID", "gemini-omni-1.1-flash-preview"
    )
    OMNI_PROJECT_ID: str = os.environ.get("OMNI_PROJECT_ID", PROJECT_ID)
    OMNI_TIMEOUT_MS: int = int(os.environ.get("OMNI_TIMEOUT_MS", "600000"))

    # VTO
    VTO_LOCATION: str = os.environ.get("VTO_LOCATION", "us-central1")
    VTO_MODEL_ID: str = os.environ.get("VTO_MODEL_ID", "virtual-try-on-001")
    GENMEDIA_VTO_MODEL_COLLECTION_NAME: str = os.environ.get(
        "GENMEDIA_VTO_MODEL_COLLECTION_NAME",
        "genmedia-vto-model",
    )
    GENMEDIA_VTO_CATALOG_COLLECTION_NAME: str = os.environ.get(
        "GENMEDIA_VTO_CATALOG_COLLECTION_NAME",
        "genmedia-vto-catalog",
    )

    # Temperatures for Character Consistency Workflow
    # Low temp for factual, structured output. Increasing may break JSON parsing.
    TEMP_FORENSIC_ANALYSIS: float = 0.1
    # Low temp for direct, non-creative translation of data to text.
    TEMP_DESCRIPTION_TRANSLATION: float = 0.1
    # Mid-range temp for creative but controlled prompt engineering.
    TEMP_SCENE_GENERATION: float = 0.3
    # Low temp for analytical comparison and structured JSON output.
    TEMP_BEST_IMAGE_SELECTION: float = 0.2

    # Character Consistency
    # NOTE: CHARACTER_CONSISTENCY_IMAGEN_MODEL ("imagen-3.0-capability-001") was
    # removed for the 2026-06-30 GA sunset. The Character Consistency edit steps
    # (subject customization + 16:9 reframe) were ported to the prompt-based
    # Gemini Image (Nano Banana) adapter, which uses GEMINI_IMAGE_GEN_MODEL.
    CHARACTER_CONSISTENCY_VEO_MODEL: str = os.environ.get(
        "CHARACTER_CONSISTENCY_VEO_MODEL",
        "veo-3.1-fast-generate-001",
    )
    CHARACTER_CONSISTENCY_GEMINI_MODEL: str = os.environ.get(
        "CHARACTER_CONSISTENCY_GEMINI_MODEL",
        MODEL_ID,
    )
    CHARACTER_CONSISTENCY_GEMINI_LOCATION: str = os.environ.get(
        "CHARACTER_CONSISTENCY_GEMINI_LOCATION",
        "global",
    )

    # Lyria
    LYRIA_LOCATION: str = os.environ.get("LYRIA_LOCATION", "us-central1")
    LYRIA_MODEL_VERSION: str = os.environ.get("LYRIA_MODEL_VERSION", "lyria-002")
    LYRIA_PROJECT_ID: str = os.environ.get("LYRIA_PROJECT_ID", PROJECT_ID)
    MEDIA_BUCKET: str = os.environ.get("MEDIA_BUCKET", f"{PROJECT_ID}-assets")

    # Imagen
    MODEL_IMAGEN4 = "imagen-4.0-generate-001"
    MODEL_IMAGEN4_FAST = "imagen-4.0-fast-generate-001"
    MODEL_IMAGEN4_ULTRA = "imagen-4.0-ultra-generate-001"

    IMAGEN_GENERATED_SUBFOLDER: str = os.environ.get(
        "IMAGEN_GENERATED_SUBFOLDER",
        "generated_images",
    )
    IMAGEN_EDITED_SUBFOLDER: str = os.environ.get(
        "IMAGEN_EDITED_SUBFOLDER",
        "edited_images",
    )

    IMAGEN_PROMPTS_JSON = "prompts/imagen_prompts.json"

    USE_MEDIA_PROXY: bool = os.environ.get("USE_MEDIA_PROXY", "true").lower() == "true"

    # Interior Design
    INTERIOR_DESIGN_VIDEO_MODEL: str = os.environ.get(
        "INTERIOR_DESIGN_VIDEO_MODEL",
        "veo-3.1-lite-generate-001",
    )
    INTERIOR_DESIGN_IMAGE_MODEL: str = os.environ.get(
        "INTERIOR_DESIGN_IMAGE_MODEL",
        "gemini-3-pro-image",
    )
    INTERIOR_DESIGN_VIDEO_DURATION: int = int(
        os.environ.get("INTERIOR_DESIGN_VIDEO_DURATION", 6),
    )

    # Object Rotation
    # Feature flag for the Object Rotation ("Edit Images") workflow. It is
    # referenced by config/navigation.json (to gate the nav entry) and by
    # main.py (to gate the /object-rotation route). Disabled by default per
    # product decision: the Object Rotation page is not exposed.
    #
    # Previously this flag was referenced but never defined, so the navigation
    # lookup `getattr(Default, "EDIT_IMAGES_ENABLED", False)` fell back to False
    # and the page was hidden only implicitly. Defining it here makes that intent
    # explicit while still allowing an operator to opt in via the environment.
    EDIT_IMAGES_ENABLED: bool = (
        os.environ.get("EDIT_IMAGES_ENABLED", "false").lower() == "true"
    )

    OBJECT_ROTATION_VIDEO_MODEL: str = os.environ.get(
        "OBJECT_ROTATION_VIDEO_MODEL",
        "veo-3.1-generate-001",
    )
    OBJECT_ROTATION_IMAGE_MODEL: str = os.environ.get(
        "OBJECT_ROTATION_IMAGE_MODEL",
        "gemini-3.1-flash-image",
    )

    image_modifiers: list[str] = field(
        default_factory=lambda: [
            "aspect_ratio",
            "content_type",
            "color_tone",
            "lighting",
            "composition",
        ],
    )


def get_config_path(rel_path: str) -> str:
    """Returns the path to a configuration file, respecting GMCS_OVERRIDE_PATH."""
    override_base = os.environ.get("GMCS_OVERRIDE_PATH")
    if override_base:
        override_path = os.path.join(override_base, rel_path)
        if os.path.exists(override_path):
            return override_path
    return rel_path


import importlib.metadata


def load_package_version() -> None:
    try:
        Default.VERSION = importlib.metadata.version(
            "vertex-ai-genmedia-creative-studio",
        )
    except importlib.metadata.PackageNotFoundError:
        pass  # Keep default


def load_build_info() -> None:
    """Loads build information from config/build.json if it exists."""
    path = get_config_path("config/build.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
                Default.BUILD_COMMIT = data.get("commit", "unknown")
                Default.BUILD_DATE = data.get("date", "unknown")
        except (FileNotFoundError, json.JSONDecodeError):
            pass


load_package_version()
load_build_info()

# Fail fast at startup on a misconfigured deployed env (AUTH_MODE=iap with no
# IAP_JWT_AUDIENCE). No-op in local mode.
validate_identity_config()


def get_welcome_page_config():
    path = get_config_path("config/navigation.json")
    with open(path) as f:
        data = json.load(f)

    # This will raise a validation error if the JSON is malformed
    config = NavConfig(**data)

    def is_feature_enabled(page: NavItem):
        if page.feature_flag:
            return bool(getattr(Default, page.feature_flag, False))
        if page.feature_flag_not:
            return not bool(getattr(Default, page.feature_flag_not, False))
        return True

    filtered_pages = [
        page.model_dump(exclude_none=True)
        for page in config.pages
        if is_feature_enabled(page)
    ]

    return sorted(filtered_pages, key=lambda x: x["id"])


def load_about_page_config():
    config_path = get_config_path("config/about_content.json")
    if not os.path.exists(config_path):
        return None

    try:
        with open(config_path) as f:
            content = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    # The rest of the function that processes GCS URLs remains the same
    bucket_name = Default.GCS_ASSETS_BUCKET
    if not bucket_name:
        return content

    base_url = f"https://storage.googleapis.com/{bucket_name}"

    for section in content.get("sections", []):
        if section.get("image"):
            section["image"] = f"{base_url}/{section['image']}"
        if section.get("video"):
            section["video"] = f"{base_url}/{section['video']}"

    return content


ABOUT_PAGE_CONTENT = load_about_page_config()
