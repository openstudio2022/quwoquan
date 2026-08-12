"""Recompute canonical Data and public-video evidence for one activation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from quwoquan_ops.cli.lib.output_paths import output_root
from quwoquan_ops.cli.lib.release_video_delivery import (
    DELIVERY_EVIDENCE_SCHEMA,
    ReleaseVideoDeliveryError,
    build_release_video_url,
    load_release_content_identity,
    load_release_video_binding,
    validate_delivery,
)
from quwoquan_ops.cli.lib.research_content_isolation import (
    verify_research_content_isolation,
)


class DataEvidenceError(ValueError):
    """Canonical Data media/lifecycle evidence is unavailable or inconsistent."""


def _read(path: Path) -> dict[str, Any]:
    candidate = path.expanduser().resolve()
    if path.is_symlink() or not candidate.is_file():
        raise DataEvidenceError("release video delivery evidence is missing or unsafe")
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataEvidenceError(
            "release video delivery evidence is invalid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise DataEvidenceError("release video delivery evidence must be an object")
    return value


def validate_data_evidence(
    *,
    data_output_root: Path,
    readiness_path: Path,
    rollback_path: Path,
    media_readback_path: Path,
    environment: str,
    target: str,
    expected_release: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute physical Data/media identity without producing new evidence."""

    del rollback_path  # The outer collector validates the exact lifecycle receipt.
    root = output_root().expanduser().resolve()
    requested_root = data_output_root.expanduser().resolve()
    if (
        requested_root != root
        or data_output_root.is_symlink()
        or not requested_root.is_dir()
    ):
        raise DataEvidenceError(
            f"data output root must equal canonical QWQ_OUTPUT_ROOT: {root}"
        )
    readiness = _read_readiness(readiness_path)
    if expected_release.get("releaseClass") == "research":
        try:
            result = verify_research_content_isolation(
                environment,
                release_id=str(expected_release["releaseId"]),
                verify_run_id=str(expected_release["verifyRunId"]),
                manifest_digest=str(expected_release["releaseDigest"]),
                data_readiness=readiness,
                data_readiness_path=readiness_path,
            )
        except ValueError as exc:
            raise DataEvidenceError(str(exc)) from exc
        receipt_path = (root / str(result["receiptRef"])).resolve()
        if media_readback_path.expanduser().resolve() != receipt_path:
            raise DataEvidenceError(
                "research media readback must be the canonical isolation receipt"
            )
        return {
            "deliveryMode": "private_signed",
            "releaseId": result["releaseId"],
            "manifestDigest": result["manifestDigest"],
            "subjectHash": result["subjectHash"],
            "receiptRef": result["receiptRef"],
            "receiptDigest": result["receiptDigest"],
            "anonymousContentStatus": result["anonymousContentStatus"],
            "anonymousMediaStatus": result["anonymousMediaStatus"],
            "signedMediaTtlSeconds": result["signedMediaTtlSeconds"],
            "mediaAuditEventId": result["mediaAuditEventId"],
        }
    if expected_release.get("releaseClass") != "commercial":
        raise DataEvidenceError("releaseClass must be research or commercial")
    try:
        content = load_release_content_identity(
            readiness_path,
            expected_environment=environment,
        )
        evidence = _read(media_readback_path)
        if (
            evidence.get("schema") != DELIVERY_EVIDENCE_SCHEMA
            or evidence.get("status") != "passed"
            or evidence.get("environment") != environment
            or evidence.get("target") != target
            or evidence.get("rolloutStage")
            != ("canary" if environment == "prod" else "local")
        ):
            raise DataEvidenceError("release video delivery identity drift")
        expected_content = {
            "releaseId": expected_release["releaseId"],
            "sourceOwner": "qwq_data",
            "manifestDigest": expected_release["releaseDigest"],
            "mediaManifestDigest": expected_release["mediaProbe"][
                "mediaManifestDigest"
            ],
            "importRunId": expected_release["importRunId"],
            "verifyRunId": expected_release["verifyRunId"],
        }
        for field, expected in expected_content.items():
            if content.get(field) != expected:
                raise DataEvidenceError(f"canonical Data {field} drift")
        release = evidence.get("release")
        if not isinstance(release, Mapping) or release != {
            **expected_content,
            "readinessReceiptRef": content["readinessReceiptRef"],
        }:
            raise DataEvidenceError("release video delivery release identity drift")
        video = evidence.get("video")
        delivery = evidence.get("delivery")
        playback = evidence.get("playback")
        if not all(isinstance(value, Mapping) for value in (video, delivery, playback)):
            raise DataEvidenceError("release video delivery sections are missing")
        binding = load_release_video_binding(
            readiness_path,
            expected_environment=environment,
            requested_work_id=str(video.get("workId") or ""),
            requested_asset_id=str(video.get("assetId") or ""),
        )
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
        authority = str(evidence.get("videoAuthority") or "").strip()
        public_url = str(video.get("publicUrl") or "").strip()
        if (
            urlsplit(authority).scheme != "https"
            or urlsplit(public_url).scheme != "https"
            or public_url != build_release_video_url({"mediaVideo": authority}, binding)
        ):
            raise DataEvidenceError("release video delivery public URL drift")
        validate_delivery(
            delivery,
            expected_mime_type=str(binding["expectedMimeType"]),
            expected_bytes=int(binding["expectedBytes"]),
            expected_hash=str(binding["expectedHash"]),
            expected_public_slice_key=str(binding["publicSliceKey"]),
        )
        duration = playback.get("durationMs")
        if (
            playback.get("firstFrameDecoded") is not True
            or not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration <= 0
            or evidence.get("publicSliceKey") != binding["publicSliceKey"]
            or evidence.get("rangeStatus") != 206
            or evidence.get("contentType") != binding["expectedMimeType"]
        ):
            raise DataEvidenceError("release video playback aliases drift")
    except ReleaseVideoDeliveryError as exc:
        raise DataEvidenceError(str(exc)) from exc
    return {
        "deliveryMode": "public_immutable",
        "assetId": binding["assetId"],
        "postId": binding["postId"],
        "publicSliceKey": binding["publicSliceKey"],
        "publicUrl": public_url,
        "contentType": binding["expectedMimeType"],
        "bytes": binding["expectedBytes"],
        "sha256": binding["expectedHash"],
        "durationMs": duration,
        "firstFrameDecoded": True,
        "rangeStatus": 206,
    }


def _read_readiness(path: Path) -> dict[str, Any]:
    candidate = path.expanduser().resolve()
    if path.is_symlink() or not candidate.is_file():
        raise DataEvidenceError("Data readiness receipt is missing or unsafe")
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataEvidenceError("Data readiness receipt is invalid JSON") from exc
    if not isinstance(value, dict):
        raise DataEvidenceError("Data readiness receipt must be an object")
    return value


__all__ = ["DataEvidenceError", "validate_data_evidence"]
