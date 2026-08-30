"""Validate formal video items inside an immutable content plan."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from core.io import read_json
from core.article_package import sha256_file
from content.post.video.source_video import SourcedVideoEvidence


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
            "publicationAdmission": source.effective_publication_admission,
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
    vertical: str,
    item: Mapping[str, Any],
    ref: str,
    claim_asset: Claim,
    claim_asset_sha: Claim,
) -> list[str]:
    issues: list[str] = []
    if str(item.get("researchLane") or "") != "video":
        issues.append(f"item[{ref}]: video work must use researchLane=video")
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


__all__ = ["validate_video_plan_item"]
