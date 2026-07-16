"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.baseline_packet import load_baseline_packet
from content.execution.coverage import coverage_entity_ids
from content.execution.support import DEFAULT_CURSOR_STARTUP_TIMEOUT_SECONDS, DEFAULT_MANAGED_AGENT_PROVIDER, ExecutionContext, MANAGED_AGENT_PROVIDERS, Path, _normalize_managed_agent_provider, _resolve_managed_model, _state_path, argparse, json, load_workflow_state, save_workflow_state, store, sys

def handle_run(args: argparse.Namespace) -> None:
    from content.execution.agent.agent_managed import run_managed_pipeline
    from content.execution.agent.agent_runner import _managed_local_workspace_guard
    from content.execution.pipeline.dag import STAGE_NAMES
    from content.execution.pipeline.pipeline_control import _workflow_signal_guard
    from content.execution.pipeline.pipeline_run import run_pipeline
    from content.execution.recovery.post_recovery import _purge_author_queue_for_stale_workflow
    from content.execution.pipeline.preflight import _managed_preflight, _write_managed_env_ready_report
    from content.execution.recovery.stage_reset import _clear_manual_repair_rewind_if_resuming, reset_stage_retries
    execution_id = args.execution_id
    if not execution_id:
        print("[execution run] ERROR: executionId is required", file=sys.stderr)
        raise SystemExit(2)
    spec = store.load_spec(execution_id)
    entity_ids = coverage_entity_ids(spec)
    if not entity_ids:
        print(f"[geo-homepages] ERROR: {execution_id} 无 coverageTargets，无实体可编排", file=sys.stderr)
        raise SystemExit(2)
    managed = bool(getattr(args, "managed", False))
    agent_provider = _normalize_managed_agent_provider(getattr(args, "agent_provider", None))
    managed_model = _resolve_managed_model(agent_provider, getattr(args, "model", None))
    if managed:
        preflight_issues = _managed_preflight(execution_id, spec, args)
        if preflight_issues:
            print("[geo-homepages] managed preflight FAILED:", file=sys.stderr)
            for issue in preflight_issues:
                print(f"  - {issue}", file=sys.stderr)
            raise SystemExit(2)
    reset_stage = str(getattr(args, "reset_stage_retries", None) or "").strip()
    reset_reason = str(getattr(args, "reset_stage_reason", None) or "").strip()
    if reset_stage and not reset_reason:
        print(
            "[geo-homepages] ERROR: --reset-stage-retries requires --reset-stage-reason",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if args.reset_state:
        p = _state_path(execution_id)
        if p.exists():
            p.unlink()
            print(f"[geo-homepages] reset workflow state: {p}")
        _purge_author_queue_for_stale_workflow(
            ExecutionContext(
                execution_id=execution_id,
                entity_ids=[],
                spec={},
            ),
            reason="reset_state",
        )
    elif reset_stage:
        recovery = reset_stage_retries(
            execution_id,
            stage=reset_stage,
            reason=reset_reason,
            reset_react_rewinds=bool(getattr(args, "reset_react_rewinds", False)),
        )
        print(json.dumps({"stageRecovery": recovery}, ensure_ascii=False))
    elif bool(getattr(args, "resume", False)):
        _clear_manual_repair_rewind_if_resuming(execution_id)
    until = args.until if getattr(args, "until", None) else None
    if until and until not in STAGE_NAMES:
        print(f"[geo-homepages] ERROR: --until 须为 {STAGE_NAMES}", file=sys.stderr)
        raise SystemExit(2)
    try:
        baseline_packet_path, baseline_packet = load_baseline_packet(
            execution_id,
            Path(args.baseline_packet) if getattr(args, "baseline_packet", None) else None,
        )
    except RuntimeError as exc:
        print(f"[geo-homepages] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    ctx = ExecutionContext(
        execution_id=execution_id, entity_ids=entity_ids,
        spec=spec, baseline_packet=baseline_packet, baseline_packet_path=baseline_packet_path,
        until=until,
        managed=managed,
        runtime=str(getattr(args, "runtime", "local") or "local"),
        max_workers=int(getattr(args, "max_workers", 3) or 3),
        model=managed_model,
        agent_provider=agent_provider,
        release_only=bool(getattr(args, "release_only", False)),
        agent_runner=getattr(args, "agent_runner", None),
        force_clean_workspace_agent_state=bool(
            getattr(args, "force_clean_workspace_agent_state", False)
        ),
    )
    if managed:
        _write_managed_env_ready_report(ctx, args)
    try:
        with _workflow_signal_guard(ctx):
            if managed:
                from core import ops_governance as og
                with og.controller_lease(execution_id) as controller:
                    setattr(ctx, "controller_run_id", controller.get("controllerRunId"))
                    state = load_workflow_state(execution_id)
                    state["controller"] = {
                        "controllerRunId": controller.get("controllerRunId"),
                        "role": controller.get("role"),
                        "pid": controller.get("pid"),
                        "startedAt": controller.get("startedAt"),
                    }
                    state["heartbeatAt"] = store.now_iso()
                    save_workflow_state(state)
                    with _managed_local_workspace_guard(ctx):
                        code = run_managed_pipeline(ctx)
            else:
                code = run_pipeline(ctx)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except RuntimeError as exc:
        print(f"[geo-homepages] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    if code != 0:
        raise SystemExit(code)

def register_run_parser(sub: argparse._SubParsersAction) -> None:
    from content.execution.pipeline.dag import STAGE_NAMES
    pr = sub.add_parser("run", help="无人值守 workflow 编排：单模式 DAG / fanout 分区叶子调度")
    pr.add_argument(
        "--mode",
        choices=["single", "fanout"],
        default="single",
        help="single=会话内单 agent 跑 DAG（默认，现状）；fanout=按冻结计划分区/叶子调度",
    )
    pr.add_argument("--execution-id", help="single 模式的唯一 executionId")
    pr.add_argument("--plan", help="fanout 模式：冻结计划 planId")
    pr.add_argument(
        "--strategy",
        choices=["by-partition", "flat-pool", "by-leaf", "by-partition-size"],
        help="fanout 模式：拉起策略（默认取计划 defaults.strategy）",
    )
    pr.add_argument("--concurrency", type=int, help="fanout 模式：并发度（设 1 即退化等价 single）")
    pr.add_argument("--partition-size", dest="partition_size", type=int, help="fanout by-partition-size 策略：每块叶子数")
    pr.add_argument("--resume", action="store_true",
                    help="从上次 checkpoint 继续（默认即 resume 语义：跳过已完成 stage）")
    pr.add_argument("--reset-state", dest="reset_state", action="store_true",
                    help="清空 workflow_state 从头跑")
    pr.add_argument(
        "--reset-stage-retries",
        dest="reset_stage_retries",
        choices=STAGE_NAMES,
        help="审计式重置一个 stage 及其下游 retry ledger，并从该 stage 继续",
    )
    pr.add_argument(
        "--reset-stage-reason",
        dest="reset_stage_reason",
        help="stage recovery 的必填根因与修复说明",
    )
    pr.add_argument(
        "--reset-react-rewinds",
        dest="reset_react_rewinds",
        action="store_true",
        help="同时重置该 stage 及下游 ReAct rewind 计数（仅质量合同代码修复使用）",
    )
    pr.add_argument(
        "--baseline-packet",
        help="baseline freeze packet path（默认 task/_shared/baseline_freeze_packet.json）",
    )
    pr.add_argument("--until", help=f"跑到指定 stage 即停: {STAGE_NAMES}")
    pr.add_argument("--managed", action="store_true", help="自动消费全部 Agent checkpoint 并续跑")
    pr.add_argument("--runtime", choices=["local", "cloud"], default="local")
    pr.add_argument("--max-workers", dest="max_workers", type=int, default=10)
    pr.add_argument(
        "--agent-provider",
        dest="agent_provider",
        choices=sorted(MANAGED_AGENT_PROVIDERS),
        default=_normalize_managed_agent_provider(DEFAULT_MANAGED_AGENT_PROVIDER),
        help="managed checkpoint 的真实 Agent 执行面：cursor_sdk 或 codex_cli",
    )
    pr.add_argument(
        "--model",
        default=None,
        help="Agent 模型；不传时按 provider 选择默认模型",
    )
    pr.add_argument(
        "--startup-timeout-seconds",
        dest="startup_timeout_seconds",
        type=float,
        default=DEFAULT_CURSOR_STARTUP_TIMEOUT_SECONDS,
        help="managed Cursor startup probe 超时时间；cloud 冷启动放量可调大",
    )
    pr.add_argument(
        "--force-clean-workspace-agent-state",
        dest="force_clean_workspace_agent_state",
        action="store_true",
        help=(
            "托管 local 运行前清理同 workspace 的旧数据 workflow/cursor bridge；"
            "默认只检测并失败快返"
        ),
    )
    pr.add_argument(
        "--release-only",
        dest="release_only",
        action="store_true",
        help="仅组装隔离 release，不写 publish/ 或运行库（当前 managed 正式模式要求）",
    )
    pr.set_defaults(handler=handle_run)
