"""Download image, source-unit cache and rejection helpers."""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from threading import Lock
from typing import Any, Mapping, Sequence

from core.paths import ensure_execution_command_layout, execution_root
from core.io import read_json, write_json
from content.execution.runtime_state import write_execution_runtime_state, write_source_catalog
from content.post.article.evidence_text import clean_source_markdown, score_source_markdown
from governance.coverage.entity_extract import entity_ref as build_entity_ref, require_domain_etype
from core.source_catalog import (
    coverage_issues,
    platform_category,
    source_category_coverage,
    source_unit_category_issues,
    vertical_from_task_id,
)
from content.source.source_unit import (
    find_source_unit_raw_snapshot,
    iter_source_units,
    remove_object_source_ref,
    resolve_entity_object_dir,
    write_source_unit,
)
from core.image_rules import MIN_ENTITY_IMAGES, pixel_size_issue, relevance_issue
from core.image_safety import assess_image, assess_image_cached, dedupe_image_payloads
from core.image_variants import image_dimensions
from core.page_media import DownloadedPageAsset, PageImagePlacement, PageImagePlacementType
from content.execution.stage_reports import write_gate_report, write_stage_result
from content.source.gate import download_requirements, gate_download
from content.source.source_inputs import (
    curated_sources_for_entity,
    curated_images_for_entity,
    manual_body_note,
    source_plan_rights_issues,
    source_frontmatter,
)
from content.source.fetch_payload import fetch_source_payload
from content.source.fetch_images import fetch_image_payload, fetch_page_image_payload
from content.source.prepare import prepare_source_plan, prepare_source_screen
from governance.coverage.license import normalize_rights_payload, validate_image_rights

from content.source.handler_plan import SOURCE_UNIT_MAX_IMAGE_BYTES, _source_unit_lane_in_scope
from content.source.source_asset_identity import (
    source_screen_report_ref as _source_screen_report_ref,
    stable_source_image_collection_id,
)

from content.source.handler_images import (
    _assess_source_image, _cached_source_image_payload,
    _cleanup_image_check_temp_file, _write_image_check_temp_file,
)

