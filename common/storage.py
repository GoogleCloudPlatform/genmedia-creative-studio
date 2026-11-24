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

import base64
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from google.cloud import storage

from common import authz
from config.default import Default
from config.firebase_config import FirebaseClient
from common.analytics import get_logger

cfg = Default()
logger = get_logger(__name__)

try:
    import urllib3.contrib.pyopenssl

    urllib3.contrib.pyopenssl.extract_from_urllib3()
except (ImportError, AttributeError):
    pass

try:
    import OpenSSL.SSL

    for _attr_name in dir(OpenSSL.SSL.Context):
        _attr = getattr(OpenSSL.SSL.Context, _attr_name)
        if callable(_attr) and not _attr_name.startswith("__"):

            def _make_wrapper(orig_func):
                def _wrapper(*args, **kwargs):
                    try:
                        return orig_func(*args, **kwargs)
                    except ValueError as e:
                        if "already been used" in str(e):
                            return None
                        raise

                return _wrapper

            setattr(OpenSSL.SSL.Context, _attr_name, _make_wrapper(_attr))
except (ImportError, AttributeError):
    pass

db = FirebaseClient(cfg.GENMEDIA_FIREBASE_DB).get_client()
_storage_client: storage.Client | None = None


def get_storage_client() -> storage.Client:
    """Returns a cached singleton GCS storage.Client."""
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client(project=cfg.PROJECT_ID)
    return _storage_client


@dataclass
class Session:
    """Represents a user session."""

    id: str
    user_email: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed_at: datetime = field(default_factory=datetime.utcnow)


def _create_session(user_email: str, session_id: str | None = None) -> Session:
    """Create and persist a fresh session record owned by ``user_email``.

    The recorded owner must equal the server-derived caller identity resolved by
    the request middleware (no attribution forgery). ``session_id`` may be
    ``None`` to mint a brand-new, unguessable id (used when rotating away from a
    session that belongs to a different identity).
    """
    caller = authz.resolve_caller_email(user_email)
    authz.authorize_attribution(user_email, caller, resource="session")
    if not session_id:
        session_id = str(uuid.uuid4())
    session = Session(id=session_id, user_email=user_email)
    db.collection(cfg.SESSIONS_COLLECTION_NAME).document(session_id).set(
        asdict(session),
    )
    return session


def get_or_create_session(session_id: str, user_email: str) -> Session:
    """Retrieve a session for its owner, or create/rotate one for the caller.

    This runs in the global identity middleware on every request, so it must be
    availability-safe: it never raises on an ownership mismatch. The client
    ``session_id`` cookie is not rotated when the identity changes (for example
    an anonymous->authenticated login, or a replayed cookie), so a stored session
    may belong to a different identity than the current caller. In that case the
    other identity's record is left untouched and a brand-new session is minted
    for the current caller (returned to the middleware so it can update the
    cookie). This closes the cross-identity access without a 500-on-every-request
    denial of service. The security value of the gate is intentionally low here:
    the record only refreshes ``last_accessed_at`` and identity is header-derived,
    never read back from the session document.
    """
    session_ref = db.collection(cfg.SESSIONS_COLLECTION_NAME).document(session_id)
    session_doc = session_ref.get()

    if session_doc.exists:
        stored = session_doc.to_dict() or {}
        stored_owner = stored.get("user_email")
        caller = authz.resolve_caller_email(user_email)
        if stored_owner is not None and stored_owner != caller:
            # Rotated/replayed cookie pointing at another identity's session:
            # do not touch it; mint a fresh session for the current caller.
            logger.info(
                "Session %s belongs to a different identity; rotating to a new "
                "session for the current caller.",
                session_id,
            )
            return _create_session(user_email)
        session = Session(**stored)
        # Update last accessed time
        session.last_accessed_at = datetime.utcnow()
        session_ref.update({"last_accessed_at": session.last_accessed_at})
        return session

    return _create_session(user_email, session_id)


