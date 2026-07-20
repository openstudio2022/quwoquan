"""Execution completion checks owned by the controller boundary."""
from __future__ import annotations

from content.execution.support import ExecutionContext, ExecutionStateStatus, ExecutionStateTransition, store


def execution_completion_issues(
    ctx: ExecutionContext,
    state: ExecutionStateTransition,
) -> list[str]:
    from content.execution.agent.agent_checkpoint import _checkpoint_is_done
    from content.execution.agent.history import last_managed_agent_run, save_managed_agent_run
    from content.execution.agent.auto_research import _download_auto_research_lanes

    issues: list[str] = []
    if state.waiting_checkpoint:
        issues.append(f"execution still waiting at {state.waiting_checkpoint}")
    failed_objects = state.failed_objects or []
    if failed_objects:
        issues.append(f"execution has failedObjects={len(failed_objects)}")
    last_agent = last_managed_agent_run(state)
    if last_agent is not None and last_agent.recovered:
        last_agent = None
    if last_agent is not None:
        run_stage = last_agent.stage.value
        snapshot_failed = bool(last_agent.job_count) and (
            last_agent.started_count <= 0
            or last_agent.finished_count < last_agent.job_count
            or last_agent.infrastructure_failures > 0
        )
        if snapshot_failed and run_stage:
            ok_now, _ = _checkpoint_is_done(ctx, run_stage)
            if ok_now:
                save_managed_agent_run(
                    state,
                    last_agent.with_recovery(
                        recovered_at=store.now_iso(),
                        recovery_reason=(
                            f"completion gate: {run_stage} checkpoint re-verified; "
                            "stale infrastructure failure snapshot"
                        ),
                    ),
                )
                last_agent = None
        if last_agent is not None:
            job_count = last_agent.job_count
            started = last_agent.started_count
            finished = last_agent.finished_count
            infra = last_agent.infrastructure_failures
            if infra:
                issues.append(f"lastAgentRun.infrastructureFailures={infra}")
            if job_count and started <= 0:
                issues.append("lastAgentRun has jobs but no started workers")
            if job_count and finished < job_count:
                issues.append(
                    f"lastAgentRun finishedCount={finished} < jobCount={job_count}"
                )
    if ctx.managed:
        try:
            from content.execution.readiness_audit import audit_execution_readiness

            audit_state = state.freeze().open_transition()
            audit_state.status = ExecutionStateStatus.SUCCEEDED
            audit_state.waiting_checkpoint = None
            audit_state.failed_objects = []
            audit_state.next_action = None
            audit = audit_execution_readiness(
                ctx.execution_id,
                execution_state_override=audit_state,
            )
        except Exception as exc:  # noqa: BLE001
            issues.append(f"managed execution audit unavailable: {exc}")
        else:
            failed_lane_count = int(audit.get("failedLaneCount") or 0)
            if failed_lane_count:
                issues.append(
                    f"managed execution audit failedLaneCount={failed_lane_count}"
                )
            lane_passed = audit.get("lanePassed") or {}
            target_count = int(audit.get("targetCount") or 0)
            enabled_lanes = _download_auto_research_lanes(ctx)
            for lane in sorted(enabled_lanes):
                passed = int(lane_passed.get(lane) or 0)
                if target_count and passed != target_count:
                    issues.append(
                        f"managed lane {lane} passed {passed}/{target_count}"
                    )
    return issues
