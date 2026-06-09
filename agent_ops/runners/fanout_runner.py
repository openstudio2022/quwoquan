"""fan-out 外部多 worker runner（cursor-sdk）：把 object_queue 叶子 job 拉起为 cloud agent。

属外部运维（agent_ops），不违反 quwoquan_data scripts 目录军规；与 `qwq-data task run --mode fanout`
互补：dispatch 负责建 task/batch + enqueue 叶子，runner 负责把 CHECKPOINT 接缝替换为
「lease packet → cloud agent 创作 → ref_review_gate → complete/fail」。

两类云端角色（与 fanout_strategies by-partition 设计一致：每分区一个 orchestrator agent + 叶子 subagent）：
- orchestrator（分区级）：先推进本分区 DAG 的三个 checkpoint —— download_plan（真实检索来源+真实 CC 图）/
  build_homepage（按 SOP 写实体主页三件套）/ content_plan（证据驱动定篇目），直到 produce_compose
  物化出每个叶子的 writing_pack + prompt。它只跑 `qwq-data data workflow run ... --until produce_compose`
  并按每个 CHECKPOINT 的 hint 做真实语义加工，不在本 runner 里拼任何成文句子。
- leaf subagent（叶子级）：从 object_queue lease author job，读 prompt/writing_pack/来源真创作正文，
  自跑单 ref review 门，complete/fail 回写。

SDK 守约束（见 .cursor skills/sdk）：
- 每 agent = 独立 cloud agent；同 agent 并发 run 会 409，高并发=多 agent（多 assignment）。
- 先设 spend limit；区分启动失败（CursorAgentError，exit1）与运行失败（result.status==error，exit2）。
- isRetryable / retry_after 指数退避；进程重启用 Agent.resume。
- 终态回写 object-queue complete|fail；用量回写 object-queue usage。

可测试性：agent_runner / orchestrator_runner 均可注入（默认用 cursor_sdk）；测试注入 mock，
不依赖真实云端，断言 orchestrate→checkpoint 校验、lease→complete 回写、startup vs run 失败分流、usage 回写。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

# 接入 quwoquan_data scripts（object_queue / fanout_plan / strategies）。
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_SCRIPTS = _REPO_ROOT / "quwoquan_data" / "scripts"
_DATA_ROOT = _REPO_ROOT / "quwoquan_data"
for _p in (_DATA_ROOT, _DATA_SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from _common import fanout_plan as fp  # noqa: E402
from _common import fanout_strategies as fs  # noqa: E402
from task import object_queue as oq  # noqa: E402

# startup 失败/运行失败的退避基数（秒）。
STARTUP_BACKOFF_BASE = 5
MAX_STARTUP_RETRIES = 3

# 分区 orchestrator 必须推进到位的三个 checkpoint（plan Phase C 缺口）。
ORCHESTRATOR_CHECKPOINTS = ("download_plan", "build_homepage", "content_plan")
# orchestrator 推进到该 stage 即停：此时每个叶子的 writing_pack + prompt 已物化，
# produce_author（叶子）交给 leaf subagent，故停在 produce_compose 之后、produce_author 之前。
ORCHESTRATOR_UNTIL = "produce_compose"


@dataclass
class RunOutcome:
    """agent_runner 的统一返回（屏蔽 SDK 细节）。

    started=False 表示从未执行（CursorAgentError；auth/config/network）；
    started=True + status 表示执行后的终态（finished/error）。
    """
    started: bool
    status: str = "finished"   # finished | error
    passed: bool = False        # ref_review_gate.passed
    tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    fingerprint: str | None = None
    retryable: bool = False
    agent_id: str | None = None
    run_id: str | None = None


AgentRunner = Callable[[Mapping[str, Any]], RunOutcome]
# orchestrator 与 leaf 用同一 RunOutcome 抽象（屏蔽 SDK 细节），便于注入 mock。
OrchestratorRunner = Callable[[Mapping[str, Any]], RunOutcome]


@dataclass
class OrchestrationResult:
    """一个分区 orchestrator 拉起的结果。

    reached=True 表示 ORCHESTRATOR_CHECKPOINTS 三个 checkpoint 都已在 workflow_state 标记完成，
    叶子 author job 的 writing_pack/prompt 已具备，可分发 leaf subagent。
    """
    task_id: str
    batch_id: str
    started: bool
    reached: bool
    missing: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class WorkerStats:
    worker: str
    leased: int = 0
    completed: int = 0
    failed: int = 0
    startup_failures: int = 0
    orchestrated: int = 0
    orchestration_failed: int = 0
    refs_completed: list[str] = field(default_factory=list)
    refs_failed: list[str] = field(default_factory=list)
    orchestrations: list[OrchestrationResult] = field(default_factory=list)


def _build_prompt(packet: Mapping[str, Any]) -> str:
    """把 lease packet 渲染为 cloud agent 的执行 prompt（含执行合约 + Ralph 出口门）。"""
    contract = packet.get("executionContract") or {}
    return (
        f"你是单篇内容创作 Subagent。严格隔离：{packet.get('isolation')}\n"
        f"目标 ref: {packet.get('ref')} / stage: {packet.get('stage')}\n"
        f"执行合约（必须全部满足）：\n{json.dumps(contract, ensure_ascii=False, indent=2)}\n"
        f"Ralph 自纠环：{packet.get('ralphLoop')}\n"
        f"完成判据：ref_review_gate.passed == true（reviewDecision == approved）。"
    )


RUNTIME_LOCAL = "local"
RUNTIME_CLOUD = "cloud"
VALID_RUNTIMES = (RUNTIME_LOCAL, RUNTIME_CLOUD)


def _build_agent_options(
    *,
    api_key: str,
    model: str,
    runtime: str,
    cwd: str | None,
    repos: list[dict[str, Any]] | None,
):
    """构造 AgentOptions：local 用本机 cwd（直接写本仓库），cloud 用 clone 的 repos。

    runtime 显式二选一（SDK trap #1：不显式设会静默退化为 local）。
    """
    from cursor_sdk import AgentOptions, CloudAgentOptions, LocalAgentOptions  # type: ignore

    if runtime == RUNTIME_LOCAL:
        return AgentOptions(
            api_key=api_key,
            model=model,
            local=LocalAgentOptions(cwd=cwd or os.getcwd()),
        )
    return AgentOptions(
        api_key=api_key,
        model=model,
        cloud=CloudAgentOptions(repos=repos or []),
    )


def default_agent_runner(
    packet: Mapping[str, Any],
    *,
    api_key: str | None = None,
    model: str = "composer-2.5",
    runtime: str = RUNTIME_CLOUD,
    cwd: str | None = None,
    repos: list[dict[str, Any]] | None = None,
    spend_limit_usd: float | None = None,
) -> RunOutcome:
    """默认 leaf runner：用 cursor-sdk 起一个 agent（local 在本机 / cloud 在托管 VM）跑单 ref 创作。

    注意：真正的 ref_review_gate.passed 由 agent 在仓库内跑
    `qwq-data object-queue complete/fail` 自行回写更稳妥；此默认 runner 作为兜底，
    依据 run 终态返回 RunOutcome，passed 由调用方再校验 gate 文件。
    """
    try:
        from cursor_sdk import Agent, CursorAgentError  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return RunOutcome(started=False, error=f"cursor_sdk unavailable: {exc}", retryable=False)

    key = api_key or os.environ.get("CURSOR_API_KEY")
    if not key:
        return RunOutcome(started=False, error="CURSOR_API_KEY missing", retryable=False)
    prompt = _build_prompt(packet)
    try:
        opts = _build_agent_options(api_key=key, model=model, runtime=runtime, cwd=cwd, repos=repos)
        result = Agent.prompt(prompt, opts)  # 一次性：起→跑→释放
    except CursorAgentError as err:  # 启动失败：从未执行
        return RunOutcome(
            started=False,
            error=getattr(err, "message", str(err)),
            retryable=bool(getattr(err, "is_retryable", False)),
        )
    status = getattr(result, "status", "error")
    return RunOutcome(
        started=True,
        status="finished" if status == "finished" else "error",
        passed=status == "finished",
        agent_id=getattr(result, "agent_id", None),
        run_id=getattr(result, "id", None),
        error=None if status == "finished" else f"run status={status}",
    )


def build_orchestrator_packet(
    target: Mapping[str, Any],
    *,
    partition_path: list[str] | None = None,
    refs: list[str] | None = None,
    until: str = ORCHESTRATOR_UNTIL,
) -> dict[str, Any]:
    """分区 orchestrator 的 handoff packet：只注入「命令 + checkpoint 清单 + 执行合约 + Ralph 出口」。

    不含任何成文句子；语义加工（检索真实来源/写主页/定篇目）由 cloud agent 按 workflow run 打印的
    每个 CHECKPOINT hint 完成。
    """
    task_id = str(target["taskId"])
    batch_id = str(target["batchId"])
    resume_cmd = (
        f"qwq-data data workflow run --task {task_id} --batch {batch_id} "
        f"--until {until} --resume"
    )
    return {
        "schemaVersion": "quwoquan_data.orchestrator_packet/1",
        "role": "orchestrator",
        "taskId": task_id,
        "batchId": batch_id,
        "partitionPath": list(partition_path or []),
        "refs": list(refs or []),
        "checkpoints": list(ORCHESTRATOR_CHECKPOINTS),
        "until": until,
        "executionContract": {
            "command": resume_cmd,
            "preflight": [
                f"若缺 baseline freeze packet 先跑 qwq-data data baseline --task {task_id}",
            ],
            "checkpointSemantics": {
                "download_plan": "按 hint 为每个 coverage 实体真实检索 ≥2 个可消费来源（URL+正文 body，含图填真实 CC imageUrls），写 source_plan.json，禁止编造来源/纯色块图",
                "build_homepage": "按 entity_page_input.json 契约与 SOP 写 page.md(≥800字)+_entity.json+manifest.json，禁止模板骨架/整段复读",
                "content_plan": "通读已下载来源，证据驱动写 content_plan_packet.json + register + brief，单篇唯一 writingIntent，禁止预置营销 ref",
            },
            "completionConditions": [
                f"workflow_state.completed ⊇ {list(ORCHESTRATOR_CHECKPOINTS)}",
                f"workflow run 推进到 --until {until}（每叶子 3.compose/writing_pack.json + prompt.md 已物化）",
            ],
            "forbidden": [
                "在脚本或正文里拼接固定句式/模板骨架",
                "伪造来源正文或用纯色块冒充 CC 图",
                "为过门注入噪声（如稿序编号）",
            ],
        },
        "ralphLoop": (
            "循环跑 workflow run --resume：退出码 10=CHECKPOINT，按打印 hint 做真实语义加工后再 resume；"
            "退出码 1 且有 fallbackStage 则按其回退重做；退出码 0=已达 until。不得假装完成。"
        ),
        "isolation": "partition-orchestrator: 只操作本分区 task/batch；叶子正文创作交给 leaf subagent，不在此越权写 article",
    }


def _build_orchestrator_prompt(packet: Mapping[str, Any]) -> str:
    contract = packet.get("executionContract") or {}
    return (
        f"你是分区编排 Orchestrator。严格隔离：{packet.get('isolation')}\n"
        f"分区 task: {packet.get('taskId')} / batch: {packet.get('batchId')}\n"
        f"必须推进到位的 checkpoint: {packet.get('checkpoints')}（推进到 --until {packet.get('until')}）\n"
        f"执行合约（必须全部满足）：\n{json.dumps(contract, ensure_ascii=False, indent=2)}\n"
        f"Ralph 自纠环：{packet.get('ralphLoop')}\n"
        f"完成判据：workflow_state.completed 覆盖全部 checkpoint，且每个叶子的 writing_pack/prompt 已物化。"
    )


def default_orchestrator_runner(
    packet: Mapping[str, Any],
    *,
    api_key: str | None = None,
    model: str = "composer-2.5",
    runtime: str = RUNTIME_CLOUD,
    cwd: str | None = None,
    repos: list[dict[str, Any]] | None = None,
    spend_limit_usd: float | None = None,
) -> RunOutcome:
    """默认 orchestrator runner：用 cursor-sdk 起 agent（local/cloud）推进本分区 checkpoint。

    与 leaf runner 同构；真正的 checkpoint 完成由调用方读 workflow_state 校验（orchestrate_partition）。
    """
    try:
        from cursor_sdk import Agent, CursorAgentError  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return RunOutcome(started=False, error=f"cursor_sdk unavailable: {exc}", retryable=False)

    key = api_key or os.environ.get("CURSOR_API_KEY")
    if not key:
        return RunOutcome(started=False, error="CURSOR_API_KEY missing", retryable=False)
    prompt = _build_orchestrator_prompt(packet)
    try:
        opts = _build_agent_options(api_key=key, model=model, runtime=runtime, cwd=cwd, repos=repos)
        result = Agent.prompt(prompt, opts)
    except CursorAgentError as err:
        return RunOutcome(
            started=False,
            error=getattr(err, "message", str(err)),
            retryable=bool(getattr(err, "is_retryable", False)),
        )
    status = getattr(result, "status", "error")
    return RunOutcome(
        started=True,
        status="finished" if status == "finished" else "error",
        passed=status == "finished",
        agent_id=getattr(result, "agent_id", None),
        run_id=getattr(result, "id", None),
        error=None if status == "finished" else f"run status={status}",
    )


def _missing_orchestrator_checkpoints(task_id: str, batch_id: str) -> list[str]:
    """读 workflow_state，返回尚未完成的 orchestrator checkpoint（真相源校验，不靠 agent 自述）。"""
    try:
        from task.run import load_workflow_state  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        return [f"(cannot load workflow state: {exc})"]
    state = load_workflow_state(task_id, batch_id)
    completed = set(state.get("completed") or [])
    return [c for c in ORCHESTRATOR_CHECKPOINTS if c not in completed]


def orchestrate_partition(
    target: Mapping[str, Any],
    *,
    orchestrator_runner: OrchestratorRunner,
    partition_path: list[str] | None = None,
    refs: list[str] | None = None,
    until: str = ORCHESTRATOR_UNTIL,
    verify_checkpoints: bool = True,
) -> OrchestrationResult:
    """拉起一个分区 orchestrator，推进三个 checkpoint，并以 workflow_state 校验是否到位。"""
    task_id = str(target["taskId"])
    batch_id = str(target["batchId"])
    packet = build_orchestrator_packet(target, partition_path=partition_path, refs=refs, until=until)
    outcome = orchestrator_runner(packet)
    if not outcome.started:
        return OrchestrationResult(
            task_id=task_id, batch_id=batch_id, started=False, reached=False,
            missing=list(ORCHESTRATOR_CHECKPOINTS), error=f"startup: {outcome.error}",
        )
    if not verify_checkpoints:
        # dry-run / 自检：不读真相源，按 run 终态判定。
        reached = outcome.status == "finished" and outcome.passed
        return OrchestrationResult(
            task_id=task_id, batch_id=batch_id, started=True, reached=reached,
            missing=[] if reached else list(ORCHESTRATOR_CHECKPOINTS),
            error=outcome.error,
        )
    missing = _missing_orchestrator_checkpoints(task_id, batch_id)
    return OrchestrationResult(
        task_id=task_id, batch_id=batch_id, started=True, reached=not missing,
        missing=missing,
        error=outcome.error if missing else None,
    )


def _process_job(
    target: Mapping[str, Any],
    job: Mapping[str, Any],
    *,
    agent_runner: AgentRunner,
    stats: WorkerStats,
) -> None:
    task_id = str(target["taskId"])
    batch_id = str(target["batchId"])
    job_id = str(job["jobId"])
    lease = str(job["lease"])
    ref = str(job["ref"])
    packet = oq.build_lease_packet(job)
    outcome = agent_runner(packet)

    if outcome.tokens or outcome.cost_usd:
        usage_job = oq.record_usage(task_id, batch_id, job_id, lease, tokens=outcome.tokens, cost_usd=outcome.cost_usd)
        # 用量超预算时 record_usage 已强制 dead 并清空 lease：不能再 complete/fail（lease 失配）。
        if usage_job.get("state") in (oq.STATE_DEAD, oq.STATE_FAILED) or usage_job.get("lease") != lease:
            stats.failed += 1
            stats.refs_failed.append(ref)
            return

    if not outcome.started:
        # 启动失败：从未执行，按 retryable 退避；fail_job 走退避/dead 状态机。
        stats.startup_failures += 1
        oq.fail_job(task_id, batch_id, job_id, lease, error=f"startup: {outcome.error}")
        return

    if outcome.status == "finished" and outcome.passed:
        oq.complete_job(task_id, batch_id, job_id, lease)
        stats.completed += 1
        stats.refs_completed.append(ref)
    else:
        stats.failed += 1
        stats.refs_failed.append(ref)
        oq.fail_job(
            task_id, batch_id, job_id, lease,
            error=outcome.error or "run failed",
            fingerprint=outcome.fingerprint,
        )


def run_assignment(
    assignment: Mapping[str, Any],
    *,
    agent_runner: AgentRunner,
    stage: str = "author",
    worker: str | None = None,
    max_jobs: int = 1000,
    ttl_seconds: int = oq.DEFAULT_LEASE_TTL_SECONDS,
    orchestrator_runner: OrchestratorRunner | None = None,
    orchestrator_until: str = ORCHESTRATOR_UNTIL,
    verify_checkpoints: bool = True,
) -> WorkerStats:
    """一个 assignment = 一次 worker 拉起：循环 lease→agent→complete/fail 直到无活。

    refs 非空（by-leaf/by-batch）：只 lease 这些 ref；refs 空（pool-worker）：跨 targets lease 全部。

    当提供 orchestrator_runner 时（by-partition 主路径）：先用分区 orchestrator 把本 assignment 的
    每个 target 推进过 download_plan/build_homepage/content_plan 三个 checkpoint（真实检索+真主页+定篇目），
    校验到位后再 lease 叶子 author job；未到位的分区跳过叶子分发（避免在缺 compose 输入时空跑）。
    """
    worker = worker or str(assignment.get("assignmentId") or "worker")
    stats = WorkerStats(worker=worker)
    refs = list(assignment.get("refs") or [])
    targets = list(assignment.get("targets") or [])
    partition_path = list(assignment.get("partitionPath") or [])

    if orchestrator_runner is not None:
        blocked: set[tuple[str, str]] = set()
        for target in targets:
            res = orchestrate_partition(
                target,
                orchestrator_runner=orchestrator_runner,
                partition_path=partition_path,
                refs=refs,
                until=orchestrator_until,
                verify_checkpoints=verify_checkpoints,
            )
            stats.orchestrations.append(res)
            if res.reached:
                stats.orchestrated += 1
            else:
                stats.orchestration_failed += 1
                blocked.add((str(target["taskId"]), str(target["batchId"])))
        # 过滤掉 checkpoint 未到位的 target，不对其分发叶子 author job。
        targets = [t for t in targets if (str(t["taskId"]), str(t["batchId"])) not in blocked]
        if not targets:
            return stats

    guard = 0
    while guard < max_jobs:
        guard += 1
        job = None
        chosen_target = None
        for target in targets:
            if refs:
                for ref in refs:
                    job = oq.acquire_lease(
                        str(target["taskId"]), str(target["batchId"]),
                        worker=worker, stage=stage, ref=ref, ttl_seconds=ttl_seconds,
                    )
                    if job is not None:
                        chosen_target = target
                        break
            else:
                job = oq.acquire_lease(
                    str(target["taskId"]), str(target["batchId"]),
                    worker=worker, stage=stage, ttl_seconds=ttl_seconds,
                )
                if job is not None:
                    chosen_target = target
            if job is not None:
                break
        if job is None:
            break
        stats.leased += 1
        _process_job(chosen_target, job, agent_runner=agent_runner, stats=stats)
    return stats


def run_fanout(
    plan_id: str,
    *,
    agent_runner: AgentRunner,
    strategy: str | None = None,
    concurrency: int | None = None,
    stage: str = "author",
    max_workers: int = 0,
    orchestrator_runner: OrchestratorRunner | None = None,
    orchestrator_until: str = ORCHESTRATOR_UNTIL,
    verify_checkpoints: bool = True,
) -> dict[str, Any]:
    """加载冻结计划 → 展开 assignment → 多 worker 执行。返回聚合统计。

    max_workers>1 时用线程池并发跑 assignment（每 assignment 独立 worker，对应独立 cloud agent，
    规避同 agent 并发 run 409）。默认顺序执行（确定性，便于测试）。

    orchestrator_runner 非空时：每个 assignment 先跑分区 orchestrator 推进三个 checkpoint，再分发叶子。
    """
    plan = fp.load_plan(plan_id)
    if plan is None:
        raise ValueError(f"plan not found: {plan_id}")
    expansion = fs.expand(plan, strategy=strategy, concurrency=concurrency)
    assignments = expansion["assignments"]

    def _run(a: Mapping[str, Any]) -> WorkerStats:
        return run_assignment(
            a,
            agent_runner=agent_runner,
            stage=stage,
            orchestrator_runner=orchestrator_runner,
            orchestrator_until=orchestrator_until,
            verify_checkpoints=verify_checkpoints,
        )

    if max_workers and max_workers > 1 and len(assignments) > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(_run, assignments))
    else:
        results = [_run(a) for a in assignments]

    orchestrations = [o for r in results for o in r.orchestrations]
    return {
        "planId": plan_id,
        "strategy": expansion["strategy"],
        "assignments": len(assignments),
        "leased": sum(r.leased for r in results),
        "completed": sum(r.completed for r in results),
        "failed": sum(r.failed for r in results),
        "startupFailures": sum(r.startup_failures for r in results),
        "orchestrated": sum(r.orchestrated for r in results),
        "orchestrationFailed": sum(r.orchestration_failed for r in results),
        "orchestrations": [
            {"taskId": o.task_id, "batchId": o.batch_id, "started": o.started,
             "reached": o.reached, "missing": o.missing, "error": o.error}
            for o in orchestrations
        ],
        "refsCompleted": sorted([r for s in results for r in s.refs_completed]),
        "refsFailed": sorted([r for s in results for r in s.refs_failed]),
        "perWorker": [
            {"worker": r.worker, "leased": r.leased, "completed": r.completed, "failed": r.failed,
             "orchestrated": r.orchestrated, "orchestrationFailed": r.orchestration_failed}
            for r in results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fanout_runner", description="fan-out cursor-sdk 多 worker runner")
    parser.add_argument("--plan", required=True, help="冻结计划 planId")
    parser.add_argument("--strategy", choices=list(fs.VALID_STRATEGIES), help="覆盖计划 defaults.strategy")
    parser.add_argument("--concurrency", type=int, help="覆盖计划 defaults.concurrency")
    parser.add_argument("--stage", default="author")
    parser.add_argument("--max-workers", dest="max_workers", type=int, default=0, help=">1 线程池并发跑 assignment")
    parser.add_argument("--model", default="composer-2.5")
    parser.add_argument(
        "--runtime", choices=list(VALID_RUNTIMES), default=RUNTIME_CLOUD,
        help="local=在本机 cwd 起多个 agent 直接写本仓库（多 worker 并行）；cloud=Cursor 托管 VM。两者都需 CURSOR_API_KEY",
    )
    parser.add_argument(
        "--cwd", default=str(_REPO_ROOT),
        help="local runtime 的工作目录（默认仓库根）；多 worker 共享 cwd，文件写入由 object_queue mutex 隔离",
    )
    parser.add_argument("--spend-limit-usd", dest="spend_limit", type=float, default=None)
    parser.add_argument(
        "--orchestrate",
        dest="orchestrate",
        action="store_true",
        default=None,
        help="先跑分区 orchestrator 推进 download_plan/build_homepage/content_plan（by-partition 默认开启）",
    )
    parser.add_argument(
        "--no-orchestrate", dest="orchestrate", action="store_false",
        help="跳过分区 orchestrator，仅 lease 叶子 author job（叶子输入须已就绪）",
    )
    parser.add_argument(
        "--orchestrator-until", dest="orchestrator_until", default=ORCHESTRATOR_UNTIL,
        help=f"orchestrator 推进到的 stage（默认 {ORCHESTRATOR_UNTIL}）",
    )
    parser.add_argument("--dry-run", action="store_true", help="不起真实 agent，只 lease→complete（连通性自检）")
    args = parser.parse_args(argv)

    # by-partition 默认开启 orchestrator（与策略语义一致）；其它策略默认关闭，除非显式 --orchestrate。
    effective_strategy = args.strategy
    if args.orchestrate is None:
        orchestrate = effective_strategy == fs.STRATEGY_BY_PARTITION
    else:
        orchestrate = bool(args.orchestrate)

    if args.dry_run:
        def runner(_packet: Mapping[str, Any]) -> RunOutcome:
            return RunOutcome(started=True, status="finished", passed=True)
        orchestrator_runner: OrchestratorRunner | None = (
            (lambda _p: RunOutcome(started=True, status="finished", passed=True))
            if orchestrate else None
        )
    else:
        def runner(packet: Mapping[str, Any]) -> RunOutcome:
            return default_agent_runner(
                packet, model=args.model, runtime=args.runtime, cwd=args.cwd,
                spend_limit_usd=args.spend_limit,
            )

        def orchestrator_runner(packet: Mapping[str, Any]) -> RunOutcome:  # type: ignore[misc]
            return default_orchestrator_runner(
                packet, model=args.model, runtime=args.runtime, cwd=args.cwd,
                spend_limit_usd=args.spend_limit,
            )

        if not orchestrate:
            orchestrator_runner = None  # type: ignore[assignment]

    report = run_fanout(
        args.plan,
        agent_runner=runner,
        strategy=args.strategy,
        concurrency=args.concurrency,
        stage=args.stage,
        max_workers=args.max_workers,
        orchestrator_runner=orchestrator_runner,
        orchestrator_until=args.orchestrator_until,
        # dry-run 无法到达真实 checkpoint，跳过真相源校验；真实运行必须校验。
        verify_checkpoints=not args.dry_run,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # 退出码：运行失败或 orchestrator checkpoint 未到位=2，否则 0（startup 失败已退避入队，不视为致命）。
    return 2 if (report["failed"] or report.get("orchestrationFailed")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
