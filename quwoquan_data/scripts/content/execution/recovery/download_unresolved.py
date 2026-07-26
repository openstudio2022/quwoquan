"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type
from content.execution.support import Any, DataIssue, DataIssueCode, DataIssueStage, DataIssueLane, DataRecoveryAction, ExecutionContext, MAX_REACT_REWINDS, Mapping, Path, _active_spec, _download_repair_lanes, data_issue, execution_root, issue_messages, load_execution_state, re, read_json, require_domain_etype, store, write_json
from content.execution.target_integrity import frozen_target_names

def _download_plan_unresolved_entities(ctx: ExecutionContext) -> dict[str, dict[str, list[str]]]:
    from content.execution.recovery.download_gate import _download_research_lane_issues
    etype = coverage_entity_type(ctx.spec)
    unresolved: dict[str, dict[str, list[str]]] = {}
    for entity in frozen_target_names(ctx):
        lane_issues = {
            lane: issue_messages(issues)
            for lane in ("homepage", "article", "image")
            if (issues := _download_research_lane_issues(ctx, entity, etype, lane))
        }
        if lane_issues:
            unresolved[entity] = lane_issues
    for entity_id, lanes in _pending_download_repair_unresolved(ctx).items():
        entity_lanes = unresolved.setdefault(entity_id, {})
        for lane, issues in lanes.items():
            lane_rows = entity_lanes.setdefault(lane, [])
            for issue in issues:
                text = str(issue or "").strip()
                if text and text not in lane_rows:
                    lane_rows.append(text)
    return unresolved

def _download_plan_repair_exhausted_unresolved(
    ctx: ExecutionContext,
    unresolved: Mapping[str, Mapping[str, list[str]]],
) -> dict[str, dict[str, list[str]]]:
    """Return unresolved rows after the bounded automatic repair budget."""
    state = load_execution_state(ctx.execution_id)
    react_rewinds = state.react_rewinds if isinstance(state.react_rewinds, Mapping) else {}
    download_fetch_rewinds = int((react_rewinds or {}).get("download_fetch") or 0)
    build_prepare_rewinds = int((react_rewinds or {}).get("build_prepare") or 0)
    retry_counts = state.retry_counts if isinstance(state.retry_counts, Mapping) else {}
    download_plan_retries = int((retry_counts or {}).get("download_plan") or 0)
    repaired_once = max(
        download_fetch_rewinds,
        build_prepare_rewinds,
        download_plan_retries,
    ) >= max(
        0,
        MAX_REACT_REWINDS - 1,
    )
    if not repaired_once:
        return {}
    return {
        str(entity_id): {
            str(lane): [str(issue) for issue in issues if str(issue).strip()]
            for lane, issues in lanes.items()
            if issues
        }
        for entity_id, lanes in unresolved.items()
        if lanes
    }

def _flatten_download_plan_issues(lanes: Mapping[str, list[str]]) -> list[str]:
    rows: list[str] = []
    for lane, issues in lanes.items():
        for issue in issues:
            text = str(issue or "").strip()
            if text:
                rows.append(f"{lane}: {text}")
    return rows

def _issue_mentions_entity_id(entity_id: str, issue: Any) -> bool:
    """Whether an issue row names an entity as a full object/ref/path segment.
    Do not use raw substring matching here: names such as `白云山景区` and
    `白云区白云山景区` can coexist in the same batch, and fast-fail replacement
    must never abandon the shorter entity because a longer entity failed.
    """
    entity = str(entity_id or "").strip()
    if isinstance(issue, DataIssue):
        return issue.ref == entity
    row = str(issue or "").strip()
    if not entity or not row:
        return False
    if row == entity or row.startswith(f"{entity}:") or row.startswith(f"{entity}_"):
        return True
    if f"/{entity}/" in row or f"/{entity}:" in row:
        return True
    if f"/entity/地点/景区/{entity}" in row:
        return True
    return bool(
        re.search(rf"""["']entityId["']\s*:\s*["']{re.escape(entity)}["']""", row)
    )

