"""Reusable multimodal target selection and batch audit helpers."""
from __future__ import annotations
import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping
from _common.entity_extract import require_domain_etype
from _common.execution_branch import stamp_execution_branch
from _common.io import read_json, write_json, write_ndjson
from _common.paths import batch_entity_page_input_path, batch_root, preset_path, task_catalog
from _common.workflow_abandonment import (
    ABANDON_SCOPE_ENTITY,
    abandoned_entity_ids,
    is_terminal_abandonment,
)
from task import store
DEFAULT_MANDATORY = ["四姑娘山", "毕棚沟", "稻城亚丁", "海螺沟", "墨石公园"]
# 跨批去重账本默认维度：全国常量（多省并行共用同一账本，防跨省/跨批重复生产）。
# 历史值「旅行/地域/四川省/景区/景区精选」错挂四川维度，已随 WP4 dedup 修正退役。
DEFAULT_SOURCE_TASK_ID = "旅行/地域/中国/景区/景区全覆盖"
DEFAULT_ARTICLE_ANGLES = ["planning_consultation", "decision_experience", "route_transport", "seasonal_timing"]
SOURCE_PRECHECK_MIN_ARTICLE_BASE_SOURCES = 4
SOURCE_PRECHECK_MIN_IMAGE_SOURCE_COLLECTIONS = 2
SOURCE_PRECHECK_MIN_SOURCE_CATEGORIES = 3
_SOURCE_PRECHECK_ARTICLE_CATEGORIES = {
    "travelogue", "guidebook", "travel_guide", "wikivoyage", "official_article", "vertical_professional",
    "ugc_longform", "community_post", "media_article", "platform_article", "forum_thread", "review_note",
}
_SOURCE_PRECHECK_OFF_ENTITY_MARKERS = ("off_entity_no_anchor", "off entity no anchor", "off-entity-no-anchor")
def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]
def _default_discovery_path() -> Path:
    """缺省 discovery = 全国主清单目录树（唯一真相源，WP3-1 目录形态消费）。
    旧缺省（source task 根下 discovery_sichuan_100e.json）随四川维度常量退役。
    """
    from _common.coverage_master_list import COVERAGE_MASTER_ROOT
    return COVERAGE_MASTER_ROOT
def _failed_object_entity(raw: Any) -> str:
    text = str(raw or "")
    match = re.match(r"^\s*([^:：]+)\s*[:：]", text)
    if not match:
        return ""
    entity = match.group(1).strip()
    if entity in {"download_plan", "download_fetch", "build_prepare", "build_homepage", "build_validate",
                  "content_plan", "produce_plan", "produce_compose", "produce_author", "produce_review"}:
        return ""
    return entity
def _workflow_failure_lane(raw: Any) -> str:
    text = str(raw or "").casefold()
    if (
        "article source unit" in text
        or "article base draft" in text
        or "article research" in text
        or "text-qualified base source" in text
        or "article base source" in text
        or "article sources=" in text
        or "usable article base sources" in text
    ):
        return "article"
    if "image research" in text or "image gate" in text or "image fetch" in text:
        return "image"
    if "homepage" in text or "entity homepage" in text:
        return "homepage"
    return "workflow"
