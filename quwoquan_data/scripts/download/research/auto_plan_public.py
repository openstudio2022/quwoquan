"""Public auto-research orchestration API."""
from __future__ import annotations

import copy
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any, Callable, Mapping

from _common.io import read_json
from _common.paths import batch_root
from _common.source_catalog import vertical_from_task_id
from download.prepare import prepare_source_plan

from download.research import network_breaker
from download.research.auto_plan_report import (
    _merge_auto_reports,
    _source_availability_summary,
    _write_auto_report_artifacts,
)
from download.research.auto_plan_writer import _write_auto_research_plans_impl
from download.research.progress import _write_auto_research_progress


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
    for key in ("candidates", "imageCollections", "sourceUnavailable"):
        for item in report.get(key) or []:
            if isinstance(item, Mapping):
                _add(item.get("entityId"))
    for item in report.get("updated") or []:
        if isinstance(item, Mapping):
            _add(item.get("entityId"))
    return ordered


def _read_existing_auto_research_report(task_id: str, batch_id: str) -> dict[str, Any] | None:
    path = batch_root(task_id, batch_id) / "_shared" / "auto_research_plan.json"
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _write_incremental_auto_research_checkpoint(
    task_id: str,
    batch_id: str,
    *,
    base_report: Mapping[str, Any] | None,
    wave_report: dict[str, Any],
    planned_entity_ids: list[str],
    completed_entity_ids: list[str],
    started_monotonic: float,
    workers: int,
    partial_reason: str,
) -> None:
    persisted = copy.deepcopy(base_report) if isinstance(base_report, Mapping) else {
        "schemaVersion": "quwoquan.download.auto_research_plan",
        "taskId": task_id,
        "batchId": batch_id,
        "vertical": vertical_from_task_id(task_id),
        "updated": [],
        "issues": [],
        "candidates": [],
        "imageCollections": [],
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
        "maxWorkers": max(int(base_throughput.get("maxWorkers") or 0), workers),
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
    _write_auto_report_artifacts(task_id, batch_id, persisted)


def write_auto_research_plans(
    task_id: str,
    batch_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
    lanes: set[str] | None = None,
    max_workers: int = 1,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Discover separated source plans, optionally parallelized per entity."""
    selected_lanes = lanes or {"homepage", "article", "image"}
    vertical = vertical_from_task_id(task_id)
    started = time.monotonic()
    workers = max(1, int(max_workers or 1))

    def emit_progress(
        status: str,
        *,
        completed_count: int = 0,
        entity_id: str = "",
        message: str = "",
    ) -> None:
        progress = _write_auto_research_progress(
            task_id,
            batch_id,
            status=status,
            entity_count=len(entity_ids),
            completed_count=completed_count,
            entity_id=entity_id,
            workers=workers,
            started_monotonic=started,
            message=message,
        )
        if progress_callback is not None:
            progress_callback(progress)

    emit_progress("running", message="auto research started")
    # 每次 wave 独立判定出口故障；跨 wave 网络状态可能已恢复。
    network_breaker.BREAKER.reset()
    network_breaker.start_wave_budget()
    no_progress_timed_out = False
    remaining_after_timeout: list[str] = []
    if workers <= 1 or len(entity_ids) <= 1:
        report = _write_auto_research_plans_impl(
            task_id,
            batch_id,
            entity_ids,
            entity_type=entity_type,
            force=force,
            lanes=selected_lanes,
            write_shared_report=False,
        )
        emit_progress(
            "running",
            completed_count=len(entity_ids),
            message="auto research completed for all entities",
        )
    else:
        entities = [
            {"entityId": entity_id, "canonicalName": entity_id, "entityType": entity_type}
            for entity_id in entity_ids
        ]
        prepare_source_plan(task_id, batch_id, entities)
        report = {
            "schemaVersion": "quwoquan.download.auto_research_plan",
            "taskId": task_id,
            "batchId": batch_id,
            "vertical": vertical,
            "selectedLanes": sorted(selected_lanes),
            "updated": [],
            "issues": [],
            "candidates": [],
            "imageCollections": [],
            "sourceUnavailable": [],
        }
        results: dict[str, dict[str, Any]] = {}
        completed_entity_ids: list[str] = []
        base_report = _read_existing_auto_research_report(task_id, batch_id)
        executor = ThreadPoolExecutor(max_workers=min(workers, len(entity_ids)))
        futures = {}
        shutdown_wait = True
        try:
            futures = {
                executor.submit(
                    _write_auto_research_plans_impl,
                    task_id,
                    batch_id,
                    [entity_id],
                    entity_type=entity_type,
                    force=force,
                    lanes=selected_lanes,
                    write_shared_report=False,
                ): entity_id
                for entity_id in entity_ids
            }
            completed_count = 0
            no_progress_budget = network_breaker.stage_no_progress_timeout_seconds()
            pending = set(futures)
            while pending:
                done, pending = wait(
                    pending,
                    timeout=no_progress_budget or None,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    # stage 无进展 watchdog：预算内没有任何实体完成 → 取消剩余、
                    # 落可续跑 checkpoint，交上层按 network/no-progress outage 处理。
                    no_progress_timed_out = True
                    for future in pending:
                        future.cancel()
                    remaining_after_timeout = sorted(
                        futures[future] for future in pending
                    )
                    break
                for future in done:
                    entity_id = futures[future]
                    try:
                        results[entity_id] = future.result()
                    except Exception as exc:  # noqa: BLE001
                        results[entity_id] = {
                            "updated": [],
                            "issues": [f"{entity_id}: source discovery infrastructure failure: {type(exc).__name__}: {exc}"],
                            "candidates": [],
                            "imageCollections": [],
                            "sourceUnavailable": [
                                {
                                    "entityId": entity_id,
                                    "lane": "all",
                                    "reason": f"source discovery infrastructure failure: {type(exc).__name__}: {exc}",
                                    "nextAction": "retry_source_discovery",
                                }
                            ],
                        }
                    _merge_auto_reports(report, results[entity_id])
                    completed_entity_ids.append(entity_id)
                    completed_count += 1
                    _write_incremental_auto_research_checkpoint(
                        task_id,
                        batch_id,
                        base_report=base_report,
                        wave_report=report,
                        planned_entity_ids=entity_ids,
                        completed_entity_ids=completed_entity_ids,
                        started_monotonic=started,
                        workers=workers,
                        partial_reason="incremental_auto_research_checkpoint",
                    )
                    emit_progress(
                        "running",
                        completed_count=completed_count,
                        entity_id=entity_id,
                        message=f"auto research completed {completed_count}/{len(entity_ids)}",
                    )
            if no_progress_timed_out:
                _write_incremental_auto_research_checkpoint(
                    task_id,
                    batch_id,
                    base_report=base_report,
                    wave_report=report,
                    planned_entity_ids=entity_ids,
                    completed_entity_ids=completed_entity_ids,
                    started_monotonic=started,
                    workers=workers,
                    partial_reason="stage_no_progress_timeout",
                )
                shutdown_wait = False
        except KeyboardInterrupt:
            for future in futures:
                future.cancel()
            if completed_entity_ids:
                _write_incremental_auto_research_checkpoint(
                    task_id,
                    batch_id,
                    base_report=base_report,
                    wave_report=report,
                    planned_entity_ids=entity_ids,
                    completed_entity_ids=completed_entity_ids,
                    started_monotonic=started,
                    workers=workers,
                    partial_reason="interrupted_auto_research_checkpoint",
                )
            emit_progress(
                "interrupted",
                completed_count=len(results),
                message="auto research interrupted; queued futures cancelled",
            )
            shutdown_wait = False
            raise
        finally:
            executor.shutdown(wait=shutdown_wait, cancel_futures=not shutdown_wait)
    elapsed = max(time.monotonic() - started, 0.001)
    scope_ids = (
        [entity_id for entity_id in entity_ids if entity_id not in set(remaining_after_timeout)]
        if no_progress_timed_out
        else list(entity_ids)
    )
    report["sourceAvailability"] = _source_availability_summary(report, scope_ids)
    report["throughput"] = {
        "maxWorkers": workers,
        "entityCount": len(scope_ids),
        "elapsedSeconds": round(elapsed, 3),
        "entitiesPerMinute": round(len(scope_ids) / elapsed * 60.0, 3),
    }
    wave_budget_exceeded = network_breaker.wave_budget_exceeded()
    outage = network_breaker.BREAKER.snapshot()
    network_breaker.clear_wave_budget()
    if outage.get("openHosts") or no_progress_timed_out or wave_budget_exceeded:
        report["networkOutage"] = {
            **outage,
            "noProgress": no_progress_timed_out,
            "waveBudgetExceeded": wave_budget_exceeded,
        }
    if no_progress_timed_out:
        report["partialRun"] = True
        report["partialReason"] = "stage_no_progress_timeout"
        report["remainingEntityIds"] = remaining_after_timeout
        report["remainingEntityCount"] = len(remaining_after_timeout)
        _write_auto_report_artifacts(task_id, batch_id, report)
        emit_progress(
            "interrupted",
            completed_count=len(scope_ids),
            message="auto research no-progress timeout; remaining entities requeued for resume",
        )
        return report
    _write_auto_report_artifacts(task_id, batch_id, report)
    emit_progress(
        "succeeded",
        completed_count=len(entity_ids),
        message="auto research report written",
    )
    return report
