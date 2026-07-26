"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
import os
import traceback

from core.control_types import ExecutionStage, ExecutionStateStatus, StageStatus
from core.runtime_observability import (
    DataRuntimeLogResource,
    DataRuntimeLogger,
    default_data_exception_code,
)
from content.execution.support import CHECKPOINT, DataIssueCode, DataIssueError, DataIssueStage, DataRecoveryAction, ExecutionContext, MAX_REACT_REWINDS, StageResult, _active_spec, _write_execution_packet, data_issue, ensure_execution_command_layout, load_execution_state, save_execution_state, store, sys


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
        message="execution stage raised an unexpected exception",
        attributes={
            "errorType": type(exc).__name__,
            "errorMessage": message,
            "errorLocation": location,
        },
    )

def _execution_runtime_logger(ctx: ExecutionContext) -> DataRuntimeLogger:
    from core.paths import OUTPUT_ROOT
    from quwoquan_ops.cli.lib.observability import write_run_manifest

    environment = os.environ.get("APP_ENV", "alpha").strip() or "alpha"
    observability_root = (
        OUTPUT_ROOT / "env" / "repo" / "observability" / ctx.execution_id
    )
    write_run_manifest(
        observability_root,
        env_name="repo",
        run_id=ctx.execution_id,
        command="task execute",
        target=ctx.execution_id,
        report_dir=OUTPUT_ROOT / "data" / "tasks" / ctx.execution_id,
    )
    return DataRuntimeLogger(
        observability_root / "logs" / "data" / "runtime.log",
        resource=DataRuntimeLogResource(
            environment=environment,
            component="execution-controller",
        ),
        execution_id=ctx.execution_id,
    )


def _record_stage_runtime(
    logger: DataRuntimeLogger,
    *,
    stage_name: str,
    kind: str,
    result: StageResult,
) -> None:
    attributes = {
        "stage": stage_name,
        "outcome": str(result.status),
        "gate": kind,
    }
    try:
        logger.runtime(
            event=stage_name,
            result=str(result.status),
            message="data execution stage completed",
            attributes=attributes,
        )
        if result.status is StageStatus.FAILED:
            logger.exception(
                error_code=default_data_exception_code(),
                message="data execution stage failed",
                failure_point=stage_name,
                attributes=attributes,
            )
    except OSError as exc:
        print(f"[task execute] runtime diagnostic write failed: {exc}", file=sys.stderr)


