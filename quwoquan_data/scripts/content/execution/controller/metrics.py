"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.support import Any, ExecutionContext, ExecutionStateTransition, Mapping, Path, datetime, execution_root, load_execution_state, re, read_json, store

def _parse_iso_seconds(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None

def _batch_file_elapsed_seconds(root: Path) -> float | None:
    mtimes: list[float] = []
    if not root.is_dir():
        return None
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    if len(mtimes) < 2:
        return None
    elapsed = max(mtimes) - min(mtimes)
    return elapsed if elapsed > 0 else None

def _reliabletask_accepted_throughput(root: Path) -> dict[str, Any] | None:
    report_path = root / "evidence/reliabletask/publish_fleet_report.json"
    if not report_path.is_file():
        return None
    from core.schema import assert_valid

    report = read_json(report_path)
    assert_valid(
        report,
        "release",
        "reliabletask_fleet_report",
        label="reliabletask_fleet_report",
    )
    accepted = int(report.get("commercialAcceptedCount") or 0)
    required_quota = int(report.get("requiredQuota") or 0)
    if (
        report.get("passed") is not True
        or report.get("acceptedContentThroughputStatus") != "MEASURED"
        or accepted < required_quota
    ):
        raise ValueError(
            "ReliableTask publish fleet report 未达准出配额："
            f"已达标 {accepted} / 配额 {required_quota}"
            f"（status={report.get('acceptedContentThroughputStatus')}）"
        )
    return {
        "measurementMode": "reliabletask_commercial_accepted_end_to_end",
        "backend": str(report.get("backend") or ""),
        "publishedObjectCount": accepted,
        "requiredQuota": required_quota,
        "finalizedObjectCount": int(report.get("finalizedObjectCount") or 0),
        "elapsedSeconds": round(
            float(report.get("endToEndWallClockMilliseconds") or 0) / 1000,
            3,
        ),
        "fleetWallClockSeconds": round(
            float(report.get("fleetWallClockMilliseconds") or 0) / 1000,
            3,
        ),
        "objectsPerHour": float(
            report.get("endToEndAcceptedThroughputPerHour") or 0.0
        ),
        "fleetAcceptedObjectsPerHour": float(
            report.get("fleetAcceptedThroughputPerHour") or 0.0
        ),
        "controlPlaneTasksPerHour": float(
            report.get("fleetControlPlaneThroughputPerHour") or 0.0
        ),
        "executionCreatedAt": str(report.get("executionCreatedAt") or ""),
        "canonicalFinalizedAt": str(report.get("canonicalFinalizedAt") or ""),
        "finalizedWithinStageBudgetRate": float(
            report.get("finalizedWithinStageBudgetRate") or 0.0
        ),
        "automaticRecoveryRate": float(
            report.get("automaticRecoveryRate") or 0.0
        ),
        "reportRef": report_path.relative_to(root).as_posix(),
    }

def _review_repaired_refs(ctx: ExecutionContext) -> set[str]:
    from content.post import object_index as content_object
    repaired: set[str] = set()
    state = load_execution_state(ctx.execution_id)
    for row in state.produce_review_retry_history or []:
        if not isinstance(row, Mapping):
            continue
        for ref in row.get("refs") or []:
            text = str(ref or "").strip()
            if text:
                repaired.add(text)
    root = execution_root(ctx.execution_id)
    ref_by_dir = {
        str(content_object.content_object_dir(ctx.execution_id, ref)): ref
        for ref in content_object.iter_content_refs(ctx.execution_id)
    }
    for path in root.rglob("5.review/repair_report.json"):
        ref = ref_by_dir.get(str(path.parent.parent))
        if ref:
            repaired.add(ref)
    return repaired

def _agent_active_throughput(state: ExecutionStateTransition) -> dict[str, Any]:
    from content.execution.agent.history import state_managed_agent_runs
    from core.control_types import ExecutionStage

    agent_runs = state_managed_agent_runs(state)
    source_stage = ExecutionStage.POST_AUTHOR
    author_runs = [row for row in agent_runs if row.stage is source_stage]
    if not author_runs:
        source_stage = ExecutionStage.BUILD_HOMEPAGE
        author_runs = [row for row in agent_runs if row.stage is source_stage]
    elapsed = 0.0
    finished = 0
    infra_failures = 0
    planned = 0
    max_worker_count = 0
    for row in author_runs:
        scheduler = row.scheduler
        elapsed += scheduler.elapsed_seconds
        worker_count = scheduler.effective_worker_count
        max_worker_count = max(max_worker_count, worker_count)
        finished += row.finished_count
        infra_failures += row.infrastructure_failures
        planned += row.planned_job_count
    aggregate_per_hour = round((finished / elapsed) * 3600, 4) if elapsed > 0 else 0.0
    # Per-worker unit rate is the aggregate author throughput divided by the
    # concurrency actually realized during the trial.  It is the only rate that
    # can be linearly projected onto a committed reliabletask worker fleet.
    realized_workers = max(1, max_worker_count)
    per_worker_per_hour = round(aggregate_per_hour / realized_workers, 4) if aggregate_per_hour else 0.0
    return {
        "measurementMode": "agent_run_history",
        "sourceStage": source_stage.value,
        "jobKind": "homepage" if source_stage is ExecutionStage.BUILD_HOMEPAGE else "author",
        "authorRunCount": len(author_runs),
        "authorActiveSeconds": round(elapsed, 3),
        "plannedAuthorJobs": planned,
        "finishedAuthorJobs": finished,
        "infrastructureFailures": infra_failures,
        "finishedAuthorJobsPerHour": aggregate_per_hour,
        "effectiveWorkerCount": realized_workers,
        "perWorkerObjectsPerHour": per_worker_per_hour,
    }

def _homepage_passed_count_from_artifacts(root: Path) -> int:
    count = 0
    entities_root = root / "entities"
    if not entities_root.is_dir():
        return 0
    for report_path in sorted(entities_root.rglob("5.review/finalization_report.json")):
        report = read_json(report_path)
        if not isinstance(report, Mapping):
            continue
        status = str(report.get("status") or report.get("decision") or "").lower()
        if status in {"passed", "approved", "done", "accepted", "success", "succeeded"} or bool(
            report.get("passed")
        ):
            count += 1
            continue
        entity_dir = report_path.parent.parent
        if (
            (entity_dir / "_entity.json").is_file()
            and (entity_dir / "page.md").is_file()
            and (entity_dir / "manifest.json").is_file()
            and (entity_dir / "5.review" / "review.json").is_file()
            and (entity_dir / "5.review" / "provenance.json").is_file()
            and str(report.get("draftArticleRef") or "") == "4.draft/page.md"
            and str(report.get("finalArticleRef") or "") == "page.md"
            and str(report.get("draftSha256") or "").strip()
            and str(report.get("finalSha256") or "").strip()
        ):
            count += 1
    return count

def _homepage_result_entity_name(result: Any) -> str:
    text = str(result or "").lstrip()
    if not text:
        return ""
    match = re.match(r"^\*\*(.+?)\*\*\s+checkpoint", text)
    return str(match.group(1) or "").strip() if match else ""

def _homepage_agent_review_stats(
    execution_id: str,
    state: ExecutionStateTransition,
    *,
    passed_count: int = 0,
) -> dict[str, Any]:
    root = execution_root(execution_id)
    run_id_to_entity: dict[str, str] = {}
    entities_root = root / "entities"
    if entities_root.is_dir():
        for meta_path in sorted(entities_root.rglob("4.draft/draft_meta.json")):
            meta = read_json(meta_path)
            if not isinstance(meta, Mapping):
                continue
            run_id = str(meta.get("agentRunId") or "").strip()
            if run_id:
                run_id_to_entity[run_id] = meta_path.parent.parent.name
    from content.execution.agent.history import state_managed_agent_runs
    from core.control_types import ExecutionStage

    attempts_by_entity: dict[str, list[str]] = {}
    for row in state_managed_agent_runs(state):
        if row.stage is not ExecutionStage.BUILD_HOMEPAGE:
            continue
        for job_outcome in row.outcomes:
            if not job_outcome.succeeded:
                continue
            outcome = job_outcome.outcome
            run_id = outcome.run_id
            entity = run_id_to_entity.get(run_id) or _homepage_result_entity_name(outcome.result_text)
            if not entity:
                continue
            marker = run_id or f"{row.finished_at}:{job_outcome.job_index}"
            markers = attempts_by_entity.setdefault(entity, [])
            if marker not in markers:
                markers.append(marker)
    reviewed = len(attempts_by_entity)
    repaired = sum(1 for markers in attempts_by_entity.values() if len(markers) > 1)
    source = "build_homepage_agent_run_history"
    if not attempts_by_entity and passed_count > 0:
        reviewed = passed_count
        source = "homepage_finalization_count_fallback"
    elif passed_count > reviewed:
        reviewed = passed_count
        source = "build_homepage_agent_run_history_plus_finalization_count"
    return {
        "reviewedRefs": reviewed,
        "repairedRefs": repaired,
        "measurementMode": source,
    }

def _write_execution_metrics(ctx: ExecutionContext, state: ExecutionStateTransition) -> None:
    """Persist production-readiness metrics derived from batch artifacts and real usage."""
    from content.post import object_index as content_object
    from content.release.canonical.runtime_integrity import scan_runtime_batch_integrity
    from content.execution.agent.history import state_managed_agent_runs

    state.agent_run_history = [
        run.to_document() for run in state_managed_agent_runs(state)[-20:]
    ]
    root = execution_root(ctx.execution_id)
    refs = content_object.iter_content_refs(ctx.execution_id)
    runtime_report = scan_runtime_batch_integrity(ctx.execution_id)
    stats = runtime_report.get("stats") if isinstance(runtime_report, Mapping) else {}
    post_count = int((stats or {}).get("postCount") or 0)
    homepage_passed = _homepage_passed_count_from_artifacts(root)
    published_object_count = post_count + homepage_passed
    start = _parse_iso_seconds(state.started_at)
    end = _parse_iso_seconds(store.now_iso())
    elapsed_seconds = max(1.0, (end - start) if start and end else 1.0)
    file_elapsed = _batch_file_elapsed_seconds(root)
    if file_elapsed and file_elapsed > elapsed_seconds:
        elapsed_seconds = file_elapsed
    objects_per_hour = round((published_object_count / elapsed_seconds) * 3600, 4) if published_object_count else 0.0
    state.throughput = {
        "measurementMode": "wall_clock_current_batch",
        "elapsedSeconds": round(elapsed_seconds, 3),
        "postCount": post_count,
        "homepageCount": homepage_passed,
        "publishedObjectCount": published_object_count,
        "objectsPerHour": objects_per_hour,
        "maxWorkers": int(ctx.max_workers or 1),
        "agentActive": _agent_active_throughput(state),
    }
    reliabletask_throughput = _reliabletask_accepted_throughput(root)
    if reliabletask_throughput is not None:
        state.throughput = {
            **state.throughput,
            **reliabletask_throughput,
        }
    repaired = _review_repaired_refs(ctx)
    homepage_review = _homepage_agent_review_stats(
        ctx.execution_id,
        state,
        passed_count=homepage_passed,
    )
    total_reviewed = len(refs) + int(homepage_review.get("reviewedRefs") or 0)
    total_repaired = len(repaired) + int(homepage_review.get("repairedRefs") or 0)
    first_pass = (
        round((total_reviewed - total_repaired) / total_reviewed, 4)
        if total_reviewed
        else 0.0
    )
    state.quality = {
        "firstPassRate": first_pass,
        "reviewedRefs": total_reviewed,
        "repairedRefs": total_repaired,
        "homepageReviewedRefs": int(homepage_review.get("reviewedRefs") or 0),
        "homepageRepairedRefs": int(homepage_review.get("repairedRefs") or 0),
        "measurementMode": (
            "repair_report_derived_plus_homepage_history"
            if homepage_review.get("reviewedRefs")
            else "repair_report_derived"
        ),
        "homepageMeasurementMode": str(homepage_review.get("measurementMode") or ""),
    }
