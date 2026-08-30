"""Build one admitted sourced-video unit with frozen rights and scan evidence."""
from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.content_source_registry import load_content_source_registry
from core.paths import (
    execution_source_unit_dir,
    relative_execution_ref,
)
from core.schema import assert_valid
from core.video_source_admission import (
    VIDEO_SOURCE_KINDS,
    assert_video_distribution_use_allowed,
)
from content.post.video.package_common import sha256_file
from content.post.video.source_video import SourcedVideoEvidence
from content.source.professional_video_receipt import (
    assert_observed_popularity_signals,
    assert_publishable_media_probe,
)
from content.source.source_unit import resolve_entity_object_dir, write_source_unit
from content.source.sourced_video_admission import (
    admitted_audio_evidence,
    probe_sourced_video,
    scan_sourced_video_watermark,
)


DISTRIBUTION_DECISIONS = ("research_allowed", "commercial_allowed")


def _commercial_source_use_mode(
    *,
    commercial_authorization_status: str,
    rights_basis: str,
    authorization_proof_url: str | None,
) -> str:
    """Derive a commercial use mode only from verified rights."""
    if commercial_authorization_status != "verified":
        raise ValueError(
            "commercial sourced video requires verified authorization"
        )
    normalized_rights_basis = str(rights_basis or "").strip()
    non_licensed_markers = {
        "attribution_no_watermark",
        "risk_accepted_attribution_only",
        "unknown",
        "unverified",
        "not_verified",
        "unspecified",
        "none",
        "n/a",
    }
    if (
        not normalized_rights_basis
        or normalized_rights_basis.casefold() in non_licensed_markers
    ):
        raise ValueError("commercial sourced video requires a licensed rights basis")
    if not str(authorization_proof_url or "").strip().startswith("https://"):
        raise ValueError(
            "commercial sourced video requires HTTPS authorization proof"
        )
    return "licensed_adaptation"