def _build_prepare_homepage_unresolved_entities(ctx: ExecutionContext) -> dict[str, dict[str, list[str]]]:
    """Map build_prepare homepage base-draft failures back to homepage source repair.
    `build_prepare` is the first deterministic stage that can inspect fetched
    homepage source units and decide whether the chosen primary authority
    base draft has enough usable facts. When it fails, the next download_plan
    pass must repair the homepage lane for only those entities; otherwise the
    execution can claim the source plan is ready and loop back into the same
    downstream gate.
    """
    from content.execution.recovery.download_gate import _execution_repair_report_issues
    state = load_execution_state(ctx.execution_id)
    records: list[DataIssue] = []
    for raw in state.failed_issue_records or []:
        if not isinstance(raw, Mapping):
            continue
        try:
            records.append(DataIssue.from_dict(raw))
        except (TypeError, ValueError):
            continue
    records.extend(_execution_repair_report_issues(ctx, "build_prepare"))
    relevant_codes = {
        DataIssueCode.CONTRACT_INVALID,
        DataIssueCode.SOURCE_MISSING,
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
        DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
        DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
    }
    records = [
        issue
        for issue in records
        if issue.stage is DataIssueStage.BUILD_PREPARE
        and issue.lane in {DataIssueLane.HOMEPAGE, DataIssueLane.ALL}
        and issue.code in relevant_codes
        and issue.ref
    ]
    if not records:
        return {}
    unresolved: dict[str, dict[str, list[str]]] = {}
    for entity_id in ctx.entity_ids:
        hits = [issue for issue in records if issue.ref == entity_id]
        if not hits:
            continue
        lane_issues = unresolved.setdefault(entity_id, {}).setdefault("homepage", [])
        for hit in hits:
            text = f"build_prepare homepage base draft repair required: {str(hit)}"
            if text not in lane_issues:
                lane_issues.append(text)
    return unresolved

def _homepage_source_failure_entities(ctx: ExecutionContext) -> dict[str, dict[str, list[str]]]:
    """Return typed Agent source failures that must rewind before another author attempt."""
    from core.homepage_source_failure import (
        SOURCE_RECOVERY_FAILURE_KINDS,
        entity_page_failure_issues,
        entity_page_failure_kind,
        read_entity_page_failure,
    )

    failures: dict[str, dict[str, list[str]]] = {}
    for target in ((_active_spec(ctx).get("scope") or {}).get("coverageTargets") or []):
        if not isinstance(target, Mapping):
            continue
        entity_id = str(target.get("name") or "").strip()
        if not entity_id:
            continue
        domain, entity_type = require_domain_etype(
            target.get("entityType"),
            context=f"coverageTargets[{entity_id}]",
        )
        draft_dir = (
            execution_root(ctx.execution_id)
            / "entities"
            / domain
            / entity_type
            / entity_id
            / "4.draft"
        )
        failure = read_entity_page_failure(draft_dir)
        if failure is None:
            continue
        problems = entity_page_failure_issues(failure, entity_name=entity_id)
        kind = entity_page_failure_kind(failure)
        if problems or kind not in SOURCE_RECOVERY_FAILURE_KINDS:
            continue
        reasons = [str(item).strip() for item in (failure.get("reasons") or []) if str(item).strip()]
        failures[entity_id] = {
            "homepage": [
                f"entity_page_failure:{kind.value}: {reason}"
                for reason in (reasons[:4] or ["Agent rejected the current homepage base source"])
            ]
        }
    return failures

