"""Reusable single-carrier target selection and execution audit helpers."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.control_types import ExecutionStateStatus, TargetSelector
from core.data_issue import DataIssue
from core.execution_branch import stamp_execution_branch
from core.paths import (
    preset_path,
)
from core.runtime_policy import active_runtime_policy

from content.execution import store, validate_execution_id
from content.execution.contracts import ExecutionStateTransition
from content.execution.identity import SelectionPolicy
from content.execution.planning.capacity_policy import execution_capacity_policy_fields
from content.execution.planning.selection_discovery import (
    coverage_target_from_selection,
    leaf_selection_name,
    load_partitions,
    ordered_partition_leaves,
    partition_targets,
    resolve_target_names,
)
from content.execution.planning.selection_materialization import write_selected_task
from content.execution.planning.source_pool_policy import source_pool_policy_fields
from content.execution.planning.source_selection import (
    TargetSourceQualifier,
    qualify_source_ready_targets,
)

DEFAULT_ARTICLE_ANGLES = ["planning_consultation", "decision_experience", "route_transport", "seasonal_timing"]
@dataclass(frozen=True)
class SelectionRequest:
    """One immutable request for creating an execution work package."""

    execution_id: str
    discovery_path: Path
    limit: int
    quota: int
    oversample_factor: float
    required_workers: int
    partition_count: int
    capacity_plan_digest: str
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
    worker_host_set_binding: Mapping[str, Any] | None = None
    scale_source_pool: Mapping[str, Any] | None = None
    source_pool_evidence_root_ref: str | None = None
    source_pool_selection: Mapping[str, Any] | None = None
    source_pool_targets: tuple[dict[str, Any], ...] = ()
    created_by: str = "execute"
    selection_policy: SelectionPolicy = SelectionPolicy.FROZEN
    target_selector: TargetSelector = TargetSelector.ALL
    source_qualifier: TargetSourceQualifier | None = None
    qualification_source_key: str = "qualifiedHomepageSource"
    persist_qualified_source: bool = True
    target_names: tuple[str, ...] = ()
    inherit_frozen_targets: bool = False
    inherited_targets: tuple[dict[str, Any], ...] = ()


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

def _candidate_pool_exhausted(
    *,
    selected_count: int,
    quota: int,
    limit: int,
    discovery_path: Path,
) -> ValueError:
    return ValueError(
        f"候选池耗尽，区域实体供给不足：selected={selected_count} quota={quota} "
        f"candidatePool={limit} discovery={discovery_path}"
    )


def _matches_category(
    row: Mapping[str, Any],
    category: str | None,
) -> bool:
    """Match a declared selection category against a structured entity type."""
    requested = str(category or "").strip()
    if not requested:
        return True
    entity_type = str(row.get("entityType") or "").strip()
    if not entity_type:
        return False
    if entity_type == requested:
        return True
    return requested in {
        segment.strip()
        for segment in entity_type.split("/")
        if segment.strip()
    }


def select_targets(
    *,
    discovery_path: Path,
    limit: int,
    quota: int,
    target_selector: TargetSelector,
    source_qualifier: TargetSourceQualifier | None = None,
    qualification_source_key: str = "qualifiedHomepageSource",
    persist_qualified_source: bool = True,
    target_names: tuple[str, ...] = (),
    category: str | None = None,
    inherit_frozen_targets: bool = False,
    inherited_targets: tuple[dict[str, Any], ...] = (),
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Select up to ``limit`` candidates and require at least ``quota`` of them.

    ``limit`` is the oversampled candidate pool, not a delivery promise: objects
    that later fail a quality gate are discarded rather than retried, so the pool
    is intentionally larger than the approved quota.  Only falling below the
    quota is a selection failure.
    """
    if not isinstance(target_selector, TargetSelector):
        raise TypeError("target_selector must be TargetSelector")
    if isinstance(quota, bool) or not isinstance(quota, int) or quota < 1:
        raise ValueError("quota must be a positive integer")
    if quota > limit:
        raise ValueError(
            f"approved quota {quota} exceeds the candidate pool {limit}"
        )
    partitions = load_partitions(discovery_path)
    all_by_name = partition_targets(partitions, target_selector=target_selector)
    by_name = {
        name: row
        for name, row in all_by_name.items()
        if _matches_category(row, category)
    }
    selected: list[dict[str, str]] = []
    seen: set[str] = set()

    if target_selector is TargetSelector.SOURCE_READY_PRIORITY and source_qualifier is None:
        raise ValueError("source-ready-priority requires source_qualifier")
    if target_names:
        target_catalog = all_by_name if inherit_frozen_targets else by_name
        resolved_target_names = resolve_target_names(target_catalog, target_names)
        if (
            target_selector is not TargetSelector.SOURCE_READY_PRIORITY
            or inherit_frozen_targets
        ):
            if inherit_frozen_targets and target_selector is TargetSelector.SOURCE_READY_PRIORITY:
                # retryOf must keep the predecessor's exact candidate pool.
                # Re-probing Commons/Wikipedia here is unbounded and can reshape
                # the immutable retry set; download admission re-verifies rights.
                if source_qualifier is None:
                    raise ValueError("source-ready-priority requires source_qualifier")
            if inherited_targets:
                inherited_names = tuple(
                    str(row.get("name") or "").strip()
                    for row in inherited_targets
                )
                if inherited_names != resolved_target_names:
                    raise ValueError(
                        "inherited target rows must match the resolved canonical "
                        "target order exactly"
                    )
                selected = [dict(row) for row in inherited_targets]
            else:
                selected = [target_catalog[name] for name in resolved_target_names]
            report = {
                "schema": "quwoquan_data.target_selection",
                "strategy": (
                    "inherited frozen target order"
                    if inherit_frozen_targets
                    else "explicit frozen target order"
                ),
                "targetSelector": target_selector.value,
                "discoveryPath": str(discovery_path),
                "limit": limit,
                "approvedQuota": quota,
                "selectedCount": len(selected),
                "selectionShortfall": max(0, quota - len(selected)),
                "targets": selected,
                "requestedTargetNames": list(target_names),
                "inheritedFrozenTargets": bool(inherit_frozen_targets),
            }
            if category:
                report["category"] = str(category).strip()
            if len(selected) < quota:
                raise _candidate_pool_exhausted(
                    selected_count=len(selected),
                    quota=quota,
                    limit=limit,
                    discovery_path=discovery_path,
                )
            return selected, report

    def add(name: str) -> None:
        if name in seen or len(selected) >= limit:
            return
        row = by_name.get(name)
        if not row:
            return
        selected.append(row)
        seen.add(name)

    candidate_rows: list[dict[str, Any]] = []
    candidate_names: set[str] = set()
    depth = 0
    while True:
        scanned_any = False
        for part in partitions:
            leaves = ordered_partition_leaves(part, target_selector=target_selector)
            if depth >= len(leaves):
                continue
            scanned_any = True
            name = leaf_selection_name(leaves[depth])
            row = by_name.get(name)
            if row is not None and name not in candidate_names:
                candidate_rows.append(row)
                candidate_names.add(name)
        if not scanned_any:
            break
        depth += 1

    if target_selector is TargetSelector.SOURCE_READY_PRIORITY:
        assert source_qualifier is not None
        selected, source_qualification, requested_target_names = qualify_source_ready_targets(
            candidate_rows,
            discovery_ref=str(discovery_path),
            limit=limit,
            quota=quota,
            source_qualifier=source_qualifier,
            target_names=target_names,
            qualification_source_key=qualification_source_key,
            persist_qualified_source=persist_qualified_source,
        )
    else:
        for row in candidate_rows:
            add(str(row["name"]))
            if len(selected) >= limit:
                break
    # 与 qualify_source_ready_targets 的非 persist 语义保持同一真相源：
    # persist lane（homepage）把 quota 当交付承诺的准入门；非 persist lane
    # （video 等）的真实供给由冻结外部输入 receipt 决定，qualification 只是
    # precheck，approvedQuota 是 scale milestone 而非 lane 级 veto。内层已对
    # persist 或零供给 fail-closed，这里不得对非 persist 的部分供给二次 veto。
    non_persist_source_ready = (
        target_selector is TargetSelector.SOURCE_READY_PRIORITY
        and not persist_qualified_source
    )
    if len(selected) < quota and (not non_persist_source_ready or not selected):
        raise _candidate_pool_exhausted(
            selected_count=len(selected),
            quota=quota,
            limit=limit,
            discovery_path=discovery_path,
        )
    report = {
        "schema": "quwoquan_data.target_selection",
        "strategy": "deterministic round-robin regional coverage",
        "targetSelector": target_selector.value,
        "discoveryPath": str(discovery_path),
        "limit": limit,
        "approvedQuota": quota,
        "selectedCount": len(selected),
        "selectionShortfall": max(0, quota - len(selected)),
        "targets": selected,
    }
    if category:
        report["category"] = str(category).strip()
    if target_selector is TargetSelector.SOURCE_READY_PRIORITY:
        report["sourceQualification"] = source_qualification
        if requested_target_names:
            report["requestedTargetNames"] = list(requested_target_names)
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
    targets: list[dict[str, Any]],
    created_by: str,
    entity_articles_per_target: int,
    entity_homepages_per_target: int,
    image_works_per_target: int,
    video_works_per_target: int,
    approved_quota: int,
    oversample_factor: float,
    required_workers: int,
    partition_count: int,
    capacity_plan_digest: str,
    worker_host_set_binding: Mapping[str, Any] | None = None,
    scale_source_pool: Mapping[str, Any] | None = None,
    source_pool_evidence_root_ref: str | None = None,
    source_pool_selection: Mapping[str, Any] | None = None,
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
    approved_quota = _validated_quota(approved_quota, field="approvedQuota")
    if approved_quota < 1 or approved_quota > target_entity_count:
        raise ValueError(
            f"approvedQuota {approved_quota} must be between 1 and the candidate "
            f"pool {target_entity_count}"
        )
    if (
        isinstance(oversample_factor, bool)
        or not isinstance(oversample_factor, (int, float))
        or oversample_factor < 1
    ):
        raise ValueError("oversampleFactor must be a number >= 1")
    capacity_fields = execution_capacity_policy_fields(
        required_workers=required_workers,
        partition_count=partition_count,
        capacity_plan_digest=capacity_plan_digest,
        worker_host_set_binding=worker_host_set_binding,
    )
    source_pool_fields = source_pool_policy_fields(
        validated_execution_id,
        binding=scale_source_pool,
        evidence_root_ref=source_pool_evidence_root_ref,
        selection=source_pool_selection,
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
            "coverageTargets": [coverage_target_from_selection(row) for row in targets],
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
            # 准出只认配额；候选池是过采冗余，不是交付承诺。
            "minEntities": approved_quota,
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
        # targetEntityCount 是候选池；approvedQuota 才是准出配额。
        "targetEntityCount": target_entity_count,
        "targetObjectCount": target_object_count,
        "approvedQuota": approved_quota,
        "oversampleFactor": float(oversample_factor),
        **capacity_fields,
        # Scale article source plans must use the registry-admitted commercial
        # frontier; they may not fall back to uncontrolled platform sources.
        "articleCommercialClosure": carriers == ["article"],
    }
    spec["executionPolicy"].update(source_pool_fields)
    # 冻结当前正式分支与 commit，供 execution schema、重放与审计同源消费。
    # detached campaign lane 仅可通过 execution_branch 的受控 frozen-mainline
    # 环境回退解析分支，普通 detached 执行仍会在 schema/preflight fail-closed。
    stamp_execution_branch(spec)
    spec["queuePolicy"] = {
        # Semantic author/reviewer state is local create-once journal truth.
        # ReliableTask remains declared below only as the independent pool
        # delivery transport selected by the frozen queue envelope.
        "backend": "local_file",
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
def create_execution_selection(request: SelectionRequest) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select targets and write the sole execution manifest/specification."""
    execution_id = validate_execution_id(request.execution_id)
    if not isinstance(request.selection_policy, SelectionPolicy):
        raise TypeError("SelectionRequest.selection_policy must be SelectionPolicy")
    if request.selection_policy is not SelectionPolicy.FROZEN:
        raise ValueError("content executions require frozen target selection")
    if not isinstance(request.target_selector, TargetSelector):
        raise TypeError("SelectionRequest.target_selector must be TargetSelector")
    discovery = request.discovery_path
    requested_limit = max(1, int(request.limit))
    approved_quota = int(request.quota)
    if request.scale_source_pool is not None:
        from content.source.research.scale_source_pool_runtime import (
            select_frozen_source_pool_targets,
        )
        targets, report = select_frozen_source_pool_targets(
            targets=request.source_pool_targets,
            requested_limit=requested_limit,
            approved_quota=approved_quota,
            target_names=request.target_names,
            discovery_path=discovery,
            pool_binding=request.scale_source_pool,
            lane_selection=request.source_pool_selection or {},
        )
    else:
        targets, report = select_targets(
            discovery_path=discovery,
            limit=requested_limit,
            quota=approved_quota,
            target_selector=request.target_selector,
            source_qualifier=request.source_qualifier,
            qualification_source_key=request.qualification_source_key,
            persist_qualified_source=request.persist_qualified_source,
            target_names=request.target_names,
            category=request.category,
            inherit_frozen_targets=bool(request.inherit_frozen_targets),
            inherited_targets=request.inherited_targets,
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
        target_entity_count=len(targets),
        approved_quota=approved_quota,
        oversample_factor=float(request.oversample_factor),
        required_workers=request.required_workers,
        partition_count=request.partition_count,
        capacity_plan_digest=request.capacity_plan_digest,
        worker_host_set_binding=request.worker_host_set_binding,
        scale_source_pool=request.scale_source_pool,
        source_pool_evidence_root_ref=request.source_pool_evidence_root_ref,
        source_pool_selection=request.source_pool_selection,
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
    write_selected_task(spec, report)
    return spec, report
