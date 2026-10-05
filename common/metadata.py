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
"""metadata implementation"""

import datetime
import json
import uuid

# from models.model_setup import ModelSetup
from dataclasses import asdict, dataclass, field

from google.cloud import firestore

from common import authz
from common.analytics import get_logger
from config.default import Default
from config.firebase_config import FirebaseClient

# Initialize configuration
# client, model_id = ModelSetup.init()
# MODEL_ID = model_id
config = Default()
db = FirebaseClient(database_id=config.GENMEDIA_FIREBASE_DB).get_client()
logger = get_logger(__name__)


@dataclass
class MediaItem:
    """Represents a single media item in the library for Firestore storage and retrieval."""

    id: str | None = None  # Firestore document ID
    status: str = (
        "created"  # Options: "created", "pending", "processing", "complete", "failed"
    )
    related_media_item_id: str | None = None  # For linking generation sequences
    user_email: str | None = None
    timestamp: datetime.datetime | None = None  # Store as datetime object

    # Common fields across media types
    prompt: str | None = None  # The final prompt used for generation
    original_prompt: str | None = None  # User's initial prompt if rewriting occurred
    rewritten_prompt: str | None = (
        None  # The prompt after any rewriter (Gemini, etc.)
    )
    model: str | None = (
        None  # Specific model ID used (e.g., "imagen-3.0-fast", "veo-2.0")
    )
    mime_type: str | None = None  # e.g., "video/mp4", "image/png", "audio/wav"
    generation_time: float | None = None  # Seconds for generation
    error_message: str | None = None  # If any error occurred during generation
    mode: str | None = None

    # URI fields
    gcsuri: str | None = (
        None  # For single file media (video, audio) -> gs://bucket/path
    )
    gcs_uris: list[str] = field(
        default_factory=list,
    )  # For multi-file media (e.g., multiple images) -> list of gs://bucket/path
    source_images_gcs: list[str] = field(
        default_factory=list,
    )  # For multi-file input media (e.g., recontext) -> list of gs://bucket/path
    source_uris: list[str] = field(
        default_factory=list,
    )  # For generic source media of any type (e.g., Pixie compositor)
    thumbnail_uri: str | None = None

    # Video specific (some may also apply to Image/Audio)
    aspect: str | None = None  # e.g., "16:9", "1:1" (also for Image)
    resolution: str | None = None  # e.g., "720p", "1080p"
    duration: float | None = None  # Seconds (also for Audio)
    reference_image: str | None = None
    last_reference_image: str | None = None
    negative_prompt: str | None = None
    enhanced_prompt_used: bool = False
    comment: str | None = (
        None  # General comment field, e.g., for video generation type
    )

    # Image specific
    # aspect is shared with Video
    modifiers: list[str] = field(
        default_factory=list,
    )  # e.g., ["photorealistic", "wide angle"]
    captions: list[str] = field(
        default_factory=list,
    )  # Captions or narrative text associated with generated images
    negative_prompt: str | None = None
    num_images: int | None = None  # Number of images generated in a batch
    seed: int | None = (
        None  # Seed used for generation (also potentially for video/audio)
    )
    critique: str | None = None  # Gemini-generated critique for images
    grounding_info: str | None = (
        None  # Grounding metadata from search, stored as JSON string
    )

    # Music specific
    # duration is shared with Video
    audio_analysis: str | None = (
        None  # Structured analysis from Gemini, stored as a JSON string
    )
    generated_text: list[str] = field(default_factory=list)

    # This field is for loading raw data from Firestore, not for writing.
    # It helps in debugging and displaying all stored fields if needed.
    raw_data: dict | None = field(default_factory=dict, compare=False, repr=False)

    # Character Consistency specific fields
    media_type: str | None = None
    source_character_images: list[str] = field(default_factory=list)
    character_description: str | None = None
    imagen_prompt: str | None = None
    veo_prompt: str | None = None
    candidate_images: list[str] = field(default_factory=list)
    best_candidate_image: str | None = None
    outpainted_image: str | None = None

    # Chirp and Gemini-TTS specific fields
    custom_pronunciations: list[dict[str, str]] = field(default_factory=list)
    voice: str | None = None
    pace: float | None = None
    volume_gain_db: float | None = None
    language_code: str | None = None
    style_prompt: str | None = None

    # Interior Design Storyboard
    storyboard_id: str | None = None

    # Object Rotation
    object_rotation_project_id: str | None = None

    # R2V specific
    r2v_reference_images: list[str] = field(default_factory=list)
    r2v_style_image: str | None = None

    # VTO specific
    person_image_gcs: str | None = None
    product_image_gcs: str | None = None

    # Upscale specific
    original_resolution: str | None = None
    upscale_factor: str | None = None
    image_size: str | None = None

    def __post_init__(self):
        # Ensure audio_analysis is always a JSON string for state serialization.
        # This handles cases where raw data from Firestore might be a dict.
        if isinstance(self.audio_analysis, dict):
            self.audio_analysis = json.dumps(self.audio_analysis)
        if isinstance(self.grounding_info, dict):
            self.grounding_info = json.dumps(self.grounding_info)