def _download_artifact_issues(ctx: ExecutionContext) -> dict[str, tuple[DataIssue, ...]]:
    """Return the full frozen-target verdict from persisted download artifacts."""
    from content.source.gate import gate_download

    active = tuple(frozen_target_names(ctx))
    active_set = set(active)
    grouped: dict[str, list[DataIssue]] = {entity_id: [] for entity_id in active}
    for issue in gate_download(ctx.execution_id, target_entities=active_set):
        targets = (issue.ref,) if issue.ref in active_set else active
        for entity_id in targets:
            if issue not in grouped[entity_id]:
                grouped[entity_id].append(issue)
    return {
        entity_id: tuple(issues)
        for entity_id, issues in grouped.items()
        if issues
    }


def _write_download_availability(
    ctx: ExecutionContext,
    unresolved: Mapping[str, Mapping[str, list[str]]],
    *,
    source: str = "artifact_gate",
) -> dict[str, Any]:
    active = list(frozen_target_names(ctx))
    merged_unresolved: dict[str, dict[str, list[str]]] = {
        str(entity_id): {
            str(lane): [str(issue) for issue in issues if str(issue).strip()]
            for lane, issues in (lanes or {}).items()
        }
        for entity_id, lanes in unresolved.items()
        if str(entity_id).strip()
    }
    for entity_id, lanes in _pending_download_repair_unresolved(ctx).items():
        entity_lanes = merged_unresolved.setdefault(entity_id, {})
        for lane, issues in lanes.items():
            entity_lanes.setdefault(lane, [])
            for issue in issues:
                text = str(issue or "").strip()
                if text and text not in entity_lanes[lane]:
                    entity_lanes[lane].append(text)
    artifact_issues = _download_artifact_issues(ctx)
    ineligible: list[dict[str, Any]] = []
    deterministic: dict[str, dict[str, list[str]]] = {}
    exhausted = _download_plan_repair_exhausted_unresolved(ctx, merged_unresolved)
    for entity_id, lanes in exhausted.items():
        entity_lanes = deterministic.setdefault(entity_id, {})
        for lane, issues in lanes.items():
            rows = entity_lanes.setdefault(lane, [])
            for issue in issues:
                if issue not in rows:
                    rows.append(issue)
    for entity_id in active:
        lanes = merged_unresolved.get(entity_id) or {}
        entity_artifact_issues = artifact_issues.get(entity_id) or ()
        if not lanes and not entity_artifact_issues:
            continue
        issues = _flatten_download_plan_issues(lanes)
        issues.extend(issue_messages(entity_artifact_issues))
        deterministic_lanes = deterministic.get(entity_id) or {}
        blocker_recovery = (
            DataRecoveryAction.STOP
            if deterministic_lanes
            else DataRecoveryAction.RETRY_SOURCE_DISCOVERY
        )
        blocker_code = DataIssueCode.SOURCE_PLAN_INVALID
        blockers = [
            data_issue(
                blocker_code,
                stage=DataIssueStage.DOWNLOAD_PLAN,
                ref=entity_id,
                lane=DataIssueLane(lane) if lane in {item.value for item in DataIssueLane} else DataIssueLane.ALL,
                recovery=blocker_recovery,
                message=str(issue),
            ).as_dict()
            for lane, lane_issues in lanes.items()
            for issue in lane_issues
            if str(issue).strip()
        ]
        for issue in entity_artifact_issues:
            payload = issue.as_dict()
            if payload not in blockers:
                blockers.append(payload)
        all_lanes = {
            str(lane)
            for lane in lanes
        }
        all_lanes.update(
            issue.lane.value
            for issue in entity_artifact_issues
            if issue.lane is not DataIssueLane.ALL
        )
        recoveries = {blocker_recovery.value}
        recoveries.update(issue.recovery.value for issue in entity_artifact_issues)
        ineligible.append(
            {
                "entityId": entity_id,
                "lanes": sorted(all_lanes),
                "issues": issues,
                "blockers": blockers,
                "recoveries": sorted(recoveries),
            }
        )
    ineligible_ids = {str(item.get("entityId") or "") for item in ineligible}
    ready = [entity for entity in active if entity not in ineligible_ids]
    report = {
        "schema": "quwoquan.content.source.source_availability",
        "executionId": ctx.execution_id,
        "source": source,
        "updatedAt": store.now_iso(),
        "readyTargets": ready,
        "readyTargetCount": len(ready),
        "ineligibleTargets": ineligible,
        "ineligibleTargetCount": len(ineligible),
    }
    if set(ready) & ineligible_ids or len(ready) + len(ineligible) != len(active):
        raise RuntimeError("download availability must partition the frozen target set")
    write_json(
        execution_root(ctx.execution_id) / "_shared" / "source_unavailable_targets.json",
        report,
    )
    return report

