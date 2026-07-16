"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ExecutionStage
from content.execution.support import Any, Callable, DataIssueCode, DataRecoveryAction, ExecutionContext, Iterable, MANAGED_SCHEDULER_STALE_SECONDS, MAX_REACT_REWINDS, Mapping, Path, StageResult, contextmanager, data_issues, execution_root, load_workflow_state, os, save_workflow_state, signal, store, subprocess, sys

def _rewind_to(completed: set[str], target_stage: ExecutionStage) -> set[str]:
    """ReAct 回退：把 target_stage 及其后所有 stage 从 completed 移除，强制重跑。"""
    from content.execution.pipeline.dag import STAGE_NAMES
    if target_stage not in STAGE_NAMES:
        return completed
    idx = STAGE_NAMES.index(target_stage)
    keep = set(STAGE_NAMES[:idx])
    return {s for s in completed if s in keep}

def _completed_until_revalidation(ctx: ExecutionContext, stage_name: str) -> tuple[bool, list[str]]:
    """Re-check a previously completed --until checkpoint before crossing it."""
    from content.execution.agent.agent_checkpoint import _checkpoint_is_done
    from content.execution.recovery.download_gate import _download_retry_entity_ids, _stale_source_plan_entities
    from content.execution.recovery.stage_reset import _source_plan_filled, _source_plan_issue_records
    if stage_name == "download_plan":
        ok, issues = _source_plan_filled(ctx)
        source_plan_issues = _source_plan_issue_records(ctx)
        repair_scope = _download_retry_entity_ids(ctx) or [
            entity_id
            for entity_id in ctx.entity_ids
            if any(issue.ref == entity_id for issue in source_plan_issues)
        ]
        if not repair_scope and len(ctx.entity_ids) == 1:
            repair_scope = list(ctx.entity_ids)
        stale_entities = _stale_source_plan_entities(ctx, entity_ids=repair_scope) if ok and repair_scope else []
        if stale_entities:
            issues = list(issues) + [
                f"{item.get('entityId')}: source_plan predates source registry/rights policy"
                for item in stale_entities
                if item.get("entityId")
            ]
        return ok and not stale_entities, issues
    return _checkpoint_is_done(ctx, stage_name)

def _stop_at_until(
    ctx: ExecutionContext,
    state: dict,
    completed: set[str],
    *,
    next_stage: str | None,
) -> int:
    state["completed"] = sorted(completed)
    state["waitingCheckpoint"] = None
    state["status"] = "stopped_at_until"
    state["stoppedAtStage"] = ctx.until
    state["nextAction"] = next_stage or "workflow complete"
    state["heartbeatAt"] = store.now_iso()
    save_workflow_state(state)
    print(f"[geo-homepages] stopped at --until {ctx.until}")
    return 0

def _react_rewind(ctx: ExecutionContext, state: dict, completed: set[str],
                  result: StageResult) -> tuple[set[str], bool]:
    """处理 failed 的 ReAct 回退。返回 (新 completed, 是否成功回退)。
    回退账本记 reactRewinds[stage] 计数；超 MAX_REACT_REWINDS 则不再回退（转人工）。
    """
    from content.execution.pipeline.dag import STAGE_NAMES
    from content.execution.recovery.post_recovery import _prepare_post_review_retry
    target = result.fallback_stage
    if not target or target not in STAGE_NAMES:
        return completed, False
    latest_state = load_workflow_state(ctx.execution_id)
    if latest_state:
        state.clear()
        state.update(latest_state)
    rewinds = state.setdefault("reactRewinds", {})
    key = result.stage
    used = int(rewinds.get(key, 0))
    if used >= MAX_REACT_REWINDS:
        print(f"[geo-homepages] ReAct 回退已达上限({MAX_REACT_REWINDS}) @ {result.stage}; 转人工", file=sys.stderr)
        return completed, False
    rewinds[key] = used + 1
    # 写 repair_report（反思账本：失败 stage → 回退链）
    from content.execution.stage_reports import write_repair_report
    repair_issues = result.issue_records or data_issues(
        DataIssueCode.SOURCE_PLAN_INVALID if target is ExecutionStage.DOWNLOAD_PLAN else DataIssueCode.QUALITY_FAILED,
        stage=result.issue_stage,
        ref=result.stage,
        messages=result.issues or [result.message],
        recovery=(
            DataRecoveryAction.REWIND_DOWNLOAD
            if target is ExecutionStage.DOWNLOAD_PLAN
            else DataRecoveryAction.REWIND_COMPOSE
        ),
    )
    write_repair_report(
        execution_id=ctx.execution_id,
        command="execution",
        ref=result.stage, failed_stage=result.stage, failed_gate=f"{result.stage}_gate",
        issues=repair_issues,
        fallback_stage=target,
        rerun_chain=STAGE_NAMES[STAGE_NAMES.index(target):STAGE_NAMES.index(result.stage) + 1],
    )
    if result.stage is ExecutionStage.POST_REVIEW:
        prepared = _prepare_post_review_retry(ctx, result, target)
        if target is ExecutionStage.POST_COMPOSE and not prepared:
            print(
                "[geo-homepages] post_review failed only at batch/release packaging; "
                "no content object will be invalidated",
                file=sys.stderr,
            )
            return completed, False
        latest = load_workflow_state(ctx.execution_id)
        if latest:
            state.clear()
            state.update(latest)
    new_completed = _rewind_to(completed, target)
    state["reactRewinds"] = rewinds
    state["completed"] = sorted(new_completed)
    save_workflow_state(state)
    print(f"[geo-homepages] ⟲ ReAct 回退 {result.stage} → {target} (第{used + 1}/{MAX_REACT_REWINDS}次)\n"
          f"           归因: {result.message.splitlines()[0]}")
    return new_completed, True

