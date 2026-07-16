"""Per-entity download fetch implementation."""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sys
import tempfile
from threading import Lock
from typing import Any, Mapping

from core.data_issue import (
    DataIssueCode, DataIssueStage,
    DataIssueLane,
    DataRecoveryAction,
    data_issues,
)
from core.paths import ensure_execution_command_layout, execution_root, execution_source_unit_dir
from core.io import read_json, write_json
from content.execution.runtime_state import write_execution_runtime_state, write_source_catalog
from content.post.evidence_text import clean_source_markdown, score_source_markdown
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
    resolve_entity_object_dir,
    slugify,
    write_source_unit,
)
from core.image_rules import MIN_ENTITY_IMAGES, pixel_size_issue, relevance_issue
from core.image_safety import assess_image, assess_image_cached, dedupe_image_payloads
from core.image_variants import image_dimensions
from content.execution.stage_reports import write_gate_report, write_stage_result
from content.source.gate import download_requirements, gate_download
from content.source.source_inputs import (
    curated_sources_for_entity,
    curated_homepage_media_for_entity,
    curated_images_for_entity,
    manual_body_note,
    source_plan_rights_issues,
    source_frontmatter,
)
from content.source.fetch_payload import fetch_source_payload
from content.source.fetch_images import fetch_image_payload
from content.source.handler_fetch_images import prepare_entity_images
from content.source.prepare import prepare_source_plan, prepare_source_screen
from governance.coverage.license import normalize_rights_payload, validate_image_rights

from content.source.handler_plan import _curated_sources_for_lanes, _write_download_progress
from content.source.handler_images import (
    _cached_source_quality_if_better,
    _download_source_unit_images,
    _find_source_unit_by_plan_key,
    _image_lane_source_unit_dirs,
    _move_rejected_source_unit,
    _prune_stale_rejected_source_units,
    _prune_stale_source_units,
)
from content.source.inline_images import build_inline_image_candidates

def _canonicalize_source_url(url: str) -> str:
    """canonical URL 归一（消重键）：去 scheme/query/fragment，小写 host，去尾斜杠。"""
    text = str(url or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"^https?://", "", text)
    text = text.split("#", 1)[0].split("?", 1)[0]
    return text.rstrip("/")


def _is_non_open_baike_source(source: Mapping[str, Any]) -> bool:
    """版权使用方式只消费显式 sourceKind，不按 host 猜 kind。"""
    from core.baike_source_contract import SOURCE_USE_MODES

    source_kind = str(source.get("sourceKind") or "")
    return SOURCE_USE_MODES.get(source_kind) == "factual_reference_only"


def _requires_factual_compression(source: Mapping[str, Any]) -> bool:
    """百科正文压缩口径只来自 registry sourceUseMode。"""
    return _is_non_open_baike_source(source)


def _publishable_homepage_source_image_count(images: list[dict[str, Any]]) -> int:
    """Count same-source images that may enter the homepage visual surface."""
    count = 0
    for image in images:
        if bool(image.get("isMapLike")):
            continue
        if str(image.get("placementType") or "") == "locatorMap":
            continue
        try:
            if int(image.get("coverCandidateRank") or 0) < 0:
                continue
        except (TypeError, ValueError):
            continue
        count += 1
    return count


