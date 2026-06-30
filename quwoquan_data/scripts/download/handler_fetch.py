"""Per-entity download fetch implementation."""
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
from typing import Any, Mapping

from _common.paths import ensure_batch_layout, batch_root, batch_source_unit_dir
from _common.io import read_json, write_json
from _common.batch_manifest import write_batch_manifest, write_source_catalog
from _common.content_evidence import clean_source_markdown, score_source_markdown
from _common.entity_extract import entity_ref as build_entity_ref, require_domain_etype
from _common.source_catalog import (
    coverage_issues,
    platform_category,
    source_category_coverage,
    source_unit_category_issues,
    vertical_from_task_id,
)
from _common.source_unit import (
    find_source_unit_raw_snapshot,
    resolve_entity_object_dir,
    slugify,
    write_source_unit,
)
from _common.image_rules import MIN_ENTITY_IMAGES, pixel_size_issue, relevance_issue
from _common.image_safety import assess_image, assess_image_cached, dedupe_image_payloads
from _common.image_variants import image_dimensions
from _common.stage_reports import write_gate_report, write_stage_result
from download.gate import download_requirements, gate_download
from download.source_inputs import (
    curated_sources_for_entity,
    curated_images_for_entity,
    manual_body_note,
    source_plan_rights_issues,
    source_frontmatter,
)
from download.fetch import fetch_image_payload, fetch_source_payload
from download.prepare import prepare_source_plan, prepare_source_screen
from vertical.license import normalize_rights_payload, validate_image_rights

from download.handler_plan import *  # noqa: F403
from download.handler_images import *  # noqa: F403
from download.handler_images import _find_source_unit_by_plan_key  # noqa: F401
from download import handler_bridge

