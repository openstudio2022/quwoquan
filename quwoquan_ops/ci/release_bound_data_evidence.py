"""Canonical Data lifecycle and public-video evidence for one release identity."""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
DATA_SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(DATA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DATA_SCRIPTS))

from verify.release_lifecycle_exit import lifecycle_exit_issues  # noqa: E402
from verify.verify_release_lifecycle import (  # noqa: E402
    environment_lifecycle_issues,
)

from quwoquan_ops.cli.lib.output_paths import output_root  # noqa: E402
from quwoquan_ops.cli.lib.release_video_delivery import (  # noqa: E402
    DELIVERY_EVIDENCE_SCHEMA,
    ReleaseVideoDeliveryError,
    build_release_video_url,
    load_release_content_identity,
    load_release_video_binding,
    validate_delivery,
)


VIDEO_SCHEMA_PATH = (
    ROOT / "quwoquan_ops" / "environments" / "release_video_delivery_evidence.schema.json"
)


class DataEvidenceError(ValueError):
    """Data evidence is not canonical, complete, or release-bound."""


def _canonical_output_root(requested: Path) -> Path:
    configured = output_root().expanduser().resolve()
    candidate = requested.expanduser().resolve()
    if candidate != configured:
        raise DataEvidenceError(
            f"data output root must equal canonical QWQ_OUTPUT_ROOT: {configured}"
        )
    if requested.is_symlink() or not candidate.is_dir():
        raise DataEvidenceError("canonical QWQ_OUTPUT_ROOT is missing or unsafe")
    return candidate


def _public_https(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    parsed = urlsplit(text)
    host = str(parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or host in {"localhost", "localhost.localdomain"}
        or host.endswith((".local", ".invalid", ".test", ".example"))
    ):
        raise DataEvidenceError(f"{label} is not a public HTTPS URL")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise DataEvidenceError(f"{label} uses a non-public address literal")
    return text


def _schema_issues(value: Any, schema: Mapping[str, Any], path: str) -> list[str]:
    issues: list[str] = []
    expected_type = schema.get("type")
    type_matches = {
        "object": isinstance(value, dict),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }
    if isinstance(expected_type, str) and not type_matches.get(expected_type, False):
        return [f"{path} must be {expected_type}"]
    if "const" in schema and value != schema["const"]:
        issues.append(f"{path} must equal {schema['const']!r}")
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        issues.append(f"{path} is not an allowed value")
    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            issues.append(f"{path} is too short")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            issues.append(f"{path} does not match its canonical pattern")
    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, int) and value < minimum:
            issues.append(f"{path} is below its minimum")
    if isinstance(value, dict):
        properties = schema.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        required = schema.get("required")
        required = required if isinstance(required, list) else []
        missing = [field for field in required if field not in value]
        if missing:
            issues.append(f"{path} is missing required fields: {missing}")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                issues.append(f"{path} has unexpected fields: {extra}")
        for field, child in properties.items():
            if field in value and isinstance(child, dict):
                issues.extend(_schema_issues(value[field], child, f"{path}.{field}"))
    return issues