def add_media_item_to_firestore(item: MediaItem):
    """Creates or updates a MediaItem in Firestore.
    If item.id is None, a new document is created with a Firestore-generated ID.
    If item.id is provided, the existing document with that ID is updated.
    """
    if not db:
        logger.warning(
            "Firestore client (db) is not initialized. Cannot add media item.",
        )
        return

    # Prepare data for Firestore using asdict
    firestore_data = asdict(item)

    # Ensure timestamp is handled correctly
    if "timestamp" not in firestore_data or firestore_data["timestamp"] is None:
        firestore_data["timestamp"] = datetime.datetime.now(datetime.UTC)
    elif isinstance(firestore_data["timestamp"], str):
        try:
            firestore_data["timestamp"] = datetime.datetime.fromisoformat(
                firestore_data["timestamp"].replace("Z", "+00:00"),
            )
        except ValueError:
            logger.warning(
                f"Could not parse timestamp string '{firestore_data['timestamp']}'. Setting to now().",
            )
            firestore_data["timestamp"] = datetime.datetime.now(datetime.UTC)

    # Server-side authorization: the caller must own an item they overwrite, and
    # a newly created item must be attributed to the server-derived caller.
    caller = authz.resolve_caller_email(fallback=item.user_email)

    try:
        if item.id:
            # If an ID is provided, update the existing document
            doc_ref = db.collection(config.GENMEDIA_COLLECTION_NAME).document(item.id)
            authz.authorize_existing_document(
                doc_ref,
                "user_email",
                caller,
                resource="media item",
            )
            # We can remove the 'id' field before setting, as it's the doc's name
            if "id" in firestore_data:
                del firestore_data["id"]
            doc_ref.set(firestore_data, merge=True)  # Use merge=True to update fields
            logger.info(
                f"Successfully updated MediaItem in Firestore with ID: {item.id}",
            )
        else:
            # If no ID is provided, create a new document
            authz.authorize_attribution(
                item.user_email,
                caller,
                resource="media item",
            )
            doc_ref = db.collection(config.GENMEDIA_COLLECTION_NAME).document()
            if "id" in firestore_data:
                del firestore_data["id"]
            doc_ref.set(firestore_data)
            # Set the new Firestore-generated ID back on the object
            item.id = doc_ref.id
            logger.info(
                f"Successfully created MediaItem in Firestore with new ID: {item.id}",
            )

    except Exception as e:
        logger.error(f"CRITICAL: Failed to save MediaItem to Firestore. Error: {e}")
        raise e