def _source_use_mode(
    *,
    distribution_decision: str,
    commercial_authorization_status: str,
    rights_basis: str,
    authorization_proof_url: str | None,
) -> str:
    """Derive the use mode from the explicit per-asset distribution decision."""
    if distribution_decision not in DISTRIBUTION_DECISIONS:
        raise ValueError(
            "sourced video distributionDecision is not admissible: "
            f"{distribution_decision}"
        )
    if distribution_decision == "research_allowed":
        return "rights_audit_only"
    return _commercial_source_use_mode(
        commercial_authorization_status=commercial_authorization_status,
        rights_basis=rights_basis,
        authorization_proof_url=authorization_proof_url,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_admitted_sourced_video_unit(
    *,
    execution_id: str,
    object_ref: str,
    source_unit: dict[str, Any],
    source_video_path: Path,
    original_creator_name: str,
    platform: str,
    source_post_url: str,
    original_asset_url: str,
    attribution_text: str,
    rights_basis: str,
    commercial_authorization_status: str,
    distribution_decision: str,
    authorization_proof_url: str | None,
    terms_url: str | None,
    audio_rights_status: str,
    audio_authorization_proof_url: str | None,
    model_release_status: str,
    property_release_status: str,
    takedown_policy: str,
    entity_type: str | None = None,
    object_dir: Path | None = None,
    frozen_source_unit_id: str = "",
) -> Path:
    """Materialize one source unit only when every admission fact passes.

    receipt 协议 execution 的 video 对象根在 `posts/video/**`（载体分根布局），
    此时调用方显式传 object_dir；缺省仍按 entityRef 解析 entities 对象目录。
    """
    if not source_video_path.is_file():
        raise FileNotFoundError(source_video_path)
    if object_dir is None:
        object_dir = resolve_entity_object_dir(
            execution_id,
            object_ref,
            etype_hint=entity_type,
        )
    source_kind = str(source_unit.get("sourceKind") or "").strip()
    if source_kind not in VIDEO_SOURCE_KINDS:
        raise ValueError(f"unsupported sourced video sourceKind: {source_kind}")
    source_id = str(source_unit.get("sourceId") or "").strip()
    source_use_mode = _source_use_mode(
        distribution_decision=distribution_decision,
        commercial_authorization_status=commercial_authorization_status,
        rights_basis=rights_basis,
        authorization_proof_url=authorization_proof_url,
    )
    research_release = source_use_mode == "rights_audit_only"
    publication_admission = (
        "research_release" if research_release else "commercial_release"
    )
    assert_video_distribution_use_allowed(
        load_content_source_registry(),
        source_id=source_id,
        source_kind=source_kind,
        publication_admission=publication_admission,
    )
    from core.source_layout import build_layout

    entity_name = str(object_ref or "").strip("/").rsplit("/", 1)[-1]
    manifest = write_source_unit(
        object_dir,
        ordinal=int(source_unit.get("ordinal") or 1),
        source_id=source_id,
        source_md=attribution_text,
        clean_md=attribution_text,
        quality={
            "sourceId": source_id,
            "entity": entity_name,
            "quality": "High",
            "score": 100,
            "reasons": [
                "sourced_video_admission",
                "acquisition_receipt_binding",
            ],
            "url": source_post_url,
            "statusCode": 200,
            "fetchSucceeded": True,
        },
        layout=build_layout(
            source_kind=source_kind,
            extractor="sourced_video_direct_download",
            title=str(source_unit.get("title") or attribution_text),
            blocks=[
                {
                    "type": "paragraph",
                    "text": attribution_text,
                    "sectionSlug": "",
                }
            ],
        ),
        platform=platform,
        source_category="tourism_video",
        source_kind=source_kind,
        extractor="sourced_video_direct_download",
        policy_revision="sourced-video-attribution",
        source_use_mode=source_use_mode,
        rights_mode=(
            "rights_audit_only"
            if research_release
            else "attribution_no_watermark"
        ),
        publish_media_mode="attributed_external_video",
        source_role="primary_video",
        research_lane="video",
        license_value=rights_basis,
        url=source_post_url,
        title=str(source_unit.get("title") or attribution_text),
        target_ref=object_ref,
        relevance=str(source_unit.get("relevance") or ""),
        has_video=True,
        execution_id=execution_id,
        source={
            "canonicalUrl": source_post_url,
            "finalUrl": source_post_url,
        },
        frozen_source_unit_id=frozen_source_unit_id,
    )
    unit_dir = execution_source_unit_dir(
        execution_id,
        str(manifest["sourceUnitId"]),
    )

    source_suffix = source_video_path.suffix.lower()
    if source_suffix not in {".mp4", ".webm", ".ogv", ".mov"}:
        raise ValueError(f"unsupported sourced video extension: {source_suffix}")
    asset_path = unit_dir / "assets" / f"source{source_suffix}"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_video_path, asset_path)

    media_probe = probe_sourced_video(asset_path)
    watermark = scan_sourced_video_watermark(asset_path)
    audio = admitted_audio_evidence(
        asset_path,
        declared_status=audio_rights_status,
        authorization_proof_url=audio_authorization_proof_url,
        allow_unverified_rights=research_release,
    )
    collected_at = datetime.now(UTC).isoformat()
    media_probe_path = unit_dir / "media" / "probe.json"
    watermark_path = unit_dir / "media" / "watermark_evidence.json"
    audio_path = unit_dir / "rights" / "audio_rights_evidence.json"
    _write_json(media_probe_path, media_probe)
    _write_json(watermark_path, watermark)
    _write_json(audio_path, audio)
    if watermark["decision"] != "passed":
        raise ValueError("sourced video watermark/OCR admission blocked")
    if audio["decision"] != "passed":
        raise ValueError("sourced video audio rights admission blocked")

    asset_sha256 = sha256_file(asset_path)
    professional_identity = (
        str(source_unit.get("professionalAcquisitionReceiptRef") or "").strip(),
        str(source_unit.get("professionalAssetId") or "").strip(),
        str(source_unit.get("professionalContentSha256") or "").strip(),
    )
    if any(professional_identity) and not all(professional_identity):
        raise ValueError(
            "professional sourced video requires receipt, assetId, and contentSha256"
        )
    popularity_signals: dict[str, Any] | None = None
    professional_media_probe: dict[str, Any] | None = None
    if professional_identity[0]:
        if professional_identity[2] != asset_sha256:
            raise ValueError("professional sourced video contentSha256 drift")
        if source_unit.get("premiumPlayableEligible") is not True:
            raise ValueError("professional sourced video is not Premium-playable")
        raw_professional_probe = source_unit.get("mediaProbe")
        assert_publishable_media_probe(
            raw_professional_probe,
            asset_id=professional_identity[1],
        )
        assert isinstance(raw_professional_probe, dict)
        for field in (
            "width",
            "height",
            "frameCount",
            "framesPerSecond",
            "durationMs",
            "codec",
        ):
            if raw_professional_probe.get(field) != media_probe.get(field):
                raise ValueError(
                    f"professional sourced video media probe drift: {field}"
                )
        professional_media_probe = dict(raw_professional_probe)
        raw_signals = source_unit.get("popularitySignals")
        assert_observed_popularity_signals(
            raw_signals,
            asset_id=professional_identity[1],
        )
        assert isinstance(raw_signals, dict)
        popularity_signals = dict(raw_signals)
    rights_status = (
        str(source_unit.get("rightsStatus") or "unverified").strip()
        if research_release
        else "verified"
    )
    if rights_status not in {"verified", "unverified", "unknown"}:
        raise ValueError(
            f"research sourced video rightsStatus is not admissible: {rights_status}"
        )
    rights_issues = [
        str(item).strip()
        for item in source_unit.get("rightsIssues") or []
        if str(item).strip()
    ]
    if rights_status != "verified" and not rights_issues:
        rights_issues = ["commercial distribution authorization is unverified"]
    content_type = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".ogv": "video/ogg",
        ".mov": "video/quicktime",
    }[source_suffix]
    _write_json(
        unit_dir / "assets" / "index.json",
        {
            "assets": [
                {
                    "sourceAssetId": "source_video_001",
                    "fileName": asset_path.name,
                    "url": original_asset_url,
                    "requestedUrl": original_asset_url,
                    "normalizedFromUrl": original_asset_url,
                    "sourceUrl": source_post_url,
                    "contentType": content_type,
                    "width": int(media_probe["width"]),
                    "height": int(media_probe["height"]),
                    "bytes": asset_path.stat().st_size,
                    "sha256": asset_sha256,
                    "license": rights_basis,
                    "credit": original_creator_name,
                    "creator": original_creator_name,
                    "termsUrl": terms_url or "",
                    "licenseSnapshot": (
                        f"{rights_basis} recorded by sourced-video admission"
                    ),
                    "usageScope": (
                        "internal_reference" if research_release else "app_publish"
                    ),
                    "collectionPageUrl": source_post_url,
                    "authorizationProof": authorization_proof_url or "",
                    "professionalAcquisitionReceiptRef": professional_identity[0],
                    "professionalAssetId": professional_identity[1],
                    "professionalContentSha256": professional_identity[2],
                    "professionalMediaProbe": professional_media_probe,
                    "popularitySignals": popularity_signals,
                    "premiumPlayableEligible": (
                        source_unit.get("premiumPlayableEligible") is True
                    ),
                    "rightsAuditStatus": rights_status,
                    "rightsAuditIssues": rights_issues,
                    "distributionDecision": distribution_decision,
                    "modelReleaseStatus": model_release_status,
                    "propertyReleaseStatus": property_release_status,
                    "fetchedAt": collected_at,
                    "caption": str(source_unit.get("relevance") or ""),
                    "relevance": str(source_unit.get("relevance") or ""),
                    "variants": [],
                }
            ]
        },
    )

    rights_path = unit_dir / "rights" / "permission_evidence.json"
    rights = {
        "schema": "quwoquan_data.sourced_video_permission_evidence",
        "rightsBasis": rights_basis,
        "commercialAuthorizationStatus": commercial_authorization_status,
        "publicationAdmission": publication_admission,
        "distributionDecision": distribution_decision,
        "authorizationRequired": rights_status != "verified",
        "rightsIssues": rights_issues,
        "authorizationProofUrl": authorization_proof_url,
        "termsUrl": terms_url,
        "riskAcceptanceId": None,
        "sourcePostUrl": source_post_url,
        "originalAssetUrl": original_asset_url,
        "audioAuthorizationProofUrl": audio_authorization_proof_url,
        "collectedAt": collected_at,
    }
    _write_json(rights_path, rights)

    evidence = SourcedVideoEvidence(
        asset_ref=relative_execution_ref(asset_path, execution_id),
        source_ref=source_post_url,
        rights_ref=relative_execution_ref(rights_path, execution_id),
        media_probe_ref=relative_execution_ref(media_probe_path, execution_id),
        watermark_evidence_ref=relative_execution_ref(
            watermark_path,
            execution_id,
        ),
        audio_rights_evidence_ref=relative_execution_ref(
            audio_path,
            execution_id,
        ),
        sha256=asset_sha256,
        is_original=False,
        original_creator_name=original_creator_name,
        platform=platform,
        source_post_url=source_post_url,
        original_asset_url=original_asset_url,
        attribution_text=attribution_text,
        rights_basis=rights_basis,
        commercial_authorization_status=commercial_authorization_status,
        publication_admission=publication_admission,
        distribution_decision=distribution_decision,
        authorization_proof_url=authorization_proof_url,
        terms_url=terms_url,
        watermark_status="absent",
        audio_rights_status=str(audio["status"]),
        model_release_status=model_release_status,
        property_release_status=property_release_status,
        collected_at=str(rights["collectedAt"]),
        takedown_policy=takedown_policy,
        direct_download=True,
        access_control_bypassed=False,
        drm_detected=False,
    )
    admission_issues = evidence.admission_issues()
    if admission_issues:
        raise ValueError(
            "sourced video admission failed: "
            + "; ".join(admission_issues)
        )
    evidence_payload = evidence.to_dict()
    assert_valid(
        evidence_payload,
        "content",
        "sourced_video_evidence",
    )
    output_path = unit_dir / "sourced_video_evidence.json"
    _write_json(output_path, evidence_payload)
    return output_path


__all__ = ["write_admitted_sourced_video_unit"]
