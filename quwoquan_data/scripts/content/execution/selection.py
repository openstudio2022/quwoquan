"""Reusable multimodal target selection and execution audit helpers."""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from governance.coverage.entity_extract import require_domain_etype
from core.data_issue import DataIssue
from core.image_asset_strategy import COMMERCIAL_SCALE_TARGET_THRESHOLD
from core.execution_branch import stamp_execution_branch
from core.io import read_json, write_json
from core.runtime_policy import active_runtime_policy
from core.paths import (
    execution_entity_page_input_path,
    execution_root,
    preset_path,
)
from content.execution import store
from content.execution import validate_execution_id
from content.execution.identity import SelectionPolicy
from content.execution.selection_materialization import write_selected_task
DEFAULT_ARTICLE_ANGLES = ["planning_consultation", "decision_experience", "route_transport", "seasonal_timing"]
SOURCE_PRECHECK_MIN_ARTICLE_BASE_SOURCES = 4
SOURCE_PRECHECK_MIN_IMAGE_SOURCE_COLLECTIONS = 2
SOURCE_PRECHECK_MIN_SOURCE_CATEGORIES = 3
SOURCE_PRECHECK_MIN_TARGET_ENTITIES = 15
_SOURCE_PRECHECK_ARTICLE_CATEGORIES = {
    "travelogue", "guidebook", "travel_guide", "wikivoyage", "official_article", "vertical_professional",
    "ugc_longform", "community_post", "media_article", "platform_article", "forum_thread", "review_note",
}
_SOURCE_PRECHECK_OFF_ENTITY_MARKERS = ("off_entity_no_anchor", "off entity no anchor", "off-entity-no-anchor")


@dataclass(frozen=True)
class SelectionRequest:
    """One immutable request for creating an execution work package."""

    execution_id: str
    discovery_path: Path
    limit: int
    mandatory: tuple[str, ...]
    excluded: frozenset[str]
    region: str
    category: str
    name: str
    title: str
    intent_label: str | None
    preset_ref: str | None
    entity_articles_per_target: int = 0
    entity_homepages_per_target: int = 1
    image_works_per_target: int = 0
    created_by: str = "geo-homepages"
    selection_policy: SelectionPolicy = SelectionPolicy.FROZEN
    force: bool = False


def workflow_failure_items(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    status = str(state.get("status") or "").strip()
    if status in ("", "succeeded", "stopped_at_until"):
        return []
    items: list[dict[str, Any]] = []
    records = state.get("failedIssueRecords")
    for raw in records if isinstance(records, list) else []:
        if not isinstance(raw, Mapping):
            continue
        try:
            issue = DataIssue.from_dict(raw)
        except (TypeError, ValueError):
            continue
        entity = issue.ref.rsplit("/", 1)[-1].strip() if issue.ref else "__execution__"
        items.append(
            {
                "entity": entity,
                "lane": "workflow" if issue.lane.value == "all" else issue.lane.value,
                "issues": [str(issue)],
            }
        )
    if not items:
        failed_objects = [
            str(item) for item in state.get("failedObjects") or [] if str(item).strip()
        ]
        items.append(
            {
                "entity": "__execution__",
                "lane": "workflow",
                "issues": failed_objects or [f"workflow status={status}"],
            }
        )
    return items

def _master_list_file_partitions(path: Path) -> list[dict[str, Any]]:
    """单个主清单市州文件（discovery_seed/2）→ 区县分区列表。"""
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, Mapping):
        raise ValueError(f"{path}: 主清单文件顶层必须是 mapping")
    partitions: list[dict[str, Any]] = []
    for group in data.get("districts") or []:
        if not isinstance(group, Mapping):
            continue
        district = str(group.get("district") or "").strip()
        leaves = [leaf for leaf in (group.get("leaves") or []) if isinstance(leaf, Mapping)]
        if district and leaves:
            partitions.append({"key": district, "leaves": leaves})
    return partitions
def _master_list_partitions(root: Path) -> list[dict[str, Any]]:
    """walk 主清单目录：区县分组映射为 partition，与 decompose discovery JSON partitions 同构。"""
    partitions: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.yaml")):
        partitions.extend(_master_list_file_partitions(path))
    if not partitions:
        raise ValueError(f"{root}: 主清单目录未发现任何区县分组（districts/leaves）")
    return partitions