def _workflow_failure_items(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    status = str(state.get("status") or "").strip()
    failed_objects = [str(item) for item in state.get("failedObjects") or [] if str(item).strip()]
    if status in ("", "succeeded", "completed_with_reasoned_rejects", "stopped_at_until"):
        return []
    items: list[dict[str, Any]] = []
    for raw in failed_objects:
        entity = _failed_object_entity(raw)
        items.append(
            {
                "entity": entity or "__batch__",
                "lane": _workflow_failure_lane(raw),
                "issues": [raw],
            }
        )
    if not items:
        items.append(
            {
                "entity": "__batch__",
                "lane": "workflow",
                "issues": [f"workflow status={status}"],
            }
        )
    return items
def _content_abandon_blocks_entity(item: Mapping[str, Any]) -> bool:
    """Only promote content-level rejects to target exclusion when the entity anchor failed."""
    if str(item.get("status") or "abandoned").strip() != "abandoned":
        return False
    stage = str(item.get("stage") or "").strip()
    reason = str(item.get("reason") or "").casefold()
    if stage == "publish" and "publish_content_anchor_unavailable_after_homepage_filter" in reason:
        return True
    if stage in {"download_plan", "download_fetch", "build_prepare"} and "homepage" in reason:
        return True
    return False
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
def _filter_partitions_by_source_readiness(
    partitions: list[dict[str, Any]],
    allowed: list[str],
) -> list[dict[str, Any]]:
    """按主清单 leaf.sourceReadiness 过滤；启用过滤的批次必须以主清单 readiness 为真相源。"""
    allowed_set = {item for item in allowed if item}
    filtered: list[dict[str, Any]] = []
    for part in partitions:
        leaves = [
            leaf
            for leaf in (part.get("leaves") or [])
            if isinstance(leaf, Mapping) and str(leaf.get("sourceReadiness") or "") in allowed_set
        ]
        if leaves:
            filtered.append({**dict(part), "leaves": leaves})
    return filtered
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
def ineligible_targets_from_batch(task_id: str, batch_id: str) -> set[str]:
    """Extract unresolved target names from a managed batch state."""
    shared = batch_root(task_id, batch_id) / "_shared"
    out: set[str] = set()
    audit_path = shared / "managed_batch_audit.json"
    if audit_path.is_file():
        try:
            audit = read_json(audit_path)
        except (OSError, ValueError, TypeError):
            audit = {}
        for item in audit.get("failedLanes") or []:
            if isinstance(item, Mapping):
                name = str(item.get("entity") or "").strip()
                if name:
                    out.add(name)
    unavailable_path = shared / "source_unavailable_targets.json"
    if unavailable_path.is_file():
        try:
            availability = read_json(unavailable_path)
        except (OSError, ValueError, TypeError):
            availability = {}
        for item in availability.get("ineligibleTargets") or []:
            if isinstance(item, Mapping):
                name = str(item.get("entityId") or "").strip()
                if name:
                    out.add(name)
    auto_research_path = shared / "auto_research_plan.json"
    if auto_research_path.is_file():
        try:
            auto_research = read_json(auto_research_path)
        except (OSError, ValueError, TypeError):
            auto_research = {}
        availability = auto_research.get("sourceAvailability") if isinstance(auto_research.get("sourceAvailability"), Mapping) else {}
        for item in availability.get("ineligibleTargets") or []:
            if isinstance(item, Mapping):
                name = str(item.get("entityId") or "").strip()
                if name:
                    out.add(name)
    path = shared / "task_workflow_state.json"
    if not path.is_file():
        return out
    try:
        state = read_json(path)
    except (OSError, ValueError, TypeError):
        return out
    out.update(abandoned_entity_ids(state.get("abandonedObjects") or [], scope="any"))
    for item in state.get("abandonedContentObjects") or []:
        if not isinstance(item, Mapping):
            continue
        if not _content_abandon_blocks_entity(item):
            continue
        name = str(item.get("entityId") or "").strip()
        ref = str(item.get("ref") or "").strip()
        if not name and "_" in ref:
            name = ref.split("_", 1)[0].strip()
        if name:
            out.add(name)
    for raw in state.get("failedObjects") or []:
        name = _failed_object_entity(raw)
        if name:
            out.add(name)
    return {item for item in out if item}
def _parse_run_ref(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if "::" not in raw:
        raise ValueError("--exclude-from-run must use TASK_ID::BATCH_ID")
    task_id, batch_id = raw.rsplit("::", 1)
    task_id = task_id.strip()
    batch_id = batch_id.strip()
    if not task_id or not batch_id:
        raise ValueError("--exclude-from-run must use non-empty TASK_ID::BATCH_ID")
    return task_id, batch_id
def select_targets(
    *,
    discovery_path: Path,
    limit: int,
    mandatory: list[str],
    excluded: set[str],
    reserve_ratio: float = 0.0,
    allow_shortfall: bool = False,
    source_readiness: list[str] | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    partitions = _load_partitions(discovery_path)
    if source_readiness:
        partitions = _filter_partitions_by_source_readiness(partitions, source_readiness)
        if not partitions:
            raise ValueError(
                f"{discovery_path}: 按 sourceReadiness={source_readiness} 过滤后无可选叶子"
            )
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
    reserve: list[dict[str, str]] = []
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
    if len(selected) != limit and not allow_shortfall:
        raise ValueError(
            f"selected {len(selected)} targets, expected {limit}; "
            f"excluded={len(excluded)} may leave too few candidates"
        )
    reserve_count = max(0, int(round(limit * max(0.0, float(reserve_ratio or 0.0)))))
    if reserve_count:
        for part in partitions:
            for leaf in _ordered_partition_leaves(part):
                name = _leaf_selection_name(leaf)
                if not name or name in seen or name in excluded:
                    continue
                row = by_name.get(name)
                if not row:
                    continue
                reserve.append(row)
                seen.add(name)
                if len(reserve) >= reserve_count:
                    break
            if len(reserve) >= reserve_count:
                break
    report = {
        "schemaVersion": "quwoquan_data.target_selection",
        "strategy": "mandatory targets plus deterministic round-robin regional coverage",
        "discoveryPath": str(discovery_path),
        "limit": limit,
        "reserveRatio": max(0.0, float(reserve_ratio or 0.0)),
        "sourceReadinessFilter": list(source_readiness or []),
        "selectedCount": len(selected),
        "selectionShortfall": max(0, limit - len(selected)),
        "allowShortfall": bool(allow_shortfall),
        "mandatory": mandatory,
        "excluded": sorted(excluded),
        "targets": selected,
        "reserveTargets": reserve,
    }
    return selected, report
def build_multimodal_spec(
    *,
    name: str,
    title: str,
    region: str,
    category: str,
    targets: list[dict[str, str]],
    created_by: str,
    intent_label: str | None = None,
    preset_ref: str | None = None,
    reserve_targets: list[dict[str, str]] | None = None,
    entity_articles_per_target: int = 4,
    entity_homepages_per_target: int = 1,
    image_works_per_target: int = 1,
    target_entity_count: int | None = None,
    elastic_overfetch: bool = False,
    overfetch_multiplier: float = 1.0,
    allow_quota_shortfall: bool = False,
    allow_over_production: bool = False,
    min_batch_completion_mode: str | None = None,
) -> dict[str, Any]:
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
    lane_concurrency = {"homepage": 3, "article": 3, "image": 4}
    carriers = []
    if entity_articles_per_target > 0:
        carriers.append("article")
    if image_works_per_target > 0:
        carriers.append("image")
    # presetRef：显式传入优先；homepage-only 形态默认绑定 homepage 家族基线。
    resolved_preset = str(preset_ref or "").strip().strip("/")
    if not resolved_preset and homepage_only_delivery:
        candidate = "content/travel/homepage/base"
        if preset_path(candidate).is_file():
            resolved_preset = candidate
    spec = store.scaffold_spec(
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
            "entityTypes": ["地点/景区"],
            # 主清单契约字段（geoTagRef/geoTagRefs/typeTagRefs/aliases）随目标透传，
            # 物化链路（build/homepage.py）据此写 _entity.json 并统一打标（WP3）。
            "coverageTargets": [
                _apply_master_list_fields(
                    {"entityType": row["entityType"], "name": row["name"]}, row
                )
                for row in targets
            ],
            "reserveCoverageTargets": [
                _apply_master_list_fields(
                    {"entityType": row["entityType"], "name": row["name"]}, row
                )
                for row in (reserve_targets or [])
            ],
        },
        content={
            "modalityContract": "separated_research",
            "research": {
                "lanes": research_lanes,
                "maxConcurrency": 10,
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
    reserve_count = len(reserve_targets or [])
    replacement_candidates_per_wave = max(8, min(50, int(math.ceil(max(len(targets), 1) * 0.25))))
    replacement_waves = max(3, int(math.ceil(max(reserve_count, 1) / replacement_candidates_per_wave)))
    reasoned_mode = str(min_batch_completion_mode or "").strip()
    if elastic_overfetch and not reasoned_mode:
        reasoned_mode = "best_effort_with_reasoned_rejects"
    spec["workflowPolicy"] = {
        "allowPartialContent": True,
        "deliveryMode": "partial_with_replacement_report",
        "maxReplacementWaves": replacement_waves,
        "maxReplacementCandidatesPerWave": replacement_candidates_per_wave,
        "maxReplacementScreenedPerRun": max(reserve_count, replacement_candidates_per_wave),
    }
    if elastic_overfetch or allow_quota_shortfall or reasoned_mode:
        spec["workflowPolicy"].update(
            {
                "elasticOverfetch": bool(elastic_overfetch),
                "overfetchMultiplier": float(overfetch_multiplier),
                "targetEntityCount": target_entity_count,
                "targetObjectCount": target_object_count,
                "allowQuotaShortfall": True,
                "allowContentQuotaShortfall": True,
                "allowMinEntityShortfall": True,
                "allowOverProduction": bool(allow_over_production or elastic_overfetch),
                "minBatchCompletionMode": reasoned_mode or "best_effort_with_reasoned_rejects",
                "publishCadence": {
                    "mode": "deterministic_creator_day_spread",
                    "targetDailyObjects": max(1, target_entity_count),
                    "maxDailyPostsPerCreator": 1,
                },
            }
        )
    spec["queuePolicy"] = {
        "backend": "reliabletask",
        "reliableTask": {
            "taskType": "data.content_object.execute",
            "queue": "reliabletask.data.content_supply",
            "store": "MongoStore",
            "readyIndex": "RedisReadyIndex",
        },
        "leaseSeconds": 900,
        "heartbeatSeconds": 60,
        "deadLetterAfterAttempts": 3,
    }
    stamp_execution_branch(spec)
    return spec
def write_selected_task(spec: dict[str, Any], report: dict[str, Any], *, force: bool) -> Path:
    if store.spec_exists(spec["taskId"]) and not force:
        raise FileExistsError(f"task already exists: {spec['taskId']} (use --force)")
    spec_path = store.save_spec(spec)
    targets = (spec.get("scope") or {}).get("coverageTargets") or []
    remaining = [f"{target['entityType']}/{target['name']}" for target in targets]
    store.save_progress(store.init_progress(spec["taskId"], remaining=remaining))
    rows = []
    region = str((spec.get("scope") or {}).get("region") or "")
    for target in targets:
        entity_type = str(target.get("entityType") or "").strip()
        name = str(target.get("name") or "").strip()
        if not entity_type or not name:
            continue
        rows.append(
            {
                "topic_id": f"{entity_type}/{name}",
                "domain": entity_type.split("/", 1)[0] if "/" in entity_type else "",
                "entity_type": entity_type,
                "canonical_name": name,
                "region": region,
                "source_count": 1,
                # 收债 7：geo ref 统一为行政区树路径制（Topic/地理/行政区/**），
                # 只来自主清单契约透传；主清单没有就留空，不再用 /tag/地域/{region} 编造。
                "geo_tag_ref": str(target.get("geoTagRef") or "").strip(),
                "source_kind": "coverageTarget",
                "status": "candidate",
                "taskId": spec["taskId"],
            }
        )
    write_ndjson(task_catalog(spec["taskId"]), rows)
    report_path = store.committed_task_root(spec["taskId"]) / "_shared" / "target_selection.json"
    write_json(report_path, report)
    return spec_path
def _batch_planned_entity_ids(task_id: str, batch_id: str) -> list[str]:
    shared = batch_root(task_id, batch_id) / "_shared"
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
    enabled = enabled or target_object_count >= 100 or target_entity_count >= 15
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
    from _common.source_catalog import platform_category
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
def _site_supply_dynamic_image_precheck_row(
    *,
    task_id: str,
    batch_id: str,
    spec: Mapping[str, Any],
    entity: str,
    single_entity_batch: bool,
    thresholds: Mapping[str, Any],
) -> dict[str, Any] | None:
    workflow = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), Mapping) else {}
    if workflow.get("siteSupplyDynamicContentPlan") is not True or not single_entity_batch:
        return None
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    if int(quotas.get("entityHomepagesPerTarget") or 0) > 0:
        return None
    if int(quotas.get("entityArticlesPerTarget") or 0) > 0:
        return None
    if int(quotas.get("imageWorksPerTarget") or 0) <= 0:
        return None
    root = batch_root(task_id, batch_id)
    report_path = root / "_shared" / "site_supply_content_plan_report.json"
    report = read_json(report_path) if report_path.is_file() else {}
    if not isinstance(report, Mapping):
        return None
    source_collection_ids: set[str] = set()
    publishable_image_count = 0
    for meta_path in (root / "sources").glob("*/meta.json"):
        meta = read_json(meta_path)
        if not isinstance(meta, Mapping):
            continue
        collection = str(
            meta.get("sourceCollectionId")
            or meta.get("collectionId")
            or meta.get("sourceUnitId")
            or meta_path.parent.name
        ).strip()
        if collection:
            source_collection_ids.add(collection)
            publishable_image_count += 1
    try:
        selected_count = int(report.get("selectedCount") or report.get("itemCount") or 0)
    except (TypeError, ValueError):
        selected_count = 0
    image_collection_count = max(len(source_collection_ids), selected_count)
    publishable_image_count = max(publishable_image_count, image_collection_count)
    site_id = str(report.get("siteId") or "").strip()
    source_categories = [f"site_supply:{site_id}"] if site_id and image_collection_count > 0 else []
    issues_by_lane: dict[str, list[str]] = {}
    min_image = int(thresholds.get("minImageSourceCollections") or 0)
    if min_image and image_collection_count < min_image:
        issues_by_lane.setdefault("image", []).append(
            "source precheck publishable image source collections="
            f"{image_collection_count} need>={min_image}"
        )
    if thresholds.get("requireSameSourcePublishableImage") and publishable_image_count <= 0:
        issues_by_lane.setdefault("image", []).append(
            "source precheck same-source publishable image is missing"
        )
    row = {
        "entity": entity,
        "passed": not issues_by_lane,
        "homepageSourceCount": 0,
        "articleSourceCount": 0,
        "articleBaseSourceCount": 0,
        "imageSourceCollectionCount": image_collection_count,
        "publishableImageCount": publishable_image_count,
        "sourceCategoryCount": len(source_categories),
        "sourceCategories": sorted(source_categories),
        "majorOffEntityNoAnchorRejectCount": 0,
        "issuesByLane": issues_by_lane,
    }
    return row

def _source_precheck_report(
    *,
    task_id: str,
    batch_id: str,
    spec: Mapping[str, Any],
    entity_ids: Iterable[str],
    etype: str,
    homepage_failed_entities: set[str],
) -> dict[str, Any]:
    from download.source_inputs import curated_images_for_entity, curated_sources_for_entity
    from vertical.license import validate_image_rights
    from task.run_baseline import _coverage_entity_type_for_entity
    thresholds = _source_precheck_thresholds(spec)
    article_precheck_enabled = int(thresholds.get("minArticleBaseSources") or 0) > 0
    rows: list[dict[str, Any]] = []
    failed_lanes: list[dict[str, Any]] = []
    diagnostics_path = batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json"
    diagnostics = read_json(diagnostics_path) if diagnostics_path.is_file() else {}
    vertical = str(spec.get("vertical") or "travel")
    entity_list = [str(entity).strip() for entity in entity_ids if str(entity).strip()]
    batch_etype = etype
    for entity in entity_list:
        # 与 audit 主循环同源：多类型分区空 batch etype 必须 per-entity 校正。
        etype = _coverage_entity_type_for_entity(dict(spec), entity) or batch_etype
        dynamic_row = _site_supply_dynamic_image_precheck_row(
            task_id=task_id,
            batch_id=batch_id,
            spec=spec,
            entity=entity,
            single_entity_batch=len(entity_list) == 1,
            thresholds=thresholds,
        )
        if dynamic_row is not None:
            rows.append(dynamic_row)
            for lane, issues in (dynamic_row.get("issuesByLane") or {}).items():
                failed_lanes.append({"entity": entity, "lane": lane, "issues": issues})
            continue
        homepage_sources = curated_sources_for_entity(
            task_id,
            batch_id,
            entity,
            etype,
            research_lane="homepage",
        )
        article_sources = curated_sources_for_entity(
            task_id,
            batch_id,
            entity,
            etype,
            research_lane="article",
        )
        image_specs = [
            image for image in curated_images_for_entity(task_id, batch_id, entity, etype)
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

def _replacement_target_rows(state: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in state.get("replacementObjects") or []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("status") or "active") != "active":
            continue
        name = str(item.get("entityId") or "").strip()
        if not name or name in seen:
            continue
        etype = str(item.get("entityType") or "地点/景区").strip()
        rows.append({"name": name, "entityType": etype})
        seen.add(name)
    return rows

def audit_managed_batch(
    task_id: str,
    batch_id: str,
    *,
    workflow_state_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize separated-current lane readiness and image-work capacity."""
    from download.source_inputs import curated_images_for_entity
    from task.run import (
        PipelineContext,
        _active_spec,
        _coverage_entity_ids,
        _coverage_entity_type,
        _download_research_lane_issues,
    )
    from task.run_baseline import _coverage_entity_type_for_entity
    from build.homepage import validate_entity_page_inputs
    spec = store.load_spec(task_id)
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    homepage_quota = int(quotas.get("entityHomepagesPerTarget") or 0)
    article_quota = int(quotas.get("entityArticlesPerTarget") or 0)
    image_quota = int(quotas.get("imageWorksPerTarget") or 0)
    state_path = batch_root(task_id, batch_id) / "_shared" / "task_workflow_state.json"
    state = read_json(state_path) if state_path.is_file() else {}
    if workflow_state_override is not None:
        state = dict(workflow_state_override)
    abandoned_rows = [
        item for item in (state.get("abandonedObjects") or [])
        if isinstance(item, Mapping)
        and str(item.get("entityId") or "").strip()
        and is_terminal_abandonment(item)
    ]
    abandoned_content_rows = [
        item for item in (state.get("abandonedContentObjects") or [])
        if isinstance(item, Mapping) and str(item.get("ref") or "").strip()
        and str(item.get("status") or "abandoned").strip() == "abandoned"
    ]
    abandoned = abandoned_entity_ids(abandoned_rows, scope=ABANDON_SCOPE_ENTITY)
    coverage_entity_ids = _coverage_entity_ids(spec)
    planned_entity_ids = _batch_planned_entity_ids(task_id, batch_id)
    if len(planned_entity_ids) < len(coverage_entity_ids):
        planned_entity_ids = []
    entity_ids = [
        entity for entity in (planned_entity_ids or coverage_entity_ids)
        if entity not in abandoned
    ]
    for row in _replacement_target_rows(state):
        name = str(row.get("name") or "").strip()
        if name and name not in abandoned and name not in entity_ids:
            entity_ids.append(name)
    ctx = PipelineContext(
        task_id=task_id,
        batch_id=batch_id,
        entity_ids=entity_ids,
        spec=spec,
    )
    etype = _coverage_entity_type(spec)
    lanes = ("homepage", "article", "image")
    active_lanes = tuple(
        lane for lane, quota in (
            ("homepage", homepage_quota),
            ("article", article_quota),
            ("image", image_quota),
        )
        if quota > 0
    )
    passed_entities = {lane: set() for lane in lanes}
    failed: list[dict[str, Any]] = []
    image_capacity: dict[str, dict[str, Any]] = {}
    for entity in ctx.entity_ids:
        # 多类型分区 batch 级 etype 为空；读路径必须 per-entity canonical 校正，
        # 否则空 hint 会落默认「打卡地」并与真实 canonical 目录假性类型冲突（WP5）。
        entity_etype = _coverage_entity_type_for_entity(spec, entity) or etype
        for lane in active_lanes:
            issues = _download_research_lane_issues(ctx, entity, entity_etype, lane)
            if issues:
                failed.append({"entity": entity, "lane": lane, "issues": issues})
            else:
                passed_entities[lane].add(entity)
        images = [
            image for image in curated_images_for_entity(task_id, batch_id, entity, entity_etype)
            if str(image.get("researchLane") or "image") == "image"
        ]
        collections: dict[str, int] = {}
        for image in images:
            collection = str(image.get("sourceCollectionId") or "").strip()
            if collection:
                collections[collection] = collections.get(collection, 0) + 1
        image_capacity[entity] = {
            "images": len(images),
            "collections": collections,
            "workCapacity": sum(min(count, 2) for count in collections.values()),
        }
    active_spec = _active_spec(ctx)
    has_homepage_inputs = False
    for target in (active_spec.get("scope") or {}).get("coverageTargets") or []:
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, target_type = require_domain_etype(
            target.get("entityType"),
            context=f"coverageTargets[{name}]",
        )
        if batch_entity_page_input_path(task_id, batch_id, domain, target_type, name).is_file():
            has_homepage_inputs = True
            break
    if homepage_quota > 0 and has_homepage_inputs:
        input_issues_by_entity: dict[str, list[str]] = {}
        for issue in validate_entity_page_inputs(task_id, batch_id, active_spec):
            label = str(issue).split(":", 1)[0]
            entity = label.split("/")[-1] if label else "__batch__"
            input_issues_by_entity.setdefault(entity, []).append(str(issue))
        for entity, issues in input_issues_by_entity.items():
            existing = next(
                (
                    item for item in failed
                    if str(item.get("entity") or "") == entity
                    and str(item.get("lane") or "") == "homepage"
                ),
                None,
            )
            if existing is None:
                failed.append({"entity": entity, "lane": "homepage", "issues": issues})
            else:
                current = existing.setdefault("issues", [])
                for issue in issues:
                    if issue not in current:
                        current.append(issue)
    failed_index = {
        (str(item.get("entity") or ""), str(item.get("lane") or "")): item
        for item in failed
    }
    source_precheck = _source_precheck_report(
        task_id=task_id,
        batch_id=batch_id,
        spec=active_spec,
        entity_ids=ctx.entity_ids,
        etype=etype,
        homepage_failed_entities={
            str(item.get("entity") or "")
            for item in failed
            if str(item.get("lane") or "") == "homepage"
        },
    )
    for item in source_precheck.get("failedLanes") or []:
        if not isinstance(item, Mapping):
            continue
        key = (str(item.get("entity") or ""), str(item.get("lane") or ""))
        existing = failed_index.get(key)
        if existing is not None:
            issues = existing.setdefault("issues", [])
            for issue in item.get("issues") or []:
                if issue not in issues:
                    issues.append(issue)
            continue
        failed.append(dict(item))
        failed_index[key] = failed[-1]
    for item in _workflow_failure_items(state):
        key = (str(item.get("entity") or ""), str(item.get("lane") or ""))
        lane = key[1]
        entity = key[0]
        if lane in passed_entities and entity in passed_entities[lane]:
            continue
        existing = failed_index.get(key)
        if existing is not None:
            issues = existing.setdefault("issues", [])
            for issue in item.get("issues") or []:
                if issue not in issues:
                    issues.append(issue)
            continue
        failed.append(item)
        failed_index[key] = item
    from _common.entity_artifacts import inactive_entity_artifact_rows
    inactive_artifacts = (
        inactive_entity_artifact_rows(
            task_id,
            batch_id,
            active_entity_names=ctx.entity_ids,
        )
        if homepage_quota > 0
        else []
    )
    for row in inactive_artifacts:
        entity = str(row.get("entity") or "")
        key = (entity, "homepage")
        issue = (
            "inactive entity has generated homepage artifact(s) outside active target set: "
            + ", ".join(str(item) for item in (row.get("artifacts") or [])[:8])
        )
        existing = failed_index.get(key)
        if existing is not None:
            issues = existing.setdefault("issues", [])
            if issue not in issues:
                issues.append(issue)
            continue
        item = {"entity": entity, "lane": "homepage", "issues": [issue]}
        failed.append(item)
        failed_index[key] = item
    for item in failed:
        lane = str(item.get("lane") or "")
        entity = str(item.get("entity") or "")
        if lane in passed_entities and entity in passed_entities[lane]:
            passed_entities[lane].remove(entity)
    passed = {lane: len(passed_entities[lane]) for lane in lanes}
    return {
        "schemaVersion": "quwoquan_data.managed_batch_audit",
        "taskId": task_id,
        "batchId": batch_id,
        "targetCount": len(ctx.entity_ids),
        "targetScope": "batch_planned" if planned_entity_ids else "task_coverage",
        "abandonedCount": len(abandoned_rows),
        "abandonedObjects": abandoned_rows,
        "replacementCount": len(_replacement_target_rows(state)),
        "replacementObjects": state.get("replacementObjects") or [],
        "abandonedContentCount": len(abandoned_content_rows),
        "abandonedContentObjects": abandoned_content_rows,
        "inactiveEntityArtifactCount": len(inactive_artifacts),
        "inactiveEntityArtifacts": inactive_artifacts,
        "lanePassed": passed,
        "failedLaneCount": len(failed),
        "failedLanes": failed,
        "sourcePrecheck": source_precheck,
        "imageCapacity": {
            row["entity"]: image_capacity[row["entity"]]
            for row in failed
            if row["lane"] == "image"
        },
        "workflowState": {
            key: state.get(key)
            for key in (
                "status",
                "waitingCheckpoint",
                "nextAction",
                "retryCounts",
                "infrastructureRetryCounts",
                "failedObjects",
            )
        },
        "lastAgentRun": {
            key: (state.get("lastAgentRun") or {}).get(key)
            for key in (
                "stage",
                "jobCount",
                "startedCount",
                "finishedCount",
                "infrastructureFailures",
                "finishedAt",
            )
        },
    }

def handle_select_targets(args: argparse.Namespace) -> None:
    source_task = args.source_task or DEFAULT_SOURCE_TASK_ID
    discovery = Path(args.discovery) if args.discovery else _default_discovery_path()
    excluded = set(_split_csv(args.exclude))
    if args.exclude_from_task and args.exclude_from_batch:
        excluded |= ineligible_targets_from_batch(args.exclude_from_task, args.exclude_from_batch)
    for run_ref in getattr(args, "exclude_from_run", None) or []:
        task_id, batch_id = _parse_run_ref(run_ref)
        excluded |= ineligible_targets_from_batch(task_id, batch_id)
    # 跨批去重账本（task/_shared/dedup_ledger.json，挂 source_task 维度）：
    # promote 采纳过的实体默认不再重复选目标，防跨 task/批次重复生产。
    from _common import dedup
    ledger_completed = {
        str(name).strip()
        for name in dedup.load_manifest(source_task).get("completedEntities", [])
        if str(name).strip()
    }
    mandatory = _split_csv(args.mandatory) if args.mandatory is not None else list(DEFAULT_MANDATORY)
    # 显式点名的 mandatory 目标视为有意重做，只豁免账本排除，不豁免显式 --exclude。
    ledger_excluded = ledger_completed - set(mandatory)
    dedup_excluded = sorted(ledger_excluded - excluded)
    excluded |= ledger_excluded
    requested_limit = max(1, int(args.limit))
    overfetch_multiplier = float(getattr(args, "overfetch_multiplier", 1.0) or 1.0)
    elastic_overfetch = bool(getattr(args, "elastic_overfetch", False))
    selection_limit = requested_limit
    if elastic_overfetch:
        selection_limit = max(requested_limit, int(math.ceil(requested_limit * max(1.0, overfetch_multiplier))))
    targets, report = select_targets(
        discovery_path=discovery,
        limit=selection_limit,
        mandatory=mandatory,
        excluded=excluded,
        reserve_ratio=float(getattr(args, "reserve_ratio", 0.2) or 0.0),
        allow_shortfall=bool(getattr(args, "allow_quota_shortfall", False)),
        source_readiness=_split_csv(getattr(args, "source_readiness", None)),
    )
    spec = build_multimodal_spec(
        name=args.name,
        title=args.title or args.name,
        region=args.region,
        category=args.category,
        targets=targets,
        intent_label=getattr(args, "intent_label", None),
        preset_ref=getattr(args, "preset", None),
        reserve_targets=report.get("reserveTargets") or [],
        created_by=args.owner or "task select-targets",
        entity_articles_per_target=int(getattr(args, "entity_articles_per_target", 4) or 0),
        entity_homepages_per_target=int(getattr(args, "entity_homepages_per_target", 1) or 0),
        image_works_per_target=int(getattr(args, "image_works_per_target", 1) or 0),
        target_entity_count=requested_limit,
        elastic_overfetch=elastic_overfetch,
        overfetch_multiplier=overfetch_multiplier,
        allow_quota_shortfall=bool(getattr(args, "allow_quota_shortfall", False)),
        allow_over_production=bool(getattr(args, "allow_over_production", False)),
        min_batch_completion_mode=str(getattr(args, "min_batch_completion_mode", "") or ""),
    )
    # 跨批去重回写维度：promote 采纳后按 spec.sourceTaskId 写 dedup_ledger。
    spec["sourceTaskId"] = source_task
    report["sourceTaskId"] = source_task
    report["taskId"] = spec["taskId"]
    report["dedupLedger"] = {
        "sourceTaskId": source_task,
        "completedEntityCount": len(ledger_completed),
        "excludedByLedger": dedup_excluded[:50],
        "excludedByLedgerCount": len(dedup_excluded),
    }
    report["quotas"] = (spec.get("content") or {}).get("quotas") or {}
    report["elasticOverfetch"] = {
        "enabled": elastic_overfetch,
        "requestedLimit": requested_limit,
        "selectionLimit": selection_limit,
        "selectedTargets": len(targets),
        "overfetchMultiplier": overfetch_multiplier,
        "allowQuotaShortfall": bool((spec.get("workflowPolicy") or {}).get("allowQuotaShortfall")),
        "allowOverProduction": bool((spec.get("workflowPolicy") or {}).get("allowOverProduction")),
        "minBatchCompletionMode": str((spec.get("workflowPolicy") or {}).get("minBatchCompletionMode") or ""),
    }
    if args.write:
        path = write_selected_task(spec, report, force=bool(args.force))
        print(f"[task select-targets] wrote {spec['taskId']}")
        print(f"  spec: {path}")
        print(
            f"  targets: {len(targets)} "
            f"(requested={requested_limit}, elastic={elastic_overfetch}) "
            f"excluded: {len(excluded)}"
        )
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

def handle_audit_batch(args: argparse.Namespace) -> None:
    report = audit_managed_batch(args.task, args.batch)
    if args.write:
        out = batch_root(args.task, args.batch) / "_shared" / "managed_batch_audit.json"
        write_json(out, report)
        print(f"[task audit-batch] wrote {out}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"[task audit-batch] {args.task} / {args.batch}: "
            f"targets={report['targetCount']} failedLanes={report['failedLaneCount']}"
        )
        print(f"  lanePassed={report['lanePassed']}")
        state = report.get("workflowState") or {}
        print(f"  status={state.get('status')} checkpoint={state.get('waitingCheckpoint')}")
        for item in (report.get("failedLanes") or [])[:50]:
            print(
                f"  - {item['entity']} {item['lane']}: "
                + "; ".join(str(issue) for issue in item.get("issues") or [])[:240]
            )
    if getattr(args, "strict", False) and int(report.get("failedLaneCount") or 0) > 0:
        raise SystemExit(1)
