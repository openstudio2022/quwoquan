"""Validate formal video items inside an immutable content plan."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from core.image_safety import assess_image_publish_prefilter
from core.io import read_json
from core.article_package import sha256_file
from content.post.video.source_video import SourcedVideoEvidence
from governance.coverage.cold_start_supply import load_cold_start_supply_policy


Claim = Callable[[str, str], None]


def _validate_sourced_video(
    *,
    root: Path,
    item: Mapping[str, Any],
    ref: str,
    claim_asset: Claim,
    claim_asset_sha: Claim,
) -> list[str]:
    raw = item.get("sourceVideo")
    if not isinstance(raw, Mapping):
        return [f"item[{ref}]: sourceVideo must be an object"]
    source, admission_issues = SourcedVideoEvidence.from_mapping(raw)
    issues = [f"item[{ref}]: {message}" for message in admission_issues]
    asset_refs = item.get("assetRefs")
    if asset_refs != [source.asset_ref]:
        issues.append(
            f"item[{ref}]: sourced video assetRefs must contain only sourceVideo.assetRef"
        )
    if urlparse(source.source_ref).scheme not in {"http", "https"}:
        issues.append(f"item[{ref}]: sourceRef must be an HTTP(S) source post URL")
    evidence_refs = {
        "rightsRef": source.rights_ref,
        "mediaProbeRef": source.media_probe_ref,
        "watermarkEvidenceRef": source.watermark_evidence_ref,
        "audioRightsEvidenceRef": source.audio_rights_evidence_ref,
    }
    resolved: dict[str, Path] = {}
    for field, relative in {
        "assetRef": source.asset_ref,
        **evidence_refs,
    }.items():
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            issues.append(f"item[{ref}]: {field} escapes execution root")
            continue
        resolved[field] = path
        if not path.is_file():
            issues.append(f"item[{ref}]: sourced video {field} not found")
    asset_path = resolved.get("assetRef")
    if asset_path is not None and asset_path.is_file():
        actual_sha = sha256_file(asset_path)
        if actual_sha != source.sha256:
            issues.append(f"item[{ref}]: sourced video sha256 mismatch")
        claim_asset(ref, source.asset_ref)
        claim_asset_sha(ref, actual_sha)
    watermark_path = resolved.get("watermarkEvidenceRef")
    if watermark_path is not None and watermark_path.is_file():
        try:
            watermark = read_json(watermark_path)
        except (OSError, TypeError, ValueError):
            watermark = {}
        if (
            watermark.get("decision") != "passed"
            or watermark.get("watermarkDetected") is not False
            or watermark.get("ocrReviewed") is not True
            or int(watermark.get("sampleCount") or 0) < 12
        ):
            issues.append(
                f"item[{ref}]: sourced video watermark/OCR evidence is not passed"
            )
    audio_path = resolved.get("audioRightsEvidenceRef")
    if audio_path is not None and audio_path.is_file():
        try:
            audio = read_json(audio_path)
        except (OSError, TypeError, ValueError):
            audio = {}
        if (
            audio.get("decision") != "passed"
            or str(audio.get("status") or "") != source.audio_rights_status
        ):
            issues.append(
                f"item[{ref}]: sourced video audio rights evidence mismatch"
            )
    rights_path = resolved.get("rightsRef")
    if rights_path is not None and rights_path.is_file():
        try:
            rights = read_json(rights_path)
        except (OSError, TypeError, ValueError):
            rights = {}
        expected_rights = {
            "rightsBasis": source.rights_basis,
            "commercialAuthorizationStatus": (
                source.commercial_authorization_status
            ),
            "publicationAdmission": source.publication_admission,
            "authorizationProofUrl": source.authorization_proof_url or "",
            "termsUrl": source.terms_url or "",
            "riskAcceptanceId": source.risk_acceptance_id or "",
            "sourcePostUrl": source.source_post_url,
            "originalAssetUrl": source.original_asset_url,
        }
        if any(
            str(rights.get(field) or "") != value
            for field, value in expected_rights.items()
        ):
            issues.append(
                f"item[{ref}]: sourced video permission evidence mismatch"
            )
    probe_path = resolved.get("mediaProbeRef")
    if probe_path is not None and probe_path.is_file():
        try:
            probe = read_json(probe_path)
        except (OSError, TypeError, ValueError):
            probe = {}
        if (
            int(probe.get("durationMs") or 0) <= 0
            or int(probe.get("width") or 0) <= 0
            or int(probe.get("height") or 0) <= 0
        ):
            issues.append(f"item[{ref}]: sourced video media probe is invalid")
    return issues


def validate_video_plan_item(
    *,
    root: Path,
    item: Mapping[str, Any],
    ref: str,
    claim_asset: Claim,
    claim_asset_sha: Claim,
) -> list[str]:
    issues: list[str] = []
    if str(item.get("researchLane") or "") != "video":
        issues.append(f"item[{ref}]: video work must use researchLane=video")
    if isinstance(item.get("sourceVideo"), Mapping):
        return [
            *issues,
            *_validate_sourced_video(
                root=root,
                item=item,
                ref=ref,
                claim_asset=claim_asset,
                claim_asset_sha=claim_asset_sha,
            ),
        ]
    asset_refs = item.get("assetRefs")
    source_frames = item.get("sourceFrames")
    minimum_frames = (
        load_cold_start_supply_policy().video_delivery.minimum_segment_count
    )
    if not isinstance(asset_refs, list) or len(asset_refs) < minimum_frames:
        issues.append(
            f"item[{ref}]: video assetRefs must contain at least "
            f"{minimum_frames} source frames"
        )
        return issues
    if len({str(value) for value in asset_refs}) != len(asset_refs):
        issues.append(f"item[{ref}]: video assetRefs contains duplicates")
    if not isinstance(source_frames, list) or len(source_frames) != len(asset_refs):
        issues.append(
            f"item[{ref}]: video sourceFrames must align one-to-one with assetRefs"
        )
        return issues
    frame_by_asset = {
        str(frame.get("assetRef") or ""): frame
        for frame in source_frames
        if isinstance(frame, Mapping)
    }
    if set(frame_by_asset) != {str(value) for value in asset_refs}:
        issues.append(f"item[{ref}]: video sourceFrames asset set mismatch")
        return issues
    for raw_asset_ref in asset_refs:
        asset_ref = str(raw_asset_ref)
        frame = frame_by_asset[asset_ref]
        required_fields = (
            "sourceRef",
            "rightsRef",
            "sourceUrl",
            "creator",
            "license",
            "sha256",
            "sourceCollectionId",
        )
        missing = [field for field in required_fields if not str(frame.get(field) or "").strip()]
        if missing:
            issues.append(f"item[{ref}]: video frame {asset_ref} missing {missing}")
            continue
        asset_path = root / asset_ref
        if not asset_path.is_file():
            issues.append(f"item[{ref}]: video frame not found: {asset_ref}")
            continue
        source_meta_path = asset_path.parent.parent / "meta.json"
        try:
            source_meta = read_json(source_meta_path)
        except (OSError, TypeError, ValueError):
            source_meta = {}
        if str(source_meta.get("researchLane") or "") != "video":
            issues.append(
                f"item[{ref}]: video frame must come from researchLane=video: {asset_ref}"
            )
        index_path = asset_path.parent / "index.json"
        try:
            rows = read_json(index_path).get("assets") or []
        except (OSError, TypeError, ValueError):
            rows = []
        row = next(
            (
                candidate
                for candidate in rows
                if isinstance(candidate, Mapping)
                and str(candidate.get("fileName") or "") == asset_path.name
            ),
            None,
        )
        if row is None:
            issues.append(f"item[{ref}]: video frame absent from source index: {asset_ref}")
            continue
        for field in ("sourceUrl", "creator", "license", "sha256", "sourceCollectionId"):
            row_value = row.get(field)
            if field == "creator" and not row_value:
                row_value = row.get("credit")
            if str(frame.get(field) or "") != str(row_value or ""):
                issues.append(f"item[{ref}]: video frame {asset_ref} {field} mismatch")
        expected_rights_ref = (
            f"{index_path.resolve().relative_to(root.resolve()).as_posix()}#"
            f"{row.get('sourceAssetId') or ''}"
        )
        if str(frame.get("rightsRef") or "") != expected_rights_ref:
            issues.append(f"item[{ref}]: video frame {asset_ref} rightsRef mismatch")
        verdict = assess_image_publish_prefilter(asset_path)
        if verdict.blocks_image_publish:
            issues.append(f"item[{ref}]: video frame blocked by image safety: {asset_ref}")
        claim_asset(ref, asset_ref)
        claim_asset_sha(ref, str(row.get("sha256") or ""))
    return issues


__all__ = ["validate_video_plan_item"]
