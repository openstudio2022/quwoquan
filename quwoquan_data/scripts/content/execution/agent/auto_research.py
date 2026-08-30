"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type, coverage_entity_type_for_entity
from content.execution.support import Any, ExecutionContext, Mapping, _active_spec, read_json, store, write_json
from content.source.research.auto_plan_report import AUTO_RESEARCH_MERGE_ROW_KEYS
from content.source.research.source_discovery_scheduler import SINGLE_RUN_OBSERVATION

def _aggregate_auto_research_throughput(waves: list[Mapping[str, Any]]) -> dict[str, Any]:
    entity_count = sum(int(wave.get("entityCount") or 0) for wave in waves)
    elapsed = sum(float(wave.get("elapsedSeconds") or 0) for wave in waves)
    # 冻结上限与实测峰值是两个词元，不得互换或合并成一个 worker 数。
    ceiling = max(
        (int(wave.get("frozenMaxConcurrentWorkers") or 0) for wave in waves),
        default=0,
    )
    peak = max(
        (int(wave.get("peakConcurrentWorkers") or 0) for wave in waves),
        default=0,
    )
    return {
        # 聚合出来的仍然是若干次运行的观测事实，不是稳态吞吐或容量结论。
        "factKind": SINGLE_RUN_OBSERVATION,
        "frozenMaxConcurrentWorkers": ceiling,
        "peakConcurrentWorkers": peak,
        "entityCount": entity_count,
        "elapsedSeconds": round(elapsed, 3),
        "entitiesPerMinute": round(entity_count / elapsed * 60, 3) if elapsed > 0 else 0,
        "waveCount": len(waves),
    }