def save_storyboard(storyboard: dict) -> dict:
    """Creates or updates an InteriorDesignStoryboard document in Firestore.

    Args:
        storyboard: A dictionary representing the storyboard.

    Returns:
        The storyboard dictionary, now with an 'id' if it was new.

    """
    db = FirebaseClient().get_client()

    # Server-side authorization: the recorded owner must be the server-derived
    # caller, and an existing storyboard may only be overwritten by its owner.
    caller = authz.resolve_caller_email(fallback=storyboard.get("user_email"))
    authz.authorize_attribution(
        storyboard.get("user_email"),
        caller,
        resource="storyboard",
    )

    is_new = "id" not in storyboard or not storyboard.get("id")
    if is_new:
        storyboard["id"] = str(uuid.uuid4())

    doc_ref = db.collection("interior_design_storyboards").document(storyboard["id"])
    if not is_new:
        authz.authorize_existing_document(
            doc_ref,
            "user_email",
            caller,
            resource="storyboard",
        )
    doc_ref.set(storyboard)
    logger.info(f"Storyboard saved to Firestore with ID: {storyboard['id']}")
    return storyboard


def field_names(dataclass_instance):
    """Helper to get field names of a dataclass instance."""
    return [f.name for f in dataclass_instance.__dataclass_fields__.values()]


def _create_media_item_from_dict(doc_id: str, raw_item_data: dict) -> MediaItem:
    """Helper to create a MediaItem from a Firestore document dictionary."""
    if raw_item_data is None:
        return None

    # Handle timestamp conversion
    timestamp_iso_str: str | None = None
    raw_timestamp = raw_item_data.get("timestamp")
    if isinstance(raw_timestamp, datetime.datetime):
        timestamp_iso_str = raw_timestamp.isoformat()
    elif isinstance(raw_timestamp, str):
        timestamp_iso_str = raw_timestamp
    elif hasattr(raw_timestamp, "isoformat"):  # For Firestore Timestamp
        timestamp_iso_str = raw_timestamp.isoformat()

    # Handle numeric conversions safely
    try:
        gen_time = (
            float(raw_item_data.get("generation_time"))
            if raw_item_data.get("generation_time") is not None
            else None
        )
    except (ValueError, TypeError):
        gen_time = None

    try:
        item_duration = (
            float(raw_item_data.get("duration"))
            if raw_item_data.get("duration") is not None
            else None
        )
    except (ValueError, TypeError):
        item_duration = None

    try:
        num_images = (
            int(raw_item_data.get("num_images"))
            if raw_item_data.get("num_images") is not None
            else None
        )
    except (ValueError, TypeError):
        num_images = None

    try:
        seed = (
            int(raw_item_data.get("seed"))
            if raw_item_data.get("seed") is not None
            else None
        )
    except (ValueError, TypeError):
        seed = None

    # Handle GCS URI (which can be a string or list)
    gcsuri: str = None
    if isinstance(raw_item_data.get("gcsuri"), list):
        gcsuri = raw_item_data.get("gcsuri")[0] if raw_item_data.get("gcsuri") else None
    elif raw_item_data.get("gcsuri") is not None:
        gcsuri = str(raw_item_data.get("gcsuri"))

    # Correctly handle thumbnail_uri vs thumbnail_url typo
    thumbnail = raw_item_data.get("thumbnail_uri") or raw_item_data.get("thumbnail_url")

    media_item = MediaItem(
        id=doc_id,
        user_email=raw_item_data.get("user_email"),
        timestamp=timestamp_iso_str,
        prompt=raw_item_data.get("prompt"),
        original_prompt=raw_item_data.get("original_prompt"),
        rewritten_prompt=raw_item_data.get("rewritten_prompt"),
        model=raw_item_data.get("model"),
        mime_type=raw_item_data.get("mime_type"),
        mode=raw_item_data.get("mode"),
        generation_time=gen_time,
        status=raw_item_data.get(
            "status", "complete",
        ),  # Default to 'complete' for legacy items
        error_message=raw_item_data.get("error_message"),
        gcsuri=gcsuri,
        gcs_uris=raw_item_data.get("gcs_uris", []),
        source_images_gcs=raw_item_data.get("source_images_gcs", []),
        source_uris=raw_item_data.get("source_uris", []),
        thumbnail_uri=thumbnail,
        aspect=raw_item_data.get("aspect"),
        resolution=raw_item_data.get("resolution"),
        duration=item_duration,
        reference_image=raw_item_data.get("reference_image"),
        last_reference_image=raw_item_data.get("last_reference_image"),
        negative_prompt=raw_item_data.get("negative_prompt"),
        enhanced_prompt_used=raw_item_data.get("enhanced_prompt_used"),
        comment=raw_item_data.get("comment"),
        modifiers=raw_item_data.get("modifiers", []),
        captions=raw_item_data.get("captions", []),
        num_images=num_images,
        seed=seed,
        critique=raw_item_data.get("critique"),
        grounding_info=raw_item_data.get("grounding_info"),
        audio_analysis=raw_item_data.get("audio_analysis"),
        generated_text=raw_item_data.get("generated_text", []),
        media_type=raw_item_data.get("media_type"),
        source_character_images=raw_item_data.get("source_character_images", []),
        character_description=raw_item_data.get("character_description"),
        imagen_prompt=raw_item_data.get("imagen_prompt"),
        veo_prompt=raw_item_data.get("veo_prompt"),
        candidate_images=raw_item_data.get("candidate_images", []),
        best_candidate_image=raw_item_data.get("best_candidate_image"),
        outpainted_image=raw_item_data.get("outpainted_image"),
        custom_pronunciations=raw_item_data.get("custom_pronunciations", []),
        voice=raw_item_data.get("voice"),
        pace=raw_item_data.get("pace"),
        volume_gain_db=raw_item_data.get("volume_gain_db"),
        language_code=raw_item_data.get("language_code"),
        style_prompt=raw_item_data.get("style_prompt"),
        storyboard_id=raw_item_data.get("storyboard_id"),
        object_rotation_project_id=raw_item_data.get("object_rotation_project_id"),
        related_media_item_id=raw_item_data.get("related_media_item_id"),
        r2v_reference_images=raw_item_data.get("r2v_reference_images", []),
        r2v_style_image=raw_item_data.get("r2v_style_image"),
        person_image_gcs=raw_item_data.get("person_image_gcs"),
        product_image_gcs=raw_item_data.get("product_image_gcs"),
        original_resolution=raw_item_data.get("original_resolution"),
        upscale_factor=raw_item_data.get("upscale_factor"),
        image_size=raw_item_data.get("image_size"),
    )
    return media_item


