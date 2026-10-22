import json
import os
import platform
import threading
from pathlib import Path
from typing import Any, Dict, Optional

def _configure_credentio_lib_path() -> None:
    """Ensures CREDENTIO_LIB_PATH is set if libcredentio_c is in a standard system/user path."""
    if os.environ.get("CREDENTIO_LIB_PATH"):
        return

    ext = ".dylib" if platform.system() == "Darwin" else ".so"
    candidates = [
        Path.home() / ".local" / "lib" / f"libcredentio_c{ext}",
        Path("/usr/local/lib") / f"libcredentio_c{ext}",
        Path("/opt/homebrew/lib") / f"libcredentio_c{ext}",
    ]
    for candidate in candidates:
        if candidate.is_file():
            os.environ["CREDENTIO_LIB_PATH"] = str(candidate)
            break

_configure_credentio_lib_path()

from credentio import CredentioError, Validator  # noqa: E402

_validator_lock = threading.Lock()
_validator_instance: Optional[Validator] = None


def _get_validator() -> Validator:
    """Returns a process-wide singleton Credentio Validator."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = Validator(skip_trust_checks=True)
    return _validator_instance


def _clean_version(ver: Optional[str]) -> Optional[str]:
    if not ver or not isinstance(ver, str):
        return ver
    parts = ver.split(":")
    if len(parts) == 2 and parts[0] and parts[0] == parts[1]:
        return parts[0]
    return ver


def get_c2pa_manifest(video_path: str) -> Dict[str, Any]:
    """
    Extracts and validates the C2PA manifest from a video file using Google Credentio.
    Returns the parsed crJSON dictionary or an error dict.
    """
    if not os.path.exists(video_path):
        return {"error": f"File not found: {video_path}"}

    try:
        with _validator_lock:
            validator = _get_validator()
            report = validator.validate_file(str(video_path))

        if not report.has_credentials or not report.raw_json:
            return {"error": "No C2PA manifest found in this file."}

        manifest_data = json.loads(report.raw_json)
        active = report.active_manifest
        sig = active.signature if active else None
        manifest_data["_credentio_meta"] = {
            "engine_id": report.engine_id,
            "engine_name": report.engine_name,
            "badge": report.badge.value,
            "core_seconds": report.core_seconds,
            "elapsed_seconds": report.elapsed_seconds,
            "media_type": report.media_type,
            "claim_generator": active.claim_generator if active else None,
            "signature_issuer": sig.issuer if sig else None,
            "signature_algorithm": sig.algorithm if sig else None,
            "signature_time": sig.time.isoformat() if (sig and sig.time) else None,
        }
        return manifest_data
    except CredentioError as e:
        return {"error": f"Credentio Validation Error: {str(e)}"}
    except Exception as e:
        return {"error": f"C2PA Read Error: {str(e)}"}


def summarize_c2pa(video_path: str) -> Dict[str, Any]:
    """
    Provides a structured summary of C2PA provenance validated by Google Credentio.
    """
    manifest = get_c2pa_manifest(video_path)
    if "error" in manifest:
        return {
            "status": "Unsigned",
            "badge": "unsigned",
            "has_credentials": False,
            "engine": "Credentio (Google)",
            "error_detail": manifest["error"],
            "actions": [],
            "generator": "Unknown",
        }

    meta = manifest.get("_credentio_meta", {})
    badge = meta.get("badge", "signed")
    core_ms = round((meta.get("core_seconds") or 0.0) * 1000, 2)
    elapsed_ms = round((meta.get("elapsed_seconds") or 0.0) * 1000, 2)

    raw_manifests = manifest.get("manifests", [])
    active_manifest: Dict[str, Any] = {}
    if isinstance(raw_manifests, list) and raw_manifests:
        active_manifest = raw_manifests[0] if isinstance(raw_manifests[0], dict) else {}
    elif isinstance(raw_manifests, dict) and raw_manifests:
        first_key = next(iter(raw_manifests))
        active_manifest = raw_manifests[first_key] if isinstance(raw_manifests[first_key], dict) else {}

    claim_dict = active_manifest.get("claim.v2") or active_manifest.get("claim") or {}

    # Extract generator name and version
    generator = "Unknown"
    generator_version = None
    gen_info = claim_dict.get("claim_generator_info") or active_manifest.get("claim_generator_info")
    if isinstance(gen_info, dict):
        generator = gen_info.get("name", "Unknown")
        generator_version = _clean_version(gen_info.get("version"))
    elif isinstance(gen_info, list) and gen_info and isinstance(gen_info[0], dict):
        generator = gen_info[0].get("name", "Unknown")
        generator_version = _clean_version(gen_info[0].get("version"))
    elif claim_dict.get("claim_generator") or active_manifest.get("claim_generator"):
        generator = claim_dict.get("claim_generator") or active_manifest.get("claim_generator")

    # Extract cryptographic signature & TSA details (handling C2PA v2 JUMBF string in claim.v2.signature)
    sig_dict = next(
        (
            cand
            for cand in (
                claim_dict.get("signature_info"),
                active_manifest.get("signature_info"),
                claim_dict.get("signature"),
                active_manifest.get("signature"),
            )
            if isinstance(cand, dict)
        ),
        {},
    )
    cert_info = sig_dict.get("certificateInfo", {}) if isinstance(sig_dict.get("certificateInfo"), dict) else {}
    subject_dict = cert_info.get("subject", {}) if isinstance(cert_info.get("subject"), dict) else {}
    issuer_dict = cert_info.get("issuer", {}) if isinstance(cert_info.get("issuer"), dict) else {}

    tsa_info = sig_dict.get("timeStampInfo", {}) if isinstance(sig_dict.get("timeStampInfo"), dict) else {}
    tsa_cert = tsa_info.get("certificateInfo", {}) if isinstance(tsa_info.get("certificateInfo"), dict) else {}
    tsa_subject_dict = tsa_cert.get("subject", {}) if isinstance(tsa_cert.get("subject"), dict) else {}

    signer_subject = subject_dict.get("CN") or sig_dict.get("common_name")
    signer_issuer = meta.get("signature_issuer") or issuer_dict.get("CN") or sig_dict.get("issuer")
    signer_org = subject_dict.get("O") or issuer_dict.get("O")
    signer_alg = meta.get("signature_algorithm") or sig_dict.get("algorithm") or sig_dict.get("alg")
    tsa_subject = tsa_subject_dict.get("CN")
    timestamp = meta.get("signature_time") or tsa_info.get("timestamp") or sig_dict.get("time")

    # Extract validation results
    val_results = active_manifest.get("validationResults", {})
    success_list = val_results.get("success", []) if isinstance(val_results, dict) else []
    failure_list = val_results.get("failure", []) if isinstance(val_results, dict) else []
    success_codes = [s.get("code") for s in success_list if isinstance(s, dict) and s.get("code")]
    failure_codes = [f.get("code") for f in failure_list if isinstance(f, dict) and f.get("code")]

    if failure_codes or badge == "invalid":
        status_label = f"Invalid ({failure_codes[0]})" if failure_codes else "Invalid"
    elif badge == "signed":
        status_label = "Signed (Verified)"
    else:
        status_label = "Unsigned"

    # Extract detailed actions
    actions = []
    raw_assertions = active_manifest.get("assertions", {})
    assertion_items = []
    if isinstance(raw_assertions, dict):
        assertion_items = list(raw_assertions.items())
    elif isinstance(raw_assertions, list):
        assertion_items = [
            (entry.get("label", ""), entry.get("data", entry))
            for entry in raw_assertions
            if isinstance(entry, dict)
        ]

    for label, assertion_data in assertion_items:
        if "c2pa.actions" in label and isinstance(assertion_data, dict):
            actions_list = assertion_data.get("actions", [])
            for action in actions_list:
                if not isinstance(action, dict):
                    continue
                action_name = action.get("action", "unknown action")
                description = action.get("description", "")
                ds_type = action.get("digitalSourceType", "")
                ds_name = ds_type.split("/")[-1] if "/" in ds_type else ds_type

                detail = f"{action_name}: {description}" if description else action_name
                if ds_name:
                    detail += f" ({ds_name})"

                actions.append({
                    "label": action_name,
                    "description": description,
                    "digital_source_type": ds_name,
                    "detail": detail,
                })

    return {
        "status": status_label,
        "badge": badge,
        "has_credentials": True,
        "engine": meta.get("engine_name", "Credentio (Google)"),
        "core_ms": core_ms,
        "elapsed_ms": elapsed_ms,
        "generator": generator,
        "generator_version": generator_version,
        "signer": {
            "subject": signer_subject,
            "issuer": signer_issuer,
            "organization": signer_org,
            "algorithm": signer_alg,
            "tsa_subject": tsa_subject,
            "timestamp": timestamp,
        },
        "validation": {
            "checks_passed": len(success_codes),
            "checks_failed": len(failure_codes),
            "bmff_hash_verified": "assertion.bmffHash.match" in success_codes,
            "signature_verified": "claimSignature.validated" in success_codes,
            "timestamp_verified": "timeStamp.validated" in success_codes,
        },
        "actions": actions,
    }