def _merge_auto_research_source_availability(
    base: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge per-wave source availability without losing earlier entity verdicts."""
    if not isinstance(base, Mapping):
        base = {}
    if not isinstance(incoming, Mapping):
        incoming = {}
    ready: list[str] = []
    for source in (base, incoming):
        for entity_id in source.get("readyTargets") or []:
            text = str(entity_id or "").strip()
            if text and text not in ready:
                ready.append(text)
    ineligible_by_id: dict[str, dict[str, Any]] = {}
    for source in (base, incoming):
        for row in source.get("ineligibleTargets") or []:
            if not isinstance(row, Mapping):
                continue
            entity_id = str(row.get("entityId") or "").strip()
            if not entity_id:
                continue
            ineligible_by_id[entity_id] = dict(row)
    ready = [entity_id for entity_id in ready if entity_id not in ineligible_by_id]
    abandoned: list[str] = []
    for source in (base, incoming):
        for entity_id in source.get("abandonedTargets") or []:
            text = str(entity_id or "").strip()
            if text and text not in abandoned:
                abandoned.append(text)
    ineligible = list(ineligible_by_id.values())
    report = {
        "readyTargets": ready,
        "readyTargetCount": len(ready),
        "ineligibleTargets": ineligible,
        "ineligibleTargetCount": len(ineligible),
    }
    if abandoned:
        report["abandonedTargets"] = abandoned
    return report

def _write_auto_research_report(
    ctx: ExecutionContext,
    wave_report: Mapping[str, Any],
    *,
    scope: str,
    entity_ids: list[str],
) -> dict[str, Any]:
    from content.execution.recovery.download_unresolved import _auto_research_plan_path, _auto_research_wave_summary
    path = _auto_research_plan_path(ctx)
    existing: dict[str, Any] = {}
    if scope != "primary" and path.is_file():
        try:
            existing = read_json(path)
        except (OSError, ValueError, TypeError):
            existing = {}
    if scope == "primary" or not existing:
        aggregate: dict[str, Any] = dict(wave_report)
        aggregate["waves"] = []
    else:
        aggregate = dict(existing)
        aggregate["latestWaveSourceAvailability"] = wave_report.get("sourceAvailability") or {}
        for key in AUTO_RESEARCH_MERGE_ROW_KEYS:
            aggregate[key] = list(aggregate.get(key) or []) + list(wave_report.get(key) or [])
        aggregate["sourceAvailability"] = _merge_auto_research_source_availability(
            aggregate.get("sourceAvailability"),
            wave_report.get("sourceAvailability"),
        )
    completed_ids: list[str] = []
    for source in (aggregate.get("completedEntityIds") or [], wave_report.get("completedEntityIds") or []):
        for entity_id in source:
            text = str(entity_id or "").strip()
            if text and text not in completed_ids:
                completed_ids.append(text)
    aggregate["completedEntityIds"] = completed_ids
    aggregate["completedEntityCount"] = len(completed_ids)
    wave = _auto_research_wave_summary(wave_report, scope=scope, entity_ids=entity_ids)
    waves = list(aggregate.get("waves") or [])
    waves.append(wave)
    aggregate["waves"] = waves
    aggregate["latestWave"] = wave
    aggregate["waveCount"] = len(waves)
    aggregate["throughput"] = _aggregate_auto_research_throughput(waves)
    if scope == "primary":
        aggregate["sourceAvailability"] = wave_report.get("sourceAvailability") or {}
    for key in (
        "partialRun",
        "partialReason",
        "fleetBatchDeadlineEpochSeconds",
        "remainingEntityIds",
        "remainingEntityCount",
        "networkOutage",
    ):
        if key in wave_report:
            aggregate[key] = wave_report.get(key)
        else:
            aggregate.pop(key, None)
    aggregate["partialRun"] = bool(wave_report.get("partialRun"))
    aggregate["remainingEntityIds"] = list(
        wave_report.get("remainingEntityIds") or []
    )
    aggregate["remainingEntityCount"] = len(aggregate["remainingEntityIds"])
    aggregate["updatedAt"] = store.now_iso()
    write_json(path, aggregate)
    return aggregate

def _entity_ids_grouped_by_type(
    ctx: ExecutionContext,
    entity_ids: list[str],
    *,
    fallback_type: str = "",
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for entity_id in entity_ids:
        entity_type = coverage_entity_type_for_entity(ctx.spec, entity_id) or fallback_type
        if not entity_type:
            raise ValueError(f"missing entityType for coverage entity {entity_id!r}")
        groups.setdefault(entity_type, []).append(entity_id)
    return groups


def _refresh_stale_source_plans_for_fetch(
    ctx: ExecutionContext,
    entity_ids: list[str],
) -> list[str]:
    """Regenerate stale source plans for the same immutable target set."""
    from content.execution.recovery.download_gate import _stale_source_plan_entities
    from content.source.prepare import prepare_source_plan

    stale_entities = _stale_source_plan_entities(ctx, entity_ids=entity_ids)
    stale_ids = [
        str(item.get("entityId") or "")
        for item in stale_entities
        if item.get("entityId")
    ]
    if not stale_ids:
        return entity_ids
    fallback_type = coverage_entity_type(ctx.spec)
    prepare_source_plan(
        ctx.execution_id,
        [
            {
                "entityId": entity_id,
                "canonicalName": entity_id,
                "entityType": (
                    coverage_entity_type_for_entity(ctx.spec, entity_id)
                    or fallback_type
                ),
            }
            for entity_id in stale_ids
        ],
    )
    _run_download_auto_research(
        ctx,
        stale_ids,
        entity_type=fallback_type,
        force=True,
        scope="download_fetch_stale_source_plan",
    )
    return entity_ids

def _run_download_auto_research(
    ctx: ExecutionContext,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
    scope: str = "primary",
) -> dict[str, Any]:
    from content.execution.recovery.download_unresolved import _auto_research_plan_path
    from content.execution.controller.control import _download_auto_research_progress_callback
    from content.source.research.auto_plan_public import write_auto_research_plans
    from content.execution.campaign.external_input_runtime import (
        bound_runtime_external_input_context,
    )
    from content.execution.identity import parse_execution_id
    ids = [str(entity_id).strip() for entity_id in entity_ids if str(entity_id or "").strip()]
    if not ids:
        return {
            "schema": "quwoquan.content.source.auto_research_plan",
            "executionId": ctx.execution_id,
            "updated": [],
            "issues": [],
            "candidates": [],
            "imageCollections": [],
            "homepageMediaAdvisories": [],
            "sourceUnavailable": [],
            "sourceAvailability": {
                "readyTargets": [],
                "readyTargetCount": 0,
                "ineligibleTargets": [],
                "ineligibleTargetCount": 0,
            },
            "throughput": {
                "factKind": SINGLE_RUN_OBSERVATION,
                "frozenMaxConcurrentWorkers": 0,
                "peakConcurrentWorkers": 0,
                "entityCount": 0,
                "elapsedSeconds": 0,
                "entitiesPerMinute": 0,
            },
        }
    selected_lanes = _download_auto_research_lanes(ctx)
    carrier = parse_execution_id(ctx.execution_id).content_type.value
    external_input_context = bound_runtime_external_input_context(
        ctx.execution_id,
        carrier,
    )
    execution_policy = ctx.spec.execution_policy
    worker_count = execution_policy.auto_research_max_concurrent_workers
    existing_wave_count = 0
    completed_entity_ids: list[str] = []
    existing: dict[str, Any] = {}
    if scope == "primary":
        path = _auto_research_plan_path(ctx)
        if path.is_file():
            try:
                existing = read_json(path)
                existing_wave_count = int(existing.get("waveCount") or 0)
                completed_entity_ids = [
                    str(entity_id).strip()
                    for entity_id in (existing.get("completedEntityIds") or [])
                    if str(entity_id or "").strip()
                ]
                if not completed_entity_ids:
                    remaining = {
                        str(entity_id).strip()
                        for entity_id in (existing.get("remainingEntityIds") or [])
                        if str(entity_id or "").strip()
                    }
                    for wave in existing.get("waves") or []:
                        if not isinstance(wave, Mapping):
                            continue
                        for entity_id in wave.get("entityIds") or []:
                            text = str(entity_id or "").strip()
                            if text and text not in remaining and text not in completed_entity_ids:
                                completed_entity_ids.append(text)
                if existing.get("partialRun"):
                    interrupted_wave_remaining_ids = [
                        str(entity_id).strip()
                        for entity_id in (existing.get("remainingEntityIds") or [])
                        if str(entity_id or "").strip()
                    ]
                    # The writer checkpoints only the unfinished suffix of its
                    # current wave. Continue from the first unresolved item in
                    # the original frozen order so later, never-started waves
                    # are not lost after a process interruption.
                    pending_positions = [
                        ids.index(entity_id)
                        for entity_id in interrupted_wave_remaining_ids
                        if entity_id in ids
                    ]
                    if pending_positions:
                        ids = ids[min(pending_positions):]
            except (OSError, ValueError, TypeError):
                existing_wave_count = 0
                completed_entity_ids = []
                existing = {}
        completed_set = set(completed_entity_ids)
        ids = [entity_id for entity_id in ids if entity_id not in completed_set]
        if not ids and existing:
            result = dict(existing)
            result["partialRun"] = False
            result["remainingEntityIds"] = []
            result["remainingEntityCount"] = 0
            result["completedEntityIds"] = completed_entity_ids
            result["completedEntityCount"] = len(completed_entity_ids)
            return result
    completed_this_run = list(completed_entity_ids)
    # 本次待处理实体一次性交给来源发现调度器：并发上限由调度器按冻结额度约束，
    # 规模增长只增加排队长度。这里再切一层批会形成额外栅栏，让先完成的额度
    # 空等本批最慢的实体，失败或超时释放的额度也无法被下一个实体接管。
    aggregate_index = existing_wave_count + 1
    dispatch_scope = scope if aggregate_index == 1 else f"{scope}_wave_{aggregate_index}"
    print(
        f"[task execute] download_plan auto_research dispatch: {len(ids)} entities "
        f"at a frozen ceiling of {worker_count}",
        flush=True,
    )
    aggregate_path = _auto_research_plan_path(ctx)
    previous_aggregate: dict[str, Any] | None = None
    if aggregate_path.is_file():
        try:
            previous_aggregate = read_json(aggregate_path)
        except (OSError, ValueError, TypeError):
            previous_aggregate = None
    # The research writer resolves the canonical type for each entity from the
    # frozen target set. Splitting heterogeneous targets here serializes small
    # groups and defeats the configured research worker pool.
    auto_report = write_auto_research_plans(
        ctx.execution_id,
        ids,
        entity_type=entity_type,
        force=force,
        lanes=selected_lanes,
        max_workers=worker_count,
        progress_callback=_download_auto_research_progress_callback(ctx),
        external_input_context=external_input_context,
    )
    if previous_aggregate is not None:
        write_json(aggregate_path, previous_aggregate)
    writer_remaining_ids = [
        str(entity_id).strip()
        for entity_id in (auto_report.get("remainingEntityIds") or [])
        if str(entity_id or "").strip() in ids
    ]
    for entity_id in ids:
        if entity_id not in writer_remaining_ids and entity_id not in completed_this_run:
            completed_this_run.append(entity_id)
    auto_report["completedEntityIds"] = list(completed_this_run)
    auto_report["completedEntityCount"] = len(completed_this_run)
    if auto_report.get("partialRun"):
        auto_report["remainingEntityIds"] = writer_remaining_ids
        auto_report["remainingEntityCount"] = len(writer_remaining_ids)
    else:
        auto_report["partialRun"] = False
        auto_report["remainingEntityIds"] = []
        auto_report["remainingEntityCount"] = 0
    latest = _write_auto_research_report(
        ctx,
        auto_report,
        scope=dispatch_scope,
        entity_ids=ids,
    )
    outage = auto_report.get("networkOutage")
    if isinstance(outage, Mapping) and not (auto_report.get("updated") or []):
        # 出口故障且本次零有效产出：把 networkOutage 透传给 stage 层做网络类可自愈失败。
        latest["networkOutage"] = dict(outage)
    return latest

def _download_auto_research_lanes(ctx: ExecutionContext) -> frozenset[str]:
    """Return the research lanes admitted by the immutable execution spec."""
    return frozenset(lane.value for lane in ctx.spec.content.research.lanes)
