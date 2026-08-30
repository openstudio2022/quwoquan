"""Source readiness precheck for immutable content executions."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from core.io import read_json
from core.image_asset_strategy import COMMERCIAL_SCALE_TARGET_THRESHOLD
from core.paths import execution_root
from content.execution.planning.source_ready_precheck import (
    SourceReadyPrecheck,
    precheck_source_ready_pool,
)

SOURCE_PRECHECK_MIN_ARTICLE_BASE_SOURCES = 4
SOURCE_PRECHECK_MIN_IMAGE_SOURCE_COLLECTIONS = 2
SOURCE_PRECHECK_MIN_SOURCE_CATEGORIES = 3
SOURCE_PRECHECK_MIN_TARGET_ENTITIES = 15
_SOURCE_PRECHECK_ARTICLE_CATEGORIES = {
    "travelogue", "guidebook", "travel_guide", "wikivoyage", "official_article",
    "vertical_professional", "ugc_longform", "community_post", "media_article",
    "platform_article", "forum_thread", "review_note",
}
_SOURCE_PRECHECK_OFF_ENTITY_MARKERS = (
    "off_entity_no_anchor", "off entity no anchor", "off-entity-no-anchor"
)

def _source_precheck_thresholds(spec: Mapping[str, Any]) -> dict[str, Any]:
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    execution = spec.get("executionPolicy") if isinstance(spec.get("executionPolicy"), Mapping) else {}
    article_quota = int(quotas.get("entityArticlesPerTarget") or 0)
    homepage_quota = int(quotas.get("entityHomepagesPerTarget") or 0)
    image_quota = int(quotas.get("imageWorksPerTarget") or 0)
    target_object_count = int(execution.get("targetObjectCount") or 0)
    target_entity_count = int(execution.get("targetEntityCount") or 0)
    enabled = image_quota >= SOURCE_PRECHECK_MIN_IMAGE_SOURCE_COLLECTIONS
    enabled = (
        enabled
        or target_object_count >= COMMERCIAL_SCALE_TARGET_THRESHOLD
        or target_entity_count >= SOURCE_PRECHECK_MIN_TARGET_ENTITIES
    )
    return {
        "enabled": bool(enabled),
        "minArticleBaseSources": (
            max(SOURCE_PRECHECK_MIN_ARTICLE_BASE_SOURCES, article_quota)
            if enabled and article_quota > 0
            else 0
        ),
        "minImageSourceCollections": (
            max(SOURCE_PRECHECK_MIN_IMAGE_SOURCE_COLLECTIONS, image_quota)
            if enabled and image_quota > 0
            else 0
        ),
        "minSourceCategories": (
            SOURCE_PRECHECK_MIN_SOURCE_CATEGORIES
            if enabled and article_quota > 0
            else 0
        ),
        "requireHomepageBaseDraft": bool(enabled and homepage_quota > 0),
        "requireSameSourcePublishableImage": bool(enabled and image_quota > 0),
    }

def _source_category(source: Mapping[str, Any]) -> str:
    from core.source_catalog import platform_category
    explicit = str(source.get("category") or "").strip()
    if explicit:
        return explicit
    return platform_category(str(source.get("platform") or "")) or ""

def _source_precheck_major_off_entity_issues(source: Mapping[str, Any]) -> list[str]:
    gate = source.get("candidateGate") if isinstance(source.get("candidateGate"), Mapping) else {}
    if gate and gate.get("passed") is False:
        return []
    rows: list[str] = []
    for issue in gate.get("issues") or []:
        text = str(issue or "").strip()
        lower = text.casefold()
        if text and any(marker in lower for marker in _SOURCE_PRECHECK_OFF_ENTITY_MARKERS):
            rows.append(text)
    return rows

_ACQUIRED_STATUS = "acquired"


def _graded_asset_row(image: Mapping[str, Any]) -> dict[str, Any] | None:
    """把已取得的图片行投影成可分级资产；未取得的行还没有权利决策可分级。"""
    if str(image.get("acquisitionStatus") or "").strip() != _ACQUIRED_STATUS:
        return None
    row: dict[str, Any] = {
        "assetId": (
            str(image.get("professionalAssetId") or "").strip()
            or str(image.get("contentSha256") or "").strip()
            or str(image.get("url") or "").strip()
        )
    }
    # 键在场性本身就是证据：缺席与空串必须能被分级器区分开，
    # 所以这里不给缺席的决策补默认值。
    if "distributionDecision" in image:
        row["distributionDecision"] = image["distributionDecision"]
    return row


def _grade_publishable_rights(
    publishable_images: Sequence[Mapping[str, Any]],
) -> SourceReadyPrecheck:
    """按来源集合分级已取得图片的权利闭合，先于任何语义 Agent 消耗配额。"""
    pool: dict[str, list[dict[str, Any]]] = {}
    for image in publishable_images:
        row = _graded_asset_row(image)
        if row is None:
            continue
        collection = str(image.get("sourceCollectionId") or "").strip()
        pool.setdefault(collection, []).append(row)
    return precheck_source_ready_pool(
        [
            {"name": collection, "assets": rows}
            for collection, rows in sorted(pool.items())
        ]
    )


def _source_precheck_diag_off_entity_count(diagnostics: Mapping[str, Any], entity: str) -> int:
    targets = diagnostics.get("targets") if isinstance(diagnostics.get("targets"), Mapping) else {}
    row = targets.get(entity) if isinstance(targets.get(entity), Mapping) else {}
    rejects = row.get("articleRejects") if isinstance(row.get("articleRejects"), Mapping) else {}
    count = 0
    for key, value in rejects.items():
        lower = str(key or "").casefold()
        if not any(marker in lower for marker in _SOURCE_PRECHECK_OFF_ENTITY_MARKERS):
            continue
        try:
            count += int(value or 0)
        except (TypeError, ValueError):
            count += 1
    return count

def source_precheck_report(
    *,
    execution_id: str,
    spec: Mapping[str, Any],
    entity_ids: Iterable[str],
    etype: str,
    homepage_failed_entities: set[str],
) -> dict[str, Any]:
    from content.source.source_inputs import curated_images_for_entity, curated_sources_for_entity
    from content.execution.coverage import coverage_entity_type_for_entity
    thresholds = _source_precheck_thresholds(spec)
    article_precheck_enabled = int(thresholds.get("minArticleBaseSources") or 0) > 0
    rows: list[dict[str, Any]] = []
    failed_lanes: list[dict[str, Any]] = []
    diagnostics_path = execution_root(execution_id) / "_shared" / "content_plan_source_diagnostics.json"
    diagnostics = read_json(diagnostics_path) if diagnostics_path.is_file() else {}
    vertical = str(spec.get("vertical") or "travel")
    entity_list = [str(entity).strip() for entity in entity_ids if str(entity).strip()]
    execution_etype = etype
    for entity in entity_list:
        # 与 audit 主循环同源：多类型分区空 execution etype 必须 per-entity 校正。
        etype = coverage_entity_type_for_entity(dict(spec), entity) or execution_etype
        homepage_sources = curated_sources_for_entity(
            execution_id,
            entity,
            etype,
            research_lane="homepage",
        )
        article_sources = curated_sources_for_entity(
            execution_id,
            entity,
            etype,
            research_lane="article",
        )
        image_specs = [
            image for image in curated_images_for_entity(execution_id, entity, etype)
            if str(image.get("researchLane") or "image") == "image"
        ]
        article_base_sources = [
            source for source in article_sources
            if str(source.get("sourceRole") or "") == "base"
            or _source_category(source) in _SOURCE_PRECHECK_ARTICLE_CATEGORIES
        ]
        source_categories = {
            category
            for category in [_source_category(source) for source in (homepage_sources + article_sources)]
            if category
        }
        publishable_images: list[Mapping[str, Any]] = []
        publishable_collections: set[str] = set()
        for image in image_specs:
            collection = str(image.get("sourceCollectionId") or "").strip()
            if not collection:
                continue
            publishable_images.append(image)
            publishable_collections.add(collection)
            category = _source_category(
                {
                    "platform": image.get("platform") or "",
                    "category": image.get("category") or "",
                }
            )
            if category:
                source_categories.add(category)
        # 权利未闭合的集合不能算进 publishable：让它在这里落榜，比让语义 Agent
        # 先写完对象再在 pool admission 被拒便宜一整个 agent run。
        source_ready = _grade_publishable_rights(publishable_images)
        rights_rejected = tuple(row for row in source_ready.verdicts if not row.ready)
        unclosed_collections = {row.name for row in rights_rejected}
        if unclosed_collections:
            publishable_collections -= unclosed_collections
            publishable_images = [
                image
                for image in publishable_images
                if str(image.get("sourceCollectionId") or "").strip()
                not in unclosed_collections
            ]
        off_entity_issues: list[str] = []
        for source in article_sources:
            off_entity_issues.extend(_source_precheck_major_off_entity_issues(source))
        off_entity_diag_count = _source_precheck_diag_off_entity_count(diagnostics, entity)
        issues_by_lane: dict[str, list[str]] = {}
        if thresholds["enabled"] and thresholds["requireHomepageBaseDraft"] and entity in homepage_failed_entities:
            issues_by_lane.setdefault("homepage", []).append(
                "source precheck homepage baseDraft/publishable homepage image gate is not ready"
            )
        min_article = int(thresholds["minArticleBaseSources"] or 0)
        if min_article and len(article_base_sources) < min_article:
            issues_by_lane.setdefault("article", []).append(
                f"source precheck article base sources={len(article_base_sources)} need>={min_article}"
            )
        min_categories = int(thresholds["minSourceCategories"] or 0)
        if min_categories and len(source_categories) < min_categories:
            issues_by_lane.setdefault("article", []).append(
                "source precheck source categories "
                f"{len(source_categories)} < required {min_categories} "
                f"(covered={sorted(source_categories)})"
            )
        if article_precheck_enabled and off_entity_issues:
            issues_by_lane.setdefault("article", []).append(
                "source precheck major off_entity_no_anchor rejects="
                f"{len(off_entity_issues)}"
            )
        min_image = int(thresholds["minImageSourceCollections"] or 0)
        if min_image and len(publishable_collections) < min_image:
            issues_by_lane.setdefault("image", []).append(
                "source precheck publishable image source collections="
                f"{len(publishable_collections)} need>={min_image}"
            )
        if thresholds["requireSameSourcePublishableImage"] and not publishable_images:
            issues_by_lane.setdefault("image", []).append(
                "source precheck same-source publishable image is missing"
            )
        for verdict in rights_rejected:
            issues_by_lane.setdefault("image", []).append(
                "source precheck rights closure "
                f"{verdict.grade.value} for sourceCollectionId={verdict.name}: "
                f"{verdict.reason}"
            )
        row = {
            "entity": entity,
            "passed": not issues_by_lane,
            "homepageSourceCount": len(homepage_sources),
            "articleSourceCount": len(article_sources),
            "articleBaseSourceCount": len(article_base_sources),
            "imageSourceCollectionCount": len(publishable_collections),
            "publishableImageCount": len(publishable_images),
            "sourceCategoryCount": len(source_categories),
            "sourceCategories": sorted(source_categories),
            "majorOffEntityNoAnchorRejectCount": len(off_entity_issues) + off_entity_diag_count,
            "sourceReady": source_ready.report(),
            "issuesByLane": issues_by_lane,
        }
        rows.append(row)
        for lane, issues in issues_by_lane.items():
            failed_lanes.append({"entity": entity, "lane": lane, "issues": issues})
    failed_entities = [str(row["entity"]) for row in rows if not row["passed"]]
    return {
        "enabled": bool(thresholds["enabled"]),
        "thresholds": thresholds,
        "failedEntityCount": len(failed_entities),
        "failedEntities": failed_entities,
        "failedLanes": failed_lanes,
        "entities": rows,
    }
