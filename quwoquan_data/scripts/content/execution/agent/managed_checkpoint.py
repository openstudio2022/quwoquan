"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.runtime_policy import active_runtime_policy
from content.execution.context import managed_lane_limits
from content.execution.support import Any, ExecutionContext, ExecutionStateStatus, MANAGED_AGENT_FUTURE_GRACE_SECONDS, MANAGED_AGENT_TIMEOUT_SECONDS, MAX_MANAGED_INFRA_RETRIES, MAX_REACT_REWINDS, Mapping, Path, ThreadPoolExecutor, _is_homepage_only_execution, _normalize_managed_agent_provider, defaultdict, execution_root, load_execution_state, os, release_root, save_execution_state, store, time, wait

_AGENT_FUTURE_POLL_TIMEOUT_SECONDS = active_runtime_policy().agent_future_poll_timeout_seconds

def _run_managed_checkpoint(ctx: ExecutionContext, stage: str) -> bool:
    from content.execution.agent.agent_checkpoint import _checkpoint_is_done, _finalize_managed_author_outputs, _managed_author_ref, _managed_checkpoint_job_issues, _managed_prompt_lane
    from content.execution.agent.checkpoint_prompts import _checkpoint_prompts
    from content.execution.agent.agent_runner import _terminate_workspace_cursor_bridges
    from content.execution.agent.agent_worker import _default_managed_agent_runner_isolated, _terminate_managed_agent_subprocesses
    from content.execution.agent.history import (
        ManagedAgentScheduler,
        build_managed_agent_run_record,
        save_managed_agent_run,
    )
    from content.execution.agent.outcome import (
        AgentRunOutcome,
        ManagedAgentJobOutcome,
        coerce_agent_outcome,
    )
    from content.execution.controller.homepage_author_finalization import _finalize_managed_homepage_outputs
    from content.execution.context import _managed_local_cursor_worker_cap
    from core.control_types import (
        AgentFailureKind,
        AgentProvider,
        ExecutionStage,
        ManagedAgentCheckpointStatus,
    )
    prompts = _checkpoint_prompts(ctx, stage)
    if not prompts:
        return False
    lane_limits = managed_lane_limits(len(prompts))
    worker_count = _managed_checkpoint_worker_count(ctx, len(prompts))
    checkpoint_started_at = store.now_iso()
    checkpoint_started_mono = time.monotonic()
    estimated_waves = (len(prompts) + max(worker_count, 1) - 1) // max(worker_count, 1)
    state = load_execution_state(ctx.execution_id)
    state.status = ExecutionStateStatus.WAITING_AGENT
    state.waiting_checkpoint = stage
    state.owner = f"managed-local:{stage}"
    state.heartbeat_at = store.now_iso()
    state.next_action = f"running {len(prompts)} agent job(s) for {stage}"
    state.failed_objects = []
    state.active_agent_scheduler = {
        "stage": stage,
        "requestedMaxWorkers": int(ctx.max_workers or 1),
        "effectiveWorkerCount": worker_count,
        "localCursorMaxWorkers": _managed_local_cursor_worker_cap(ctx),
        "runtime": str(ctx.runtime),
        "promptCount": len(prompts),
        "estimatedMinWaves": estimated_waves,
        "laneLimits": dict(lane_limits),
        "agentProvider": _normalize_managed_agent_provider(ctx.agent_provider),
        "startedAt": checkpoint_started_at,
    }
    state.last_agent_run = None
    save_execution_state(state)
    if ctx.agent_runner is not None:
        runner = ctx.agent_runner
    else:
        def runner(prompt: str):
            return _default_managed_agent_runner_isolated(ctx, prompt)
    queued = list(range(len(prompts)))
    futures: dict[Any, tuple[int, str, float]] = {}
    active_by_lane: dict[str, int] = defaultdict(int)
    job_timings: dict[int, dict[str, Any]] = {}
    outcomes: list[ManagedAgentJobOutcome] = []
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
                    cap = lane_limits.get(lane, worker_count)
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
                    for lane, cap in lane_limits.items()
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
                    outcome = coerce_agent_outcome(
                        future.result(),
                        label=f"managed agent runner {stage}/{index}",
                    )
                except Exception as exc:  # noqa: BLE001
                    outcome = AgentRunOutcome.failed(
                        AgentFailureKind.SDK_EXECUTION_FAILED,
                        message=f"managed agent runner failed: {type(exc).__name__}: {exc}",
                        provider=ctx.agent_provider,
                    )
                checkpoint_ref = _managed_checkpoint_ref(ctx, stage, prompts[index])
                job_outcome = ManagedAgentJobOutcome(
                    outcome=outcome,
                    job_index=index,
                    lane=lane,
                    ref=checkpoint_ref,
                    timing=tuple(timing.items()),
                )
                if job_outcome.succeeded:
                    gate_issues = _managed_checkpoint_job_issues(
                        ctx,
                        stage=stage,
                        prompt=prompts[index],
                    )
                    if gate_issues:
                        job_outcome = job_outcome.with_gate_issues(tuple(gate_issues))
                outcomes.append(job_outcome)
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
                    ManagedAgentJobOutcome(
                        outcome=AgentRunOutcome.failed(
                            AgentFailureKind.FUTURE_TIMEOUT,
                            message=(
                                f"managed agent future timed out after "
                                f"{int(now - started_at)}s for {stage}/{lane}"
                            ),
                            retryable=True,
                            provider=ctx.agent_provider,
                        ),
                        job_index=index,
                        lane=lane,
                        ref=_managed_checkpoint_ref(ctx, stage, prompts[index]),
                        timing=tuple(timing.items()),
                    )
                )
                if str(ctx.runtime) == "local":
                    _terminate_workspace_cursor_bridges(Path.cwd())
            state = load_execution_state(ctx.execution_id)
            state.heartbeat_at = store.now_iso()
            state.next_action = (
                f"{stage}: {len(outcomes)}/{len(prompts)} agent job(s) finished; "
                f"active={dict(active_by_lane)}"
            )
            save_execution_state(state)
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
        outcomes.sort(key=lambda item: item.job_index)
        if stage == "post_author":
            _finalize_managed_author_outputs(ctx, prompts, outcomes)
        elif stage == "build_homepage":
            outcomes = list(_finalize_managed_homepage_outputs(ctx, prompts, outcomes))
        finished_count = sum(out.succeeded for out in outcomes)
        started_count = sum(out.outcome.started for out in outcomes)
        infrastructure_failures = sum(not out.outcome.started for out in outcomes)
        state = load_execution_state(ctx.execution_id)
        state.active_agent_scheduler = None
        resumable_author_interrupt = stage == "post_author"
        state.status = (
            ExecutionStateStatus.REPAIRING
            if resumable_author_interrupt
            else ExecutionStateStatus.MANUAL_REQUIRED
        )
        retry_hint = (
            f"{stage}: interrupted; resume will retry remaining agent job(s); "
            f"finished={finished_count}, cancelledQueued={cancelled_queued_count}, "
            f"cancelledActive={cancelled_active_count}; {interrupt_reason}"
        )
        state.failed_objects = [retry_hint]
        state.next_action = retry_hint if resumable_author_interrupt else f"{stage}: interrupted ({interrupt_reason})"
        state.heartbeat_at = store.now_iso()
        interrupted_at = store.now_iso()
        yield_reason = "managed checkpoint interrupted"
        if finished_count > 0:
            yield_reason = "managed checkpoint interrupted after partial author progress"
        partial_record = build_managed_agent_run_record(
            stage=ExecutionStage(stage),
            planned_job_count=len(prompts),
            scheduler=ManagedAgentScheduler(
                requested_max_workers=int(ctx.max_workers or 1),
                effective_worker_count=worker_count,
                local_cursor_max_workers=_managed_local_cursor_worker_cap(ctx),
                runtime=str(ctx.runtime),
                prompt_count=len(prompts),
                estimated_min_waves=estimated_waves,
                lane_limits=tuple(sorted(lane_limits.items())),
                provider=AgentProvider(_normalize_managed_agent_provider(ctx.agent_provider)),
                started_at=checkpoint_started_at,
                finished_at=interrupted_at,
                elapsed_seconds=round(max(0.0, time.monotonic() - checkpoint_started_mono), 3),
            ),
            outcomes=tuple(outcomes),
            finished_at=interrupted_at,
            status=ManagedAgentCheckpointStatus.INTERRUPTED,
            interrupt_reason=interrupt_reason,
            cancelled_queued_job_count=cancelled_queued_count,
            cancelled_active_job_count=cancelled_active_count,
            terminated_subprocess_pids=tuple(terminated_subprocesses),
        )
        save_managed_agent_run(state, partial_record)
        if resumable_author_interrupt:
            state.managed_checkpoint_interruption = {
                "stage": stage,
                "reason": interrupt_reason,
                "resumable": True,
                "finishedCount": finished_count,
                "plannedJobCount": len(prompts),
                "cancelledQueuedJobCount": cancelled_queued_count,
                "cancelledActiveJobCount": cancelled_active_count,
                "interruptedAt": interrupted_at,
            }
            state.controller_yield = {
                "stage": stage,
                "reason": yield_reason,
                "hint": retry_hint,
                "yieldedAt": state.heartbeat_at,
            }
        else:
            state.managed_checkpoint_interruption = None
        save_execution_state(state)
        raise
    finally:
        pool.shutdown(wait=not (interrupted or force_abort_pool), cancel_futures=True)
    outcomes.sort(key=lambda item: item.job_index)
    if stage == "post_author":
        _finalize_managed_author_outputs(ctx, prompts, outcomes)
    elif stage == "build_homepage":
        outcomes = list(_finalize_managed_homepage_outputs(ctx, prompts, outcomes))
    started_count = sum(out.outcome.started for out in outcomes)
    finished_count = sum(out.succeeded for out in outcomes)
    infrastructure_failures = sum(not out.outcome.started for out in outcomes)
    finished_at = store.now_iso()
    state = load_execution_state(ctx.execution_id)
    state.active_agent_scheduler = None
    typed_stage = ExecutionStage(stage)
    if typed_stage in {ExecutionStage.BUILD_HOMEPAGE, ExecutionStage.POST_AUTHOR}:
        from content.execution.agent.checkpoint_exclusion import (
            write_semantic_checkpoint_exclusion,
        )

        for outcome in outcomes:
            if not outcome.succeeded and outcome.ref:
                write_semantic_checkpoint_exclusion(
                    ctx.execution_id,
                    stage=typed_stage,
                    job_outcome=outcome,
                    recorded_at=finished_at,
                )
    agent_run_record = build_managed_agent_run_record(
        stage=typed_stage,
        planned_job_count=len(prompts),
        scheduler=ManagedAgentScheduler(
            requested_max_workers=int(ctx.max_workers or 1),
            effective_worker_count=worker_count,
            local_cursor_max_workers=_managed_local_cursor_worker_cap(ctx),
            runtime=str(ctx.runtime),
            prompt_count=len(prompts),
            estimated_min_waves=estimated_waves,
            lane_limits=tuple(sorted(lane_limits.items())),
            provider=AgentProvider(_normalize_managed_agent_provider(ctx.agent_provider)),
            started_at=checkpoint_started_at,
            finished_at=finished_at,
            elapsed_seconds=round(max(0.0, time.monotonic() - checkpoint_started_mono), 3),
        ),
        outcomes=tuple(outcomes),
        finished_at=finished_at,
    )
    save_managed_agent_run(state, agent_run_record)
    save_execution_state(state)
    failures = [out for out in outcomes if not out.succeeded]
    if failures:
        state = load_execution_state(ctx.execution_id)
        state.status = ExecutionStateStatus.REPAIRING
        state.failed_objects = [out.outcome.message for out in failures]
        save_execution_state(state)
        return False
    ok, issues = _checkpoint_is_done(ctx, stage)
    state = load_execution_state(ctx.execution_id)
    state.owner = "managed-local"
    state.heartbeat_at = store.now_iso()
    state.managed_checkpoint_interruption = None
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
        state.failed_objects = []
        state.status = ExecutionStateStatus.RUNNING
        state.next_action = (
            f"continue {stage}: managed ref slice completed "
            f"({len(prompts)} refs); remaining checkpoint issues={len(issues)}"
        )
        if _managed_yield_after_ref_slice():
            state.status = ExecutionStateStatus.REPAIRING
            state.controller_yield = {
                "stage": stage,
                "reason": "managed ref slice completed",
                "hint": state.next_action,
                "yieldedAt": state.heartbeat_at,
            }
    else:
        state.failed_objects = list(issues)
        state.status = (
            ExecutionStateStatus.RUNNING
            if ok
            else ExecutionStateStatus.REPAIRING
        )
        state.next_action = None if ok else f"repair {stage}: {issues[:5]}"
        state.controller_yield = None
    save_execution_state(state)
    return ok or limited_slice_progress