def get_media_item_by_id(
    item_id: str,
    *,
    caller_email: str | None = None,
) -> MediaItem | None:  # Assuming MediaItem class is defined/imported
    """Retrieve a media item by its Firestore document ID, scoped to its owner.

    This is a load-by-client-supplied-id path: ``item_id`` can originate from a
    client-controllable value (a Mesop ``WebEvent.key`` → ``selected_media_item_id``,
    a URL/query param, etc.). Returning the document with no ownership check is a
    read-side IDOR (information disclosure of another user's media). This mirrors
    the server-side read authorization added for the other load-by-id paths in
    PR #1930 (``common.authz.authorize_read``).

    The server-derived caller identity is resolved via
    :func:`common.authz.resolve_caller_email` (the verified ``AppState.user_email``
    for the active request, or an explicit ``caller_email`` a caller already
    derived server-side). The item is returned **only** when the caller owns it
    (or it is a legacy ownerless document, per :func:`common.authz.is_owner`).

    Returns ``None`` when the document does not exist **or** the caller is not
    authorized — the two cases are deliberately indistinguishable so a non-owner
    cannot probe existence/contents (no existence oracle). Fails closed when no
    server-derived caller identity is resolvable.

    System/background callers that legitimately run outside a request context and
    operate on a server-managed id (e.g. the Veo generation/thumbnail pipeline
    updating its own job) must use :func:`get_media_item_by_id_system`, which is
    the only sanctioned unscoped read.
    """
    try:
        logger.info(f"Trying to retrieve {item_id}")
        caller = authz.resolve_caller_email(caller_email)
        doc_ref = db.collection(config.GENMEDIA_COLLECTION_NAME).document(item_id)
        data = authz.authorize_read(
            doc_ref, "user_email", caller, resource="media item"
        )
        if data is None:
            # Not found OR not authorized — indistinguishable by design.
            logger.warning(
                f"No media item returned for ID {item_id} "
                "(absent or caller not authorized)"
            )
            return None
        return _create_media_item_from_dict(item_id, data)
    except Exception as e:
        logger.error(f"Error fetching media item by ID {item_id}: {e}")
        return None