def run_controller(ctx: ExecutionContext) -> int:
    """按 DAG 顺序执行；遇 waiting checkpoint 停（10），failed 走 ReAct 回退或停（1）。"""
    from content.execution.controller.dag import DAG, STAGE_NAMES
    from content.execution.controller.completion import execution_completion_issues
    from content.execution.controller.metrics import _write_execution_metrics
    from content.execution.controller.control import _completed_until_revalidation, _managed_checkpoint_interruption_is_resumable, _mark_execution_interrupted, _react_rewind, _recover_stale_agent_scheduler, _recover_stale_auto_research, _rewind_to, _stage_exception_fallback, _stop_at_until
    if ctx.baseline_packet is None or ctx.baseline_packet_path is None:
        raise RuntimeError("execution run requires baseline freeze packet")
    runtime_logger = _execution_runtime_logger(ctx)
    try:
        runtime_logger.runtime(
            event="execution_started",
            result="started",
            message="data execution controller started",
            attributes={"stage": "execution", "outcome": "started", "gate": "controller"},
        )
    except OSError as exc:
        print(f"[task execute] runtime diagnostic write failed: {exc}", file=sys.stderr)
    state = load_execution_state(ctx.execution_id)
    if _recover_stale_agent_scheduler(ctx, state):
        state = load_execution_state(ctx.execution_id)
    if _recover_stale_auto_research(ctx, state):
        state = load_execution_state(ctx.execution_id)
    if not ctx.entity_ids:
        state.status = ExecutionStateStatus.MANUAL_REQUIRED
        state.failed_objects = ["frozen execution contains no coverage targets"]
        save_execution_state(state)
        print("[task execute] FAILED: frozen execution contains no coverage targets", file=sys.stderr)
        return 1
    state.status = ExecutionStateStatus.RUNNING
    state.owner = "managed-local" if ctx.managed else "execution-cli"
    if not state.started_at and not state.completed:
        state.started_at = store.now_iso()
    state.heartbeat_at = store.now_iso()
    state.next_action = None
    state.controller_yield = None
    completed = set(state.completed or [])
    ensure_execution_command_layout(ctx.execution_id, "execution")
    state.baseline_packet_path = str(ctx.baseline_packet_path)
    state.baseline_packet_summary = ctx.baseline_packet.get("summary") or {}
    save_execution_state(state)
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
            state = load_execution_state(ctx.execution_id)
            state.completed = sorted(completed)
            state.waiting_checkpoint = None
            state.status = ExecutionStateStatus.RUNNING
            state.next_action = f"revalidate completed --until {until_stage}"
            state.failed_objects = list(issues)
            state.heartbeat_at = store.now_iso()
            save_execution_state(state)
            print(
                f"[task execute] revalidating completed --until {until_stage}: "
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
                interrupted_state = load_execution_state(ctx.execution_id)
                if _managed_checkpoint_interruption_is_resumable(
                    ctx,
                    interrupted_state,
                    stage=stage_name,
                ):
                    interrupted_state.completed = sorted(completed)
                    interrupted_state.interrupt_reason = interrupt_reason
                    interrupted_state.heartbeat_at = store.now_iso()
                    save_execution_state(interrupted_state)
                else:
                    _mark_execution_interrupted(
                        ctx,
                        stage=stage_name,
                        completed=completed,
                        reason=(
                            f"{stage_name}: interrupted; execution stopped before "
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
            state = load_execution_state(ctx.execution_id)
            _record_stage_runtime(
                runtime_logger,
                stage_name=stage_name,
                kind=kind,
                result=result,
            )
            if result.status is StageStatus.WAITING:
                controller_yield = result.controller_yield
                state.completed = sorted(completed)
                state.waiting_checkpoint = stage_name
                state.status = (
                    ExecutionStateStatus.REPAIRING
                    if controller_yield
                    else ExecutionStateStatus.WAITING_AGENT
                )
                state.heartbeat_at = store.now_iso()
                state.next_action = result.checkpoint_hint
                state.failed_objects = list(result.issues or [])
                state.failed_issue_records = [
                    issue.as_dict() for issue in result.issue_records
                ]
                if controller_yield:
                    state.controller_yield = {
                        "stage": stage_name,
                        "reason": result.message,
                        "hint": result.checkpoint_hint,
                        "yieldedAt": state.heartbeat_at,
                    }
                else:
                    state.controller_yield = None
                save_execution_state(state)
                _write_execution_packet(
                    ctx,
                    stage_name=stage_name,
                    kind=kind,
                    result=result,
                    completed=sorted(completed),
                    next_stage=next_stage,
                    state=state,
                )
                print(f"[task execute] PAUSED at checkpoint '{stage_name}'\n")
                print(result.checkpoint_hint)
                return 10
            if result.status is StageStatus.FAILED:
                completed, rewound = _react_rewind(ctx, state, completed, result)
                _write_execution_packet(
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
                state.completed = sorted(completed)
                state.waiting_checkpoint = None
                state.last_failed_stage = stage_name
                state.status = ExecutionStateStatus.MANUAL_REQUIRED
                state.failed_objects = list(result.issues)
                state.failed_issue_records = [
                    issue.as_dict() for issue in result.issue_records
                ]
                state.next_action = result.message
                save_execution_state(state)
                print(f"[task execute] FAILED at '{stage_name}': {result.message}", file=sys.stderr)
                return 1
            # done / skipped
            completed.add(stage_name)
            progressed = True
            state.completed = sorted(completed)
            state.waiting_checkpoint = None
            state.status = ExecutionStateStatus.RUNNING
            state.heartbeat_at = store.now_iso()
            state.next_action = next_stage
            state.failed_objects = []
            state.failed_issue_records = []
            if str(state.last_failed_stage or "") == stage_name:
                state.last_failed_stage = None
            retry_counts = state.retry_counts
            retry_counts.pop(stage_name, None)
            state.retry_counts = retry_counts
            infrastructure_retries = state.infrastructure_retry_counts
            infrastructure_retries.pop(stage_name, None)
            state.infrastructure_retry_counts = infrastructure_retries
            react_rewinds = state.react_rewinds
            react_rewinds.pop(stage_name, None)
            state.react_rewinds = react_rewinds
            save_execution_state(state)
            _write_execution_packet(
                ctx,
                stage_name=stage_name,
                kind=kind,
                result=result,
                completed=sorted(completed),
                next_stage=next_stage,
                state=state,
            )
            print(f"[task execute] ✓ {stage_name} ({kind}): {result.message}")
            if ctx.until and stage_name == ctx.until:
                state = load_execution_state(ctx.execution_id)
                return _stop_at_until(ctx, state, completed, next_stage=next_stage)
        else:
            # DAG 全遍历无 break → 全部 stage 完成
            # failedObjects 是「最近一次 stage 运行」的 issues 快照：写入路径要么
            # 立即 return（waiting rc=10 / failed rc=1），要么在该 stage 之后
            # done/skipped 时被清空。能走到这里说明所有 stage 都已收口，此时
            # 残留的 failedObjects 只可能是历史 waiting 轮的 stale 快照（全部
            # stage 被 completed 集合跳过、无 stage 触发清空的 resume 重放），
            # 不得据此把已收口的 execution 打成 manual_required。留审计痕迹。
            stale_failed = [str(item) for item in (state.failed_objects or []) if str(item).strip()]
            if stale_failed and not state.waiting_checkpoint:
                state.failed_objects = []
                state.failed_issue_records = []
            _write_execution_metrics(ctx, state)
            completion_issues = execution_completion_issues(ctx, state)
            if completion_issues:
                state.completed = sorted(completed)
                state.waiting_checkpoint = None
                state.status = ExecutionStateStatus.MANUAL_REQUIRED
                # gate issues 单独落 completionGateIssues；不得写回 failedObjects
                # 造成「execution has failedObjects=N」自嵌套污染对象级明细。
                state.completion_gate_issues = completion_issues
                state.next_action = "execution completion gate failed"
                state.heartbeat_at = store.now_iso()
                save_execution_state(state)
                print(
                    f"[task execute] FAILED completion gate — {ctx.execution_id} / {ctx.execution_id}",
                    file=sys.stderr,
                )
                for issue in completion_issues[:50]:
                    print(f"  - {issue}", file=sys.stderr)
                return 1
            print(f"[task execute] EXECUTION COMPLETE — {ctx.execution_id} / {ctx.execution_id}")
            state.status = ExecutionStateStatus.SUCCEEDED
            state.heartbeat_at = store.now_iso()
            state.next_action = None
            state.last_failed_stage = None
            state.interrupt_reason = None
            state.completion_gate_issues = []
            state.failed_issue_records = []
            save_execution_state(state)
            return 0
        if not progressed:
            break
    print(f"[task execute] FAILED: ReAct 回退耗尽未收敛 — {ctx.execution_id} / {ctx.execution_id}", file=sys.stderr)
    return 1