def _stage_exception_fallback(stage_name: ExecutionStage) -> ExecutionStage | None:
    if stage_name is ExecutionStage.POST_COMPOSE:
        return ExecutionStage.CONTENT_PLAN
    if stage_name is ExecutionStage.POST_AUTHOR:
        return ExecutionStage.POST_COMPOSE
    if stage_name is ExecutionStage.BUILD_VALIDATE:
        return ExecutionStage.BUILD_HOMEPAGE
    if stage_name is ExecutionStage.POST_REVIEW:
        return ExecutionStage.POST_COMPOSE
    return None

def _managed_agent_process_alive(
    ctx: ExecutionContext,
    *,
    include_workspace_bridge: bool = True,
) -> bool:
    """Best-effort check for a local managed Cursor/task-run process."""
    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "pid=", "-o", "command="],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return True
    workspace_text = str(Path.cwd())
    current_pid = os.getpid()
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _sep, command = stripped.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            pid = -1
            command = stripped
        if pid == current_pid:
            continue
        if include_workspace_bridge and "cursor-sdk-bridge" in command and workspace_text in command:
            return True
        if (
            "scripts/cli.py" in command
            and ("task geo-homepages" in command)
            and (ctx.execution_id in command or ctx.execution_id in command)
        ):
            return True
    return False

def _recover_stale_agent_scheduler(ctx: ExecutionContext, state: dict[str, Any]) -> bool:
    """Clear orphaned waiting_agent state left by interrupted managed-local runs."""
    from content.execution.pipeline.metrics import _parse_iso_seconds
    scheduler = state.get("activeAgentScheduler")
    if not isinstance(scheduler, Mapping):
        return False
    if str(scheduler.get("runtime") or ctx.runtime) != "local":
        return False
    if str(state.get("status") or "") != "waiting_agent":
        return False
    heartbeat = _parse_iso_seconds(
        state.get("heartbeatAt") or scheduler.get("updatedAt") or scheduler.get("startedAt")
    )
    now = _parse_iso_seconds(store.now_iso())
    if _managed_agent_process_alive(ctx):
        return False
    if heartbeat is not None and now is not None and now - heartbeat < MANAGED_SCHEDULER_STALE_SECONDS:
        scheduler["recoveredBeforeStaleTimeout"] = True
    stage = str(scheduler.get("stage") or state.get("waitingCheckpoint") or "")
    recovered = {
        "stage": stage,
        "reason": "orphaned managed-local scheduler without live Cursor/task-run process",
        "previous": dict(scheduler),
        "recoveredAt": store.now_iso(),
    }
    history = state.setdefault("schedulerRecoveryActions", [])
    if isinstance(history, list):
        history.append(recovered)
        state["schedulerRecoveryActions"] = history[-20:]
    state.pop("activeAgentScheduler", None)
    state["waitingCheckpoint"] = stage or state.get("waitingCheckpoint")
    state["status"] = "running"
    state["nextAction"] = (
        f"recovered stale managed scheduler at {stage or '<unknown>'}; "
        "resume will revalidate checkpoint"
    )
    state["heartbeatAt"] = store.now_iso()
    state["failedObjects"] = []
    save_workflow_state(state)
    return True

