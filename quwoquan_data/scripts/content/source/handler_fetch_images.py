"""Entity image preparation for the source download stage."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.image_rules import pixel_size_issue, relevance_issue
from core.media_processing_policy import MEDIA_PROCESSING_POLICY
from core.image_safety import dedupe_image_payloads
from core.image_variants import image_dimensions
from content.source.gate import download_requirements
from content.source.handler_images import (
    _assess_source_image,
    _cached_image_lane_payload,
    _cleanup_image_check_temp_file,
    _write_image_check_temp_file,
)
from content.source.handler_plan import _write_download_progress
from content.source.fetch_images import fetch_image_payload
from governance.coverage.license import normalize_rights_payload, validate_image_rights


@dataclass(frozen=True)
class PreparedEntityImages:
    image_manifest: list[dict[str, Any]]
    rights_issues: list[str]
    video_rights_issues: list[str]
    quality_issues: list[str]
    rejected_by_category: dict[str, int]
    pending_images: list[dict[str, Any]]
    required_image_work_images: int
    planned_homepage_source_images: int
    required_homepage_media: int
    required_video_frames: int
    required_images: int


def prepare_entity_images(
    *,
    execution_id: str,
    entity_id: str,
    entity_index: int,
    entity_count: int,
    vertical: str,
    object_dir: Path,
    sources: list[dict[str, Any]],
    image_specs: list[dict[str, Any]],
    image_lane_selected: bool,
    homepage_media_selected: bool,
    video_lane_selected: bool,
) -> PreparedEntityImages:
    image_manifest: list[dict] = []
    image_rights_issues: list[str] = []
    video_rights_issues: list[str] = []
    image_quality_issues: list[str] = []
    rejected_by_category = {
        "fetch_or_non_image": 0,
        "pixel_too_small": 0,
        "safety_or_watermark": 0,
        "rights": 0,
        "duplicate": 0,
        "other": 0,
    }
    pending_images: list[dict] = []
    requirements = download_requirements(execution_id)
    required_image_work_images = requirements.min_images if image_lane_selected else 0
    planned_homepage_source_images = sum(
        len(source.get("imageUrls") or [])
        for source in sources
        if str(source.get("researchLane") or "") == "homepage"
        and isinstance(source.get("imageUrls"), list)
    )
    required_homepage_media = (
        requirements.min_homepage_media if homepage_media_selected else 0
    )
    required_video_frames = requirements.min_video_frames if video_lane_selected else 0
    required_images = (
        required_image_work_images
        + required_homepage_media
        + required_video_frames
    )
    image_fetch_target = (
        required_image_work_images
        + MEDIA_PROCESSING_POLICY.image_fetch_target_surplus
    )
    image_candidate_limit = (
        image_fetch_target + MEDIA_PROCESSING_POLICY.image_candidate_surplus
    )
    pending_image_work_count = 0
    image_work_candidate_index = 0
    for idx_img, spec in enumerate(image_specs, start=1):
        lane = str(spec.get("researchLane") or "").strip()
        is_page_owned_homepage_media = lane == "homepage"
        if lane == "image":
            image_work_candidate_index += 1
        if lane == "image" and pending_image_work_count >= image_fetch_target:
            continue
        if (
            lane == "image"
            and image_work_candidate_index > image_candidate_limit
        ):
            image_quality_issues.append(
                f"imageFetch: {entity_id} stopped after {image_candidate_limit} image candidate(s)"
            )
            rejected_by_category["other"] += 1
            continue
        _write_download_progress(
            execution_id,
            status="running",
            entity_id=entity_id,
            entity_index=entity_index,
            entity_count=entity_count,
            sources=0,
            images=len(pending_images),
            message="image candidate check",
            lane=lane,
            imageCandidateIndex=idx_img,
            imageCandidateCount=len(image_specs),
            imageFetchTarget=(
                "complete_source_page" if is_page_owned_homepage_media else image_fetch_target
            ),
            imageSpecScope=(
                "homepage_source_page"
                if is_page_owned_homepage_media
                else ("video_frame" if lane == "video" else "image_work")
            ),
        )
        asset_label = f"{entity_id}#{idx_img}"
        issues = validate_image_rights(spec, vertical=vertical)
        if issues:
            target = video_rights_issues if lane == "video" else image_rights_issues
            target.extend([f"{idx_img}: {issue}" for issue in issues])
            rejected_by_category["rights"] += 1
            continue
        payload = _cached_image_lane_payload(object_dir, spec)
        if payload is None:
            payload = fetch_image_payload(spec["url"])
        if payload is None:
            image_quality_issues.append(
                f"imageFetch: {asset_label} 下载失败/非图片/过小 ({spec.get('url')})"
            )
            rejected_by_category["fetch_or_non_image"] += 1
            continue
        # 最小像素尺寸门：糊图/缩略图不进内容页。
        dims = image_dimensions(payload["bytes"]) or (0, 0)
        width, height = dims
        px_issue = pixel_size_issue(width, height, asset_id=asset_label)
        if px_issue:
            image_quality_issues.append(px_issue)
            rejected_by_category["pixel_too_small"] += 1
            continue
        temp_path = _write_image_check_temp_file(
            execution_id,
            subdir="tmp_image_checks",
            payload=payload,
        )
        try:
            verdict = _assess_source_image(temp_path, spec, execution_id=execution_id)
        finally:
            _cleanup_image_check_temp_file(temp_path)
        if verdict.blocks_image_publish:
            image_quality_issues.append(
                f"imageSafety: {asset_label} blocked ({verdict.status}) reasons={list(verdict.reasons)}"
            )
            rejected_by_category["safety_or_watermark"] += 1
            continue
        # 相关性门：必须有与检索对象的真实相关性说明（来自 source_plan，禁通用模板串）。
        relevance = str(spec.get("relevance") or spec.get("caption") or "")
        rel_issue = relevance_issue(relevance, entity_id=entity_id, asset_id=asset_label)
        if rel_issue:
            image_quality_issues.append(rel_issue)
            rejected_by_category["other"] += 1
            continue
        rights = normalize_rights_payload(spec)
        pending_images.append(
            {
                "bytes": payload["bytes"],
                "ext": payload["ext"],
                "url": payload.get("url") or spec["url"],
                "requestedUrl": payload.get("requestedUrl") or spec["url"],
                "normalizedFromUrl": payload.get("normalizedFromUrl") or "",
                "sourceUrl": spec.get("sourceUrl") or spec["url"],
                "contentType": payload.get("contentType") or "",
                "width": width,
                "height": height,
                "license": rights.get("license") or spec.get("license") or "",
                "credit": rights.get("credit") or spec.get("credit") or "",
                "termsUrl": rights.get("termsUrl") or spec.get("termsUrl") or "",
                "licenseSnapshot": rights.get("licenseSnapshot") or spec.get("licenseSnapshot") or "",
                "usageScope": rights.get("usageScope") or spec.get("usageScope") or "",
                "generationModel": rights.get("generationModel") or "",
                "generationPromptHash": rights.get("generationPromptHash") or "",
                "generatedAt": rights.get("generatedAt") or "",
                "syntheticDisclosure": rights.get("syntheticDisclosure") or "",
                "sourceCollectionId": spec.get("sourceCollectionId") or "",
                "creator": spec.get("creator") or spec.get("credit") or "",
                "collectionPageUrl": spec.get("collectionPageUrl") or spec.get("sourceUrl") or "",
                "authorizationProof": spec.get("authorizationProof") or "",
                "researchLane": spec.get("researchLane") or "image",
                "sourceId": spec.get("sourceId") or "",
                "caption": str(spec.get("caption") or relevance),
                "relevance": relevance,
                "slug": f"{entity_id}_{idx_img}",
                "sha256": payload.get("sha256"),
            }
        )
        if lane == "image":
            pending_image_work_count += 1
        image_manifest.append({**payload, "url": spec["url"], **rights})
    # 感知哈希去重（落盘前）：剔除同实体近重复图，避免画报/详情页重复观感。
    pending_images, dup_idx = dedupe_image_payloads(pending_images)
    if dup_idx:
        image_quality_issues.append(
            f"imageDedupe: {entity_id} 剔除 {len(dup_idx)} 张近重复图"
        )
        image_manifest = [
            m for i, m in enumerate(image_manifest) if i not in set(dup_idx)
        ]
        rejected_by_category["duplicate"] += len(dup_idx)

    return PreparedEntityImages(
        image_manifest=image_manifest,
        rights_issues=image_rights_issues,
        video_rights_issues=video_rights_issues,
        quality_issues=image_quality_issues,
        rejected_by_category=rejected_by_category,
        pending_images=pending_images,
        required_image_work_images=required_image_work_images,
        planned_homepage_source_images=planned_homepage_source_images,
        required_homepage_media=required_homepage_media,
        required_video_frames=required_video_frames,
        required_images=required_images,
    )
