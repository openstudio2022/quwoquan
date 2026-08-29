"""Public auto-research orchestration API."""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from core.data_issue import (
    DataIssueCode, DataIssueStage,
    DataIssueError,
    DataIssueLane,
    DataRecoveryAction,
    data_issue,
)
from core.io import read_json
from core.paths import execution_root
from core.source_catalog import vertical_from_task_id
from content.execution import store
from content.source.prepare import prepare_source_plan, resolve_research_entity_types

from content.source.research import network_breaker
from content.source.research.network_io import NetworkFetchError
from content.source.research.auto_plan_recovery import (
    _invalidate_forced_lane_plans,
    _network_failure_entity_result,
    _recover_homepage_source_plans,
)
from content.source.research.auto_plan_report import (
    _merge_auto_reports,
    _source_availability_summary,
    _write_auto_report_artifacts,
)
from content.source.research.auto_plan_writer import _write_auto_research_plans_impl
from content.source.research.source_discovery_scheduler import (
    EntityTerminalOutcome,
    SourceDiscoveryOutcome,
    SourceDiscoveryStopReason,
    StageProgressSnapshot,
    ThreadPoolSchedulerRuntime,
    run_bounded_source_discovery,
)
from content.source.research.stage_liveness import (
    SINGLE_RUN_OBSERVATION,
    StageStatus,
    write_source_discovery_progress,
)



# 排程为什么停下来与报告怎么描述这次部分运行，是一一对应的显式映射，
# 不由剩余实体是否为空反推。
_PARTIAL_REASON_BY_STOP = {
    SourceDiscoveryStopReason.STAGE_NO_PROGRESS: "stage_no_progress_timeout",
    SourceDiscoveryStopReason.ADMISSION_DEADLINE_REACHED: (
        "fleet_batch_deadline_exhausted"
    ),
}


@dataclass(frozen=True, slots=True)
class _FrozenStageBounds:
    """本 execution 冻结的阶段级取值，全部指回 executionPolicy 一处声明。"""

    entity_timeout_seconds: float
    heartbeat_interval_seconds: int
    heartbeat_stale_after_seconds: int
    fleet_batch_deadline_epoch_seconds: int