def _recover_stale_auto_research(ctx: ExecutionContext, state: dict[str, Any]) -> bool:
    """Mark orphaned deterministic source discovery as an explicit checkpoint failure.
    Unlike managed Agent jobs, auto research runs inside the workflow process.
    If the process is interrupted or killed after the progress callback writes
    `activeAutoResearch`, the batch can otherwise sit in `running` forever with
    no live worker. Recovery must be deterministic: record the interruption,
    clear the active marker, and let the next run revalidate download_plan.
    """
    from content.execution.pipeline.metrics import _parse_iso_seconds
    active = state.get("activeAutoResearch")
    if not isinstance(active, Mapping):
        return False
    if str(active.get("stage") or "") != "download_plan":
        return False
    status = str(active.get("status") or "").strip()
    if status == "succeeded":
        state.pop("activeAutoResearch", None)
        save_workflow_state(state)
        return True
    heartbeat = _parse_iso_seconds(
        state.get("heartbeatAt") or active.get("updatedAt") or active.get("startedAt")
    )
    now = _parse_iso_seconds(store.now_iso())
    stale = heartbeat is None or now is None or now - heartbeat >= MANAGED_SCHEDULER_STALE_SECONDS
    interrupted = status == "interrupted"
    live_process = _managed_agent_process_alive(ctx)
    fresh_orphan = status == "running" and not live_process
    if not interrupted and not stale and not fresh_orphan:
        return False
    if live_process:
        return False
    recovered_at = store.now_iso()
    recovered = {
        "stage": "download_plan",
        "reason": (
            "interrupted auto research progress"
            if interrupted
            else (
                "orphaned running auto research without live workflow process"
                if fresh_orphan
                else "stale auto research heartbeat without live workflow process"
            )
        ),
        "previous": dict(active),
        "recoveredAt": recovered_at,
    }
    history = state.setdefault("autoResearchRecoveryActions", [])
    if isinstance(history, list):
        history.append(recovered)
        state["autoResearchRecoveryActions"] = history[-20:]
    state.pop("activeAutoResearch", None)
    state["waitingCheckpoint"] = "download_plan"
    state["lastFailedStage"] = "download_plan"
    state["status"] = "manual_required"
    state["failedObjects"] = [
        "download_plan: auto_research interrupted or stale; resume will revalidate checkpoint"
    ]
    state["nextAction"] = "download_plan auto_research interrupted/stale; rerun workflow to revalidate source readiness"
    state["heartbeatAt"] = recovered_at
    save_workflow_state(state)
    return True

def _recover_stale_controller_yield(ctx: ExecutionContext, state: dict[str, Any]) -> bool:
    """Clear stale controllerYield left by a dead managed-local controller."""
    controller_yield = state.get("controllerYield")
    if not isinstance(controller_yield, Mapping):
        return False
    stage = str(controller_yield.get("stage") or state.get("waitingCheckpoint") or "")
    from core import ops_governance as og
    lease = og.read_controller_lease(ctx.execution_id)
    lease_live = (
        isinstance(lease, Mapping)
        and str(lease.get("status") or "active") == "active"
        and og.pid_alive(lease.get("pid"))
    )
    try:
        workflow_live = _managed_agent_process_alive(ctx, include_workspace_bridge=False)
    except TypeError as exc:
        if "include_workspace_bridge" not in str(exc):
            raise
        workflow_live = _managed_agent_process_alive(ctx)
    if lease_live or workflow_live:
        return False
    recovered_at = store.now_iso()
    recovered = {
        "stage": stage,
        "reason": "stale controllerYield without live controller lease or workflow process",
        "previous": dict(controller_yield),
        "previousLease": dict(lease or {}) if isinstance(lease, Mapping) else None,
        "recoveredAt": recovered_at,
    }
    history = state.setdefault("controllerYieldRecoveryActions", [])
    if isinstance(history, list):
        history.append(recovered)
        state["controllerYieldRecoveryActions"] = history[-20:]
    state.pop("controllerYield", None)
    state.pop("activeAgentScheduler", None)
    state["waitingCheckpoint"] = stage or state.get("waitingCheckpoint")
    state["status"] = "running"
    state["failedObjects"] = []
    state["nextAction"] = (
        f"recovered stale controller yield at {stage or '<unknown>'}; "
        "managed loop will revalidate checkpoint"
    )
    state["heartbeatAt"] = recovered_at
    try:
        lease_path = og.controller_lease_path(ctx.execution_id, create=False)
        if lease_path.is_file() and not lease_live:
            lease_path.unlink()
    except OSError:
        pass
    save_workflow_state(state)
    return True