def _load_partitions(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        return _master_list_partitions(path)
    if path.suffix in {".yaml", ".yml"}:
        # 市州级主清单单文件（如 coverage/中国/浙江省/舟山市.yaml）：批次可精确圈定一个市州。
        partitions = _master_list_file_partitions(path)
        if not partitions:
            raise ValueError(f"{path}: 主清单文件未发现任何区县分组（districts/leaves）")
        return partitions
    data = read_json(path)
    rows = data.get("partitions") if isinstance(data, dict) else []
    if not isinstance(rows, list):
        raise ValueError(f"{path}: partitions must be an array")
    return [row for row in rows if isinstance(row, dict)]
# 主清单 leaf → coverageTarget 契约字段透传集（task_spec.schema.json coverageTargets 同口径）。
_MASTER_LIST_LIST_FIELDS = ("geoTagRefs", "typeTagRefs", "aliases")
def _apply_master_list_fields(row: dict[str, Any], leaf: Mapping[str, Any]) -> dict[str, Any]:
    geo_tag_ref = str(leaf.get("geoTagRef") or "").strip()
    if geo_tag_ref:
        row["geoTagRef"] = geo_tag_ref
    for list_field in _MASTER_LIST_LIST_FIELDS:
        values = [str(v).strip() for v in (leaf.get(list_field) or []) if str(v).strip()]
        if values:
            row[list_field] = values
    return row
def _partition_targets(partitions: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for part in partitions:
        region = str(part.get("key") or "").strip()
        for leaf in _ordered_partition_leaves(part):
            source_name = str(leaf.get("name") or "").strip()
            name = _leaf_selection_name(leaf)
            etype = str(leaf.get("entityType") or "地点/景区").strip()
            if name and name not in by_name:
                by_name[name] = _apply_master_list_fields(
                    {
                        "name": name,
                        "entityType": etype,
                        "region": region,
                        "sourceName": source_name,
                    },
                    leaf,
                )
    return by_name
def _leaf_selection_name(leaf: Mapping[str, Any]) -> str:
    source_name = str(leaf.get("name") or "").strip()
    return str(leaf.get("canonicalName") or source_name).strip()
def _leaf_selection_priority(leaf: Mapping[str, Any]) -> float | None:
    if "selectionPriority" not in leaf:
        return None
    try:
        return float(leaf.get("selectionPriority"))
    except (TypeError, ValueError):
        return None
def _ordered_partition_leaves(part: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    leaves = [leaf for leaf in (part.get("leaves") or []) if isinstance(leaf, Mapping)]
    if not any(_leaf_selection_priority(leaf) is not None for leaf in leaves):
        return leaves
    return sorted(
        leaves,
        key=lambda leaf: (
            _leaf_selection_priority(leaf)
            if _leaf_selection_priority(leaf) is not None
            else float("inf"),
            _leaf_selection_name(leaf),
        ),
    )

def select_targets(
    *,
    discovery_path: Path,
    limit: int,
    mandatory: list[str],
    excluded: set[str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    partitions = _load_partitions(discovery_path)
    by_name = _partition_targets(partitions)
    missing_mandatory = [name for name in mandatory if name not in by_name]
    if missing_mandatory:
        raise ValueError(f"mandatory targets missing from discovery: {missing_mandatory}")
    blocked_mandatory = [name for name in mandatory if name in excluded]
    if blocked_mandatory:
        raise ValueError(
            "mandatory targets are marked ineligible and cannot be auto-replaced: "
            + ", ".join(blocked_mandatory)
        )
    selected: list[dict[str, str]] = []
    seen: set[str] = set()
    def add(name: str) -> None:
        if name in seen or name in excluded or len(selected) >= limit:
            return
        row = by_name.get(name)
        if not row:
            return
        selected.append(row)
        seen.add(name)
    for name in mandatory:
        add(name)
    depth = 0
    while len(selected) < limit:
        scanned_any = False
        for part in partitions:
            leaves = _ordered_partition_leaves(part)
            if depth >= len(leaves):
                continue
            scanned_any = True
            name = _leaf_selection_name(leaves[depth])
            add(name)
            if len(selected) >= limit:
                break
        if not scanned_any:
            break
        depth += 1
    if len(selected) != limit:
        raise ValueError(
            f"selected {len(selected)} targets, expected {limit}; "
            f"excluded={len(excluded)} may leave too few candidates"
        )
    report = {
        "schemaVersion": "quwoquan_data.target_selection",
        "strategy": "mandatory targets plus deterministic round-robin regional coverage",
        "discoveryPath": str(discovery_path),
        "limit": limit,
        "selectedCount": len(selected),
        "selectionShortfall": max(0, limit - len(selected)),
        "mandatory": mandatory,
        "excluded": sorted(excluded),
        "targets": selected,
    }
    return selected, report
def build_multimodal_spec(
    *,
    execution_id: str,
    name: str,
    title: str,
    region: str,
    category: str,
    targets: list[dict[str, str]],
    created_by: str,
    intent_label: str | None = None,
    preset_ref: str | None = None,
    entity_articles_per_target: int = 4,
    entity_homepages_per_target: int = 1,
    image_works_per_target: int = 1,
    target_entity_count: int | None = None,
    selection_policy: SelectionPolicy = SelectionPolicy.FROZEN,
) -> dict[str, Any]:
    validated_execution_id = validate_execution_id(execution_id)
    if not isinstance(selection_policy, SelectionPolicy):
        raise TypeError("selection_policy must be SelectionPolicy")
    if selection_policy is not SelectionPolicy.FROZEN:
        raise ValueError("content executions require frozen target selection")
    entity_articles_per_target = max(0, int(entity_articles_per_target))
    entity_homepages_per_target = max(0, int(entity_homepages_per_target))
    image_works_per_target = max(0, int(image_works_per_target))
    target_entity_count = max(0, int(target_entity_count if target_entity_count is not None else len(targets)))
    homepage_only_delivery = (
        entity_homepages_per_target > 0
        and entity_articles_per_target <= 0
        and image_works_per_target <= 0
    )
    target_object_count = (
        target_entity_count * entity_homepages_per_target
        if homepage_only_delivery
        else target_entity_count * (entity_articles_per_target + image_works_per_target)
    )
    min_posts_per_entity = (
        entity_homepages_per_target
        if homepage_only_delivery
        else entity_articles_per_target + image_works_per_target
    )
    required_article_angles = DEFAULT_ARTICLE_ANGLES[:entity_articles_per_target]
    research_lanes = []
    if entity_homepages_per_target > 0:
        research_lanes.append("homepage")
    if entity_articles_per_target > 0:
        research_lanes.append("article")
    if image_works_per_target > 0:
        research_lanes.append("image")
    runtime_policy = active_runtime_policy()
    lane_concurrency = {
        "homepage": runtime_policy.research_workers,
        "article": runtime_policy.research_workers,
        "image": runtime_policy.research_workers,
    }
    carriers = []
    if entity_articles_per_target > 0:
        carriers.append("article")
    if image_works_per_target > 0:
        carriers.append("image")
    selected_entity_types = sorted(
        {
            str(row.get("entityType") or "").strip()
            for row in targets
            if str(row.get("entityType") or "").strip()
        }
    )
    # presetRef：显式传入优先；homepage-only 形态默认绑定 homepage 家族基线。
    resolved_preset = str(preset_ref or "").strip().strip("/")
    if not resolved_preset and homepage_only_delivery:
        candidate = "content/travel/homepage/base"
        if preset_path(candidate).is_file():
            resolved_preset = candidate
    spec = store.scaffold_spec(
        execution_id=validated_execution_id,
        vertical="travel",
        organize_by="地域",
        key=region,
        category=category,
        name=name,
        title=title,
        intent_label=intent_label,
        preset_ref=resolved_preset or None,
        scope={
            "region": region,
            "entityTypes": selected_entity_types,
            # 主清单契约字段（geoTagRef/geoTagRefs/typeTagRefs/aliases）随目标透传，
            # 物化链路（build/homepage.py）据此写 _entity.json 并统一打标（WP3）。
            "coverageTargets": [
                _apply_master_list_fields(
                    {"entityType": row["entityType"], "name": row["name"]}, row
                )
                for row in targets
            ],
        },
        content={
            "modalityContract": "separated_research",
            "research": {
                "lanes": research_lanes,
                "maxConcurrency": runtime_policy.download_concurrency,
                "laneConcurrency": {lane: lane_concurrency[lane] for lane in research_lanes},
                "imageAssetStrategy": "open_license_publish",
                "imageCountPolicy": "score_bonus",
                "allowAiImages": False,
            },
            "carriers": carriers,
            "quotas": {
                "entityArticlesPerTarget": entity_articles_per_target,
                "imageWorksPerTarget": image_works_per_target,
                "entityHomepagesPerTarget": entity_homepages_per_target,
                "routeArticles": 0,
            },
        },
        acceptance={
            "minEntities": target_entity_count,
            "minPostsPerEntity": min_posts_per_entity,
            "requiredAngles": required_article_angles,
            "scoredAngles": (["image"] if image_works_per_target else []),
        },
        created_by=created_by,
    )
    spec["status"] = "active"
    spec.setdefault("acceptance", {})["requiredAngles"] = required_article_angles
    spec["workflowPolicy"] = {
        "selectionPolicy": selection_policy.value,
        "targetEntityCount": target_entity_count,
        "targetObjectCount": target_object_count,
    }
    spec["queuePolicy"] = {
        "backend": "reliabletask",
        "reliableTask": {
            "taskType": "data.content_object.execute",
            "queue": "reliabletask.data.content_supply",
            "store": "MongoStore",
            "readyIndex": "RedisReadyIndex",
        },
        "leaseSeconds": runtime_policy.queue_lease_ttl_seconds,
        "heartbeatSeconds": runtime_policy.queue_heartbeat_seconds,
        "deadLetterAfterAttempts": runtime_policy.queue_max_attempts,
    }
    stamp_execution_branch(spec)
    return spec
def execution_planned_entity_ids(execution_id: str) -> list[str]:
    shared = execution_root(execution_id) / "_shared"
    report = read_json(shared / "auto_research_plan.json") if (shared / "auto_research_plan.json").is_file() else {}
    availability = report.get("sourceAvailability") if isinstance(report.get("sourceAvailability"), dict) else {}
    ids: list[str] = []
    seen: set[str] = set()
    for entity_id in availability.get("readyTargets") or []:
        text = str(entity_id or "").strip()
        if text and text not in seen:
            ids.append(text)
            seen.add(text)
    for item in availability.get("ineligibleTargets") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("entityId") or "").strip()
        if text and text not in seen:
            ids.append(text)
            seen.add(text)
    if ids:
        return ids
    for item in report.get("updated") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("entityId") or "").strip()
        if text and text not in seen:
            ids.append(text)
            seen.add(text)
    return ids
def _source_precheck_thresholds(spec: Mapping[str, Any]) -> dict[str, Any]:
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    workflow = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), Mapping) else {}
    article_quota = int(quotas.get("entityArticlesPerTarget") or 0)
    homepage_quota = int(quotas.get("entityHomepagesPerTarget") or 0)
    image_quota = int(quotas.get("imageWorksPerTarget") or 0)
    target_object_count = int(workflow.get("targetObjectCount") or 0)
    target_entity_count = int(workflow.get("targetEntityCount") or 0)
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
    from governance.coverage.license import validate_image_rights
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
            if validate_image_rights(image, vertical=vertical):
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

def create_execution_selection(request: SelectionRequest) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select targets and write the sole execution manifest/specification."""
    execution_id = validate_execution_id(request.execution_id)
    if not isinstance(request.selection_policy, SelectionPolicy):
        raise TypeError("SelectionRequest.selection_policy must be SelectionPolicy")
    if request.selection_policy is not SelectionPolicy.FROZEN:
        raise ValueError("content executions require frozen target selection")
    discovery = request.discovery_path
    excluded = set(request.excluded)
    mandatory = list(request.mandatory)
    requested_limit = max(1, int(request.limit))
    targets, report = select_targets(
        discovery_path=discovery,
        limit=requested_limit,
        mandatory=mandatory,
        excluded=excluded,
    )
    spec = build_multimodal_spec(
        execution_id=execution_id,
        name=request.name,
        title=request.title or request.name,
        region=request.region,
        category=request.category,
        targets=targets,
        intent_label=request.intent_label,
        preset_ref=request.preset_ref,
        created_by=request.created_by,
        entity_articles_per_target=int(request.entity_articles_per_target or 0),
        entity_homepages_per_target=int(request.entity_homepages_per_target or 0),
        image_works_per_target=int(request.image_works_per_target or 0),
        target_entity_count=requested_limit,
        selection_policy=request.selection_policy,
    )
    spec["title"] = str(request.title or request.name)
    report["executionId"] = spec["executionId"]
    target_refs = sorted(
        f"{str(item.get('entityType') or '地点/景区').strip()}/{str(item.get('name') or '').strip()}"
        for item in targets
    )
    report["targetRefs"] = target_refs
    report["targetRefsSha256"] = "sha256:" + hashlib.sha256(
        ("\n".join(target_refs) + "\n").encode("utf-8")
    ).hexdigest()
    report["quotas"] = (spec.get("content") or {}).get("quotas") or {}
    write_selected_task(spec, report, force=request.force)
    return spec, report
