"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type, coverage_entity_type_for_entity
from content.execution.support import Any, ExecutionContext, Mapping, _active_spec, read_json, store, write_json
from core.runtime_policy import active_runtime_policy

def _aggregate_auto_research_throughput(waves: list[Mapping[str, Any]]) -> dict[str, Any]:
    entity_count = sum(int(wave.get("entityCount") or 0) for wave in waves)
    elapsed = sum(float(wave.get("elapsedSeconds") or 0) for wave in waves)
    workers = max((int(wave.get("maxWorkers") or 0) for wave in waves), default=0)
    return {
        "maxWorkers": workers,
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
        for key in (
            "updated",
            "issues",
            "candidates",
            "imageCollections",
            "homepageMediaCollections",
            "sourceUnavailable",
        ):
            aggregate[key] = list(aggregate.get(key) or []) + list(wave_report.get(key) or [])
        aggregate["sourceAvailability"] = _merge_auto_research_source_availability(
            aggregate.get("sourceAvailability"),
            wave_report.get("sourceAvailability"),
        )
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
        "maxAutoResearchWavesPerRun",
        "remainingEntityIds",
        "remainingEntityCount",
        "networkOutage",
    ):
        if key in wave_report:
            aggregate[key] = wave_report.get(key)
        else:
            aggregate.pop(key, None)
    aggregate["updatedAt"] = store.now_iso()
    write_json(path, aggregate)
    return aggregate

def _sync_auto_research_availability(ctx: ExecutionContext, availability: Mapping[str, Any]) -> None:
    from content.execution.recovery.download_unresolved import _auto_research_plan_path
    path = _auto_research_plan_path(ctx)
    if not path.is_file():
        return
    try:
        report = read_json(path)
    except (OSError, ValueError, TypeError):
        return
    # Fetch/screen is stronger evidence than plan-time discovery. A real
    # source fetch may resolve a preliminary media warning, so the synced
    # download verdict intentionally replaces the plan-time availability.
    report["sourceAvailability"] = dict(availability)
    report["sourceAvailabilitySyncedAt"] = store.now_iso()
    write_json(path, report)

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
    for group_type, group_ids in _entity_ids_grouped_by_type(
        ctx,
        stale_ids,
        fallback_type=fallback_type,
    ).items():
        _run_download_auto_research(
            ctx,
            group_ids,
            entity_type=group_type,
            force=True,
            scope="download_fetch_stale_source_plan",
        )
    return entity_ids