def store_to_gcs(
    folder: str,
    file_name: str,
    mime_type: str,
    contents: str | bytes,
    decode: bool = False,
    bucket_name: str | None = None,
):
    """Store contents to GCS"""
    raw_bucket_name = bucket_name if bucket_name else cfg.GENMEDIA_BUCKET
    if not raw_bucket_name:
        raise ValueError(
            "GCS bucket name is not configured. Please set GENMEDIA_BUCKET environment variable or provide bucket_name.",
        )
    # Strip any leading 'gs://' scheme and subpath (e.g. 'gs://bucket/folder' -> 'bucket')
    actual_bucket_name = raw_bucket_name.removeprefix("gs://").split("/")[0]

    logger.info(
        f"store_to_gcs: Target project {cfg.PROJECT_ID}, target bucket {actual_bucket_name}",
    )
    client = get_storage_client()
    bucket = client.get_bucket(actual_bucket_name)
    destination_blob_name = f"{folder}/{file_name}"
    logger.info(f"store_to_gcs: Destination {destination_blob_name}")
    blob = bucket.blob(destination_blob_name)
    if decode:
        contents_bytes = base64.b64decode(contents)
        blob.upload_from_string(contents_bytes, content_type=mime_type)
    elif isinstance(contents, bytes):
        blob.upload_from_string(contents, content_type=mime_type)
    else:
        blob.upload_from_string(contents, content_type=mime_type)
    return (
        f"gs://{actual_bucket_name}/{destination_blob_name}"  # Return full gsutil URI
    )


def _allowed_proxy_buckets() -> set[str]:
    """Return the set of GCS bucket NAMES the app may read objects from by URI.

    Shared by the ``/media`` proxy, ``/api/get_signed_url`` and GIF conversion.

    The allowlist is sourced exclusively from the application's own storage
    configuration (the buckets this app writes its generated media to). Several
    of those config values embed a path prefix (e.g. ``"my-bucket/videos"``) or
    a ``gs://`` scheme; only the leading bucket component is used for the
    allowlist comparison.

    An empty result means "allow nothing": callers MUST fail closed so that a
    missing/unconfigured allowlist can never degrade into "allow all".
    """
    candidates = (
        Default.GENMEDIA_BUCKET,
        Default.VIDEO_BUCKET,
        Default.IMAGE_BUCKET,
        Default.GCS_ASSETS_BUCKET,
        getattr(Default, "MEDIA_BUCKET", None),
    )
    allowed: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        # Normalize: drop any gs:// scheme, then keep only the bucket component
        # preceding the first path separator.
        name = candidate.replace("gs://", "", 1).split("/", 1)[0].strip()
        if name:
            allowed.add(name)
    return allowed


def _is_proxy_bucket_allowed(bucket_name: str) -> bool:
    """Return True only if ``bucket_name`` is one of the app's own buckets.

    Fails closed: any empty/unknown bucket, or an empty allowlist, returns False.
    """
    if not bucket_name:
        return False
    return bucket_name in _allowed_proxy_buckets()


def download_from_gcs(gcs_uri: str) -> bytes:
    """Downloads a file from a GCS URI and returns its content as bytes."""
    client = get_storage_client()
    blob = storage.Blob.from_string(gcs_uri, client=client)
    return blob.download_as_bytes()


def download_from_gcs_as_string(gcs_uri: str):
    """Downloads a file from a GCS URI and returns its content as a string."""
    client = get_storage_client()
    blob = storage.Blob.from_string(gcs_uri, client=client)
    return blob.download_as_string()


def list_files_in_bucket(bucket_name, prefix=None):
    """Lists all blobs (files) in the specified GCS bucket, optionally filtered by a prefix."""
    client = get_storage_client()
    bucket = client.get_bucket(bucket_name)

    # List blobs, optionally with a prefix to emulate a "folder"
    blobs = bucket.list_blobs(prefix=prefix)

    file_names = []
    for blob in blobs:
        file_names.append(blob.name)

    return file_names


def generate_upload_signed_url(
    bucket_name: str,
    blob_name: str,
    content_type: str,
) -> str:
    """Generate a v4 signed URL for uploading a file via PUT request."""
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=15),
        method="PUT",
        content_type=content_type,
    )
