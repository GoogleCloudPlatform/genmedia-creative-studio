# Copyright 2025 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import base64
import concurrent.futures
import io
import json
import re
import threading
import time
from typing import Any
import datetime

from absl import logging
from PIL import Image
import google.auth
from google.cloud import storage
from google.auth import impersonated_credentials

import os

from config.default import Default as cfg


def _unsigned_display_url(gcs_uri: str) -> str:
    """Return the plain (unsigned) storage.cloud.google.com link for a gs:// URI."""
    return gcs_uri.replace("gs://", "https://storage.cloud.google.com/")


# --- Cached V4 signed display URLs -----------------------------------------
#
# Signing through an impersonated service account costs an IAM ``signBlob``
# round trip per URL, and building the credentials/storage client is slow too.
# Both are therefore created once per process, and the resulting URLs are cached
# for slightly less than their lifetime so that every Mesop re-render (and the
# browser HTTP cache) sees the exact same URL for an asset.
DISPLAY_URL_VALID_MINUTES = 60
DISPLAY_URL_CACHE_TTL_SECONDS = 50 * 60
# A failed signing attempt falls back to the unsigned link; remember the failure
# briefly so a misconfigured environment is not retried on every render.
DISPLAY_URL_FAILURE_TTL_SECONDS = 60
DISPLAY_URL_CACHE_MAX_ENTRIES = 5000
DISPLAY_URL_WARM_MAX_WORKERS = 8
_SIGNING_SCOPES = ["https://www.googleapis.com/auth/devstorage.read_only"]

_display_url_cache: dict[tuple[str, str], tuple[str, float]] = {}
_display_url_cache_lock = threading.Lock()
_signing_resources: dict[str, tuple[storage.Client, Any]] = {}
_signing_resources_lock = threading.Lock()


def _now() -> float:
    """Monotonic clock used for cache expiry (patched in tests)."""
    return time.monotonic()


def _get_signing_resources(service_account_email: str) -> tuple[storage.Client, Any]:
    """Return the process-wide (storage client, signing credentials) pair.

    Created once per ``service_account_email`` and reused for every signature.
    """
    with _signing_resources_lock:
        resources = _signing_resources.get(service_account_email)
        if resources is None:
            source_credentials, _ = google.auth.default()
            signing_credentials = impersonated_credentials.Credentials(
                source_credentials=source_credentials,
                target_principal=service_account_email,
                target_scopes=_SIGNING_SCOPES,
            )
            resources = (storage.Client(), signing_credentials)
            _signing_resources[service_account_email] = resources
        return resources


def _prune_display_url_cache(now: float) -> None:
    """Bounds the cache: drops expired entries, then the oldest if still full."""
    for key in [k for k, (_, expires) in _display_url_cache.items() if expires <= now]:
        del _display_url_cache[key]
    overflow = len(_display_url_cache) - DISPLAY_URL_CACHE_MAX_ENTRIES
    if overflow > 0:
        oldest = sorted(_display_url_cache, key=lambda k: _display_url_cache[k][1])
        for key in oldest[:overflow]:
            del _display_url_cache[key]


def _cached_display_url(key: tuple[str, str]) -> str | None:
    with _display_url_cache_lock:
        entry = _display_url_cache.get(key)
    if entry and entry[1] > _now():
        return entry[0]
    return None


def get_signed_display_url(gcs_uri: str) -> str:
    """Return a cached V4 signed GET URL for a ``gs://`` URI.

    Signs as ``SERVICE_ACCOUNT_EMAIL`` and caches the URL for
    ``DISPLAY_URL_CACHE_TTL_SECONDS``. If signing fails (for example locally,
    without impersonation rights) it logs a warning and falls back to the
    unsigned link, so rendering never breaks.
    """
    service_account_email = cfg().SERVICE_ACCOUNT_EMAIL or ""
    key = (service_account_email, gcs_uri)
    cached = _cached_display_url(key)
    if cached:
        return cached

    try:
        bucket_name, _, blob_name = gcs_uri.removeprefix("gs://").partition("/")
        client, signing_credentials = _get_signing_resources(service_account_email)
        url = client.bucket(bucket_name).blob(blob_name).generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=DISPLAY_URL_VALID_MINUTES),
            method="GET",
            credentials=signing_credentials,
        )
        ttl = DISPLAY_URL_CACHE_TTL_SECONDS
    except Exception as e:  # noqa: BLE001 - never break rendering over signing
        logging.warning("Could not sign display URL for %s: %s", gcs_uri, e)
        url = _unsigned_display_url(gcs_uri)
        ttl = DISPLAY_URL_FAILURE_TTL_SECONDS

    now = _now()
    with _display_url_cache_lock:
        _display_url_cache[key] = (url, now + ttl)
        if len(_display_url_cache) > DISPLAY_URL_CACHE_MAX_ENTRIES:
            _prune_display_url_cache(now)
    return url


def warm_display_urls(gcs_uris: list[str | None]) -> None:
    """Pre-signs not-yet-cached display URLs in parallel.

    A page of results would otherwise sign each asset serially (one IAM round
    trip each). This is a no-op when signed URLs are not in use.
    """
    cfg_ = cfg()
    if cfg_.USE_MEDIA_PROXY or not cfg_.SERVICE_ACCOUNT_EMAIL:
        return
    email = cfg_.SERVICE_ACCOUNT_EMAIL
    pending = list(
        dict.fromkeys(
            uri
            for uri in gcs_uris
            if uri
            and uri.startswith("gs://")
            and _cached_display_url((email, uri)) is None
        ),
    )
    if not pending:
        return
    # Create the shared client/credentials once, before the workers race for it.
    try:
        _get_signing_resources(email)
    except Exception as e:  # noqa: BLE001
        logging.warning("Could not initialize signing credentials: %s", e)
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(DISPLAY_URL_WARM_MAX_WORKERS, len(pending)),
    ) as pool:
        list(pool.map(get_signed_display_url, pending))