def _merge_auto_research_reports(*reports: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    list_keys = (
        "updated",
        "issues",
        "candidates",
        "imageCollections",
        "homepageMediaCollections",
        "sourceUnavailable",
    )
    for report in reports:
        if not isinstance(report, Mapping):
            continue
        if not merged:
            merged = dict(report)
            for key in list_keys:
                merged[key] = list(merged.get(key) or [])
            continue
        for key in list_keys:
            merged.setdefault(key, [])
            merged[key].extend(list(report.get(key) or []))
        outage = report.get("networkOutage")
        if isinstance(outage, Mapping) and not merged.get("networkOutage"):
            merged["networkOutage"] = dict(outage)
        if report.get("partialRun"):
            merged["partialRun"] = True
            merged["partialReason"] = report.get("partialReason") or merged.get("partialReason")
            merged["remainingEntityIds"] = list(report.get("remainingEntityIds") or [])
            merged["remainingEntityCount"] = int(report.get("remainingEntityCount") or 0)
    return merged

def _run_download_auto_research(
    ctx: ExecutionContext,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
    scope: str = "primary",
) -> dict[str, Any]:
    from content.execution.recovery.download_unresolved import _auto_research_plan_path
    from content.execution.pipeline.pipeline_control import _download_auto_research_progress_callback
    from content.source.research.auto_plan_public import write_auto_research_plans
    ids = [str(entity_id).strip() for entity_id in entity_ids if str(entity_id or "").strip()]
    if not ids:
        return {
            "schemaVersion": "quwoquan.content.source.auto_research_plan",
            "executionId": ctx.execution_id,
            "updated": [],
            "issues": [],
            "candidates": [],
            "imageCollections": [],
            "sourceUnavailable": [],
            "sourceAvailability": {
                "readyTargets": [],
                "readyTargetCount": 0,
                "ineligibleTargets": [],
                "ineligibleTargetCount": 0,
            },
            "throughput": {"maxWorkers": 0, "entityCount": 0, "elapsedSeconds": 0, "entitiesPerMinute": 0},
        }
    selected_lanes = _download_auto_research_lanes(ctx)
    runtime_policy = active_runtime_policy()
    worker_count = runtime_policy.research_workers
    wave_size = _auto_research_wave_size(ctx, entity_count=len(ids), worker_count=worker_count)
    max_waves_per_run = runtime_policy.research_max_waves_per_run
    existing_wave_count = 0
    if scope == "primary":
        path = _auto_research_plan_path(ctx)
        if path.is_file():
            try:
                existing = read_json(path)
                existing_wave_count = int(existing.get("waveCount") or 0)
                if existing.get("partialRun"):
                    remaining_ids = [
                        str(entity_id).strip()
                        for entity_id in (existing.get("remainingEntityIds") or [])
                        if str(entity_id or "").strip()
                    ]
                    if remaining_ids:
                        ids = remaining_ids
            except (OSError, ValueError, TypeError):
                existing_wave_count = 0
    latest: dict[str, Any] = {}
    for index in range(0, len(ids), wave_size):
        wave_ids = ids[index:index + wave_size]
        wave_index = index // wave_size + 1
        wave_count = (len(ids) + wave_size - 1) // wave_size
        aggregate_wave_index = existing_wave_count + wave_index
        wave_scope = scope if aggregate_wave_index == 1 else f"{scope}_wave_{aggregate_wave_index}"
        print(
            f"[geo-homepages] download_plan auto_research wave {wave_index}/{wave_count}: "
            f"{len(wave_ids)} entities",
            flush=True,
        )
        aggregate_path = _auto_research_plan_path(ctx)
        previous_aggregate: dict[str, Any] | None = None
        if aggregate_path.is_file():
            try:
                previous_aggregate = read_json(aggregate_path)
            except (OSError, ValueError, TypeError):
                previous_aggregate = None
        auto_report = _merge_auto_research_reports(
            *[
                write_auto_research_plans(
                    ctx.execution_id,
                    group_ids,
                    entity_type=group_type,
                    force=force,
                    lanes=selected_lanes,
                    max_workers=worker_count,
                    progress_callback=_download_auto_research_progress_callback(ctx),
                )
                for group_type, group_ids in _entity_ids_grouped_by_type(
                    ctx,
                    wave_ids,
                    fallback_type=entity_type,
                ).items()
            ]
        )
        if previous_aggregate is not None:
            write_json(aggregate_path, previous_aggregate)
        remaining_ids = ids[index + wave_size:]
        if max_waves_per_run and (wave_index % max_waves_per_run) == 0 and remaining_ids:
            auto_report["partialRun"] = True
            auto_report["partialReason"] = "max_auto_research_waves_per_run"
            auto_report["maxAutoResearchWavesPerRun"] = max_waves_per_run
            auto_report["remainingEntityIds"] = remaining_ids
            auto_report["remainingEntityCount"] = len(remaining_ids)
        latest = _write_auto_research_report(
            ctx,
            auto_report,
            scope=wave_scope,
            entity_ids=wave_ids,
        )
        outage = auto_report.get("networkOutage")
        if isinstance(outage, Mapping) and not (auto_report.get("updated") or []):
            # 出口故障且本 wave 零有效产出：立刻停止后续 wave，
            # 把 networkOutage 透传给 stage 层做网络类可自愈失败。
            latest["networkOutage"] = dict(outage)
            break
        if auto_report.get("partialRun"):
            break
    return latest

def _download_auto_research_lanes(ctx: ExecutionContext) -> set[str] | None:
    """Restrict source discovery lanes to lanes enabled by content quotas."""
    quotas = ((_active_spec(ctx).get("content") or {}).get("quotas") or {})
    lanes: set[str] = set()
    if int(quotas.get("entityHomepagesPerTarget") or 0) > 0:
        lanes.add("homepage")
    if int(quotas.get("entityArticlesPerTarget") or 0) > 0 or int(quotas.get("routeArticles") or 0) > 0:
        lanes.add("article")
    if int(quotas.get("imageWorksPerTarget") or 0) > 0:
        lanes.add("image")
    return lanes or None

def _auto_research_wave_size(ctx: ExecutionContext, *, entity_count: int, worker_count: int) -> int:
    del ctx, worker_count
    configured = active_runtime_policy().research_wave_size
    return min(max(1, entity_count), configured)
