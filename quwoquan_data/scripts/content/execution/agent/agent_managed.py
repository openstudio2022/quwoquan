"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.runtime_policy import active_runtime_policy
from content.execution.support import Any, ExecutionContext, MANAGED_AGENT_FUTURE_GRACE_SECONDS, MANAGED_AGENT_TIMEOUT_SECONDS, MANAGED_CODEX_CLI_MAX_WORKERS, MANAGED_LANE_LIMITS, MAX_MANAGED_INFRA_RETRIES, MAX_REACT_REWINDS, Mapping, Path, ThreadPoolExecutor, _is_homepage_only_workflow, _normalize_managed_agent_provider, defaultdict, execution_root, load_workflow_state, os, release_root, save_workflow_state, store, time, wait

_AGENT_FUTURE_POLL_TIMEOUT_SECONDS = active_runtime_policy().agent_future_poll_timeout_seconds

def _run_managed_checkpoint(ctx: ExecutionContext, stage: str) -> bool:
    from content.execution.agent.agent_checkpoint import _checkpoint_is_done, _checkpoint_prompts, _finalize_managed_author_outputs, _managed_author_ref, _managed_checkpoint_job_issues, _managed_prompt_lane
    from content.execution.agent.agent_runner import _terminate_workspace_cursor_bridges
    from content.execution.agent.agent_worker import _default_managed_agent_runner_isolated, _terminate_managed_agent_subprocesses
    from content.execution.pipeline.homepage_authoring import _finalize_managed_homepage_outputs
    from content.execution.pipeline.metrics import _dedupe_agent_runs
    from content.execution.recovery.stage_reset import _managed_local_cursor_worker_cap
    prompts = _checkpoint_prompts(ctx, stage)
    if not prompts:
        return False
    worker_count = _managed_checkpoint_worker_count(ctx, len(prompts))
    checkpoint_started_at = store.now_iso()
    checkpoint_started_mono = time.monotonic()
    estimated_waves = (len(prompts) + max(worker_count, 1) - 1) // max(worker_count, 1)
    state = load_workflow_state(ctx.execution_id)
    state["status"] = "waiting_agent"
    state["waitingCheckpoint"] = stage
    state["owner"] = f"managed-local:{stage}"
    state["heartbeatAt"] = store.now_iso()
    state["nextAction"] = f"running {len(prompts)} agent job(s) for {stage}"
    state["failedObjects"] = []
    state["activeAgentScheduler"] = {
        "stage": stage,
        "requestedMaxWorkers": int(ctx.max_workers or 1),
        "effectiveWorkerCount": worker_count,
        "localCursorMaxWorkers": _managed_local_cursor_worker_cap(ctx),
        "runtime": str(ctx.runtime),
        "promptCount": len(prompts),
        "estimatedMinWaves": estimated_waves,
        "laneLimits": dict(MANAGED_LANE_LIMITS),
        "agentProvider": _normalize_managed_agent_provider(ctx.agent_provider),
        "startedAt": checkpoint_started_at,
    }
    previous_agent_run = state.get("lastAgentRun")
    if isinstance(previous_agent_run, Mapping):
        history = state.setdefault("agentRunHistory", [])
        if isinstance(history, list):
            history.append(dict(previous_agent_run))
            state["agentRunHistory"] = list(_dedupe_agent_runs(history))[-20:]
    state.pop("lastAgentRun", None)
    save_workflow_state(state)
    runner = ctx.agent_runner or (lambda prompt: _default_managed_agent_runner_isolated(ctx, prompt))
    queued = list(range(len(prompts)))
    futures: dict[Any, tuple[int, str, float]] = {}
    active_by_lane: dict[str, int] = defaultdict(int)
    job_timings: dict[int, dict[str, Any]] = {}
    outcomes: list[dict[str, Any]] = []
    pool = ThreadPoolExecutor(max_workers=worker_count)
    interrupted = False
    force_abort_pool = False
    try:
        while queued or futures:
            submitted = True
            while queued and len(futures) < worker_count and submitted:
                submitted = False
                for position, index in enumerate(queued):
                    lane = _managed_prompt_lane(prompts[index])
                    cap = MANAGED_LANE_LIMITS.get(lane, worker_count)
                    if active_by_lane[lane] >= cap:
                        continue
                    future = pool.submit(runner, prompts[index])
                    futures[future] = (index, lane, time.monotonic())
                    job_timings[index] = {
                        "lane": lane,
                        "submittedAt": store.now_iso(),
                    }
                    active_by_lane[lane] += 1
                    queued.pop(position)
                    submitted = True
                    break
                if submitted:
                    continue
                # Borrow a lane's idle quota only after that lane has no queued
                # work and fewer active jobs than its reservation.
                queued_lanes = {_managed_prompt_lane(prompts[index]) for index in queued}
                idle_slots = sum(
                    max(0, cap - active_by_lane.get(lane, 0))
                    for lane, cap in MANAGED_LANE_LIMITS.items()
                    if lane not in queued_lanes
                )
                if idle_slots and queued:
                    index = queued.pop(0)
                    lane = _managed_prompt_lane(prompts[index])
                    future = pool.submit(runner, prompts[index])
                    futures[future] = (index, lane, time.monotonic())
                    job_timings[index] = {
                        "lane": lane,
                        "submittedAt": store.now_iso(),
                        "borrowedIdleLaneQuota": True,
                    }
                    active_by_lane[lane] += 1
                    submitted = True
            if not futures:
                break
            done, _pending = wait(set(futures), timeout=_AGENT_FUTURE_POLL_TIMEOUT_SECONDS)
            for future in done:
                index, lane, _started_at = futures.pop(future)
                active_by_lane[lane] = max(0, active_by_lane[lane] - 1)
                timing = dict(job_timings.get(index) or {})
                timing["finishedAt"] = store.now_iso()
                timing["durationSeconds"] = round(max(0.0, time.monotonic() - _started_at), 3)
                try:
                    outcome = future.result()
                except Exception as exc:  # noqa: BLE001
                    outcome = {
                        "started": False,
                        "status": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                        "retryable": False,
                    }
                outcome["jobIndex"] = index
                outcome["timing"] = timing
                if stage == "post_author":
                    outcome["ref"] = _managed_author_ref(prompts[index])
                if str(outcome.get("status")) == "finished":
                    gate_issues = _managed_checkpoint_job_issues(
                        ctx,
                        stage=stage,
                        prompt=prompts[index],
                    )
                    if gate_issues:
                        outcome["status"] = "error"
                        outcome["error"] = (
                            "agent finished but checkpoint lane gate still fails: "
                            + "; ".join(str(item) for item in gate_issues[:8])
                        )
                        outcome["retryable"] = True
                        outcome["gateIssues"] = [str(item) for item in gate_issues[:20]]
                outcomes.append(outcome)
            now = time.monotonic()
            expired = [
                (future, index, lane, started_at)
                for future, (index, lane, started_at) in list(futures.items())
                if now - started_at > MANAGED_AGENT_TIMEOUT_SECONDS + MANAGED_AGENT_FUTURE_GRACE_SECONDS
            ]
            for future, index, lane, started_at in expired:
                futures.pop(future, None)
                active_by_lane[lane] = max(0, active_by_lane[lane] - 1)
                future.cancel()
                force_abort_pool = True
                timing = dict(job_timings.get(index) or {})
                timing["finishedAt"] = store.now_iso()
                timing["durationSeconds"] = round(max(0.0, now - started_at), 3)
                outcomes.append(
                    {
                        "started": False,
                        "status": "error",
                        "error": (
                            f"managed agent future timed out after "
                            f"{int(now - started_at)}s for {stage}/{lane}"
                        ),
                        "retryable": True,
                        "errorType": "future_timeout",
                        "jobIndex": index,
                        "timing": timing,
                        **({"ref": _managed_author_ref(prompts[index])} if stage == "post_author" else {}),
                    }
                )
                if str(ctx.runtime) == "local":
                    _terminate_workspace_cursor_bridges(Path.cwd())
            state = load_workflow_state(ctx.execution_id)
            state["heartbeatAt"] = store.now_iso()
            state["nextAction"] = (
                f"{stage}: {len(outcomes)}/{len(prompts)} agent job(s) finished; "
                f"active={dict(active_by_lane)}"
            )
            save_workflow_state(state)
    except KeyboardInterrupt as exc:
        interrupted = True
        interrupt_reason = str(exc) or "KeyboardInterrupt"
        cancelled_queued_count = len(queued)
        cancelled_active_count = len(futures)
        queued.clear()
        for future in futures:
            future.cancel()
        terminated_subprocesses = _terminate_managed_agent_subprocesses()
        if str(ctx.runtime) == "local":
            _terminate_workspace_cursor_bridges(Path.cwd())
        outcomes.sort(key=lambda item: int(item.get("jobIndex", 0)))
        if stage == "post_author":
            _finalize_managed_author_outputs(ctx, prompts, outcomes)
        elif stage == "build_homepage":
            _finalize_managed_homepage_outputs(ctx, prompts, outcomes)
        finished_count = sum(str(out.get("status")) == "finished" for out in outcomes)
        started_count = sum(bool(out.get("started")) for out in outcomes)
        infrastructure_failures = sum(not bool(out.get("started")) for out in outcomes)
        state = load_workflow_state(ctx.execution_id)
        state.pop("activeAgentScheduler", None)
        resumable_author_interrupt = stage == "post_author"
        state["status"] = "repairing" if resumable_author_interrupt else "manual_required"
        retry_hint = (
            f"{stage}: interrupted; resume will retry remaining agent job(s); "
            f"finished={finished_count}, cancelledQueued={cancelled_queued_count}, "
            f"cancelledActive={cancelled_active_count}; {interrupt_reason}"
        )
        state["failedObjects"] = [retry_hint]
        state["nextAction"] = retry_hint if resumable_author_interrupt else f"{stage}: interrupted ({interrupt_reason})"
        state["heartbeatAt"] = store.now_iso()
        interrupted_at = store.now_iso()
        yield_reason = "managed checkpoint interrupted"
        if finished_count > 0:
            yield_reason = "managed checkpoint interrupted after partial author progress"
        partial_record = {
            "stage": stage,
            "status": "interrupted",
            "interruptReason": interrupt_reason,
            "jobCount": len(outcomes),
            "plannedJobCount": len(prompts),
            "scheduler": {
                "requestedMaxWorkers": int(ctx.max_workers or 1),
                "effectiveWorkerCount": worker_count,
                "localCursorMaxWorkers": _managed_local_cursor_worker_cap(ctx),
                "runtime": str(ctx.runtime),
                "promptCount": len(prompts),
                "estimatedMinWaves": estimated_waves,
                "laneLimits": dict(MANAGED_LANE_LIMITS),
                "agentProvider": _normalize_managed_agent_provider(ctx.agent_provider),
                "startedAt": checkpoint_started_at,
                "interruptedAt": interrupted_at,
                "elapsedSeconds": round(max(0.0, time.monotonic() - checkpoint_started_mono), 3),
            },
            "refs": [
                str(out.get("ref"))
                for out in outcomes
                if str(out.get("ref") or "").strip()
            ],
            "startedCount": started_count,
            "finishedCount": finished_count,
            "infrastructureFailures": infrastructure_failures,
            "cancelledQueuedJobCount": cancelled_queued_count,
            "cancelledActiveJobCount": cancelled_active_count,
            "terminatedSubprocessPids": terminated_subprocesses,
            "outcomes": outcomes,
            "finishedAt": interrupted_at,
        }
        history = state.setdefault("agentRunHistory", [])
        if isinstance(history, list):
            history.append(partial_record)
            state["agentRunHistory"] = list(_dedupe_agent_runs(history))[-20:]
        state["lastAgentRun"] = partial_record
        if resumable_author_interrupt:
            state["managedCheckpointInterruption"] = {
                "stage": stage,
                "reason": interrupt_reason,
                "resumable": True,
                "finishedCount": finished_count,
                "plannedJobCount": len(prompts),
                "cancelledQueuedJobCount": cancelled_queued_count,
                "cancelledActiveJobCount": cancelled_active_count,
                "interruptedAt": interrupted_at,
            }
            state["controllerYield"] = {
                "stage": stage,
                "reason": yield_reason,
                "hint": retry_hint,
                "yieldedAt": state["heartbeatAt"],
            }
        else:
            state.pop("managedCheckpointInterruption", None)
        save_workflow_state(state)
        raise
    finally:
        pool.shutdown(wait=not (interrupted or force_abort_pool), cancel_futures=True)
    outcomes.sort(key=lambda item: int(item.get("jobIndex", 0)))
    if stage == "post_author":
        _finalize_managed_author_outputs(ctx, prompts, outcomes)
    elif stage == "build_homepage":
        _finalize_managed_homepage_outputs(ctx, prompts, outcomes)
    started_count = sum(bool(out.get("started")) for out in outcomes)
    finished_count = sum(str(out.get("status")) == "finished" for out in outcomes)
    infrastructure_failures = sum(not bool(out.get("started")) for out in outcomes)
    finished_at = store.now_iso()
    state = load_workflow_state(ctx.execution_id)
    state.pop("activeAgentScheduler", None)
    agent_run_record = {
        "stage": stage,
        "jobCount": len(outcomes),
        "plannedJobCount": len(prompts),
        "scheduler": {
            "requestedMaxWorkers": int(ctx.max_workers or 1),
            "effectiveWorkerCount": worker_count,
            "localCursorMaxWorkers": _managed_local_cursor_worker_cap(ctx),
            "runtime": str(ctx.runtime),
            "promptCount": len(prompts),
            "estimatedMinWaves": estimated_waves,
            "laneLimits": dict(MANAGED_LANE_LIMITS),
            "agentProvider": _normalize_managed_agent_provider(ctx.agent_provider),
            "startedAt": checkpoint_started_at,
            "finishedAt": finished_at,
            "elapsedSeconds": round(max(0.0, time.monotonic() - checkpoint_started_mono), 3),
        },
        "refs": [
            str(out.get("ref"))
            for out in outcomes
            if str(out.get("ref") or "").strip()
        ],
        "startedCount": started_count,
        "finishedCount": finished_count,
        "infrastructureFailures": infrastructure_failures,
        "outcomes": outcomes,
        "finishedAt": finished_at,
    }
    history = state.setdefault("agentRunHistory", [])
    if isinstance(history, list):
        history.append(agent_run_record)
        state["agentRunHistory"] = list(_dedupe_agent_runs(history))[-20:]
    state["lastAgentRun"] = agent_run_record
    save_workflow_state(state)
    failures = [out for out in outcomes if str(out.get("status")) != "finished"]
    if failures:
        state = load_workflow_state(ctx.execution_id)
        state["status"] = "repairing"
        state["failedObjects"] = [str(out.get("error") or "agent failed") for out in failures]
        save_workflow_state(state)
        return False
    ok, issues = _checkpoint_is_done(ctx, stage)
    state = load_workflow_state(ctx.execution_id)
    state["owner"] = "managed-local"
    state["heartbeatAt"] = store.now_iso()
    state.pop("managedCheckpointInterruption", None)
    ref_limit = _managed_checkpoint_ref_limit()
    limited_slice_progress = (
        stage == "post_author"
        and not ok
        and ref_limit > 0
        and len(prompts) >= ref_limit
        and finished_count == len(prompts)
        and not failures
    )
    if limited_slice_progress:
        state["failedObjects"] = []
        state["status"] = "running"
        state["nextAction"] = (
            f"continue {stage}: managed ref slice completed "
            f"({len(prompts)} refs); remaining checkpoint issues={len(issues)}"
        )
        if _managed_yield_after_ref_slice():
            state["status"] = "repairing"
            state["controllerYield"] = {
                "stage": stage,
                "reason": "managed ref slice completed",
                "hint": state["nextAction"],
                "yieldedAt": state["heartbeatAt"],
            }
    else:
        state["failedObjects"] = list(issues)
        state["status"] = "running" if ok else "repairing"
        state["nextAction"] = None if ok else f"repair {stage}: {issues[:5]}"
        state.pop("controllerYield", None)
    save_workflow_state(state)
    return ok or limited_slice_progress