def create_display_url(gcs_uri: str) -> str:
    """
    Creates a cacheable display URL for a GCS asset.

    * ``USE_MEDIA_PROXY=true``: the app's ``/media`` proxy path.
    * otherwise, with ``SERVICE_ACCOUNT_EMAIL`` configured: a cached V4 signed
      ``storage.googleapis.com`` URL, so users who cannot be granted bucket
      access (for example cross-tenant IAP users) can still load the asset.
    * otherwise: the plain ``storage.cloud.google.com`` link.
    """
    if not gcs_uri or not gcs_uri.startswith("gs://"):
        return ""

    cfg_ = cfg()
    if cfg_.USE_MEDIA_PROXY:
        # Use the fast, simple proxy URL
        proxy_path = gcs_uri.replace("gs://", "")
        return f"/media/{proxy_path}"
    if cfg_.SERVICE_ACCOUNT_EMAIL:
        return get_signed_display_url(gcs_uri)
    # Use the direct GCS URL
    return _unsigned_display_url(gcs_uri)




def extract_username(email_string: str | None) -> str:
    """Extracts the username from an email-like string.

    Args:
        email_string: The string containing the username and domain.

    Returns:
        The extracted username, or None if no valid username is found.
    """
    if email_string:
        match = re.search(
            r":([^@]+)@", email_string
        )  # Matches anything between ":" and "@"
        if match:
            return match.group(1)
    return "Anonymous"


def get_image_dimensions_from_base64(base64_string: str) -> tuple[int, int]:
    """Retrieves the width and height of an image from a base64 encoded string.

    Args:
        base64_string: The base64 encoded image data.

    Returns:
        A tuple (width, height) if successful, or None if an error occurs.
    """
    try:
        # Remove the data URL prefix if it exists.
        if base64_string.startswith("data:image"):
            parts = base64_string.split(",")
            if len(parts) > 1:
                base64_string = parts[1]

        image_data = base64.b64decode(base64_string)
        image_stream = io.BytesIO(image_data)
        img = Image.open(image_stream)
        width, height = img.size
        return width, height
    except Exception as e:
        logging.info(f"App: Error getting image dimensions: {e}")
        return None


def make_local_request(endpoint: str) -> dict[str, Any]:
    filepath = (
        f"mocks/{endpoint}.json"  # Assuming mock files are in a 'mocks' directory
    )
    try:
        with open(filepath) as f:
            return json.load(f)
    except FileNotFoundError:
        logging.info(f"Mock file not found: {filepath}")
        return None  # Or raise an exception
    
    
def print_keys(obj, prefix=""):
    """Recursively prints keys of a JSON object."""
    if obj is None:  # Base case: if obj is None, do nothing and return
        return
    if isinstance(obj, dict):
        for key in obj:
            print(prefix + key)
            print_keys(obj[key], prefix + "  ")  # Recurse with increased indentation
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            # For lists, we might want to indicate the index and then recurse on the item
            # If the item itself is a complex object.
            # If you only want to print keys of dicts within a list,
            # you might adjust the print statement here or what you pass to print_keys.
            # Current behavior: treats list items as potentially new objects to explore.
            print_keys(item, prefix + f"  [{i}] ")  # indicate list index in prefix

GCS_PUBLIC_URL_PREFIX = "https://storage.cloud.google.com/"

def _get_gcs_public_https_url(gcs_uri: str | None) -> str:
    """
    (Internal use only) Converts a GCS URI to a publicly accessible URL.
    This performs a simple string replacement and does NOT work for private objects.
    """
    if not gcs_uri:
        return ""
    if gcs_uri.startswith("https://"):
        return gcs_uri
    if gcs_uri.startswith("gs://"):
        return gcs_uri.replace("gs://", GCS_PUBLIC_URL_PREFIX)
    # Return as-is if it's not a recognized format
    return gcs_uri

def https_url_to_gcs_uri(url: str | None) -> str:
    """
    Converts a public GCS HTTPS URL (including signed URLs) back to a gs:// URI.
    """
    if not url:
        return ""
    if url.startswith("gs://"):
        return url

    # Handle local media proxy URLs
    if url.startswith("/media/"):
        return f"gs://{url.replace('/media/', '')}"

    # Take the base URL, stripping any query parameters from a signed URL
    url_to_convert = url.split("?")[0]

    if url_to_convert.startswith("https://storage.googleapis.com/"):
        return url_to_convert.replace("https://storage.googleapis.com/", "gs://")
    if url_to_convert.startswith(GCS_PUBLIC_URL_PREFIX):
        return url_to_convert.replace(GCS_PUBLIC_URL_PREFIX, "gs://")

    # If it's not a recognized GCS URL, return the original input as a fallback.
    return url


def get_media_type(mime_type: str | None = None, url: str | None = None) -> str:
    """Determines the media type (image, video, audio) based on mime_type or URL."""
    if mime_type:
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith("image/"):
            return "image"
        if mime_type.startswith("audio/"):
            return "audio"

    if url:
        url_lower = url.lower()
        if any(ext in url_lower for ext in [".mp4", ".webm", ".mov"]):
            return "video"
        if any(ext in url_lower for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
            return "image"
        if any(ext in url_lower for ext in [".wav", ".mp3", ".ogg"]):
            return "audio"

    return "image"  # Default fallback