def _fetch_download_entity(
    *,
    task_id: str,
    batch_id: str,
    entity_type: str,
    vertical: str,
    domain: str,
    etype: str,
    entity_id: str,
    entity_index: int,
    entity_count: int,
    selected_lanes: set[str] | None = None,
) -> dict[str, Any]:
    """Fetch and gate one entity in isolation for download_fetch concurrency."""
    fetched_sources: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    failed_image = False
    print(f"[download] Fetch entity {entity_index}/{entity_count}: {entity_id}", flush=True)
    _write_download_progress(
        task_id,
        batch_id,
        status="running",
        entity_id=entity_id,
        entity_index=entity_index,
        entity_count=entity_count,
        message="entity fetch started",
    )
    # 对象同构目录：来源写成来源单元（编号 + 类目 + assets/），禁对象级散 images/。
    object_dir = resolve_entity_object_dir(task_id, batch_id, entity_id, etype_hint=entity_type)
    target_ref = build_entity_ref(domain, etype, entity_id)
    sources = _curated_sources_for_lanes(
        task_id,
        batch_id,
        entity_id,
        entity_type,
        selected_lanes,
    )
    existing_image_source_dirs = _image_lane_source_unit_dirs(object_dir)
    written_source_dirs: set[Path] = set()
    written_rejected_source_dirs: set[Path] = set()
    # 实体级 imageUrls 全部归属首个（概览类）来源单元，并标注相关性，避免无归属散图。
    image_lane_selected = selected_lanes is None or "image" in selected_lanes
    image_specs = (
        curated_images_for_entity(
            task_id,
            batch_id,
            entity_id,
            entity_type,
            research_lane=None if selected_lanes is None else "image",
        )
        if image_lane_selected
        else []
    )
    _write_download_progress(
        task_id,
        batch_id,
        status="running",
        entity_id=entity_id,
        entity_index=entity_index,
        entity_count=entity_count,
        sources=0,
        images=0,
        message="entity source plan loaded",
        plannedSources=len(sources),
        plannedImages=len(image_specs),
    )
    image_manifest: list[dict] = []
    image_rights_issues: list[str] = []
    image_quality_issues: list[str] = []
    pending_images: list[dict] = []
    required_images = download_requirements(task_id)["minImages"] if image_lane_selected else 0
    image_fetch_target = max(
        required_images,
        int(os.environ.get("QWQ_DOWNLOAD_IMAGE_FETCH_TARGET_PER_ENTITY", str(required_images + 2))),
    )
    image_candidate_limit = max(
        image_fetch_target,
        int(os.environ.get("QWQ_DOWNLOAD_IMAGE_CANDIDATE_LIMIT_PER_ENTITY", str(image_fetch_target + 4))),
    )
    for idx_img, spec in enumerate(image_specs, start=1):
        if len(pending_images) >= image_fetch_target:
            break
        if idx_img > image_candidate_limit:
            image_quality_issues.append(
                f"imageFetch: {entity_id} stopped after {image_candidate_limit} image candidate(s)"
            )
            break
        _write_download_progress(
            task_id,
            batch_id,
            status="running",
            entity_id=entity_id,
            entity_index=entity_index,
            entity_count=entity_count,
            sources=0,
            images=len(pending_images),
            message="image candidate check",
            lane="image",
            imageCandidateIndex=idx_img,
            imageCandidateCount=len(image_specs),
            imageFetchTarget=image_fetch_target,
        )
        asset_label = f"{entity_id}#{idx_img}"
        issues = validate_image_rights(spec, vertical=vertical)
        if issues:
            image_rights_issues.extend([f"{idx_img}: {issue}" for issue in issues])
            continue
        payload = _cached_image_lane_payload(object_dir, spec)
        if payload is None:
            payload = handler_bridge.call("fetch_image_payload", fetch_image_payload, spec["url"])
        if payload is None:
            image_quality_issues.append(
                f"imageFetch: {asset_label} 下载失败/非图片/过小 ({spec.get('url')})"
            )
            continue
        # 最小像素尺寸门：糊图/缩略图不进内容页。
        dims = image_dimensions(payload["bytes"]) or (0, 0)
        width, height = dims
        px_issue = pixel_size_issue(width, height, asset_id=asset_label)
        if px_issue:
            image_quality_issues.append(px_issue)
            continue
        temp_path = _write_image_check_temp_file(
            task_id,
            batch_id,
            subdir="tmp_image_checks",
            payload=payload,
        )
        try:
            verdict = _assess_source_image(temp_path, spec, task_id=task_id, batch_id=batch_id)
        finally:
            _cleanup_image_check_temp_file(temp_path)
        if verdict.blocks_image_publish:
            image_quality_issues.append(
                f"imageSafety: {asset_label} blocked ({verdict.status}) reasons={list(verdict.reasons)}"
            )
            continue
        # 相关性门：必须有与检索对象的真实相关性说明（来自 source_plan，禁通用模板串）。
        relevance = str(spec.get("relevance") or spec.get("caption") or "")
        rel_issue = relevance_issue(relevance, entity_id=entity_id, asset_id=asset_label)
        if rel_issue:
            image_quality_issues.append(rel_issue)
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

    for ordinal, source in enumerate(sources, start=1):
        _write_download_progress(
            task_id,
            batch_id,
            status="running",
            entity_id=entity_id,
            entity_index=entity_index,
            entity_count=entity_count,
            sources=len(fetched_sources),
            images=len(pending_images),
            message="source fetch started",
            lane=str(source.get("researchLane") or ""),
            sourceId=str(source.get("source_id") or ""),
            sourceIndex=ordinal,
            sourceCount=len(sources),
        )
        html_bytes: bytes | None = None
        status_code = 0
        fetched_text = ""
        raw_format = ""
        # RC3：本次抓取的同源内联 <img> 清单（与 source_md 的 source-inline 占位同序）。
        inline_images: list = []
        try:
            fetched = handler_bridge.call(
                "fetch_source_payload",
                fetch_source_payload,
                source["url"],
                source=source,
            )
            html_bytes = fetched["htmlBytes"]
            status_code = fetched["statusCode"]
            fetched_text = str(fetched.get("text") or "").strip()
            inline_images = fetched.get("inlineImages") or []
            raw_format = str((fetched.get("runtime") or {}).get("rawFormat") or "")
            source_md = source_frontmatter(source, entity_id)
            if fetched_text:
                source_md += fetched_text
        except Exception:
            source_md = source_frontmatter(source, entity_id)
        note = manual_body_note(source)
        if note:
            source_md = source_md.rstrip() + f"\n\n{note}\n"
        clean_md = clean_source_markdown(source_md, raw_format=raw_format)
        assessment = score_source_markdown(source["source_id"], source_md, entity_name=entity_id)
        quality = {
            "sourceId": source["source_id"],
            "entity": entity_id,
            "quality": assessment.quality,
            "score": assessment.score,
            "reasons": list(assessment.reasons),
            "excerpt": assessment.excerpt,
            "url": source["url"],
            "statusCode": status_code,
            "fetchSucceeded": bool(fetched_text),
            "taskProvidedBodyPresent": bool(str(source.get("body") or "").strip()),
        }
        cached_quality = _cached_source_quality_if_better(
            object_dir,
            ordinal=ordinal,
            source_id=source["source_id"],
            url=source["url"],
            candidate_quality=quality,
        )
        if cached_quality is not None:
            unit = _find_source_unit_by_plan_key(
                object_dir,
                ordinal=ordinal,
                source_id=source["source_id"],
                url=source["url"],
            )
            if unit is None:
                cached_quality = None
            else:
                source_md = (unit / "source.md").read_text(encoding="utf-8")
                # 缓存命中：复用既有已绑定的来源 source.md/资产，不再用本次 fetch 的
                # 内联清单二次注入（否则会重复下载并与已绑定占位错位）。
                inline_images = []
                clean_path = unit / "source.clean.md"
                clean_md = clean_path.read_text(encoding="utf-8") if clean_path.is_file() else ""
                page_path = find_source_unit_raw_snapshot(unit)
                html_bytes = page_path.read_bytes() if page_path else None
                # 复用既有原始快照格式，避免缓存恢复后又写错扩展名。
                raw_format = (
                    "mediawiki_api_json"
                    if page_path is not None and page_path.name == "page.raw.json"
                    else raw_format
                )
                print(
                    "[download] Preserve better cached source "
                    f"{entity_id}/{source['source_id']}: "
                    f"{cached_quality.get('quality')}({cached_quality.get('score')}) > "
                    f"{quality.get('quality')}({quality.get('score')})",
                    flush=True,
                )
                quality = {**cached_quality, "retainedFromCache": True}
        # P3：检测来源页是否含内联视频（文章类据此弃稿，不把视频强行图文化）。
        from download.fetch import html_has_inline_video

        page_has_video = False
        if html_bytes:
            page_has_video = html_has_inline_video(html_bytes.decode("utf-8", errors="replace"))
        if not page_has_video and fetched_text:
            page_has_video = html_has_inline_video(fetched_text)
        source_images, source_image_issues, source_image_funnel = _download_source_unit_images(
            source,
            task_id=task_id,
            batch_id=batch_id,
            entity_id=entity_id,
            object_dir=object_dir,
            ordinal=ordinal,
            vertical=vertical,
            extra_candidates=build_inline_image_candidates(inline_images, entity_id=entity_id),
        )
        if source_image_issues:
            image_quality_issues.extend(
                f"sourceImage:{source['source_id']}: {issue}"
                for issue in source_image_issues
            )
        manifest = write_source_unit(
            object_dir,
            ordinal=ordinal,
            source_id=source["source_id"],
            source_md=source_md,
            clean_md=clean_md,
            html_bytes=html_bytes,
            quality=quality,
            platform=source.get("platform") or "web",
            source_category=source.get("category") or source.get("platform") or "web",
            source_use_mode=source.get("sourceUseMode") or "",
            publish_media_mode=source.get("publishMediaMode") or "",
            source_role=source.get("sourceRole") or "",
            image_evidence_mode=source.get("imageEvidenceMode") or "",
            research_lane=source.get("researchLane") or "",
            license_value=source.get("license") or "",
            url=source["url"],
            title=source.get("title") or source["source_id"],
            target_ref=target_ref,
            relevance=f"覆盖 {entity_id} 的基础事实/交通/季节等",
            has_video=page_has_video,
            images=source_images,
            asset_funnel=source_image_funnel,
            raw_format=raw_format,
            task_id=task_id,
            batch_id=batch_id,
            build_variants=False,
        )
        unit_dir = batch_source_unit_dir(task_id, batch_id, str(manifest.get("sourceUnitId") or ""))
        if str(quality.get("quality") or "") == "Reject":
            rejected_dir = _move_rejected_source_unit(object_dir, unit_dir, quality=quality)
            written_rejected_source_dirs.add(rejected_dir)
            print(
                f"[download] Rejected source isolated {entity_id}/{source['source_id']}",
                flush=True,
            )
            _write_download_progress(
                task_id,
                batch_id,
                status="running",
                entity_id=entity_id,
                entity_index=entity_index,
                entity_count=entity_count,
                sources=len(fetched_sources),
                images=len(pending_images),
                message="source rejected",
                lane=str(source.get("researchLane") or ""),
                sourceId=str(source.get("source_id") or ""),
                sourceIndex=ordinal,
                sourceCount=len(sources),
            )
            continue
        written_source_dirs.add(unit_dir)
        if "wikipedia.org" in str(source.get("url") or "") or "wikivoyage.org" in str(source.get("url") or ""):
            try:
                from download.fetch import enrich_source_unit_meta_wikitext

                enrich_source_unit_meta_wikitext(unit_dir, str(source.get("url") or ""))
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[download] wikitext enrich skipped {entity_id}/{source['source_id']}: {exc}",
                    flush=True,
                )
        quality_rows.append(
            {
                "sourceId": source["source_id"],
                "quality": quality.get("quality"),
                "score": quality.get("score"),
                "url": source["url"],
                "statusCode": quality.get("statusCode", status_code),
                "retainedFromCache": bool(quality.get("retainedFromCache")),
            }
        )
        fetched_sources.append(
            {
                "sourceId": source["source_id"],
                "url": source["url"],
                "quality": quality.get("quality"),
                "score": quality.get("score"),
                "entityId": entity_id,
                "retainedFromCache": bool(quality.get("retainedFromCache")),
            }
        )
        _write_download_progress(
            task_id,
            batch_id,
            status="running",
            entity_id=entity_id,
            entity_index=entity_index,
            entity_count=entity_count,
            sources=len(fetched_sources),
            images=len(pending_images),
            message="source fetch done",
            lane=str(source.get("researchLane") or ""),
            sourceId=str(source.get("source_id") or ""),
            sourceIndex=ordinal,
            sourceCount=len(sources),
        )
    image_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for image in pending_images:
        lane = str(image.get("researchLane") or "image")
        collection_id = str(image.get("sourceCollectionId") or "").strip()
        if not collection_id:
            image_quality_issues.append(
                f"imageCollection: {image.get('url') or '?'} missing sourceCollectionId"
            )
            continue
        image_groups[(lane, collection_id)].append(image)
    for offset, ((lane, collection_id), group) in enumerate(
        sorted(image_groups.items()),
        start=1,
    ):
        first = group[0]
        source_id = (
            str(first.get("sourceId") or "").strip()
            or f"{lane}_{slugify(collection_id)}"
        )
        unit_lane = "homepage_image" if lane == "homepage" else "image"
        collection_page = str(first.get("collectionPageUrl") or first.get("sourceUrl") or "")
        collection_md = (
            "---\n"
            f"researchLane: {unit_lane}\n"
            f"sourceCollectionId: {collection_id}\n"
            f"creator: {first.get('creator') or first.get('credit') or ''}\n"
            f"url: {collection_page}\n"
            f"license: {first.get('license') or ''}\n"
            "---\n\n"
            f"{entity_id} 图片来源集合，仅供结构化资产与授权链使用。\n"
        )
        manifest = write_source_unit(
            object_dir,
            ordinal=len(sources) + offset,
            source_id=source_id,
            source_md=collection_md,
            quality={
                "sourceId": source_id,
                "entity": entity_id,
                "quality": "B-fact",
                "score": 1,
                "reasons": ["structured image collection"],
                "url": collection_page,
                "fetchSucceeded": True,
            },
            platform=str(first.get("platform") or "image_collection"),
            source_category="image_collection",
            source_use_mode="licensed_adaptation",
            research_lane=unit_lane,
            license_value=str(first.get("license") or ""),
            url=collection_page,
            title=f"{entity_id} image collection {collection_id}",
            target_ref=target_ref,
            relevance=f"{entity_id} 同一来源图片集合",
            images=group,
            task_id=task_id,
            batch_id=batch_id,
            build_variants=False,
        )
        written_source_dirs.add(batch_source_unit_dir(task_id, batch_id, str(manifest.get("sourceUnitId") or "")))
    kept_images = len(pending_images)
    count_issue = None
    if image_lane_selected and required_images > 0 and kept_images < required_images:
        count_issue = (
            f"imageCount: {entity_id} 仅下到 {kept_images} 张合格图"
            f"（要求 ≥{required_images}）"
            if required_images <= MIN_ENTITY_IMAGES
            else (
                f"imageCount: {entity_id} 仅下到 {kept_images} 张合格去重图"
                f"（规模化任务要求 ≥{required_images}）"
            )
        )
    fetch_issues = list(image_rights_issues)
    if count_issue:
        fetch_issues.append(count_issue)
    if image_lane_selected and required_images > 0 and kept_images == 0 and not image_rights_issues:
        fetch_issues.append(
            "imageFetch: 未下到真实图片，请在 source_plan 提供可用 imageUrls(CC/PD/授权)"
        )
    blocking_fetch_issues = fetch_issues if required_images > 0 else []
    preserved_image_dirs: set[Path] = set()
    if fetch_issues:
        preserved_image_dirs = existing_image_source_dirs - written_source_dirs
        written_source_dirs.update(preserved_image_dirs)
    pruned_units = _prune_stale_source_units(
        object_dir,
        written_source_dirs,
        selected_lanes=selected_lanes,
    )
    pruned_rejected_units = _prune_stale_rejected_source_units(
        object_dir,
        written_rejected_source_dirs,
        selected_lanes=selected_lanes,
    )
    if preserved_image_dirs:
        print(
            f"[download] Preserved {len(preserved_image_dirs)} previous image source unit(s) "
            f"for failed repair of {entity_id}",
            flush=True,
        )
    if pruned_units:
        print(
            f"[download] Pruned {len(pruned_units)} stale source unit(s) for {entity_id}: "
            + ", ".join(pruned_units),
            flush=True,
        )
    if pruned_rejected_units:
        print(
            f"[download] Pruned {len(pruned_rejected_units)} stale rejected source unit(s) for {entity_id}: "
            + ", ".join(pruned_rejected_units),
            flush=True,
        )
    if image_lane_selected:
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="image_rights",
            ref=entity_id,
            passed=not image_rights_issues,
            issues=image_rights_issues,
            evidence_summary={"plannedImages": len(image_specs), "blockedImages": len(image_rights_issues)},
            next_step="image_fetch",
            fallback_stage="source_plan" if image_rights_issues else None,
        )
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="image_fetch",
            ref=entity_id,
            passed=not blocking_fetch_issues,
            issues=blocking_fetch_issues,
            evidence_summary={
                "plannedImages": len(image_specs),
                "downloadedImages": kept_images,
                "minRequired": required_images,
                "rejectedForQuality": image_quality_issues,
                "nonBlockingImageIssues": fetch_issues if not blocking_fetch_issues else [],
            },
            next_step="quality_analysis",
            fallback_stage="source_plan" if blocking_fetch_issues else None,
        )
    if image_lane_selected and blocking_fetch_issues:
        failed_image = True
    print(
        f"[download] Entity done {entity_index}/{entity_count}: {entity_id} "
        f"sources={len(sources)} images={kept_images}",
        flush=True,
    )
    _write_download_progress(
        task_id,
        batch_id,
        status="running",
        entity_id=entity_id,
        entity_index=entity_index,
        entity_count=entity_count,
        sources=len(sources),
        images=kept_images,
        message="entity fetch done",
    )


    return {
        "entityId": entity_id,
        "entityIndex": entity_index,
        "sourceCount": len(sources),
        "imageCount": kept_images,
        "fetchedSources": fetched_sources,
        "qualityRows": quality_rows,
        "failedImage": failed_image,
    }

__all__ = [name for name in globals() if not name.startswith("__")]