def _managed_checkpoint_worker_count(ctx: ExecutionContext, prompt_count: int) -> int:
    from content.execution.recovery.stage_reset import _managed_local_cursor_worker_cap
    worker_count = max(1, min(ctx.max_workers, prompt_count))
    provider = _normalize_managed_agent_provider(ctx.agent_provider)
    if ctx.agent_runner is None and str(ctx.runtime) == "local" and provider == "cursor_sdk":
        worker_count = min(worker_count, _managed_local_cursor_worker_cap(ctx))
    if ctx.agent_runner is None and str(ctx.runtime) == "local" and provider == "codex_cli":
        worker_count = min(worker_count, MANAGED_CODEX_CLI_MAX_WORKERS)
    return worker_count

def _managed_checkpoint_ref_limit() -> int:
    from core.runtime_policy import active_runtime_policy

    return active_runtime_policy().managed_checkpoint_ref_limit

def _managed_yield_after_ref_slice() -> bool:
    return str(os.environ.get("QWQ_MANAGED_YIELD_AFTER_REF_SLICE") or "").strip() in {
        "1",
        "true",
        "yes",
    }

def _reconcile_completed_publish_state(ctx: ExecutionContext) -> bool:
    """Close canonical publish evidence when an object Agent finished first."""
    from content.execution.pipeline.publish import _publishable_homepage_refs, _workflow_release_id
    state = load_workflow_state(ctx.execution_id)
    if "publish" not in set(state.get("completed") or []):
        return True
    if _is_homepage_only_workflow(ctx):
        from content.execution.qualification import finalize_execution_qualification

        try:
            qualification = finalize_execution_qualification(ctx.execution_id)
        except (OSError, TypeError, ValueError) as exc:
            qualification_issues = [str(exc)]
        else:
            qualification_issues = [str(issue) for issue in qualification.issues]
        if qualification_issues:
            state["completed"] = [
                stage for stage in (state.get("completed") or []) if stage != "publish"
            ]
            state["status"] = "running"
            state["failedObjects"] = qualification_issues
            state["nextAction"] = "repair execution source qualification before publish"
            save_workflow_state(state)
            return False
        from core.paths import PUBLISH_ROOT
        from content.execution.workspace import execution_root, write_publish_ref
        from content.release.canonical.object_transaction import validate_canonical_publish

        closure = validate_canonical_publish(PUBLISH_ROOT)
        if closure["status"] != "passed":
            state["completed"] = [stage for stage in (state.get("completed") or []) if stage != "publish"]
            state["status"] = "running"
            state["failedObjects"] = [str(issue) for issue in closure["issues"]]
            state["nextAction"] = "repair canonical publish closure before publish"
            save_workflow_state(state)
            return False
        homepage_refs = _publishable_homepage_refs(ctx)
        write_publish_ref(
            ctx.execution_id,
            entity_refs=[ref.removeprefix("/entity/") for ref in homepage_refs],
        )
        for key in ("releaseId", "releaseEvidencePath", "shipReportPath"):
            state.pop(key, None)
        save_workflow_state(state)
        return True
    release_id = _workflow_release_id(ctx.execution_id)
    release_dir = release_root(release_id)
    from content.release.canonical.gate import gate_publish

    issues = gate_publish(release_id) if release_dir.is_dir() else ["release directory missing"]
    if issues:
        state["completed"] = [
            stage for stage in (state.get("completed") or []) if stage != "publish"
        ]
        state["status"] = "running"
        state["failedObjects"] = list(issues)
        state["nextAction"] = "rebuild invalid or missing immutable release"
        save_workflow_state(state)
        return False
    entities = sum(1 for path in (release_dir / "objects/entities").rglob("manifest.json"))
    posts = sum(1 for path in (release_dir / "objects/posts").rglob("manifest.json"))
    ship_report = execution_root(ctx.execution_id) / "_shared" / "ship_report.json"
    if not ship_report.is_file():
        from content.release.environment.handler import write_release_only_ship_report

        write_release_only_ship_report(
            output_path=ship_report,
            release_id=release_id,
            summary={"entityCount": entities, "postCount": posts},
        )
    for key in ("releaseId", "releaseEvidencePath", "shipReportPath"):
        state.pop(key, None)
    save_workflow_state(state)
    return True

