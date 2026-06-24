"""Download lane selection, source-plan gates and progress artifacts."""
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

from _common.paths import ensure_batch_layout, batch_root, source_unit_dir
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

SOURCE_UNIT_MAX_IMAGES_PER_SOURCE = max(1, int(os.environ.get("QWQ_SOURCE_UNIT_MAX_IMAGES_PER_SOURCE", "8")))

SOURCE_UNIT_MAX_IMAGE_BYTES = max(
    0,
    int(os.environ.get("QWQ_SOURCE_UNIT_MAX_IMAGE_BYTES", str(8 * 1024 * 1024))),
)

_DOWNLOAD_PROGRESS_LOCK = Lock()

_ALL_DOWNLOAD_LANES = {"homepage", "article", "image"}

_TEXT_DOWNLOAD_LANES = ("homepage", "article")

def _selected_download_lanes(args: argparse.Namespace) -> set[str] | None:
    lane = str(getattr(args, "lane", "all") or "all").strip()
    if lane in ("", "all"):
        return None
    if lane not in _ALL_DOWNLOAD_LANES:
        raise SystemExit(f"[download] unknown lane={lane!r}; expected all/homepage/article/image")
    return {lane}

def _source_unit_lane_in_scope(lane: str, selected_lanes: set[str] | None) -> bool:
    if selected_lanes is None:
        return True
    normalized = str(lane or "").strip()
    if normalized == "homepage_image":
        return "homepage" in selected_lanes
    return normalized in selected_lanes

def _curated_sources_for_lanes(
    task_id: str,
    batch_id: str,
    entity_id: str,
    entity_type: str,
    selected_lanes: set[str] | None,
) -> list[dict[str, Any]]:
    if selected_lanes is None:
        return curated_sources_for_entity(task_id, batch_id, entity_id, entity_type)
    sources: list[dict[str, Any]] = []
    for lane in _TEXT_DOWNLOAD_LANES:
        if lane in selected_lanes:
            sources.extend(
                curated_sources_for_entity(
                    task_id,
                    batch_id,
                    entity_id,
                    entity_type,
                    research_lane=lane,
                )
            )
    return sources

def _homepage_plan_authority_issues(
    planned_sources: list[Mapping[str, Any]],
    *,
    entity_id: str,
) -> list[str]:
    authority_categories = {"encyclopedia", "official", "official_site"}
    covered = {
        str(source.get("category") or "")
        or (source_category_coverage([source], vertical="travel").get("coveredCategories") or [""])[0]
        for source in planned_sources
        if isinstance(source, Mapping)
    }
    if covered & authority_categories:
        return []
    return [f"{entity_id}: homepage research needs encyclopedia or official evidence"]

_ARTICLE_BASE_CATEGORIES = {
    "travelogue",
    "guidebook",
    "travel_guide",
    "wikivoyage",
    "official_article",
    "vertical_professional",
    "ugc_longform",
    "community_post",
    "media_article",
    "platform_article",
    "forum_thread",
    "review_note",
}

def _article_plan_quality_issues(
    planned_sources: list[Mapping[str, Any]],
    *,
    entity_id: str,
    min_article_sources: int,
) -> list[str]:
    issues: list[str] = []
    if len(planned_sources) < min_article_sources:
        issues.append(f"{entity_id}: article sources={len(planned_sources)} need>={min_article_sources}")
    base_sources = [
        source for source in planned_sources
        if str(source.get("sourceRole") or "") == "base"
    ]
    if len(base_sources) < min_article_sources:
        issues.append(
            f"{entity_id}: article research needs >= {min_article_sources} text-qualified base sources"
        )
    for source in base_sources:
        category = (
            str(source.get("category") or "").strip()
            or platform_category(str(source.get("platform") or ""))
            or ""
        )
        if category and category not in _ARTICLE_BASE_CATEGORIES:
            issues.append(
                f"{entity_id}: article source {source.get('source_id')}: "
                f"base source category must be article-quality, got {category}"
            )
    return issues

def _source_plan_gate_issues(
    *,
    task_id: str,
    batch_id: str,
    entity_id: str,
    entity_type: str,
    planned_sources: list[Mapping[str, Any]],
    selected_lanes: set[str] | None,
    vertical: str,
) -> list[str]:
    text_lane_selected = selected_lanes is None or bool(selected_lanes & set(_TEXT_DOWNLOAD_LANES))
    if not text_lane_selected:
        return []

    requirements = download_requirements(task_id)
    plan_issues: list[str] = []
    scoped_lane = next(iter(selected_lanes)) if selected_lanes and len(selected_lanes) == 1 else None
    if scoped_lane == "article":
        plan_issues.extend(
            _article_plan_quality_issues(
                planned_sources,
                entity_id=entity_id,
                min_article_sources=int(
                    requirements.get("minArticleBaseSources") or requirements["minSources"]
                ),
            )
        )
    elif scoped_lane == "homepage":
        plan_issues.extend(
            _homepage_plan_authority_issues(
                planned_sources,
                entity_id=entity_id,
            )
        )
    else:
        if len(planned_sources) < 2:
            plan_issues.append("sourcePlan: fewer than 2 planned sources")
        plan_issues.extend(coverage_issues(planned_sources, vertical=vertical, entity_id=entity_id))

    plan_issues.extend(
        source_plan_rights_issues(
            task_id,
            batch_id,
            entity_id,
            entity_type,
            require_explicit=requirements["minSources"] >= 4,
            research_lane=scoped_lane,
        )
    )
    return plan_issues

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _write_download_progress(
    task_id: str,
    batch_id: str,
    *,
    status: str,
    entity_id: str = "",
    entity_index: int = 0,
    entity_count: int = 0,
    sources: int = 0,
    images: int = 0,
    message: str = "",
    **extra: Any,
) -> None:
    shared = batch_root(task_id, batch_id) / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": "quwoquan.download.progress",
        "updatedAt": _now_iso(),
        "status": status,
        "entityId": entity_id,
        "entityIndex": entity_index,
        "entityCount": entity_count,
        "sources": sources,
        "images": images,
        "message": message,
    }
    for key, value in extra.items():
        if value in (None, ""):
            continue
        payload[key] = value
    with _DOWNLOAD_PROGRESS_LOCK:
        write_json(shared / "download_progress.json", payload)
        with (shared / "download_events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

__all__ = [name for name in globals() if not name.startswith("__")]