def get_media_item_by_id_system(item_id: str) -> MediaItem | None:
    """Unscoped read by id for trusted server-side callers only (NO ownership check).

    This is the deliberate, clearly-named bypass of the owner-scoping enforced by
    :func:`get_media_item_by_id`. It exists for internal server-side code that runs
    **outside** a request context (no ``AppState.user_email`` to resolve) and
    operates on a document id the server itself produced and manages — today, the
    Veo background generation/thumbnail pipeline reading back the job it is
    processing to update its status.

    It MUST NOT be used on any path reachable by a client-controllable id for a
    caller-facing read; doing so reintroduces the read-side IDOR that
    :func:`get_media_item_by_id` closes.
    """
    try:
        doc_ref = db.collection(config.GENMEDIA_COLLECTION_NAME).document(item_id)
        doc = doc_ref.get()
        if doc.exists:
            return _create_media_item_from_dict(doc.id, doc.to_dict())
        logger.warning(f"No document found with ID: {item_id}")
        return None
    except Exception as e:
        logger.error(f"Error fetching media item by ID {item_id}: {e}")
        return None


def add_media_item(user_email: str, **kwargs):
    """Add a media item to Firestore persistence"""
    # Server-side authorization: a new item must be attributed to the
    # server-derived caller (prevent attribution forgery).
    caller = authz.resolve_caller_email(fallback=user_email)
    authz.authorize_attribution(user_email, caller, resource="media item")

    current_datetime = datetime.datetime.now(datetime.UTC)

    # Prepare data for Firestore
    firestore_data = {
        "user_email": user_email,
        "timestamp": current_datetime,
    }

    # Merge kwargs into firestore_data
    firestore_data.update(kwargs)

    doc_ref = db.collection(config.GENMEDIA_COLLECTION_NAME).document()
    doc_ref.set(firestore_data)

    logger.info(f"Media data stored in Firestore with document ID: {doc_ref.id}")


