"""Execution completion checks owned by the controller boundary."""
from __future__ import annotations

from content.execution.support import ExecutionContext, ExecutionStateStatus, ExecutionStateTransition, store


def execution_completion_issues(
    ctx: ExecutionContext,
    state: ExecutionStateTransition,
) -> list[str]:
    from content.execution.agent.agent_checkpoint import _checkpoint_is_done
    from content.execution.agent.auto_research import _download_auto_research_lanes

    issues: list[str] = []
    if state.waiting_checkpoint:
        issues.append(f"execution still waiting at {state.waiting_checkpoint}")
    failed_objects = state.failed_objects or []
    if failed_objects:
        issues.append(f"execution has failedObjects={len(failed_objects)}")
    last_agent = state.last_agent_run or {}
    if isinstance(last_agent, dict) and last_agent:
        if bool(last_agent.get("recovered")):
            last_agent = {}
    if isinstance(last_agent, dict) and last_agent:
        run_stage = str(last_agent.get("stage") or "").strip()
        snapshot_failed = bool(int(last_agent.get("jobCount") or 0)) and (
            int(last_agent.get("startedCount") or 0) <= 0
            or int(last_agent.get("finishedCount") or 0)
            < int(last_agent.get("jobCount") or 0)
            or int(last_agent.get("infrastructureFailures") or 0) > 0
        )
        if snapshot_failed and run_stage:
            ok_now, _ = _checkpoint_is_done(ctx, run_stage)
            if ok_now:
                recovered_run = dict(last_agent)
                recovered_run["recovered"] = True
                recovered_run["recoveredAt"] = store.now_iso()
                recovered_run["recoveryReason"] = (
                    f"completion gate: {run_stage} checkpoint re-verified; "
                    "stale infrastructure failure snapshot"
                )
                state.last_agent_run = recovered_run
                last_agent = {}
        if isinstance(last_agent, dict) and last_agent:
            job_count = int(last_agent.get("jobCount") or 0)
            started = int(last_agent.get("startedCount") or 0)
            finished = int(last_agent.get("finishedCount") or 0)
            infra = int(last_agent.get("infrastructureFailures") or 0)
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
