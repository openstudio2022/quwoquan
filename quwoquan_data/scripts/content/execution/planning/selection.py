"""Reusable single-carrier target selection and execution audit helpers."""
from __future__ import annotations

import hashlib
import time
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
from content.execution.identity import SelectionPolicy, parse_execution_id
from content.execution.planning.capacity_policy import execution_capacity_policy_fields
from content.execution.planning.selection_discovery import coverage_target_from_selection
from content.execution.planning.selection_materialization import write_selected_task
from content.execution.planning.selection_targets import select_targets
from content.execution.planning.media_work_units import project_media_work_units
from content.execution.planning.source_pool_policy import source_pool_policy_fields
from content.execution.planning.source_selection import TargetSourceQualifier

DEFAULT_ARTICLE_ANGLES = ["planning_consultation", "decision_experience", "route_transport", "seasonal_timing"]
@dataclass(frozen=True)
class SelectionRequest:
    """One immutable request for creating an execution work package."""

    execution_id: str
    discovery_path: Path
    limit: int
    quota: int
    oversample_factor: float
    capacity_calibration: Mapping[str, Any]
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
    qualification_candidate_names: tuple[str, ...] | None = None
    qualification_supply_count: int | None = None
    media_work_unit_candidates: tuple[dict[str, Any], ...] = ()
    target_names: tuple[str, ...] = ()
    inherit_frozen_targets: bool = False
    inherited_targets: tuple[dict[str, Any], ...] = ()


def _diversity_carriers(request: SelectionRequest) -> tuple[str, ...]:
    """本次执行真正会产出的载体；多样性上限只对这些载体计数。"""
    return tuple(
        carrier
        for carrier, per_target in (
            ("homepage", request.entity_homepages_per_target),
            ("article", request.entity_articles_per_target),
            ("image", request.image_works_per_target),
            ("video", request.video_works_per_target),
        )
        if int(per_target) > 0
    )


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
    capacity_calibration: Mapping[str, Any],
    frozen_at_epoch_seconds: int | None = None,
    worker_host_set_binding: Mapping[str, Any] | None = None,
    scale_source_pool: Mapping[str, Any] | None = None,
    source_pool_evidence_root_ref: str | None = None,
    source_pool_selection: Mapping[str, Any] | None = None,
    intent_label: str | None = None,
    preset_ref: str | None = None,
    target_entity_count: int | None = None,
    selection_policy: SelectionPolicy = SelectionPolicy.FROZEN,
    media_work_units: tuple[dict[str, Any], ...] = (),
    media_work_unit_exclusions: tuple[dict[str, Any], ...] = (),
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
    if approved_quota < 1 or (
        not media_work_units and approved_quota > target_entity_count
    ):
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
    source_pool_fields = source_pool_policy_fields(
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
    target_object_count = (
        len(media_work_units)
        if media_work_units
        else target_entity_count * objects_per_target
    )
    # 容量在此处一次冻结：工作单元数只能是本执行的对象数，两个并行上限只能
    # 来自选中的 calibration receipt，分区数与 capacityPlanDigest 由二者派生。
    capacity_fields = execution_capacity_policy_fields(
        target_scale=parse_execution_id(validated_execution_id).phase.value,
        carrier=carriers[0],
        work_unit_count=target_object_count,
        capacity_calibration=capacity_calibration,
        frozen_at_epoch_seconds=(
            int(time.time())
            if frozen_at_epoch_seconds is None
            else int(frozen_at_epoch_seconds)
        ),
        worker_host_set_binding=worker_host_set_binding,
    )
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
            },
            "carriers": carriers,
            "quotas": {
                "entityArticlesPerTarget": entity_articles_per_target,
                "imageWorksPerTarget": image_works_per_target,
                "videoWorksPerTarget": video_works_per_target,
                "entityHomepagesPerTarget": entity_homepages_per_target,
                "routeArticles": 0,
            },
            **(
                {"workUnits": [dict(row) for row in media_work_units]}
                if media_work_units
                else {}
            ),
            **(
                {
                    "workUnitExclusions": [
                        dict(row) for row in media_work_unit_exclusions
                    ]
                }
                if media_work_unit_exclusions
                else {}
            ),
        },
        acceptance={
            # 准出只认配额；候选池是过采冗余，不是交付承诺。
            "minEntities": target_entity_count if media_work_units else approved_quota,
            "minPostsPerEntity": 0 if media_work_units else objects_per_target,
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
            qualification_candidate_names=request.qualification_candidate_names,
            qualification_supply_count=request.qualification_supply_count,
            target_names=request.target_names,
            category=request.category,
            inherit_frozen_targets=bool(request.inherit_frozen_targets),
            inherited_targets=request.inherited_targets,
            diversity_carriers=_diversity_carriers(request),
        )
    media_work_units: tuple[dict[str, Any], ...] = ()
    media_work_unit_exclusions: tuple[dict[str, Any], ...] = ()
    if request.media_work_unit_candidates:
        projection = project_media_work_units(
            request.media_work_unit_candidates,
            targets,
        )
        if not projection.work_units:
            raise ValueError(
                "GATE_BLOCK DATA.SOURCE.ENTITY_CATALOG_UNMAPPED: "
                "frozen external media supply has zero governed work units"
            )
        admitted_names = set(projection.coverage_target_names)
        targets = [
            row
            for row in targets
            if str(row.get("name") or "").strip() in admitted_names
        ]
        media_work_units = projection.work_units
        media_work_unit_exclusions = projection.exclusions
        report["availableSupplyCount"] = projection.mapped_object_count
        report["selectionShortfall"] = projection.shortfall(approved_quota)
        report["workUnitCount"] = projection.mapped_object_count
        report["workUnitExclusionCount"] = len(projection.exclusions)
        report["workUnitExclusions"] = [dict(row) for row in projection.exclusions]
        report["selectedCount"] = len(targets)
        report["targets"] = targets
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
        capacity_calibration=request.capacity_calibration,
        worker_host_set_binding=request.worker_host_set_binding,
        scale_source_pool=request.scale_source_pool,
        source_pool_evidence_root_ref=request.source_pool_evidence_root_ref,
        source_pool_selection=request.source_pool_selection,
        selection_policy=request.selection_policy,
        media_work_units=media_work_units,
        media_work_unit_exclusions=media_work_unit_exclusions,
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