def _managed_checkpoint_ref(
    ctx: ExecutionContext,
    stage: str,
    prompt: str,
) -> str:
    """Resolve the stable object identity attached to one managed Agent run."""
    from content.execution.agent.agent_checkpoint import (
        _managed_author_ref,
        _managed_prompt_entity,
    )

    if stage == "post_author":
        return _managed_author_ref(prompt)
    if stage != "build_homepage":
        return ""
    entity = _managed_prompt_entity(prompt)
    from content.execution.workspace import frozen_target_by_name

    target = frozen_target_by_name(ctx.execution_id, entity)
    if target is None:
        return ""
    from governance.coverage.entity_extract import require_domain_etype

    domain, entity_type = require_domain_etype(target.entity_type, context=entity)
    return f"/entity/{domain}/{entity_type}/{entity}"


def _managed_checkpoint_worker_count(ctx: ExecutionContext, prompt_count: int) -> int:
    """Every prompt of one checkpoint may start; this is not a capacity ceiling."""
    return max(1, prompt_count)
def _managed_checkpoint_ref_limit() -> int:
    from core.runtime_policy import active_runtime_policy

    return active_runtime_policy().managed_checkpoint_ref_limit
def _managed_yield_after_ref_slice() -> bool:
    return str(os.environ.get("QWQ_MANAGED_YIELD_AFTER_REF_SLICE") or "").strip() in {
        "1",
        "true",
        "yes",
    }
