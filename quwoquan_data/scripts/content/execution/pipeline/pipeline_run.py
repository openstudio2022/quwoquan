"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
import traceback

from core.control_types import ExecutionStage, StageStatus
from content.execution.support import CHECKPOINT, DataIssueCode, DataIssueError, DataIssueStage, DataRecoveryAction, ExecutionContext, MAX_REACT_REWINDS, StageResult, _active_spec, _write_workflow_packet, data_issue, ensure_execution_command_layout, load_workflow_state, save_workflow_state, store, sys


def _unexpected_stage_issue(stage_name: str, exc: Exception):
    """Render an internal exception as a bounded, non-secret typed issue."""
    message = " ".join(str(exc).split())[:400] or type(exc).__name__
    frames = traceback.extract_tb(exc.__traceback__)
    location = ""
    if frames:
        frame = frames[-1]
        location = f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}:{frame.name}"
    return data_issue(
        DataIssueCode.INTERNAL_UNEXPECTED,
        stage=DataIssueStage(stage_name),
        recovery=DataRecoveryAction.STOP,
        message="workflow stage raised an unexpected exception",
        attributes={
            "errorType": type(exc).__name__,
            "errorMessage": message,
            "errorLocation": location,
        },
    )


def run_pipeline(ctx: ExecutionContext) -> int:
    """按 DAG 顺序执行；遇 waiting checkpoint 停（10），failed 走 ReAct 回退或停（1）。"""
    from content.execution.pipeline.dag import DAG, STAGE_NAMES
    from content.execution.pipeline.metrics import _workflow_completion_issues, _write_workflow_execution_metrics
    from content.execution.pipeline.pipeline_control import _completed_until_revalidation, _managed_checkpoint_interruption_is_resumable, _mark_workflow_interrupted, _react_rewind, _recover_stale_agent_scheduler, _recover_stale_auto_research, _rewind_to, _stage_exception_fallback, _stop_at_until
    if ctx.baseline_packet is None or ctx.baseline_packet_path is None:
        raise RuntimeError("workflow run requires baseline freeze packet")
    state = load_workflow_state(ctx.execution_id)
    if _recover_stale_agent_scheduler(ctx, state):
        state = load_workflow_state(ctx.execution_id)
    if _recover_stale_auto_research(ctx, state):
        state = load_workflow_state(ctx.execution_id)
    if not ctx.entity_ids:
        state["status"] = "manual_required"
        state["failedObjects"] = ["frozen execution contains no coverage targets"]
        save_workflow_state(state)
        print("[geo-homepages] FAILED: frozen execution contains no coverage targets", file=sys.stderr)
        return 1
    state["status"] = "running"
    state["owner"] = "managed-local" if ctx.managed else "workflow-cli"
    if not state.get("startedAt") and not state.get("completed"):
        state["startedAt"] = store.now_iso()
    state["heartbeatAt"] = store.now_iso()
    state["nextAction"] = None
    state.pop("controllerYield", None)
    completed = set(state.get("completed") or [])
    ensure_execution_command_layout(ctx.execution_id, "execution")
    state["baselinePacketPath"] = str(ctx.baseline_packet_path)
    state["baselinePacketSummary"] = ctx.baseline_packet.get("summary") or {}
    save_workflow_state(state)
    # 批次级公共信息上提（规格 §4/§14）：任务定义快照 + 受控来源类目，不在对象目录重复。
    from content.execution.runtime_state import write_execution_runtime_state, write_source_catalog
    write_execution_runtime_state(ctx.execution_id, command="execution")
    write_source_catalog(ctx.execution_id)
    if ctx.until and ctx.until in completed:
        until_index = STAGE_NAMES.index(ctx.until)
        until_stage, until_kind, _until_runner = DAG[until_index]
        next_stage = STAGE_NAMES[until_index + 1] if until_index + 1 < len(STAGE_NAMES) else None
        if until_kind == CHECKPOINT:
            ok, issues = _completed_until_revalidation(ctx, until_stage)
            if ok:
                return _stop_at_until(ctx, state, completed, next_stage=next_stage)
            completed = _rewind_to(completed, until_stage)
            state = load_workflow_state(ctx.execution_id)
            state["completed"] = sorted(completed)
            state["waitingCheckpoint"] = None
            state["status"] = "running"
            state["nextAction"] = f"revalidate completed --until {until_stage}"
            state["failedObjects"] = list(issues)
            state["heartbeatAt"] = store.now_iso()
            save_workflow_state(state)
            print(
                f"[geo-homepages] revalidating completed --until {until_stage}: "
                f"{'; '.join(str(issue) for issue in issues[:5])}",
                flush=True,
            )
        else:
            return _stop_at_until(ctx, state, completed, next_stage=next_stage)
    # 外层循环支持 ReAct 回退后重新遍历 DAG
    for _ in range(MAX_REACT_REWINDS * len(DAG) + len(DAG) + 1):
        progressed = False
        for stage_index, (stage_name, kind, runner) in enumerate(DAG):
            if stage_name in completed:
                continue
            next_stage = STAGE_NAMES[stage_index + 1] if stage_index + 1 < len(STAGE_NAMES) else None
            try:
                result = runner(ctx)
            except KeyboardInterrupt as exc:
                interrupt_reason = str(exc).strip() or "KeyboardInterrupt"
                interrupted_state = load_workflow_state(ctx.execution_id)
                if _managed_checkpoint_interruption_is_resumable(
                    ctx,
                    interrupted_state,
                    stage=stage_name,
                ):
                    interrupted_state["completed"] = sorted(completed)
                    interrupted_state["interruptReason"] = interrupt_reason
                    interrupted_state["heartbeatAt"] = store.now_iso()
                    save_workflow_state(interrupted_state)
                else:
                    _mark_workflow_interrupted(
                        ctx,
                        stage=stage_name,
                        completed=completed,
                        reason=(
                            f"{stage_name}: interrupted; workflow stopped before "
                            f"checkpoint completion; {interrupt_reason}"
                        ),
                    )
                raise
            except DataIssueError as exc:
                result = StageResult(
                    ExecutionStage(stage_name),
                    kind,
                    StageStatus.FAILED,
                    f"{stage_name} blocked by typed data issue",
                    issue_records=list(exc.issues),
                    fallback_stage=_stage_exception_fallback(stage_name),
                )
            except Exception as exc:  # noqa: BLE001
                issue = _unexpected_stage_issue(stage_name, exc)
                result = StageResult(
                    ExecutionStage(stage_name),
                    kind,
                    StageStatus.FAILED,
                    f"{stage_name} raised {type(exc).__name__}",
                    issue_records=[issue],
                    fallback_stage=_stage_exception_fallback(stage_name),
                )
            # Stage runners may persist execution-state deltas such as
            # abandoned objects, content refs, agent summaries or retry
            # ledgers. Use the persisted state as the base before the outer
            # loop records stage status; otherwise an older in-memory copy can
            # silently erase object-level fast-fail decisions.
            state = load_workflow_state(ctx.execution_id)
            if result.status is StageStatus.WAITING:
                controller_yield = result.controller_yield
                state["completed"] = sorted(completed)
                state["waitingCheckpoint"] = stage_name
                state["status"] = "repairing" if controller_yield else "waiting_agent"
                state["heartbeatAt"] = store.now_iso()
                state["nextAction"] = result.checkpoint_hint
                state["failedObjects"] = list(result.issues or [])
                state["failedIssueRecords"] = [
                    issue.as_dict() for issue in result.issue_records
                ]
                if controller_yield:
                    state["controllerYield"] = {
                        "stage": stage_name,
                        "reason": result.message,
                        "hint": result.checkpoint_hint,
                        "yieldedAt": state["heartbeatAt"],
                    }
                else:
                    state.pop("controllerYield", None)
                save_workflow_state(state)
                _write_workflow_packet(
                    ctx,
                    stage_name=stage_name,
                    kind=kind,
                    result=result,
                    completed=sorted(completed),
                    next_stage=next_stage,
                    state=state,
                )
                print(f"[geo-homepages] PAUSED at checkpoint '{stage_name}'\n")
                print(result.checkpoint_hint)
                return 10
            if result.status is StageStatus.FAILED:
                completed, rewound = _react_rewind(ctx, state, completed, result)
                _write_workflow_packet(
                    ctx,
                    stage_name=stage_name,
                    kind=kind,
                    result=result,
                    completed=sorted(completed),
                    next_stage=next_stage,
                    state=state,
                )
                if rewound:
                    progressed = True
                    break  # 回 DAG 头重跑回退目标
                state["completed"] = sorted(completed)
                state["waitingCheckpoint"] = None
                state["lastFailedStage"] = stage_name
                state["status"] = "manual_required"
                state["failedObjects"] = list(result.issues)
                state["failedIssueRecords"] = [
                    issue.as_dict() for issue in result.issue_records
                ]
                state["nextAction"] = result.message
                save_workflow_state(state)
                print(f"[geo-homepages] FAILED at '{stage_name}': {result.message}", file=sys.stderr)
                return 1
            # done / skipped
            completed.add(stage_name)
            progressed = True
            state["completed"] = sorted(completed)
            state["waitingCheckpoint"] = None
            state["status"] = "running"
            state["heartbeatAt"] = store.now_iso()
            state["nextAction"] = next_stage
            state["failedObjects"] = []
            state["failedIssueRecords"] = []
            if str(state.get("lastFailedStage") or "") == stage_name:
                state.pop("lastFailedStage", None)
            retry_counts = state.setdefault("retryCounts", {})
            retry_counts.pop(stage_name, None)
            state["retryCounts"] = retry_counts
            infrastructure_retries = state.setdefault("infrastructureRetryCounts", {})
            infrastructure_retries.pop(stage_name, None)
            state["infrastructureRetryCounts"] = infrastructure_retries
            react_rewinds = state.setdefault("reactRewinds", {})
            react_rewinds.pop(stage_name, None)
            state["reactRewinds"] = react_rewinds
            save_workflow_state(state)
            _write_workflow_packet(
                ctx,
                stage_name=stage_name,
                kind=kind,
                result=result,
                completed=sorted(completed),
                next_stage=next_stage,
                state=state,
            )
            print(f"[geo-homepages] ✓ {stage_name} ({kind}): {result.message}")
            if ctx.until and stage_name == ctx.until:
                state = load_workflow_state(ctx.execution_id)
                return _stop_at_until(ctx, state, completed, next_stage=next_stage)
        else:
            # DAG 全遍历无 break → 全部 stage 完成
            # failedObjects 是「最近一次 stage 运行」的 issues 快照：写入路径要么
            # 立即 return（waiting rc=10 / failed rc=1），要么在该 stage 之后
            # done/skipped 时被清空。能走到这里说明所有 stage 都已收口，此时
            # 残留的 failedObjects 只可能是历史 waiting 轮的 stale 快照（全部
            # stage 被 completed 集合跳过、无 stage 触发清空的 resume 重放），
            # 不得据此把已收口的 workflow 打成 manual_required。留审计痕迹。
            stale_failed = [str(item) for item in (state.get("failedObjects") or []) if str(item).strip()]
            if stale_failed and not state.get("waitingCheckpoint"):
                state["staleFailedObjectsCleared"] = {
                    "count": len(stale_failed),
                    "sample": stale_failed[:10],
                    "clearedAt": store.now_iso(),
                }
                state["failedObjects"] = []
                state["failedIssueRecords"] = []
            _write_workflow_execution_metrics(ctx, state)
            completion_issues = _workflow_completion_issues(ctx, state)
            if completion_issues:
                state["completed"] = sorted(completed)
                state["waitingCheckpoint"] = None
                state["status"] = "manual_required"
                # gate issues 单独落 completionGateIssues；不得写回 failedObjects
                # 造成「workflow has failedObjects=N」自嵌套污染对象级明细。
                state["completionGateIssues"] = completion_issues
                state["nextAction"] = "workflow completion gate failed"
                state["heartbeatAt"] = store.now_iso()
                save_workflow_state(state)
                print(
                    f"[geo-homepages] FAILED completion gate — {ctx.execution_id} / {ctx.execution_id}",
                    file=sys.stderr,
                )
                for issue in completion_issues[:50]:
                    print(f"  - {issue}", file=sys.stderr)
                return 1
            print(f"[geo-homepages] WORKFLOW COMPLETE — {ctx.execution_id} / {ctx.execution_id}")
            state["status"] = "succeeded"
            state["heartbeatAt"] = store.now_iso()
            state["nextAction"] = None
            state.pop("lastFailedStage", None)
            state.pop("interruptReason", None)
            state.pop("completionGateIssues", None)
            state["failedIssueRecords"] = []
            save_workflow_state(state)
            return 0
        if not progressed:
            break
    print(f"[geo-homepages] FAILED: ReAct 回退耗尽未收敛 — {ctx.execution_id} / {ctx.execution_id}", file=sys.stderr)
    return 1