def _download_source_unit_images(
    source: Mapping[str, Any],
    *,
    execution_id: str,
    entity_id: str,
    object_dir: Path,
    ordinal: int,
    vertical: str,
    extra_candidates: Sequence[Mapping[str, Any]] = (),
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Download and gate images that belong to the same text source unit.

    Article/homepage source images are part of that source's draft evidence.
    They must stay attached to the source unit instead of being mixed into the
    independent image-work collection lane.

    下载该来源 imageUrls 中所有与底稿相符、且通过 权利→抓取→像素→安全→相关性 五道门、
    再经感知去重的真实图（广告/图标/占位/视频在这些门里被排除），而不是只留 1 张。
    返回 (images, issues, funnel)：funnel 记录候选数、保留数、按原因聚合的丢弃明细与去重数，
    用于写入 assets/index.json 做候选/丢弃可审计。
    """
    images: list[dict[str, Any]] = []
    issues: list[str] = []
    drops: list[dict[str, object]] = []
    fetch_failures: list[dict[str, object]] = []

    def _funnel(candidate_count: int, dedupe_removed: int) -> dict[str, Any]:
        reason_counts: dict[str, int] = {}
        for drop in drops:
            key = str(drop.get("reason") or "unknown").split(":", 1)[0]
            reason_counts[key] = reason_counts.get(key, 0) + 1
        return {
            "candidateCount": candidate_count,
            "keptCount": len(images),
            "droppedCount": len(drops),
            "dedupeRemoved": dedupe_removed,
            "quotaMode": "complete_source_page",
            "dropReasonCounts": reason_counts,
            "drops": drops,
            "fetchFailures": fetch_failures,
        }

    raw_images = source.get("imageUrls") or []
    if not isinstance(raw_images, list):
        msg = f"{source.get('source_id') or '?'} imageUrls must be a list"
        return images, [msg], _funnel(0, 0)
    # RC3：同源内联 <img> 候选与计划 imageUrls 合并，走同一套五道硬门（不绕许可），
    # 经 placeholderId 把通过门的内联图回连 source.md 段落占位。
    all_candidates = list(raw_images) + list(extra_candidates or [])
    source_id = str(source.get("source_id") or "")
    candidate_count = len(all_candidates)
    for idx_img, raw in enumerate(all_candidates, start=1):
        candidate_group = str(raw.get("groupId") or "") if isinstance(raw, Mapping) else ""
        if not isinstance(raw, Mapping):
            issues.append(f"{source_id} image[{idx_img}] invalid payload")
            drops.append({"slug": f"{source_id}#{idx_img}", "reason": "invalidPayload"})
            continue
        spec = {
            **{
                "license": source.get("license") or "",
                "credit": source.get("credit") or "",
                "termsUrl": source.get("termsUrl") or "",
                "licenseSnapshot": source.get("licenseSnapshot") or "",
                "authorizationProof": source.get("authorizationProof") or "",
                "usageScope": source.get("usageScope") or "",
                "sourceUrl": source.get("url") or "",
                "platform": source.get("platform") or "",
                "sourceCollectionId": "",
                "creator": source.get("credit") or "",
                "collectionPageUrl": source.get("url") or "",
            },
            **{k: v for k, v in raw.items() if v not in ("", None)},
        }
        spec["sourceCollectionId"] = stable_source_image_collection_id(
            entity_id=entity_id,
            source_id=source_id,
            spec=spec,
        )
        label = f"{entity_id}/{source_id}#{idx_img}"
        spec_url = str(spec.get("url") or "")
        rights_issues = validate_image_rights(spec, vertical=vertical)
        if rights_issues:
            issues.extend(f"{label}: {issue}" for issue in rights_issues)
            drops.append({"slug": label, "url": spec_url, "reason": f"rights: {rights_issues[0]}"})
            continue
        payload = _cached_source_image_payload(
            object_dir,
            ordinal=ordinal,
            source_id=source_id,
            spec=spec,
        )
        if payload is None:
            placement_type = str(spec.get("placementType") or "")
            is_structured_page_image = placement_type in {
                item.value for item in PageImagePlacementType
            }
            if is_structured_page_image:
                page_fetch = fetch_page_image_payload(
                    str(spec.get("url") or ""),
                    max_bytes=SOURCE_UNIT_MAX_IMAGE_BYTES,
                )
                if page_fetch.succeeded:
                    assert page_fetch.payload is not None
                    payload = page_fetch.payload.to_asset_mapping()
                else:
                    assert page_fetch.failure is not None
                    issues.append(
                        f"{label}: page image fetch {page_fetch.failure.value} "
                        f"(status={page_fetch.status_code}, attempts={page_fetch.attempt_count})"
                    )
                    drops.append(
                        {
                            "slug": label,
                            "url": spec_url,
                            "reason": f"fetch:{page_fetch.failure.value}",
                            "statusCode": page_fetch.status_code,
                        }
                    )
                    fetch_failures.append(
                        page_fetch.as_failure_evidence(
                            source_order=int(spec.get("sourceOrder") or 0)
                        )
                    )
                    continue
            else:
                payload = fetch_image_payload(
                    str(spec.get("url") or ""),
                    max_bytes=SOURCE_UNIT_MAX_IMAGE_BYTES,
                )
        if payload is None:
            size_note = (
                f"/too large >{SOURCE_UNIT_MAX_IMAGE_BYTES} bytes"
                if SOURCE_UNIT_MAX_IMAGE_BYTES
                else ""
            )
            issues.append(f"{label}: imageFetch failed/non-image/too small{size_note} ({spec.get('url')})")
            drops.append({"slug": label, "url": spec_url, "reason": "fetch: 抓取失败/非图片/视频/过小或过大"})
            continue
        dims = image_dimensions(payload["bytes"]) or (0, 0)
        width, height = dims
        px_issue = pixel_size_issue(width, height, asset_id=label)
        if px_issue:
            issues.append(px_issue)
            drops.append({"slug": label, "url": spec_url, "reason": f"pixel: {px_issue}"})
            continue
        temp_file = _write_image_check_temp_file(
            execution_id,
            subdir="tmp_source_unit_image_checks",
            payload=payload,
        )
        try:
            verdict = _assess_source_image(temp_file, spec, execution_id=execution_id)
        finally:
            _cleanup_image_check_temp_file(temp_file)
        if verdict.blocks_image_publish:
            issues.append(f"{label}: imageSafety blocked ({verdict.status}) reasons={list(verdict.reasons)}")
            drops.append({"slug": label, "url": spec_url, "reason": f"safety: {verdict.status} {list(verdict.reasons)}"})
            continue
        relevance = str(spec.get("relevance") or spec.get("caption") or "")
        rel_issue = relevance_issue(relevance, entity_id=entity_id, asset_id=label)
        if rel_issue:
            issues.append(rel_issue)
            drops.append({"slug": label, "url": spec_url, "reason": f"relevance: {rel_issue}"})
            continue
        rights = normalize_rights_payload(spec)
        asset_payload = {
                "bytes": payload["bytes"],
                "ext": payload["ext"],
                "url": payload.get("url") or spec.get("url") or "",
                "requestedUrl": payload.get("requestedUrl") or spec.get("url") or "",
                "normalizedFromUrl": payload.get("normalizedFromUrl") or "",
                "sourceUrl": spec.get("sourceUrl") or spec.get("url") or "",
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
                "caption": str(spec.get("caption") or relevance),
                "relevance": relevance,
                "slug": f"{source_id}_{idx_img}",
                # RC3：内联同源图回连 source.md 段落占位（非内联候选为空字符串）。
                "placeholderId": str(spec.get("placeholderId") or ""),
                # 布局/封面候选语义透传（source.layout.json figure 同源；无结构源为默认值）。
                "placementType": str(spec.get("placementType") or ""),
                "groupId": candidate_group,
                "sectionSlug": str(spec.get("sectionSlug") or ""),
                "sourceOrder": int(spec.get("sourceOrder") or 0),
                "coverCandidateRank": int(spec.get("coverCandidateRank") or 0),
                "subjectKey": str(spec.get("subjectKey") or ""),
                "isMapLike": bool(spec.get("isMapLike")),
                "fileTitle": str(spec.get("fileTitle") or ""),
                "pageResolvedTitle": str(spec.get("pageResolvedTitle") or ""),
                "pageId": int(spec.get("pageId") or 0),
                "pageRevisionId": int(spec.get("pageRevisionId") or 0),
                "pageContentSha256": str(spec.get("pageContentSha256") or ""),
                "renderedImageCount": int(spec.get("renderedImageCount") or 0),
            }
        placement_type_raw = str(spec.get("placementType") or "")
        if placement_type_raw in {item.value for item in PageImagePlacementType}:
            file_title = str(spec.get("fileTitle") or "").strip()
            if not file_title:
                file_title = str(spec.get("url") or "").split("?", 1)[0].rsplit("/", 1)[-1]
            placement = PageImagePlacement(
                file_title=file_title or f"page-image-{idx_img}.jpg",
                caption=str(spec.get("caption") or relevance),
                section_slug=str(spec.get("sectionSlug") or ""),
                paragraph_index=int(spec.get("paragraphIndex") or 0),
                source_order=int(spec.get("sourceOrder") or 0),
                placement_type=PageImagePlacementType(placement_type_raw),
                group_id=candidate_group,
                cover_rank=int(spec.get("coverCandidateRank") or 0),
                placeholder_id=str(spec.get("placeholderId") or ""),
                subject_key=str(spec.get("subjectKey") or ""),
                is_map_like=bool(spec.get("isMapLike")),
            )
            typed_asset = DownloadedPageAsset(
                placement=placement,
                content=payload["bytes"],
                ext=str(payload["ext"]),
                url=str(payload.get("url") or spec.get("url") or ""),
                requested_url=str(payload.get("requestedUrl") or spec.get("url") or ""),
                source_url=str(spec.get("sourceUrl") or spec.get("url") or ""),
                content_type=str(payload.get("contentType") or ""),
                width=width,
                height=height,
                license_name=str(rights.get("license") or spec.get("license") or ""),
                credit=str(rights.get("credit") or spec.get("credit") or ""),
                terms_url=str(rights.get("termsUrl") or spec.get("termsUrl") or ""),
                authorization_proof=str(
                    spec.get("authorizationProof")
                    or rights.get("termsUrl")
                    or spec.get("termsUrl")
                    or spec.get("sourceUrl")
                    or ""
                ),
            )
            asset_payload.update(typed_asset.as_dict())
        images.append(asset_payload)
    images, duplicates = dedupe_image_payloads(images)
    if duplicates:
        issues.append(f"{source_id}: source image dedupe removed {len(duplicates)} near-duplicate image(s)")
    funnel = _funnel(candidate_count, len(duplicates))
    structured_page_images = any(
        str(spec.get("placementType") or "")
        in {"lead", "infoboxLead", "inline", "groupMember", "locatorMap"}
        for spec in all_candidates
        if isinstance(spec, Mapping)
    )
    incomplete_downloads = [
        row for row in drops if str(row.get("reason") or "").startswith("fetch:")
    ]
    if structured_page_images and incomplete_downloads:
        return (
            images,
            [
                "DATA.MEDIA.DOWNLOAD_INCOMPLETE: "
                f"{len(incomplete_downloads)} structured page image(s) failed to download"
            ],
            funnel,
        )
    # 策略排除（许可/像素/安全/去重）保留在 funnel；结构化页面的网络下载漏失必须阻断。
    if images:
        return images, [], funnel
    return images, issues, funnel
