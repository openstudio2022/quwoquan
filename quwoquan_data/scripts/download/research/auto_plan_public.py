"""Public auto-research orchestration API."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from _common.source_catalog import vertical_from_task_id
from download.prepare import prepare_source_plan

from download.research.auto_plan_report import (
    _merge_auto_reports,
    _source_availability_summary,
    _write_auto_report_artifacts,
)
from download.research.auto_plan_writer import _write_auto_research_plans_impl
from download.research.progress import _write_auto_research_progress

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
            for future in as_completed(futures):
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
                completed_count += 1
                emit_progress(
                    "running",
                    completed_count=completed_count,
                    entity_id=entity_id,
                    message=f"auto research completed {completed_count}/{len(entity_ids)}",
                )
        except KeyboardInterrupt:
            for future in futures:
                future.cancel()
            emit_progress(
                "interrupted",
                completed_count=len(results),
                message="auto research interrupted; queued futures cancelled",
            )
            shutdown_wait = False
            raise
        finally:
            executor.shutdown(wait=shutdown_wait, cancel_futures=not shutdown_wait)
        for entity_id in entity_ids:
            _merge_auto_reports(report, results.get(entity_id) or {})
    elapsed = max(time.monotonic() - started, 0.001)
    report["sourceAvailability"] = _source_availability_summary(report, entity_ids)
    report["throughput"] = {
        "maxWorkers": workers,
        "entityCount": len(entity_ids),
        "elapsedSeconds": round(elapsed, 3),
        "entitiesPerMinute": round(len(entity_ids) / elapsed * 60.0, 3),
    }
    _write_auto_report_artifacts(task_id, batch_id, report)
    emit_progress(
        "succeeded",
        completed_count=len(entity_ids),
        message="auto research report written",
    )
    return report