def _validate_video_schema(payload: Mapping[str, Any]) -> None:
    try:
        schema = json.loads(VIDEO_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataEvidenceError("release video delivery schema is unavailable") from exc
    issues = _schema_issues(dict(payload), schema, "release-video-delivery")
    if issues:
        raise DataEvidenceError(
            "release video delivery evidence violates schema: " + issues[0]
        )


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataEvidenceError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise DataEvidenceError(f"{label} must contain a JSON object")
    return payload


def _validate_video_evidence(
    payload: dict[str, Any],
    *,
    readiness_path: Path,
    content_identity: Mapping[str, Any],
    environment: str,
    target: str,
) -> dict[str, Any]:
    _validate_video_schema(payload)
    if (
        payload.get("schema") != DELIVERY_EVIDENCE_SCHEMA
        or payload.get("status") != "passed"
        or payload.get("environment") != environment
        or payload.get("target") != target
        or payload.get("rolloutStage")
        != ("gray-initial" if environment == "prod" else "local")
    ):
        raise DataEvidenceError("release video delivery environment identity drift")
    try:
        captured = dt.datetime.fromisoformat(
            str(payload.get("capturedAt") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise DataEvidenceError("release video delivery capturedAt is invalid") from exc
    if captured.tzinfo is None:
        raise DataEvidenceError("release video delivery capturedAt must be timezone-aware")

    release = payload.get("release")
    video = payload.get("video")
    delivery = payload.get("delivery")
    playback = payload.get("playback")
    if not all(isinstance(item, dict) for item in (release, video, delivery, playback)):
        raise DataEvidenceError("release video delivery sections are missing")
    expected_release = {
        "releaseId": content_identity["releaseId"],
        "sourceOwner": "qwq_data",
        "manifestDigest": content_identity["manifestDigest"],
        "mediaManifestDigest": content_identity["mediaManifestDigest"],
        "importRunId": content_identity["importRunId"],
        "verifyRunId": content_identity["verifyRunId"],
        "readinessReceiptRef": content_identity["readinessReceiptRef"],
    }
    if release != expected_release:
        raise DataEvidenceError("release video delivery release identity drift")
    try:
        binding = load_release_video_binding(
            readiness_path,
            expected_environment=environment,
            requested_work_id=str(video.get("workId") or ""),
            requested_asset_id=str(video.get("assetId") or ""),
        )
    except ReleaseVideoDeliveryError as exc:
        raise DataEvidenceError(f"release video binding is invalid: {exc}") from exc
    for field in (
        "workId",
        "postId",
        "postRef",
        "assetId",
        "assetVersion",
        "publicSliceKey",
        "expectedMimeType",
        "expectedBytes",
        "expectedHash",
    ):
        if video.get(field) != binding.get(field):
            raise DataEvidenceError(f"release video delivery video.{field} drift")
    public_url = _public_https(video.get("publicUrl"), label="video.publicUrl")
    authority = _public_https(payload.get("videoAuthority"), label="videoAuthority")
    if urlsplit(public_url).hostname != urlsplit(authority).hostname:
        raise DataEvidenceError("release video URL and authority host drift")
    try:
        expected_public_url = build_release_video_url(
            {"mediaVideo": authority},
            binding,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise DataEvidenceError("release video canonical URL cannot be built") from exc
    if public_url != expected_public_url:
        raise DataEvidenceError("release video URL does not match canonical publicSliceKey")
    if (
        payload.get("publicSliceKey") != video.get("publicSliceKey")
        or payload.get("rangeStatus") != delivery.get("rangeStatus")
        or payload.get("contentType") != delivery.get("mimeType")
        or playback.get("firstFrameDecoded") is not True
        or not isinstance(playback.get("durationMs"), int)
        or isinstance(playback.get("durationMs"), bool)
        or playback["durationMs"] <= 0
    ):
        raise DataEvidenceError("release video delivery aliases or playback proof drift")
    try:
        validate_delivery(
            delivery,
            expected_mime_type=str(binding["expectedMimeType"]),
            expected_bytes=int(binding["expectedBytes"]),
            expected_hash=str(binding["expectedHash"]),
            expected_public_slice_key=str(binding["publicSliceKey"]),
        )
    except ReleaseVideoDeliveryError as exc:
        raise DataEvidenceError(f"release video delivery is invalid: {exc}") from exc
    return {
        "assetId": binding["assetId"],
        "postId": binding["postId"],
        "publicSliceKey": binding["publicSliceKey"],
        "publicUrl": public_url,
        "contentType": binding["expectedMimeType"],
        "bytes": binding["expectedBytes"],
        "sha256": binding["expectedHash"],
        "durationMs": playback["durationMs"],
        "firstFrameDecoded": True,
        "rangeStatus": 206,
    }


def validate_data_evidence(
    *,
    data_output_root: Path,
    readiness_path: Path,
    rollback_path: Path,
    video_path: Path,
    environment: str,
    target: str,
    expected_release: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute canonical release, lifecycle, and public-video bindings."""

    root = _canonical_output_root(data_output_root)
    resolved_paths: dict[str, Path] = {}
    for label, path in (
        ("release-readiness", readiness_path),
        ("rollback-receipt", rollback_path),
        ("release-video-delivery", video_path),
    ):
        resolved = path.expanduser().resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise DataEvidenceError(f"{label} must stay below QWQ_OUTPUT_ROOT") from exc
        if path.is_symlink() or not resolved.is_file():
            raise DataEvidenceError(f"{label} is missing or unsafe")
        resolved_paths[label] = resolved
    rollback_payload = _read_json_object(
        resolved_paths["rollback-receipt"],
        label="rollback-receipt",
    )
    video_payload = _read_json_object(
        resolved_paths["release-video-delivery"],
        label="release-video-delivery",
    )
    try:
        content_identity = load_release_content_identity(
            resolved_paths["release-readiness"],
            expected_environment=environment,
        )
    except ReleaseVideoDeliveryError as exc:
        raise DataEvidenceError(f"canonical Data readiness is invalid: {exc}") from exc
    for field in (
        "releaseId",
        "manifestDigest",
        "mediaManifestDigest",
        "importRunId",
        "verifyRunId",
    ):
        if content_identity.get(field) != expected_release.get(field):
            raise DataEvidenceError(f"canonical Data readiness {field} drift")
    release_id = str(expected_release.get("releaseId") or "").strip()
    import_run_id = str(expected_release.get("importRunId") or "").strip()
    verify_run_id = str(expected_release.get("verifyRunId") or "").strip()
    canonical_readiness = (
        root
        / "env"
        / environment
        / "runs"
        / "data-release"
        / release_id
        / verify_run_id
        / "release-readiness.json"
    )
    if resolved_paths["release-readiness"] != canonical_readiness:
        raise DataEvidenceError(
            "release-readiness is not the canonical environment verify-run receipt"
        )
    readiness_issues = environment_lifecycle_issues(
        release_id,
        environment=environment,
        import_run_id=import_run_id,
        verify_run_id=verify_run_id,
        prod_mode="activated",
        release_root=root / "data" / "releases",
        output_root=root,
    )
    if readiness_issues:
        raise DataEvidenceError(
            "canonical Data readiness failed: " + "; ".join(readiness_issues[:8])
        )
    issues = lifecycle_exit_issues(
        rollback_payload,
        path=resolved_paths["rollback-receipt"],
        release_root=root / "data" / "releases",
        output_root=root,
    )
    if issues:
        raise DataEvidenceError("canonical Data lifecycle failed: " + "; ".join(issues[:8]))
    return _validate_video_evidence(
        video_payload,
        readiness_path=resolved_paths["release-readiness"],
        content_identity=content_identity,
        environment=environment,
        target=target,
    )


__all__ = ["DataEvidenceError", "validate_data_evidence"]
