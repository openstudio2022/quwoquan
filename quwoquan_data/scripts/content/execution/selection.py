"""Reusable single-carrier target selection and execution audit helpers."""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from governance.coverage.entity_extract import require_domain_etype
from core.data_issue import DataIssue
from core.control_types import ExecutionStateStatus
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
from content.execution.contracts import ExecutionStateTransition
from content.execution.selection_materialization import write_selected_task
DEFAULT_ARTICLE_ANGLES = ["planning_consultation", "decision_experience", "route_transport", "seasonal_timing"]


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
    entity_articles_per_target: int
    entity_homepages_per_target: int
    image_works_per_target: int
    video_works_per_target: int
    created_by: str = "execute"
    selection_policy: SelectionPolicy = SelectionPolicy.FROZEN
    force: bool = False


def execution_failure_items(state: ExecutionStateTransition) -> list[dict[str, Any]]:
    status = state.status
    if status in {
        ExecutionStateStatus.SUCCEEDED,
        ExecutionStateStatus.STOPPED_AT_UNTIL,
    }:
        return []
    items: list[dict[str, Any]] = []
    records = state.failed_issue_records
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
                "lane": "execution" if issue.lane.value == "all" else issue.lane.value,
                "issues": [str(issue)],
            }
        )
    if not items:
        failed_objects = [
            str(item) for item in state.failed_objects or [] if str(item).strip()
        ]
        items.append(
            {
                "entity": "__execution__",
                "lane": "execution",
                "issues": failed_objects or [f"execution status={status.value}"],
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
        if list_field == "aliases":
            source_name = str(leaf.get("name") or "").strip()
            canonical_name = str(leaf.get("canonicalName") or source_name).strip()
            if source_name and source_name != canonical_name and source_name not in values:
                values.insert(0, source_name)
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
        "schema": "quwoquan_data.target_selection",
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
def _validated_quota(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def build_execution_spec(
    *,
    execution_id: str,
    name: str,
    title: str,
    region: str,
    category: str,
    targets: list[dict[str, str]],
    created_by: str,
    entity_articles_per_target: int,
    entity_homepages_per_target: int,
    image_works_per_target: int,
    video_works_per_target: int,
    intent_label: str | None = None,
    preset_ref: str | None = None,
    target_entity_count: int | None = None,
    selection_policy: SelectionPolicy = SelectionPolicy.FROZEN,
) -> dict[str, Any]:
    validated_execution_id = validate_execution_id(execution_id)
    if not isinstance(selection_policy, SelectionPolicy):
        raise TypeError("selection_policy must be SelectionPolicy")
    if selection_policy is not SelectionPolicy.FROZEN:
        raise ValueError("content executions require frozen target selection")
    entity_articles_per_target = _validated_quota(
        entity_articles_per_target, field="entityArticlesPerTarget"
    )
    entity_homepages_per_target = _validated_quota(
        entity_homepages_per_target, field="entityHomepagesPerTarget"
    )
    image_works_per_target = _validated_quota(
        image_works_per_target, field="imageWorksPerTarget"
    )
    video_works_per_target = _validated_quota(
        video_works_per_target, field="videoWorksPerTarget"
    )
    resolved_target_count = len(targets) if target_entity_count is None else target_entity_count
    target_entity_count = _validated_quota(
        resolved_target_count, field="targetEntityCount"
    )
    required_article_angles = DEFAULT_ARTICLE_ANGLES[:entity_articles_per_target]
    research_lanes = []
    if entity_homepages_per_target > 0:
        research_lanes.append("homepage")
    if entity_articles_per_target > 0:
        research_lanes.append("article")
    if image_works_per_target > 0:
        research_lanes.append("image")
    if video_works_per_target > 0:
        research_lanes.append("video")
    runtime_policy = active_runtime_policy()
    lane_concurrency = {
        "homepage": runtime_policy.research_workers,
        "article": runtime_policy.research_workers,
        "image": runtime_policy.research_workers,
        "video": runtime_policy.research_workers,
    }
    carriers = []
    if entity_homepages_per_target > 0:
        carriers.append("homepage")
    if entity_articles_per_target > 0:
        carriers.append("article")
    if image_works_per_target > 0:
        carriers.append("image")
    if video_works_per_target > 0:
        carriers.append("video")
    if len(carriers) != 1:
        raise ValueError(
            "execution must enable exactly one carrier; split homepage, article, "
            "image, and video through separate executions"
        )
    objects_per_target = (
        entity_homepages_per_target
        + entity_articles_per_target
        + image_works_per_target
        + video_works_per_target
    )
    target_object_count = target_entity_count * objects_per_target
    selected_entity_types = sorted(
        {
            str(row.get("entityType") or "").strip()
            for row in targets
            if str(row.get("entityType") or "").strip()
        }
    )
    # presetRef：显式传入优先；否则由唯一 carrier 绑定对应家族基线。
    resolved_preset = str(preset_ref or "").strip().strip("/")
    if not resolved_preset:
        candidate = f"content/travel/{carriers[0]}/base"
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
            },
            "carriers": carriers,
            "quotas": {
                "entityArticlesPerTarget": entity_articles_per_target,
                "imageWorksPerTarget": image_works_per_target,
                "videoWorksPerTarget": video_works_per_target,
                "entityHomepagesPerTarget": entity_homepages_per_target,
                "routeArticles": 0,
            },
        },
        acceptance={
            "minEntities": target_entity_count,
            "minPostsPerEntity": objects_per_target,
            "requiredAngles": required_article_angles,
            "scoredAngles": (["image"] if image_works_per_target else []),
        },
        created_by=created_by,
    )
    spec["status"] = "active"
    spec.setdefault("acceptance", {})["requiredAngles"] = required_article_angles
    spec["executionPolicy"] = {
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
    spec = build_execution_spec(
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
        video_works_per_target=int(request.video_works_per_target or 0),
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
