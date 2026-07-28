"""Build one admitted sourced-video unit with frozen rights and scan evidence."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
from typing import Any

from content.post.video.package_common import sha256_file
from content.post.video.source_video import SourcedVideoEvidence
from content.source.source_unit import resolve_entity_object_dir, write_source_unit
from content.source.sourced_video_admission import (
    admitted_audio_evidence,
    probe_sourced_video,
    scan_sourced_video_watermark,
)
from core.paths import (
    execution_source_unit_dir,
    relative_execution_ref,
)
from core.schema import assert_valid
from core.content_source_registry import load_content_source_registry
from core.video_source_admission import (
    VIDEO_SOURCE_KINDS,
    assert_video_source_admitted,
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
    publication_admission: str,
    authorization_proof_url: str | None,
    terms_url: str | None,
    risk_acceptance_id: str | None,
    audio_rights_status: str,
    audio_authorization_proof_url: str | None,
    model_release_status: str,
    property_release_status: str,
    takedown_policy: str,
    entity_type: str | None = None,
) -> Path:
    """Materialize one source unit only when every admission fact passes."""
    if not source_video_path.is_file():
        raise FileNotFoundError(source_video_path)
    object_dir = resolve_entity_object_dir(
        execution_id,
        object_ref,
        etype_hint=entity_type,
    )
    source_kind = str(source_unit.get("sourceKind") or "").strip()
    if source_kind not in VIDEO_SOURCE_KINDS:
        raise ValueError(f"unsupported sourced video sourceKind: {source_kind}")
    source_id = str(source_unit.get("sourceId") or "").strip()
    assert_video_source_admitted(
        load_content_source_registry(),
        source_id=source_id,
        source_kind=source_kind,
        publication_admission=publication_admission,
    )
    manifest = write_source_unit(
        object_dir,
        ordinal=int(source_unit.get("ordinal") or 1),
        source_id=source_id,
        source_md=attribution_text,
        clean_md=attribution_text,
        platform=platform,
        source_category="tourism_video",
        source_kind=source_kind,
        extractor="sourced_video_direct_download",
        policy_revision="sourced-video-attribution-v1",
        source_use_mode="attribution_no_watermark",
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
                    "usageScope": "app_publish",
                    "collectionPageUrl": source_post_url,
                    "authorizationProof": authorization_proof_url or "",
                    "rightsAuditStatus": "verified",
                    "rightsAuditIssues": [],
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
        "authorizationProofUrl": authorization_proof_url,
        "termsUrl": terms_url,
        "riskAcceptanceId": risk_acceptance_id,
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
        authorization_proof_url=authorization_proof_url,
        terms_url=terms_url,
        risk_acceptance_id=risk_acceptance_id,
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