def _pending_download_repair_unresolved(ctx: ExecutionContext) -> dict[str, dict[str, list[str]]]:
    """Expose pending download repair as source-availability ineligible rows.
    A source plan can look lane-complete while the last fetch gate still proves
    its sources were rejected or underfilled. Availability must reflect that
    pending repair, otherwise target selection and scale audit will treat the
    object as ready and move failure pressure downstream.
    """
    from content.execution.recovery.download_gate import _download_repair_active_issues, _download_repair_entry_pending, _download_repair_path
    repair_path = _download_repair_path(ctx)
    if not repair_path.is_file():
        return {}
    try:
        repair = read_json(repair_path)
    except (OSError, ValueError, TypeError):
        return {}
    scoped_entities = set(frozen_target_names(ctx))
    unresolved: dict[str, dict[str, list[str]]] = {}
    for row in repair.get("entities") or []:
        if not isinstance(row, dict) or not _download_repair_entry_pending(row):
            continue
        entity_id = str(row.get("entityId") or "").strip()
        if not entity_id or entity_id not in scoped_entities:
            continue
        lanes = _download_repair_lanes(row) or {"download"}
        active_issues = _download_repair_active_issues(ctx, row)
        if not active_issues:
            continue
        for lane in lanes:
            unresolved.setdefault(entity_id, {}).setdefault(str(lane), [])
            for issue in active_issues:
                text = f"download_repair required: {issue}"
                if text not in unresolved[entity_id][str(lane)]:
                    unresolved[entity_id][str(lane)].append(text)
    return unresolved

def _format_download_unresolved(
    unresolved: Mapping[str, Mapping[str, list[str]]],
    *,
    prefix: str,
) -> list[str]:
    rows: list[str] = []
    for entity_id, lanes in sorted(unresolved.items()):
        lane_summary = "; ".join(
            f"{lane}: {', '.join(str(item) for item in issues[:3])}"
            for lane, issues in lanes.items()
        )
        rows.append(f"{entity_id}: {prefix}: {lane_summary}")
    return rows

def _auto_research_plan_path(ctx: ExecutionContext) -> Path:
    return execution_root(ctx.execution_id) / "_shared" / "auto_research_plan.json"

def _auto_research_wave_summary(
    report: Mapping[str, Any],
    *,
    scope: str,
    entity_ids: list[str],
) -> dict[str, Any]:
    throughput = report.get("throughput") if isinstance(report.get("throughput"), Mapping) else {}
    availability = (
        report.get("sourceAvailability")
        if isinstance(report.get("sourceAvailability"), Mapping)
        else {}
    )
    return {
        "scope": scope,
        "entityIds": list(entity_ids),
        "entityCount": len(entity_ids),
        "issueCount": len(report.get("issues") or []),
        "sourceUnavailableCount": len(report.get("sourceUnavailable") or []),
        "updatedCount": len(report.get("updated") or []),
        "readyTargetCount": int((availability or {}).get("readyTargetCount") or 0),
        "ineligibleTargetCount": int((availability or {}).get("ineligibleTargetCount") or 0),
        "elapsedSeconds": float((throughput or {}).get("elapsedSeconds") or 0),
        "entitiesPerMinute": float((throughput or {}).get("entitiesPerMinute") or 0),
        "maxWorkers": int((throughput or {}).get("maxWorkers") or 0),
        "recordedAt": store.now_iso(),
    }