def _fetch_download_entity(
    *,
    execution_id: str,
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
        execution_id,
        status="running",
        entity_id=entity_id,
        entity_index=entity_index,
        entity_count=entity_count,
        message="entity fetch started",
    )
    # 对象同构目录：来源写成来源单元（编号 + 类目 + assets/），禁对象级散 images/。
    object_dir = resolve_entity_object_dir(execution_id, entity_id, etype_hint=entity_type)
    target_ref = build_entity_ref(domain, etype, entity_id)
    sources = _curated_sources_for_lanes(
        execution_id,
        entity_id,
        entity_type,
        selected_lanes,
    )
    existing_image_source_dirs = _image_lane_source_unit_dirs(object_dir)
    written_source_dirs: set[Path] = set()
    written_rejected_source_dirs: set[Path] = set()
    # 实体级 imageUrls 全部归属首个（概览类）来源单元，并标注相关性，避免无归属散图。
    image_lane_selected = selected_lanes is None or "image" in selected_lanes
    homepage_media_selected = selected_lanes is None or "homepage" in selected_lanes
    image_work_specs = (
        curated_images_for_entity(
            execution_id,
            entity_id,
            entity_type,
            research_lane=None if selected_lanes is None else "image",
        )
        if image_lane_selected
        else []
    )
    homepage_media_specs = (
        curated_homepage_media_for_entity(
            execution_id,
            entity_id,
            entity_type,
        )
        if homepage_media_selected
        else []
    )
    # Page-owned homepage media are enumerated evidence, not a search pool:
    # process the complete list before applying the independent image-work
    # budget. A page image must end in download, explicit policy exclusion, or
    # a typed hard failure; it must never disappear because an unrelated image
    # work filled a quota first.
    image_specs = [*homepage_media_specs, *image_work_specs]
    homepage_media_spec_count = len(homepage_media_specs)
    _write_download_progress(
        execution_id,
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
    image_result = prepare_entity_images(
        execution_id=execution_id,
        entity_id=entity_id,
        entity_index=entity_index,
        entity_count=entity_count,
        vertical=vertical,
        object_dir=object_dir,
        sources=sources,
        image_specs=image_specs,
        homepage_media_spec_count=homepage_media_spec_count,
        image_lane_selected=image_lane_selected,
        homepage_media_selected=homepage_media_selected,
    )
    image_manifest = image_result.image_manifest
    image_rights_issues = image_result.rights_issues
    image_quality_issues = image_result.quality_issues
    rejected_by_category = dict(image_result.rejected_by_category)
    pending_images = image_result.pending_images
    required_image_work_images = image_result.required_image_work_images
    planned_homepage_source_images = image_result.planned_homepage_source_images
    required_homepage_media = image_result.required_homepage_media
    required_images = image_result.required_images

    # 同实体源级去重：canonical URL 归一后重复的候选直接 Reject（跨源站消重）。
    seen_canonical_urls: set[str] = set()
    kept_source_homepage_images = 0

    for ordinal, source in enumerate(sources, start=1):
        _write_download_progress(
            execution_id,
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
        fetch_runtime: dict[str, Any] = {}
        # 统一结构化 IR（wiki wikitext / baike HTML 前端产物；None = 该源无结构前端）。
        source_layout: dict[str, Any] | None = None
        # RC3：本次抓取的同源内联 <img> 清单（与 source_md 的 source-inline 占位同序）。
        inline_images: list = []
        try:
            fetched = fetch_source_payload(
                source["url"],
                source=source,
            )
            html_bytes = fetched["htmlBytes"]
            status_code = fetched["statusCode"]
            fetched_text = str(fetched.get("text") or "").strip()
            inline_images = fetched.get("inlineImages") or []
            source_layout = fetched.get("layout") if isinstance(fetched.get("layout"), dict) else None
            fetch_runtime = (
                dict(fetched.get("runtime") or {})
                if isinstance(fetched.get("runtime"), Mapping)
                else {}
            )
            raw_format = str(fetch_runtime.get("rawFormat") or "")
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
        quality_value = assessment.quality
        quality_score = assessment.score
        quality_reasons = list(assessment.reasons)

        # 同实体 canonical URL 消重：同一 URL 归一后第二次出现直接 Reject。
        canonical_url = _canonicalize_source_url(str(source.get("url") or ""))
        if canonical_url and canonical_url in seen_canonical_urls:
            quality_value = "Reject"
            quality_score = 0
            quality_reasons.append("duplicate_source_url")
        elif canonical_url:
            seen_canonical_urls.add(canonical_url)

        # homepage 底稿事实门：通用 UGC 打分不足以保底稿，主页 lane 叠加事实密度/
        # 消歧义/重定向检查（西岭雪山类弱源、消歧义页在此打回，触发候选补源）。
        source_identity_issue = ""
        if (
            quality_value != "Reject"
            and str(source.get("researchLane") or "") == "homepage"
            and str(source.get("sourceRole") or "") != "support"
        ):
            from content.source.research.homepage_text_quality import homepage_text_quality_issue
            from content.source.research.text_match import _wiki_resolved_title_matches_entity

            resolved_title = str(fetch_runtime.get("resolvedTitle") or "").strip()
            if (
                str(source.get("sourceKind") or "") == "wikipedia"
                and resolved_title
                and not _wiki_resolved_title_matches_entity(resolved_title, entity_id)
            ):
                source_identity_issue = (
                    "resolved_wiki_title_mismatch: "
                    f"requested={fetch_runtime.get('requestedTitle') or entity_id}; "
                    f"resolved={resolved_title}; entity={entity_id}"
                )

            homepage_issue = source_identity_issue or homepage_text_quality_issue(
                fetched_text or source_md,
                entity_id,
            )
            if homepage_issue:
                quality_value = "Reject"
                quality_score = 0
                quality_reasons.append(homepage_issue)

        # factual_reference_only 来源（百度/搜狗/今日头条百科）事实化压缩：
        # >2000 字压至约 50%，1000-2000 轻度，<=1000 不压；
        # 结果进 source.clean.md，账目进 quality。
        compression_note: dict = {}
        if quality_value != "Reject" and _requires_factual_compression(source):
            from core.factual_compression import factual_compress_text

            compressed = factual_compress_text(clean_md or fetched_text, entity_name=entity_id)
            if compressed["policy"] != "none":
                clean_md = compressed["text"]
                quality_reasons.append(f"factual_compression_{compressed['policy']}")
            compression_note = {
                "policy": compressed["policy"],
                "originalChars": compressed["originalChars"],
                "compressedChars": compressed["compressedChars"],
            }

        quality = {
            "sourceId": source["source_id"],
            "entity": entity_id,
            "quality": quality_value,
            "score": quality_score,
            "reasons": quality_reasons,
            "excerpt": assessment.excerpt,
            "url": source["url"],
            "statusCode": status_code,
            "fetchSucceeded": bool(fetched_text),
            "taskProvidedBodyPresent": bool(str(source.get("body") or "").strip()),
        }
        if compression_note:
            quality["factualCompression"] = compression_note
        cached_quality = _cached_source_quality_if_better(
            object_dir,
            ordinal=ordinal,
            source_id=source["source_id"],
            url=source["url"],
            candidate_quality=quality,
        )
        if cached_quality is not None and not source_identity_issue:
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
        from content.source.fetch_text import html_has_inline_video

        page_has_video = False
        if html_bytes:
            page_has_video = html_has_inline_video(html_bytes.decode("utf-8", errors="replace"))
        if not page_has_video and fetched_text:
            page_has_video = html_has_inline_video(fetched_text)
        source_images, source_image_issues, source_image_funnel = _download_source_unit_images(
            source,
            execution_id=execution_id,
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
        source_drop_categories = source_image_funnel.get("dropReasonCounts")
        if isinstance(source_drop_categories, Mapping):
            category_map = {
                "fetch": "fetch_or_non_image",
                "pixel": "pixel_too_small",
                "safety": "safety_or_watermark",
                "rights": "rights",
                "relevance": "other",
                "invalidPayload": "other",
            }
            for category, count in source_drop_categories.items():
                target_category = category_map.get(str(category), "other")
                rejected_by_category[target_category] += int(count or 0)
        source_for_unit = dict(source)
        for key in ("requestedTitle", "resolvedTitle", "redirectChain"):
            if key in fetch_runtime:
                source_for_unit[key] = fetch_runtime[key]
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
            source_kind=source.get("sourceKind") or "",
            extractor=source.get("extractor") or "",
            policy_revision=source.get("policyRevision") or "",
            source_use_mode=source.get("sourceUseMode") or "",
            publish_media_mode=source.get("publishMediaMode") or "",
            source_role=source.get("sourceRole") or "",
            image_evidence_mode=source.get("imageEvidenceMode") or "",
            research_lane=source.get("researchLane") or "",
            license_value=source.get("license") or "",
            url=source["url"],
            title=(
                fetch_runtime.get("resolvedTitle")
                or source.get("sourceTitle")
                or source.get("title")
                or source["source_id"]
            ),
            target_ref=target_ref,
            relevance=f"覆盖 {entity_id} 的基础事实/交通/季节等",
            has_video=page_has_video,
            images=source_images,
            asset_funnel=source_image_funnel,
            raw_format=raw_format,
            layout=source_layout,
            execution_id=execution_id,
            build_variants=False,
            source=source_for_unit,
        )
        unit_dir = execution_source_unit_dir(execution_id, str(manifest.get("sourceUnitId") or ""))
        if str(quality.get("quality") or "") == "Reject":
            rejected_dir = _move_rejected_source_unit(object_dir, unit_dir, quality=quality)
            written_rejected_source_dirs.add(rejected_dir)
            print(
                f"[download] Rejected source isolated {entity_id}/{source['source_id']}",
                flush=True,
            )
            _write_download_progress(
                execution_id,
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
        if str(source.get("researchLane") or "") == "homepage":
            kept_source_homepage_images += _publishable_homepage_source_image_count(
                source_images
            )
        written_source_dirs.add(unit_dir)
        if "wikipedia.org" in str(source.get("url") or "") or "wikivoyage.org" in str(source.get("url") or ""):
            try:
                from content.source.fetch_wikitext import enrich_source_unit_meta_wikitext

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
            execution_id,
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
            rejected_by_category["other"] += 1
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
            execution_id=execution_id,
            build_variants=False,
        )
        written_source_dirs.add(execution_source_unit_dir(execution_id, str(manifest.get("sourceUnitId") or "")))
    kept_images = len(pending_images) + kept_source_homepage_images
    kept_by_lane = {
        lane: sum(1 for image in pending_images if str(image.get("researchLane") or "image") == lane)
        for lane in ("image", "homepage")
    }
    kept_by_lane["homepage"] += kept_source_homepage_images
    image_count_issues: list[str] = []
    homepage_count_issues: list[str] = []
    if image_lane_selected and kept_by_lane["image"] < required_image_work_images:
        image_count_issues.append(
            f"imageCount: {entity_id} image lane 仅下到 {kept_by_lane['image']} 张合格图"
            f"（要求 ≥{required_image_work_images}）"
        )
    if homepage_media_selected and kept_by_lane["homepage"] < required_homepage_media:
        homepage_count_issues.append(
            f"homepageMediaCount: {entity_id} 独立主页媒体仅下到 "
            f"{kept_by_lane['homepage']} 张合格图（要求 ≥{required_homepage_media}）"
        )
    count_issues = [*image_count_issues, *homepage_count_issues]
    fetch_issues = list(image_rights_issues)
    fetch_issues.extend(count_issues)
    if required_images > 0 and kept_images == 0 and not image_rights_issues:
        fetch_issues.append(
            "imageFetch: 未下到真实图片，请在 source_plan 提供可用 imageUrls(CC/PD/授权)"
        )
    blocking_fetch_issues = fetch_issues if required_images > 0 else []
    typed_blocking_fetch_issues = []
    if required_images > 0:
        typed_blocking_fetch_issues.extend(
            data_issues(
                DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                stage=DataIssueStage.IMAGE_FETCH,
                ref=entity_id,
                lane=DataIssueLane.IMAGE,
                messages=image_rights_issues,
                recovery=DataRecoveryAction.REPLACE_MEDIA,
            )
        )
        typed_blocking_fetch_issues.extend(
            data_issues(
                DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                stage=DataIssueStage.IMAGE_FETCH,
                ref=entity_id,
                lane=DataIssueLane.IMAGE,
                messages=image_count_issues,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            )
        )
        typed_blocking_fetch_issues.extend(
            data_issues(
                DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                stage=DataIssueStage.IMAGE_FETCH,
                ref=entity_id,
                lane=DataIssueLane.HOMEPAGE,
                messages=homepage_count_issues,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            )
        )
        remaining_fetch_issues = [
            issue for issue in blocking_fetch_issues
            if issue not in image_rights_issues and issue not in count_issues
        ]
        typed_blocking_fetch_issues.extend(
            data_issues(
                DataIssueCode.MEDIA_FETCH_FAILED,
                stage=DataIssueStage.IMAGE_FETCH,
                ref=entity_id,
                lane=DataIssueLane.IMAGE,
                messages=remaining_fetch_issues,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            )
        )
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
    if image_lane_selected or homepage_media_selected:
        write_gate_report(
            execution_id=execution_id,
            command="source",
            step="image_rights",
            ref=entity_id,
            passed=not image_rights_issues,
            issues=data_issues(
                DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                stage=DataIssueStage.IMAGE_RIGHTS,
                ref=entity_id,
                lane=DataIssueLane.IMAGE,
                messages=image_rights_issues,
                recovery=DataRecoveryAction.REPLACE_MEDIA,
            ),
            evidence_summary={
                "plannedImages": len(image_specs) + planned_homepage_source_images,
                "blockedImages": len(image_rights_issues),
            },
            next_step="image_fetch",
        )
        write_gate_report(
            execution_id=execution_id,
            command="source",
            step="image_fetch",
            ref=entity_id,
            passed=not blocking_fetch_issues,
            issues=typed_blocking_fetch_issues,
            evidence_summary={
                "plannedImages": len(image_specs) + planned_homepage_source_images,
                "downloadedImages": kept_images,
                "minRequired": required_images,
                "requiredByLane": {
                    "image": required_image_work_images,
                    "homepage": required_homepage_media,
                },
                "downloadedByLane": kept_by_lane,
                "rejectedForQuality": image_quality_issues,
                "rejectedByCategory": rejected_by_category,
                "nonBlockingImageIssues": fetch_issues if not blocking_fetch_issues else [],
            },
            next_step="quality_analysis",
        )
    if (image_lane_selected or homepage_media_selected) and blocking_fetch_issues:
        failed_image = True
    print(
        f"[download] Entity done {entity_index}/{entity_count}: {entity_id} "
        f"sources={len(sources)} images={kept_images}",
        flush=True,
    )
    _write_download_progress(
        execution_id,
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
