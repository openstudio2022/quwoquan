"""Execution readiness audit across every canonical content lane."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.control_types import ContentType
from core.entity_artifacts import inactive_entity_artifact_rows
from core.paths import execution_entity_page_input_path
from governance.coverage.entity_extract import require_domain_etype

from content.execution import store
from content.execution.contracts import ExecutionStateTransition
from content.execution.execution_state_journal import (
    verify_execution_state_journal_for_execution,
)
from content.execution.planning.selection import (
    execution_failure_items,
    execution_planned_entity_ids,
)
from content.execution.planning.source_precheck import source_precheck_report
from content.execution.spec_contract import ExecutionSpec


def audit_execution_readiness(
    execution_id: str,
    *,
    execution_state_override: ExecutionStateTransition | None = None,
) -> dict[str, Any]:
    """Return one typed report for all enabled content lanes of an execution."""
    verify_execution_state_journal_for_execution(execution_id)
    from content.execution.planning.active_spec import active_spec
    from content.execution.context import ExecutionContext, load_execution_state
    from content.execution.coverage import (
        coverage_entity_ids,
        coverage_entity_type,
        coverage_entity_type_for_entity,
    )
    from content.execution.recovery.download_gate import _download_research_lane_issues
    from content.homepage.homepage import validate_entity_page_inputs
    from content.source.source_inputs import curated_images_for_entity

    spec_model = store.load_spec_model(execution_id)
    spec = spec_model.to_dict()
    quota_by_lane = _quota_by_lane(spec_model)
    state = execution_state_override or load_execution_state(execution_id)
    coverage_ids = coverage_entity_ids(spec)
    planned_ids = execution_planned_entity_ids(execution_id)
    if len(planned_ids) < len(coverage_ids):
        planned_ids = []
    entity_ids = list(planned_ids or coverage_ids)
    ctx = ExecutionContext(execution_id=execution_id, entity_ids=entity_ids, spec=spec)
    execution_etype = coverage_entity_type(spec)
    active_lanes = tuple(lane for lane, quota in quota_by_lane.items() if quota > 0)
    passed_entities = {lane: set() for lane in quota_by_lane}
    failures: list[dict[str, Any]] = []
    image_capacity: dict[str, dict[str, Any]] = {}
    for entity in ctx.entity_ids:
        entity_etype = coverage_entity_type_for_entity(spec, entity) or execution_etype
        for lane in active_lanes:
            issues = _download_research_lane_issues(ctx, entity, entity_etype, lane)
            if issues:
                failures.append(
                    {
                        "entity": entity,
                        "lane": lane,
                        "issues": [issue.as_dict() for issue in issues],
                    }
                )
            else:
                passed_entities[lane].add(entity)
        collections: dict[str, int] = {}
        for image in curated_images_for_entity(execution_id, entity, entity_etype):
            if str(image.get("researchLane") or "image") != "image":
                continue
            collection = str(image.get("sourceCollectionId") or "").strip()
            if collection:
                collections[collection] = collections.get(collection, 0) + 1
        image_capacity[entity] = {
            "images": sum(collections.values()),
            "collections": collections,
            "workCapacity": sum(min(count, 2) for count in collections.values()),
        }
    execution_spec = active_spec(ctx)
    has_page_inputs = _has_page_inputs(execution_id, execution_spec)
    if quota_by_lane["homepage"] > 0 and has_page_inputs:
        _merge_failures(
            failures,
            [
                {"entity": issue.ref or "__execution__", "lane": "homepage", "issues": [str(issue)]}
                for issue in validate_entity_page_inputs(execution_id, execution_spec)
            ],
        )
    precheck = source_precheck_report(
        execution_id=execution_id,
        spec=execution_spec,
        entity_ids=ctx.entity_ids,
        etype=execution_etype,
        homepage_failed_entities={str(item.get("entity") or "") for item in failures if item.get("lane") == "homepage"},
    )
    _merge_failures(failures, [dict(item) for item in precheck.get("failedLanes") or [] if isinstance(item, Mapping)])
    _merge_failures(failures, execution_failure_items(state), skip_when_passed=passed_entities)
    inactive = inactive_entity_artifact_rows(execution_id, active_entity_names=ctx.entity_ids) if quota_by_lane["homepage"] else []
    _merge_failures(
        failures,
        [
            {
                "entity": str(row.get("entity") or ""),
                "lane": "homepage",
                "issues": ["inactive entity has generated homepage artifact(s) outside active target set: " + ", ".join(str(item) for item in (row.get("artifacts") or [])[:8])],
            }
            for row in inactive
        ],
    )
    for item in failures:
        lane, entity = str(item.get("lane") or ""), str(item.get("entity") or "")
        if lane in passed_entities:
            passed_entities[lane].discard(entity)
    return {
        "schema": "quwoquan_data.execution_audit",
        "executionId": execution_id,
        "targetCount": len(ctx.entity_ids),
        "targetScope": "execution_planned" if planned_ids else "execution_coverage",
        "inactiveEntityArtifactCount": len(inactive),
        "inactiveEntityArtifacts": inactive,
        "lanePassed": {lane: len(items) for lane, items in passed_entities.items()},
        "failedLaneCount": len(failures),
        "failedLanes": failures,
        "sourcePrecheck": precheck,
        "imageCapacity": {str(row["entity"]): image_capacity[str(row["entity"])] for row in failures if row.get("lane") == "image" and str(row.get("entity") or "") in image_capacity},
        "executionState": {
            "status": state.status.value,
            "waitingCheckpoint": state.waiting_checkpoint,
            "nextAction": state.next_action,
            "retryCounts": dict(state.retry_counts),
            "infrastructureRetryCounts": dict(state.infrastructure_retry_counts),
            "failedObjects": list(state.failed_objects),
        },
        "lastAgentRun": _last_agent_run_summary(state),
    }


def _quota_by_lane(spec: ExecutionSpec) -> dict[str, int]:
    """Project the closed carrier vocabulary to its configured per-target quota."""

    return {
        content_type.value: spec.content.quotas.for_type(content_type)
        for content_type in ContentType
    }


def _last_agent_run_summary(state: ExecutionStateTransition) -> dict[str, object]:
    from content.execution.agent.history import last_managed_agent_run

    record = last_managed_agent_run(state)
    if record is None:
        return {}
    return {
        "stage": record.stage.value,
        "jobCount": record.job_count,
        "startedCount": record.started_count,
        "finishedCount": record.finished_count,
        "infrastructureFailures": record.infrastructure_failures,
        "finishedAt": record.finished_at,
    }


def _merge_failures(
    target: list[dict[str, Any]],
    additions: list[dict[str, Any]],
    *,
    skip_when_passed: Mapping[str, set[str]] | None = None,
) -> None:
    index = {(str(row.get("entity") or ""), str(row.get("lane") or "")): row for row in target}
    for addition in additions:
        entity, lane = str(addition.get("entity") or ""), str(addition.get("lane") or "")
        if skip_when_passed and lane in skip_when_passed and entity in skip_when_passed[lane]:
            continue
        key = (entity, lane)
        if key not in index:
            copied = {**addition, "issues": list(addition.get("issues") or [])}
            target.append(copied)
            index[key] = copied
            continue
        existing = index[key].setdefault("issues", [])
        for issue in addition.get("issues") or []:
            if issue not in existing:
                existing.append(issue)


def _has_page_inputs(execution_id: str, spec: Mapping[str, Any]) -> bool:
    for target in (spec.get("scope") or {}).get("coverageTargets") or []:
        if not isinstance(target, Mapping):
            continue
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, entity_type = require_domain_etype(
            target.get("entityType"),
            context=f"coverageTargets[{name}]",
        )
        if execution_entity_page_input_path(execution_id, domain, entity_type, name).is_file():
            return True
    return False