def _frozen_stage_bounds(execution_id: str) -> _FrozenStageBounds:
    """Read the frozen per-entity budget and liveness thresholds, fail closed."""
    execution_spec = store.resolve_spec(store.load_spec(execution_id))
    calibration = (
        (execution_spec.get("executionPolicy") or {}).get("capacityCalibration") or {}
    )
    capacity = calibration.get("frozenCapacity")
    liveness = calibration.get("frozenLiveness")
    if not isinstance(capacity, Mapping) or not isinstance(liveness, Mapping):
        raise ValueError(
            "source discovery requires executionPolicy.capacityCalibration with "
            "both frozenCapacity and frozenLiveness; freeze the execution against "
            "a governed calibration receipt before running the stage"
        )
    try:
        return _FrozenStageBounds(
            entity_timeout_seconds=float(capacity["objectWallClockSeconds"]),
            heartbeat_interval_seconds=int(
                liveness["sourceDiscoveryHeartbeatIntervalSeconds"]
            ),
            heartbeat_stale_after_seconds=int(
                liveness["sourceDiscoveryHeartbeatStaleAfterSeconds"]
            ),
            fleet_batch_deadline_epoch_seconds=int(
                calibration["fleetBatchDeadlineEpochSeconds"]
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "frozen source discovery bounds are incomplete: " + str(exc)
        ) from exc


def _existing_report_entity_ids(report: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(report, Mapping):
        return []
    seen: set[str] = set()
    ordered: list[str] = []

    def _add(value: Any) -> None:
        entity_id = str(value or "").strip()
        if entity_id and entity_id not in seen:
            seen.add(entity_id)
            ordered.append(entity_id)

    for wave in report.get("waves") or []:
        if isinstance(wave, Mapping):
            for entity_id in wave.get("entityIds") or []:
                _add(entity_id)
    availability = report.get("sourceAvailability")
    if isinstance(availability, Mapping):
        for entity_id in availability.get("readyTargets") or []:
            _add(entity_id)
        for item in availability.get("ineligibleTargets") or []:
            if isinstance(item, Mapping):
                _add(item.get("entityId"))
    for key in (
        "candidates",
        "imageCollections",
        "homepageMediaAdvisories",
        "sourceUnavailable",
    ):
        for item in report.get(key) or []:
            if isinstance(item, Mapping):
                _add(item.get("entityId"))
    for item in report.get("updated") or []:
        if isinstance(item, Mapping):
            _add(item.get("entityId"))
    return ordered


def _read_existing_auto_research_report(execution_id: str) -> dict[str, Any] | None:
    path = execution_root(execution_id) / "_shared" / "auto_research_plan.json"
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _write_incremental_auto_research_checkpoint(
    execution_id: str,
    *,
    base_report: Mapping[str, Any] | None,
    wave_report: dict[str, Any],
    planned_entity_ids: list[str],
    completed_entity_ids: list[str],
    started_monotonic: float,
    workers: int,
    peak_workers: int,
    partial_reason: str,
) -> None:
    persisted = copy.deepcopy(base_report) if isinstance(base_report, Mapping) else {
        "schema": "quwoquan.content.source.auto_research_plan",
        "executionId": execution_id,
        "vertical": vertical_from_task_id(execution_id),
        "updated": [],
        "issues": [],
        "candidates": [],
        "imageCollections": [],
        "homepageMediaAdvisories": [],
        "sourceUnavailable": [],
        "rescueEvents": [],
    }
    for key in (
        "selectedLanes",
        "imageAssetStrategy",
        "imageCountPolicy",
        "imagePublishableAssetsRequired",
        "scoringPolicy",
        "professionalImageLibraryCompliance",
    ):
        if key in wave_report and key not in persisted:
            persisted[key] = copy.deepcopy(wave_report[key])
    _merge_auto_reports(persisted, wave_report)
    completed_set = set(completed_entity_ids)
    existing_ids = _existing_report_entity_ids(base_report)
    existing_id_set = set(existing_ids)
    scope_ids = existing_ids + [
        entity_id for entity_id in completed_entity_ids
        if entity_id not in existing_id_set
    ]
    elapsed = max(time.monotonic() - started_monotonic, 0.001)
    base_throughput = (
        base_report.get("throughput")
        if isinstance(base_report, Mapping) and isinstance(base_report.get("throughput"), Mapping)
        else {}
    )
    base_elapsed = float(base_throughput.get("elapsedSeconds") or 0)
    total_elapsed = max(base_elapsed + elapsed, 0.001)
    persisted["sourceAvailability"] = _source_availability_summary(persisted, scope_ids)
    persisted["throughput"] = {
        # 冻结上限与实测峰值是两个词元；聚合只取各自的最大值，不互相顶替。
        "factKind": SINGLE_RUN_OBSERVATION,
        "frozenMaxConcurrentWorkers": max(
            int(base_throughput.get("frozenMaxConcurrentWorkers") or 0),
            workers,
        ),
        "peakConcurrentWorkers": max(
            int(base_throughput.get("peakConcurrentWorkers") or 0),
            peak_workers,
        ),
        "entityCount": len(scope_ids),
        "elapsedSeconds": round(total_elapsed, 3),
        "entitiesPerMinute": round(len(scope_ids) / total_elapsed * 60.0, 3),
    }
    persisted["partialRun"] = True
    persisted["partialReason"] = partial_reason
    persisted["remainingEntityIds"] = [
        entity_id for entity_id in planned_entity_ids if entity_id not in completed_set
    ]
    persisted["remainingEntityCount"] = len(persisted["remainingEntityIds"])
    _write_auto_report_artifacts(execution_id, persisted)


def write_auto_research_plans(
    execution_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
    lanes: set[str] | None = None,
    max_workers: int | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    external_input_context: Any | None = None,
) -> dict[str, Any]:
    """Discover separated source plans, optionally parallelized per entity."""
    if lanes is None:
        execution_spec = store.resolve_spec(store.load_spec(execution_id))
        selected_lanes = {
            str(lane).strip()
            for lane in (
                ((execution_spec.get("content") or {}).get("research") or {}).get("lanes")
                or []
            )
            if str(lane).strip()
        }
    else:
        selected_lanes = set(lanes)
    if not selected_lanes:
        raise ValueError("execution must declare at least one research lane")
    vertical = vertical_from_task_id(execution_id)
    started = time.monotonic()
    from core.runtime_policy import active_runtime_policy

    runtime_policy = active_runtime_policy()
    # 并发上限只来自调用方冻结的 calibration；缺省退化为逐实体一线程，运行时策略
    # 不再持有静态 worker 数（见 DEC-002 单轨容量）。
    workers = max(1, max_workers or len(entity_ids))
    bounds = _frozen_stage_bounds(execution_id)
    last_heartbeat_epoch: int | None = None
    measured_peak = 0

    def emit_progress(
        status: StageStatus,
        *,
        completed_count: int = 0,
        running_entity_ids: tuple[str, ...] = (),
        entity_id: str = "",
        message: str = "",
    ) -> None:
        """写一次统一进度面。运行中的每次写入就是一次心跳。"""
        nonlocal last_heartbeat_epoch
        now_epoch = int(time.time())
        progress = write_source_discovery_progress(
            execution_id,
            status=status,
            candidate_entity_count=len(entity_ids),
            terminal_entity_count=completed_count,
            running_entity_ids=running_entity_ids,
            frozen_max_concurrent_workers=workers,
            heartbeat_interval_seconds=bounds.heartbeat_interval_seconds,
            heartbeat_stale_after_seconds=bounds.heartbeat_stale_after_seconds,
            elapsed_seconds=max(time.monotonic() - started, 0.0),
            now_epoch_seconds=now_epoch,
            last_heartbeat_epoch_seconds=last_heartbeat_epoch,
            last_terminal_entity_id=entity_id,
            message=message,
        )
        if status is StageStatus.RUNNING:
            last_heartbeat_epoch = now_epoch
        if progress_callback is not None:
            progress_callback(progress)

    emit_progress(StageStatus.RUNNING, message="auto research started")
    if force:
        _invalidate_forced_lane_plans(
            execution_id,
            entity_ids,
            entity_type=entity_type,
            lanes=selected_lanes,
        )
    # 每次 exact pending workload 独立判定出口故障。
    network_breaker.BREAKER.reset()
    stopped_before_terminal: SourceDiscoveryStopReason | None = None
    remaining_after_stop: list[str] = []
    # 无论几个实体、冻结额度多大，都走同一个调度器：实体数不改变调度语义，
    # 也不让小规模走另一套终态与报告口径。
    resolved_types = resolve_research_entity_types(
        execution_id,
        entity_ids,
        fallback_type=entity_type,
    )
    entities = [
        {
            "entityId": entity_id,
            "canonicalName": entity_id,
            "entityType": resolved_types[entity_id],
        }
        for entity_id in entity_ids
    ]
    prepare_source_plan(execution_id, entities)
    report = {
        "schema": "quwoquan.content.source.auto_research_plan",
        "executionId": execution_id,
        "vertical": vertical,
        "selectedLanes": sorted(selected_lanes),
        "updated": [],
        "issues": [],
        "candidates": [],
        "imageCollections": [],
        "homepageMediaAdvisories": [],
        "sourceUnavailable": [],
    }
    completed_entity_ids: list[str] = []
    base_report = _read_existing_auto_research_report(execution_id)
    no_progress_budget = network_breaker.stage_no_progress_timeout_seconds()

    def _run_entity(entity_id: str) -> dict[str, Any]:
        try:
            return _write_auto_research_plans_impl(
                execution_id,
                [entity_id],
                entity_type=entity_type,
                force=force,
                lanes=selected_lanes,
                write_shared_report=False,
                external_input_context=external_input_context,
            )
        except NetworkFetchError as exc:
            # 出口故障是该实体的判定结论，不是调度失败：额度照常释放，
            # 终态由实体级 typed 结果承载。
            return _network_failure_entity_result(entity_id, exc)

    def _entity_result(outcome: EntityTerminalOutcome) -> dict[str, Any]:
        if outcome.outcome is SourceDiscoveryOutcome.SUCCEEDED:
            return dict(outcome.report or {})
        return {
            "updated": [],
            "issues": [
                f"{outcome.entity_id}: source discovery infrastructure failure: "
                f"{outcome.failure_text}"
            ],
            "candidates": [],
            "imageCollections": [],
            "sourceUnavailable": [
                data_issue(
                    DataIssueCode.INTERNAL_UNEXPECTED,
                    stage=DataIssueStage.DOWNLOAD_PLAN,
                    ref=outcome.entity_id,
                    lane=DataIssueLane.ALL,
                    recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                    message=(
                        "source research worker raised unexpectedly"
                        if outcome.outcome is SourceDiscoveryOutcome.FAILED
                        else "source research exceeded the frozen per-entity budget"
                    ),
                ).as_dict()
            ],
        }

    def _on_terminal(
        outcome: EntityTerminalOutcome,
        progress: StageProgressSnapshot,
    ) -> None:
        nonlocal measured_peak
        measured_peak = progress.measured_peak_concurrent_workers
        _merge_auto_reports(report, _entity_result(outcome))
        completed_entity_ids.append(outcome.entity_id)
        _write_incremental_auto_research_checkpoint(
            execution_id,
            base_report=base_report,
            wave_report=report,
            planned_entity_ids=entity_ids,
            completed_entity_ids=completed_entity_ids,
            started_monotonic=started,
            workers=workers,
            peak_workers=measured_peak,
            partial_reason="incremental_auto_research_checkpoint",
        )
        emit_progress(
            StageStatus.RUNNING,
            completed_count=len(completed_entity_ids),
            running_entity_ids=progress.running_entity_ids,
            entity_id=outcome.entity_id,
            message=(
                f"auto research completed {len(completed_entity_ids)}/"
                f"{len(entity_ids)}"
            ),
        )

    def _on_heartbeat(progress: StageProgressSnapshot) -> None:
        # 心跳与实体终态解耦：即使一个实体也没得出终态，进度面仍按冻结间隔前移。
        nonlocal measured_peak
        measured_peak = progress.measured_peak_concurrent_workers
        emit_progress(
            StageStatus.RUNNING,
            completed_count=progress.terminal_entity_count,
            running_entity_ids=progress.running_entity_ids,
            message=(
                "auto research running "
                f"{progress.terminal_entity_count}/{len(entity_ids)}"
            ),
        )

    runtime = ThreadPoolSchedulerRuntime(
        _run_entity,
        max_workers=min(workers, len(entity_ids)),
    )
    # 冻结批次截止是绝对 epoch 时刻，换算到本 runtime 的单调时钟上做准入判定。
    admission_deadline = started + max(
        bounds.fleet_batch_deadline_epoch_seconds - int(time.time()),
        0,
    )
    try:
        run = run_bounded_source_discovery(
            entity_ids,
            frozen_max_concurrent_workers=workers,
            entity_timeout_seconds=bounds.entity_timeout_seconds,
            heartbeat_interval_seconds=bounds.heartbeat_interval_seconds,
            runtime=runtime,
            on_heartbeat=_on_heartbeat,
            on_terminal=_on_terminal,
            stage_no_progress_timeout_seconds=no_progress_budget or None,
            admission_deadline_seconds=admission_deadline,
            fatal_exceptions=(DataIssueError,),
        )
    except KeyboardInterrupt:
        if completed_entity_ids:
            _write_incremental_auto_research_checkpoint(
                execution_id,
                base_report=base_report,
                wave_report=report,
                planned_entity_ids=entity_ids,
                completed_entity_ids=completed_entity_ids,
                started_monotonic=started,
                workers=workers,
                peak_workers=measured_peak,
                partial_reason="interrupted_auto_research_checkpoint",
            )
        emit_progress(
            StageStatus.INTERRUPTED,
            completed_count=len(completed_entity_ids),
            message="auto research interrupted; queued futures cancelled",
        )
        raise
    measured_peak = run.measured_peak_concurrent_workers
    if run.stop_reason is not SourceDiscoveryStopReason.ALL_ENTITIES_TERMINAL:
        # 未准入或被 watchdog 收回的实体尚未得出终态：落可续跑 checkpoint，
        # 由停下来的原因决定 partialReason，不合并成同一个词元。
        partial_reason = _PARTIAL_REASON_BY_STOP[run.stop_reason]
        stopped_before_terminal = run.stop_reason
        remaining_after_stop = [
            entity_id
            for entity_id in entity_ids
            if entity_id in set(run.abandoned_entity_ids)
        ]
        _write_incremental_auto_research_checkpoint(
            execution_id,
            base_report=base_report,
            wave_report=report,
            planned_entity_ids=entity_ids,
            completed_entity_ids=completed_entity_ids,
            started_monotonic=started,
            workers=workers,
            peak_workers=measured_peak,
            partial_reason=partial_reason,
        )
    recovered_homepage_entities: list[str] = []
    if "homepage" in selected_lanes and stopped_before_terminal is None:
        recovered_homepage_entities = _recover_homepage_source_plans(
            execution_id,
            entity_ids,
            entity_type=entity_type,
            recovery_passes=runtime_policy.source_plan_recovery_passes,
            report=report,
            external_input_context=external_input_context,
        )
    if recovered_homepage_entities:
        report["homepageRecovery"] = {
            "recoveredEntityIds": recovered_homepage_entities,
            "recoveredEntityCount": len(recovered_homepage_entities),
        }
    elapsed = max(time.monotonic() - started, 0.001)
    remaining_set = set(remaining_after_stop)
    scope_ids = [
        entity_id for entity_id in entity_ids if entity_id not in remaining_set
    ]
    report["sourceAvailability"] = _source_availability_summary(report, scope_ids)
    report["throughput"] = run.throughput_facts(
        scope_entity_count=len(scope_ids),
        elapsed_seconds=elapsed,
    )
    stage_made_no_progress = (
        stopped_before_terminal is SourceDiscoveryStopReason.STAGE_NO_PROGRESS
    )
    outage = network_breaker.BREAKER.snapshot()
    if outage.get("openHosts") or stage_made_no_progress:
        report["networkOutage"] = {
            **outage,
            "noProgress": stage_made_no_progress,
        }
    if stopped_before_terminal is not None:
        report["partialRun"] = True
        report["partialReason"] = _PARTIAL_REASON_BY_STOP[stopped_before_terminal]
        report["remainingEntityIds"] = remaining_after_stop
        report["remainingEntityCount"] = len(remaining_after_stop)
        if (
            stopped_before_terminal
            is SourceDiscoveryStopReason.ADMISSION_DEADLINE_REACHED
        ):
            report["fleetBatchDeadlineEpochSeconds"] = (
                bounds.fleet_batch_deadline_epoch_seconds
            )
        _write_auto_report_artifacts(execution_id, report)
        emit_progress(
            StageStatus.INTERRUPTED,
            completed_count=len(scope_ids),
            message=(
                f"auto research stopped as {report['partialReason']}; "
                "remaining entities requeued for resume"
            ),
        )
        return report
    _write_auto_report_artifacts(execution_id, report)
    emit_progress(
        StageStatus.SUCCEEDED,
        completed_count=len(entity_ids),
        message="auto research report written",
    )
    return report