def _mark_workflow_interrupted(
    ctx: ExecutionContext,
    *,
    stage: str,
    completed: Iterable[str],
    reason: str,
) -> None:
    state = load_workflow_state(ctx.execution_id)
    state["completed"] = sorted(set(completed))
    state["waitingCheckpoint"] = stage
    state["lastFailedStage"] = stage
    state["status"] = "manual_required"
    state["failedObjects"] = [reason]
    state["nextAction"] = f"{stage}: interrupted; rerun workflow to revalidate checkpoint"
    state["interruptReason"] = reason
    state["heartbeatAt"] = store.now_iso()
    state.pop("activeAgentScheduler", None)
    active = state.get("activeAutoResearch")
    if isinstance(active, Mapping):
        updated = dict(active)
        updated["status"] = "interrupted"
        updated["interruptedAt"] = state["heartbeatAt"]
        updated["interruptReason"] = reason
        state["activeAutoResearch"] = updated
    save_workflow_state(state)

def _managed_checkpoint_interruption_is_resumable(
    ctx: ExecutionContext,
    state: Mapping[str, Any],
    *,
    stage: str,
) -> bool:
    """Whether a managed checkpoint already persisted a resumable interruption."""
    if not ctx.managed:
        return False
    if str(state.get("status") or "") != "repairing":
        return False
    marker = state.get("managedCheckpointInterruption")
    if isinstance(marker, Mapping) and str(marker.get("stage") or "") == stage:
        return bool(marker.get("resumable"))
    last_run = state.get("lastAgentRun")
    if not isinstance(last_run, Mapping):
        return False
    return (
        str(last_run.get("stage") or "") == stage
        and str(last_run.get("status") or "") == "interrupted"
    )

@contextmanager
def _workflow_signal_guard(ctx: ExecutionContext):
    """Persist workflow interruption before SIGTERM/SIGINT tears down the process."""
    previous: dict[int, Any] = {}
    def _handler(signum: int, _frame: object) -> None:
        state = load_workflow_state(ctx.execution_id)
        active_auto = state.get("activeAutoResearch") if isinstance(state.get("activeAutoResearch"), Mapping) else {}
        stage = str(
            state.get("waitingCheckpoint")
            or active_auto.get("stage")
            or state.get("lastFailedStage")
            or "workflow"
        )
        completed = state.get("completed") if isinstance(state.get("completed"), list) else []
        _mark_workflow_interrupted(
            ctx,
            stage=stage,
            completed=[str(item) for item in completed],
            reason=f"{stage}: interrupted by signal {signum}; workflow controller stopped",
        )
        raise KeyboardInterrupt(f"workflow interrupted by signal {signum}")
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.getsignal(sig)
        signal.signal(sig, _handler)
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)

def _download_auto_research_progress_callback(ctx: ExecutionContext) -> Callable[[dict[str, Any]], None]:
    def _callback(progress: dict[str, Any]) -> None:
        state = load_workflow_state(ctx.execution_id)
        state["status"] = "running"
        state["waitingCheckpoint"] = None
        state["heartbeatAt"] = store.now_iso()
        completed_count = int(progress.get("completedCount") or 0)
        entity_count = int(progress.get("entityCount") or 0)
        state["nextAction"] = (
            f"download_plan auto_research {completed_count}/{entity_count}: "
            f"{progress.get('message') or progress.get('status') or 'running'}"
        )
        state["activeAutoResearch"] = {
            "stage": "download_plan",
            "status": progress.get("status"),
            "entityId": progress.get("entityId"),
            "entityCount": entity_count,
            "completedCount": completed_count,
            "remainingCount": progress.get("remainingCount"),
            "workers": progress.get("workers"),
            "entitiesPerMinute": progress.get("entitiesPerMinute"),
            "progressPath": str(execution_root(ctx.execution_id) / "_shared" / "auto_research_progress.json"),
            "updatedAt": progress.get("updatedAt"),
        }
        save_workflow_state(state)
        print(f"[geo-homepages] {state['nextAction']}", flush=True)
    return _callback