def _managed_checkpoint_repair_budget_exhausted(used_attempts: int) -> bool:
    """Return whether a checkpoint spent its initial pass and all ReAct repairs."""
    return used_attempts > MAX_REACT_REWINDS

def run_managed_pipeline(ctx: ExecutionContext) -> int:
    """父进程消费全部 Agent checkpoint，直到 release verify 通过或转人工。"""
    from content.execution.agent.agent_checkpoint import _checkpoint_is_done, _handle_managed_infra_budget_exhausted, _managed_author_failure_refs, _managed_consecutive_no_start_infra_failures
    from content.execution.recovery.download_unresolved import _download_plan_unresolved_entities, _write_download_plan_availability
    from content.execution.pipeline.pipeline_control import _recover_stale_controller_yield
    from content.execution.pipeline.pipeline_run import run_pipeline
    while True:
        code = run_pipeline(ctx)
        if code == 0:
            if _reconcile_completed_publish_state(ctx):
                return 0
            continue
        if code != 10:
            return code
        state = load_workflow_state(ctx.execution_id)
        stage = str(state.get("waitingCheckpoint") or "")
        if isinstance(state.get("controllerYield"), Mapping):
            if _recover_stale_controller_yield(ctx, state):
                continue
            print(f"[geo-homepages] controller yield at checkpoint '{stage}'; resume later")
            return 10
        retries = state.setdefault("retryCounts", {})
        used = int(retries.get(stage, 0))
        retry_blocked_author_progress = (
            stage == "post_author"
            and used >= MAX_REACT_REWINDS
            and isinstance(state.get("lastAgentRun"), Mapping)
            and str((state.get("lastAgentRun") or {}).get("stage") or "") == stage
            and int((state.get("lastAgentRun") or {}).get("finishedCount") or 0) > 0
        )
        if retry_blocked_author_progress:
            last_run = state.get("lastAgentRun") or {}
            failed_refs = _managed_author_failure_refs(
                list((last_run.get("outcomes") or []) if isinstance(last_run, Mapping) else [])
            )
            retries.pop(stage, None)
            state["retryCounts"] = retries
            state["status"] = "repairing"
            state["failedObjects"] = failed_refs or list(_checkpoint_is_done(ctx, stage)[1])
            state["nextAction"] = (
                f"retry remaining {stage} refs after partial author progress; "
                f"finished={int((last_run or {}).get('finishedCount') or 0)}, "
                f"remaining={len(state['failedObjects'])}"
            )
            state["heartbeatAt"] = store.now_iso()
            save_workflow_state(state)
            used = 0
        # ``MAX_REACT_REWINDS`` is the number of corrective ReAct passes, not
        # the total number of Agent attempts.  A checkpoint therefore gets its
        # initial authoring pass plus the configured repair passes.  Stopping
        # at ``used >=`` consumed the final repair before it could receive the
        # validation failure produced by the preceding pass.
        if _managed_checkpoint_repair_budget_exhausted(used):
            _ok, issues = _checkpoint_is_done(ctx, stage)
            state["status"] = "manual_required"
            state["failedObjects"] = list(issues)
            state["nextAction"] = (
                f"{stage} failed validation after {used} managed attempts"
                + (f"; unresolved={len(issues)}" if issues else "")
            )
            save_workflow_state(state)
            return 1
        consecutive_no_start_failures = _managed_consecutive_no_start_infra_failures(
            state,
            stage=stage,
        )
        if consecutive_no_start_failures >= MAX_MANAGED_INFRA_RETRIES:
            last_run = state.get("lastAgentRun") or {}
            infrastructure_failures = int((last_run or {}).get("infrastructureFailures") or 0)
            result = _handle_managed_infra_budget_exhausted(
                ctx,
                state,
                stage=stage,
                infra_used=consecutive_no_start_failures,
                infrastructure_failures=infrastructure_failures,
            )
            if result:
                return result
            continue
        state["status"] = "repairing" if used else "waiting_agent"
        save_workflow_state(state)
        if _run_managed_checkpoint(ctx, stage):
            state = load_workflow_state(ctx.execution_id)
            infra = state.setdefault("infrastructureRetryCounts", {})
            infra.pop(stage, None)
            state["infrastructureRetryCounts"] = infra
            save_workflow_state(state)
            if isinstance(state.get("controllerYield"), Mapping):
                print(f"[geo-homepages] controller yield after managed slice at checkpoint '{stage}'")
                return 10
            continue
        state = load_workflow_state(ctx.execution_id)
        last_run = state.get("lastAgentRun") or {}
        finished_count = int(last_run.get("finishedCount") or 0)
        if stage == "post_author" and finished_count > 0:
            retries = state.setdefault("retryCounts", {})
            retries.pop(stage, None)
            state["retryCounts"] = retries
            infra = state.setdefault("infrastructureRetryCounts", {})
            infra.pop(stage, None)
            state["infrastructureRetryCounts"] = infra
            failed_refs = _managed_author_failure_refs(
                list((last_run.get("outcomes") or []) if isinstance(last_run, Mapping) else [])
            )
            state["status"] = "repairing"
            state["failedObjects"] = failed_refs or list(_checkpoint_is_done(ctx, stage)[1])
            state["nextAction"] = (
                f"retry remaining {stage} refs after partial author progress: "
                f"finished={finished_count}, remaining={len(state['failedObjects'])}"
            )
            state["heartbeatAt"] = store.now_iso()
            if _managed_yield_after_ref_slice():
                state["controllerYield"] = {
                    "stage": stage,
                    "reason": "managed ref slice partially completed",
                    "hint": state["nextAction"],
                    "yieldedAt": state["heartbeatAt"],
                }
                save_workflow_state(state)
                print(f"[geo-homepages] controller yield after partial managed slice at checkpoint '{stage}'")
                return 10
            state.pop("controllerYield", None)
            save_workflow_state(state)
            time.sleep(2)
            continue
        infrastructure_failures = int(last_run.get("infrastructureFailures") or 0)
        if infrastructure_failures:
            infra = state.setdefault("infrastructureRetryCounts", {})
            if stage == "post_author" and finished_count > 0:
                # Cursor bridge failures are infrastructure noise, not content
                # failures.  Large author waves may still make real progress
                # while a subset of jobs fails to start; count only consecutive
                # no-progress waves against the infra retry budget.
                infra.pop(stage, None)
                state["infrastructureRetryCounts"] = infra
                failed_refs = _managed_author_failure_refs(
                    list((last_run.get("outcomes") or []) if isinstance(last_run, Mapping) else [])
                )
                state["status"] = "repairing"
                state["failedObjects"] = failed_refs
                state["nextAction"] = (
                    f"retry remaining {stage} refs after partial progress: "
                    f"finished={finished_count}, infraFailures={infrastructure_failures}, "
                    f"remaining={len(failed_refs)}"
                )
                state["heartbeatAt"] = store.now_iso()
                save_workflow_state(state)
                time.sleep(10)
                continue
            consecutive_no_start_failures = _managed_consecutive_no_start_infra_failures(
                state,
                stage=stage,
            )
            infra_used = max(int(infra.get(stage, 0)) + 1, consecutive_no_start_failures)
            infra[stage] = infra_used
            state["infrastructureRetryCounts"] = infra
            if infra_used >= MAX_MANAGED_INFRA_RETRIES:
                ok_after_failures, issues_after_failures = _checkpoint_is_done(ctx, stage)
                if ok_after_failures:
                    result = _handle_managed_infra_budget_exhausted(
                        ctx,
                        state,
                        stage=stage,
                        infra_used=infra_used,
                        infrastructure_failures=infrastructure_failures,
                        checkpoint_issues=issues_after_failures,
                    )
                    if result:
                        return result
                    continue
                if stage == "download_plan":
                    unresolved = _download_plan_unresolved_entities(ctx)
                    _write_download_plan_availability(ctx, unresolved, source="managed_infra_retry")
                result = _handle_managed_infra_budget_exhausted(
                    ctx,
                    state,
                    stage=stage,
                    infra_used=infra_used,
                    infrastructure_failures=infrastructure_failures,
                    checkpoint_issues=issues_after_failures,
                )
                if result:
                    return result
                if ok_after_failures:
                    continue
                return 1
            state["nextAction"] = (
                f"retry {stage} infrastructure: attempt "
                f"{infra_used + 1}/{MAX_MANAGED_INFRA_RETRIES}"
            )
            save_workflow_state(state)
            time.sleep(min(30, 5 * infra_used))
            continue
        retries = state.setdefault("retryCounts", {})
        retries[stage] = used + 1
        state["retryCounts"] = retries
        save_workflow_state(state)
        time.sleep(min(2 ** used, 5))