def get_latest_videos(limit: int = 10):
    """Retrieve the last 10 videos"""
    try:
        media_ref = (
            db.collection(config.GENMEDIA_COLLECTION_NAME)
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        media = []
        for doc in media_ref.stream():
            media.append(doc.to_dict())

        return media
    except Exception as e:
        logger.error(f"Error fetching media: {e}")
        return []


def get_total_media_count():
    """Get count of all media in firestore"""
    media_ref = db.collection(config.GENMEDIA_COLLECTION_NAME).order_by(
        "timestamp", direction=firestore.Query.DESCENDING,
    )
    count = len([doc.to_dict() for doc in media_ref.stream()])
    return count


def add_vto_metadata(
    person_image_gcs: str,
    product_image_gcs: str,
    result_image_gcs: list[str],
    user_email: str,
):
    """Add VTO metadata to Firestore persistence"""
    # Server-side authorization: a new record must be attributed to the
    # server-derived caller (prevent attribution forgery).
    caller = authz.resolve_caller_email(fallback=user_email)
    authz.authorize_attribution(user_email, caller, resource="VTO result")

    current_datetime = datetime.datetime.now()

    doc_ref = db.collection(config.GENMEDIA_COLLECTION_NAME).document()
    doc_ref.set(
        {
            "person_image_gcs": person_image_gcs,
            "product_image_gcs": product_image_gcs,
            "gcs_uris": result_image_gcs,
            "mime_type": "image/png",
            "user_email": user_email,
            "timestamp": current_datetime,
            "model": config.VTO_MODEL_ID,
        },
    )

    logger.info(f"VTO data stored in Firestore with document ID: {doc_ref.id}")


def get_media_for_page(
    page: int,
    media_per_page: int,
    type_filters: list[str] | None = None,
    error_filter: str = "all",  # "all", "no_errors", "only_errors"
    sort_by_timestamp: bool = False,
    filter_by_user_email: str | None = None,  # New parameter
) -> list[MediaItem]:
    """Fetches a paginated and filtered list of media items from Firestore.

    NOTE: This implementation currently fetches a larger batch of items (up to 'fetch_limit')
    and then performs filtering and pagination client-side (in Python). For very large datasets
    in Firestore (e.g., many thousands of media items), this approach might become inefficient
    in terms of data transfer and memory usage. A more scalable long-term solution would involve
    server-side pagination and filtering directly using Firestore query cursors (`start_after`)
    and more complex `where` clauses if feasible, potentially via dedicated API endpoints.

    Args:
        page: The page number to fetch.
        media_per_page: The number of media items to fetch per page.
        type_filters: A list of media types to filter by.
        error_filter: The error filter to apply.

    Returns:
        A list of MediaItem objects.

    """
    fetch_limit = 1000  # Max items to fetch for client-side filtering/pagination

    try:
        query = db.collection(config.GENMEDIA_COLLECTION_NAME)

        if sort_by_timestamp:
            query = query.order_by("timestamp", direction=firestore.Query.DESCENDING)

        all_docs = list(query.limit(fetch_limit).stream())
        logger.info(
            f"[get_media_for_page] Fetched {len(all_docs)} total documents from Firestore before filtering.",
        )

        all_fetched_items: list[MediaItem] = []
        for doc in all_docs:
            raw_item_data = doc.to_dict()

            if raw_item_data is None:
                logger.warning(f"doc.to_dict() returned None for doc ID: {doc.id}")
                continue

            # Ensure mime_type is a string, even if it's null in Firestore
            mime_type = raw_item_data.get("mime_type") or ""
            error_message_present = bool(raw_item_data.get("error_message"))

            # Apply type filters
            passes_type_filter = False
            if not type_filters or "all" in type_filters or ("videos" in type_filters and mime_type.startswith("video/")) or ("images" in type_filters and mime_type.startswith("image/")) or ("music" in type_filters and mime_type.startswith("audio/")):
                passes_type_filter = True

            if not passes_type_filter:
                continue

            # Apply error filter
            passes_error_filter = False
            if error_filter == "all" or (error_filter == "no_errors" and not error_message_present) or (error_filter == "only_errors" and error_message_present):
                passes_error_filter = True

            if not passes_error_filter:
                continue

            # Apply user email filter
            if (
                filter_by_user_email
                and raw_item_data.get("user_email") != filter_by_user_email
            ):
                continue

            # If all filters pass, create the object using the helper
            media_item = _create_media_item_from_dict(doc.id, raw_item_data)
            if media_item:
                all_fetched_items.append(media_item)

        logger.info(
            f"[get_media_for_page] {len(all_fetched_items)} items remaining after client-side filtering.",
        )

        # For pagination, slice the fully filtered list
        start_slice = (page - 1) * media_per_page
        end_slice = start_slice + media_per_page
        return all_fetched_items[start_slice:end_slice]

    except Exception as e:
        logger.error(f"Error fetching media from Firestore: {e}")
        # Optionally, you could re-raise or handle more gracefully
        return []


def get_media_for_page_optimized(
    page_size: int,
    type_filters: list[str],
    start_after=None,
    filter_by_user_email: str | None = None,
):
    """Fetches a paginated and filtered list of media items from Firestore
    using server-side pagination and filtering.
    """
    try:
        query = db.collection(config.GENMEDIA_COLLECTION_NAME)

        # Apply user email filter if provided
        if filter_by_user_email:
            query = query.where("user_email", "==", filter_by_user_email)

        # Apply type filters using WHERE clauses
        # Note: This requires Firestore indexes. For a single 'mime_type' startsWith,
        # a single-field index on 'mime_type' might suffice. For combinations with
        # sorting, a composite index is likely needed.
        if "videos" in type_filters:
            query = query.where("mime_type", ">=", "video/").where(
                "mime_type", "<", "video0",
            )
        elif "images" in type_filters:
            query = query.where("mime_type", ">=", "image/").where(
                "mime_type", "<", "image0",
            )
        elif "music" in type_filters or "audio" in type_filters:
            query = query.where("mime_type", ">=", "audio/").where(
                "mime_type", "<", "audio0",
            )

        # Always sort by timestamp
        query = query.order_by("timestamp", direction=firestore.Query.DESCENDING)

        # Server-side pagination
        if start_after:
            query = query.start_after(start_after)

        query = query.limit(page_size)

        docs = list(query.stream())
        media_items = []
        for doc in docs:
            # This reuses the same parsing logic as the original function
            # A refactor could extract this parsing into a helper
            raw_item_data = doc.to_dict()
            if raw_item_data is None:
                continue

            if isinstance(raw_item_data.get("gcsuri"), list):
                gcsuri = (
                    raw_item_data.get("gcsuri")[0]
                    if raw_item_data.get("gcsuri")
                    else None
                )
            elif raw_item_data.get("gcsuri") is not None:
                gcsuri = str(raw_item_data.get("gcsuri"))
            else:
                gcsuri = None

            timestamp_iso_str: str | None = None
            raw_timestamp = raw_item_data.get("timestamp")
            if isinstance(raw_timestamp, datetime.datetime):
                timestamp_iso_str = raw_timestamp.isoformat()
            elif isinstance(raw_timestamp, str):
                timestamp_iso_str = raw_timestamp  # Assuming it's already ISO format
            elif hasattr(raw_timestamp, "isoformat"):  # For Firestore Timestamp objects
                timestamp_iso_str = raw_timestamp.isoformat()

            try:
                gen_time = (
                    float(raw_item_data.get("generation_time"))
                    if raw_item_data.get("generation_time") is not None
                    else None
                )
            except (ValueError, TypeError):
                gen_time = None

            try:
                item_duration = (
                    float(raw_item_data.get("duration"))
                    if raw_item_data.get("duration") is not None
                    else None
                )
            except (ValueError, TypeError):
                item_duration = None

            media_item = MediaItem(
                id=doc.id,
                aspect=(
                    str(raw_item_data.get("aspect"))
                    if raw_item_data.get("aspect") is not None
                    else None
                ),
                gcsuri=gcsuri,
                gcs_uris=raw_item_data.get("gcs_uris", []),
                source_images_gcs=raw_item_data.get("source_images_gcs", []),
                prompt=(
                    str(raw_item_data.get("prompt"))
                    if raw_item_data.get("prompt") is not None
                    else None
                ),
                generation_time=gen_time,
                timestamp=timestamp_iso_str,
                reference_image=(
                    str(raw_item_data.get("reference_image"))
                    if raw_item_data.get("reference_image") is not None
                    else None
                ),
                last_reference_image=(
                    str(raw_item_data.get("last_reference_image"))
                    if raw_item_data.get("last_reference_image") is not None
                    else None
                ),
                negative_prompt=(
                    str(raw_item_data.get("negative_prompt"))
                    if raw_item_data.get("negative_prompt") is not None
                    else None
                ),
                enhanced_prompt_used=raw_item_data.get("enhanced_prompt"),
                duration=item_duration,
                error_message=(
                    str(raw_item_data.get("error_message"))
                    if raw_item_data.get("error_message") is not None
                    else None
                ),
                rewritten_prompt=(
                    str(raw_item_data.get("rewritten_prompt"))
                    if raw_item_data.get("rewritten_prompt") is not None
                    else None
                ),
                comment=(
                    str(raw_item_data.get("comment"))
                    if raw_item_data.get("comment") is not None
                    else None
                ),
                resolution=(
                    str(raw_item_data.get("resolution"))
                    if raw_item_data.get("resolution") is not None
                    else None
                ),
                media_type=(
                    str(raw_item_data.get("media_type"))
                    if raw_item_data.get("media_type") is not None
                    else None
                ),
                source_character_images=raw_item_data.get(
                    "source_character_images", [],
                ),
                character_description=(
                    str(raw_item_data.get("character_description"))
                    if raw_item_data.get("character_description") is not None
                    else None
                ),
                imagen_prompt=(
                    str(raw_item_data.get("imagen_prompt"))
                    if raw_item_data.get("imagen_prompt") is not None
                    else None
                ),
                veo_prompt=(
                    str(raw_item_data.get("veo_prompt"))
                    if raw_item_data.get("veo_prompt") is not None
                    else None
                ),
                candidate_images=raw_item_data.get("candidate_images", []),
                best_candidate_image=(
                    str(raw_item_data.get("best_candidate_image"))
                    if raw_item_data.get("best_candidate_image") is not None
                    else None
                ),
                outpainted_image=(
                    str(raw_item_data.get("outpainted_image"))
                    if raw_item_data.get("outpainted_image") is not None
                    else None
                ),
                original_resolution=raw_item_data.get("original_resolution"),
                upscale_factor=raw_item_data.get("upscale_factor"),
            )
            media_items.append(media_item)

        last_doc = docs[-1] if docs else None
        return media_items, last_doc

    except Exception as e:
        logger.error(f"Error fetching media from Firestore (optimized): {e}")
        return [], None


def get_media_for_chooser(
    media_type: str, page_size: int, start_after=None,
) -> tuple[list[MediaItem], firestore.DocumentSnapshot | None]:
    """Fetches media items for the chooser, using a hybrid query strategy."""
    # TODO: This function uses two queries for backward compatibility (one for `media_type`
    # and one for `mime_type`). After a data migration to ensure all documents have the
    # `media_type` field, this should be simplified to a single, more performant query
    # on `media_type` only.
    if not db:
        return [], None

    try:
        # Query 1: For new data with the media_type field
        query1 = (
            db.collection(config.GENMEDIA_COLLECTION_NAME)
            .where("media_type", "==", media_type)
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
        )

        # Query 2: For legacy data using mime_type
        mime_prefix = f"{media_type}/"
        mime_prefix_end = f"{media_type}0"
        query2 = (
            db.collection(config.GENMEDIA_COLLECTION_NAME)
            .where("mime_type", ">=", mime_prefix)
            .where("mime_type", "<", mime_prefix_end)
            .order_by("mime_type", direction=firestore.Query.ASCENDING)
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
        )

        if start_after:
            query1 = query1.start_after(start_after)
            query2 = query2.start_after(start_after)

        query1 = query1.limit(page_size)
        query2 = query2.limit(page_size)

        # Execute queries and merge results
        docs1 = list(query1.stream())
        docs2 = list(query2.stream())

        merged_docs = {doc.id: doc for doc in docs1}
        for doc in docs2:
            if doc.id not in merged_docs:
                merged_docs[doc.id] = doc

        # Sort merged results by timestamp
        sorted_docs = sorted(
            merged_docs.values(),
            key=lambda doc: doc.to_dict().get("timestamp"),
            reverse=True,
        )

        # Paginate the final sorted list
        paginated_docs = sorted_docs[:page_size]

        media_items = [
            _create_media_item_from_dict(doc.id, doc.to_dict())
            for doc in paginated_docs
        ]

        # Determine the correct `last_doc` for pagination
        last_doc = paginated_docs[-1] if paginated_docs else None

        return media_items, last_doc

    except Exception as e:
        logger.error(f"Error fetching media for chooser: {e}")
        return [], None
