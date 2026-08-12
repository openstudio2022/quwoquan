"""Prepare one governed manual video input without entering acquisition.

The preparation bundle is disposable operator evidence.  It does not create an
acquisition receipt, campaign, canonical post, or release.  The only public
entrypoint is the Data ``task prepare-video-manual-input`` command.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.image_decode import probe_image_bytes
from core.io import read_json, write_json
from core.schema import assert_valid

from content.source.professional_safety_evidence import file_sha256
from content.source.professional_video_manual_input_media import (
    command_profile,
    ffmpeg_executable,
    ffmpeg_version,
    render_contact_sheet,
    run_transcode,
    transformation,
)
from content.source.professional_video_probe import probe_professional_video
from content.source.sourced_video_admission import probe_sourced_video

PREPARATION_SCHEMA = (
    "quwoquan_data.professional_video_manual_input_preparation_receipt"
)
PREPARATION_INVALID = "DATA.SOURCE.VIDEO_MANUAL_INPUT_INVALID"
SOURCE_SHA_DRIFT = "DATA.SOURCE.VIDEO_MANUAL_INPUT_SHA_DRIFT"
DUPLICATE_OUTPUT = "DATA.SOURCE.DUPLICATE_ASSET"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_ASSET_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]*$")
_MIN_DURATION_MS = 3_000
_MAX_DURATION_MS = 180_000


class VideoManualInputPreparationError(ValueError):
    """Typed fail-closed preparation error."""

    def __init__(self, code: str, issue: str) -> None:
        self.code = code
        self.issue = issue
        super().__init__(f"{code} {issue}")


def _fail(issue: str, *, code: str = PREPARATION_INVALID) -> None:
    raise VideoManualInputPreparationError(code, issue)


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _relative_ref(value: object, *, label: str) -> Path:
    raw = str(value or "").strip()
    relative = Path(raw)
    if (
        not raw
        or relative.is_absolute()
        or ".." in relative.parts
        or "\x00" in raw
    ):
        _fail(f"{label} must be a safe relative reference")
    return relative


def _absolute_root(path: Path, *, label: str, must_exist: bool) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        _fail(f"{label} must be absolute")
    if expanded.is_symlink():
        _fail(f"{label} must not be a symlink")
    if must_exist and (not expanded.exists() or not expanded.is_dir()):
        _fail(f"{label} must be an existing directory")
    if expanded.exists() and not expanded.is_dir():
        _fail(f"{label} must be a directory")
    return expanded.resolve()


def _existing_file(root: Path, ref: object, *, label: str) -> Path:
    relative = _relative_ref(ref, label=label)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _fail(f"{label} must not traverse a symlink")
    try:
        resolved = current.resolve(strict=True)
    except FileNotFoundError:
        _fail(f"{label} is missing")
    if root not in resolved.parents or not resolved.is_file():
        _fail(f"{label} escapes its declared root or is not a regular file")
    return resolved


def _validated_text(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if not text or "\x00" in text:
        _fail(f"{label} must be non-empty")
    return text


def _validated_timestamp(value: object) -> str:
    timestamp = _validated_text(value, label="preparedAt")
    normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        _fail("preparedAt must be an ISO-8601 timestamp")
    if parsed.tzinfo is None:
        _fail("preparedAt must include a timezone")
    return timestamp


def _validated_source_page(value: object) -> str:
    source_page = _validated_text(value, label="sourcePageUrl")
    parsed = urlparse(source_page)
    if parsed.scheme != "https" or not parsed.hostname:
        _fail("sourcePageUrl must be an HTTPS URL")
    return source_page


def _safety_skeleton(
    *,
    asset_id: str,
    entity_id: str,
    observed_entity_id: str,
    source_page_url: str,
    source_sha256: str,
    transformation: str,
    video_ref: str,
    video_sha256: str,
    video_bytes: int,
    contact_sheet_ref: str,
    contact_sheet_sha256: str,
    media_probe: Mapping[str, Any],
    prepared_at: str,
) -> dict[str, Any]:
    skeleton = {
        "schema": "quwoquan_data.manual_asset_safety_evidence",
        "assetId": asset_id,
        "entityId": entity_id,
        "observedEntityId": observed_entity_id,
        "sourcePageUrl": source_page_url,
        "fileRef": video_ref,
        "fileSha256": video_sha256,
        "bytes": video_bytes,
        "contactSheetRef": contact_sheet_ref,
        "contactSheetSha256": contact_sheet_sha256,
        "sourceContentSha256": source_sha256,
        "transformation": transformation,
        "mediaProbe": dict(media_probe),
        "status": "pending",
        "entityMatch": "unknown",
        "privacyRisk": "unknown",
        "minorRisk": "unknown",
        "maliciousMediaRisk": "unknown",
        "watermarkStatus": "unknown",
        "reviewedAt": prepared_at,
        "reviewer": "pending_independent_review",
    }
    assert_valid(
        skeleton,
        "source",
        "professional_video_safety_evidence",
        label="professional video safety evidence skeleton",
    )
    return skeleton


def _receipt_digest(receipt: Mapping[str, Any]) -> str:
    return _digest({key: value for key, value in receipt.items() if key != "receiptDigest"})


def _load_receipt(
    path: Path,
    *,
    output_root: Path,
    expected_plan_digest: str | None = None,
    verify_probe: bool,
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        _fail(f"preparation receipt is missing or is a symlink: {path}")
    payload = read_json(path)
    if not isinstance(payload, dict):
        _fail("preparation receipt must be an object")
    assert_valid(
        payload,
        "source",
        "professional_video_manual_input_preparation_receipt",
        label="professional video manual input preparation receipt",
    )
    if payload.get("receiptDigest") != _receipt_digest(payload):
        _fail("preparation receipt digest mismatch")
    if expected_plan_digest and payload.get("planDigest") != expected_plan_digest:
        _fail("preparation bundle planDigest collision")
    receipt_ref = Path(str(payload["bundleRef"])) / "receipt.json"
    if (output_root / receipt_ref).resolve() != path.resolve():
        _fail("preparation receipt path is not canonical")
    bindings = (
        ("videoRef", "videoSha256"),
        ("contactSheetRef", "contactSheetSha256"),
        ("safetyEvidenceSkeletonRef", "safetyEvidenceSkeletonSha256"),
    )
    resolved: dict[str, Path] = {}
    for ref_field, digest_field in bindings:
        candidate = _existing_file(
            output_root,
            payload[ref_field],
            label=ref_field,
        )
        if file_sha256(candidate) != payload[digest_field]:
            _fail(f"{ref_field} SHA-256 drift")
        resolved[ref_field] = candidate
    skeleton = read_json(resolved["safetyEvidenceSkeletonRef"])
    assert_valid(
        skeleton,
        "source",
        "professional_video_safety_evidence",
        label="professional video safety evidence skeleton",
    )
    contact = probe_image_bytes(resolved["contactSheetRef"].read_bytes())
    if not contact.succeeded:
        _fail("preparation contact sheet is not decodable")
    if verify_probe:
        observed = probe_professional_video(resolved["videoRef"])
        if observed != payload["mediaProbe"]:
            _fail("prepared video mediaProbe drift")
    return payload


def _reject_duplicate_outputs(
    output_root: Path,
    *,
    video_sha256: str,
    contact_sheet_sha256: str,
) -> None:
    bundles = output_root / "manual-inputs"
    if not bundles.exists():
        return
    if bundles.is_symlink() or not bundles.is_dir():
        _fail("manual-inputs root must be a regular directory")
    for receipt_path in sorted(bundles.glob("*/receipt.json")):
        receipt = _load_receipt(
            receipt_path,
            output_root=output_root,
            verify_probe=False,
        )
        if receipt["videoSha256"] == video_sha256:
            _fail(
                f"prepared video duplicates {receipt['preparationId']}",
                code=DUPLICATE_OUTPUT,
            )
        if receipt["contactSheetSha256"] == contact_sheet_sha256:
            _fail(
                f"contact sheet duplicates {receipt['preparationId']}",
                code=DUPLICATE_OUTPUT,
            )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def prepare_video_manual_input(
    *,
    source_root: Path,
    source_ref: str,
    source_sha256: str,
    output_root: Path,
    asset_id: str,
    entity_id: str,
    observed_entity_id: str,
    source_page_url: str,
    start_ms: int,
    duration_ms: int,
    prepared_at: str,
    operator_id: str,
) -> tuple[dict[str, Any], Path]:
    """Create or replay one atomic, digest-bound manual-input bundle."""

    source_root = _absolute_root(source_root, label="sourceRoot", must_exist=True)
    source_relative = _relative_ref(source_ref, label="sourceRef").as_posix()
    source = _existing_file(source_root, source_relative, label="sourceRef")
    if not _SHA256.fullmatch(source_sha256):
        _fail("sourceSha256 must be a lowercase sha256 digest")
    observed_source_sha256 = file_sha256(source)
    if observed_source_sha256 != source_sha256:
        _fail("sourceSha256 does not match source bytes", code=SOURCE_SHA_DRIFT)
    if not _ASSET_ID.fullmatch(asset_id):
        _fail("assetId is invalid")
    entity_id = _validated_text(entity_id, label="entityId")
    observed_entity_id = _validated_text(
        observed_entity_id,
        label="observedEntityId",
    )
    if entity_id != observed_entity_id:
        _fail("observedEntityId must exactly equal entityId")
    source_page_url = _validated_source_page(source_page_url)
    prepared_at = _validated_timestamp(prepared_at)
    operator_id = _validated_text(operator_id, label="operatorId")
    if isinstance(start_ms, bool) or not isinstance(start_ms, int) or start_ms < 0:
        _fail("startMs must be a non-negative integer")
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or not _MIN_DURATION_MS <= duration_ms <= _MAX_DURATION_MS
    ):
        _fail("durationMs must be between 3000 and 180000")

    source_probe = probe_sourced_video(source)
    if start_ms + duration_ms > int(source_probe["durationMs"]) + 250:
        _fail("requested trim exceeds source duration")
    executable = ffmpeg_executable()
    version = ffmpeg_version(executable, fail=_fail)
    transformation_value = transformation(
        start_ms=start_ms,
        duration_ms=duration_ms,
    )
    normalized_command = command_profile(
        start_ms=start_ms,
        duration_ms=duration_ms,
    )
    command_digest = _digest({"argv": normalized_command})
    plan = {
        "schema": "quwoquan_data.professional_video_manual_input_preparation_plan",
        "assetId": asset_id,
        "entityId": entity_id,
        "observedEntityId": observed_entity_id,
        "sourcePageUrl": source_page_url,
        "sourceRef": source_relative,
        "sourceSha256": source_sha256,
        "startMs": start_ms,
        "durationMs": duration_ms,
        "transformation": transformation_value,
        "commandDigest": command_digest,
    }
    plan_digest = _digest(plan)
    raw_digest = plan_digest.removeprefix("sha256:")
    preparation_id = f"video-manual-input-{raw_digest[:16]}"
    bundle_ref = f"manual-inputs/{raw_digest}"
    output_candidate = output_root.expanduser()
    if not output_candidate.is_absolute():
        _fail("outputRoot must be absolute")
    if output_candidate.exists():
        resolved_output_root = _absolute_root(
            output_candidate,
            label="outputRoot",
            must_exist=True,
        )
        existing_receipt = resolved_output_root / bundle_ref / "receipt.json"
        if existing_receipt.exists():
            receipt = _load_receipt(
                existing_receipt,
                output_root=resolved_output_root,
                expected_plan_digest=plan_digest,
                verify_probe=True,
            )
            return receipt, existing_receipt
    if output_candidate.is_symlink():
        _fail("outputRoot must not be a symlink")
    output_candidate.mkdir(parents=True, exist_ok=True)
    resolved_output_root = _absolute_root(
        output_candidate,
        label="outputRoot",
        must_exist=True,
    )
    bundles_root = resolved_output_root / "manual-inputs"
    if bundles_root.exists() and (bundles_root.is_symlink() or not bundles_root.is_dir()):
        _fail("manual-inputs root must be a regular directory")
    bundles_root.mkdir(parents=True, exist_ok=True)
    bundle_path = resolved_output_root / bundle_ref

    with tempfile.TemporaryDirectory(
        prefix=".video-manual-input-",
        dir=resolved_output_root,
    ) as temporary:
        stage_bundle = Path(temporary) / "bundle"
        stage_bundle.mkdir()
        stage_video = stage_bundle / "video.mp4"
        stage_contact = stage_bundle / "contact-sheet.jpg"
        stage_skeleton = stage_bundle / "safety-evidence-skeleton.json"
        stage_receipt = stage_bundle / "receipt.json"
        run_transcode(
            source,
            stage_video,
            executable=executable,
            start_ms=start_ms,
            duration_ms=duration_ms,
            fail=_fail,
        )
        video_sha256 = file_sha256(stage_video)
        if video_sha256 == source_sha256:
            _fail("prepared video bytes equal source bytes", code=DUPLICATE_OUTPUT)
        media_probe = probe_professional_video(stage_video)
        if not (
            media_probe["playable"] is True
            and media_probe["motionVideo"] is True
            and media_probe["premiumPlayableEligible"] is True
        ):
            _fail("prepared video is not playable motion Premium media")
        if int(media_probe["frameCount"]) > int(source_probe["frameCount"]):
            _fail("prepared video frame count exceeds source; synthetic frames suspected")
        if int(media_probe["durationMs"]) > duration_ms + 1_000:
            _fail("prepared video duration exceeds requested trim")
        render_contact_sheet(
            stage_video,
            stage_contact,
            frame_count=int(media_probe["frameCount"]),
            fail=_fail,
        )
        contact_sheet_sha256 = file_sha256(stage_contact)
        video_ref = f"{bundle_ref}/video.mp4"
        contact_sheet_ref = f"{bundle_ref}/contact-sheet.jpg"
        safety_ref = f"{bundle_ref}/safety-evidence-skeleton.json"
        skeleton = _safety_skeleton(
            asset_id=asset_id,
            entity_id=entity_id,
            observed_entity_id=observed_entity_id,
            source_page_url=source_page_url,
            source_sha256=source_sha256,
            transformation=transformation_value,
            video_ref=video_ref,
            video_sha256=video_sha256,
            video_bytes=stage_video.stat().st_size,
            contact_sheet_ref=contact_sheet_ref,
            contact_sheet_sha256=contact_sheet_sha256,
            media_probe=media_probe,
            prepared_at=prepared_at,
        )
        write_json(stage_skeleton, skeleton)
        stable = {
            "schema": PREPARATION_SCHEMA,
            "preparationId": preparation_id,
            "planDigest": plan_digest,
            "preparedAt": prepared_at,
            "operatorId": operator_id,
            "sourceRef": source_relative,
            "sourceSha256": source_sha256,
            "sourceBytes": source.stat().st_size,
            "entityId": entity_id,
            "observedEntityId": observed_entity_id,
            "sourcePageUrl": source_page_url,
            "startMs": start_ms,
            "durationMs": duration_ms,
            "transformation": transformation_value,
            "syntheticFrames": False,
            "bundleRef": bundle_ref,
            "videoRef": video_ref,
            "videoSha256": video_sha256,
            "videoBytes": stage_video.stat().st_size,
            "contactSheetRef": contact_sheet_ref,
            "contactSheetSha256": contact_sheet_sha256,
            "safetyEvidenceSkeletonRef": safety_ref,
            "safetyEvidenceSkeletonSha256": file_sha256(stage_skeleton),
            "mediaProbe": media_probe,
            "executor": {
                "tool": "ffmpeg",
                "version": version,
                "commandDigest": command_digest,
            },
        }
        receipt = {**stable, "receiptDigest": _digest(stable)}
        assert_valid(
            receipt,
            "source",
            "professional_video_manual_input_preparation_receipt",
            label="professional video manual input preparation receipt",
        )
        write_json(stage_receipt, receipt)
        _reject_duplicate_outputs(
            resolved_output_root,
            video_sha256=video_sha256,
            contact_sheet_sha256=contact_sheet_sha256,
        )
        if bundle_path.exists():
            replay = _load_receipt(
                bundle_path / "receipt.json",
                output_root=resolved_output_root,
                expected_plan_digest=plan_digest,
                verify_probe=True,
            )
            return replay, bundle_path / "receipt.json"
        try:
            stage_bundle.rename(bundle_path)
        except FileExistsError:
            replay = _load_receipt(
                bundle_path / "receipt.json",
                output_root=resolved_output_root,
                expected_plan_digest=plan_digest,
                verify_probe=True,
            )
            return replay, bundle_path / "receipt.json"
        _fsync_directory(bundles_root)
    final_receipt = bundle_path / "receipt.json"
    verified = _load_receipt(
        final_receipt,
        output_root=resolved_output_root,
        expected_plan_digest=plan_digest,
        verify_probe=True,
    )
    return verified, final_receipt


__all__ = [
    "DUPLICATE_OUTPUT",
    "PREPARATION_INVALID",
    "SOURCE_SHA_DRIFT",
    "VideoManualInputPreparationError",
    "prepare_video_manual_input",
]
