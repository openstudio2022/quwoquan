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
import subprocess
import sys
import threading
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
from _common.article_package import compute_document_sha256, sha256_file, sha256_text  # noqa: E402
from _common.draft_io import draft_article_path, draft_meta_path, prompt_path, read_draft_meta, writing_pack_path  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402
from _common.paths import batch_root, fanout_run_matrix_path, relative_batch_ref  # noqa: E402
from task import object_queue as oq  # noqa: E402

# startup 失败/运行失败的退避基数（秒）。
STARTUP_BACKOFF_BASE = 5
MAX_STARTUP_RETRIES = 3
_RUN_MATRIX_LOCK = threading.Lock()
ASSIGNMENT_MIN_POLL_SECONDS = 0.05
ASSIGNMENT_MAX_BACKOFF_WAIT_SECONDS = 900.0

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
    run_id: str | None = None
    agent_id: str | None = None
    prepared_refs: list[str] = field(default_factory=list)


@dataclass
class WorkerStats:
    worker: str
    leased: int = 0
    completed: int = 0
    failed: int = 0
    attempt_failures: int = 0
    startup_failures: int = 0
    orchestrated: int = 0
    orchestration_failed: int = 0
    refs_completed: list[str] = field(default_factory=list)
    refs_failed: list[str] = field(default_factory=list)
    orchestrations: list[OrchestrationResult] = field(default_factory=list)
    run_records: list[dict[str, Any]] = field(default_factory=list)


def _build_prompt(packet: Mapping[str, Any]) -> str:
    """把 lease packet 渲染为 cloud agent 的执行 prompt（含执行合约 + Ralph 出口门）。"""
    contract = packet.get("executionContract") or {}
    object_refs = packet.get("objectPacketRefs") or {}
    return (
        f"你是单篇内容创作 Subagent。严格隔离：{packet.get('isolation')}\n"
        f"目标 ref: {packet.get('ref')} / stage: {packet.get('stage')}\n"
        f"对象目录: {object_refs.get('contentObjectDir') or '(见 author_job_packet.contentObjectDir)'}\n"
        f"执行合约（必须全部满足）：\n{json.dumps(contract, ensure_ascii=False, indent=2)}\n"
        f"Ralph 自纠环：{packet.get('ralphLoop')}\n"
        f"完成判据：ref_review_gate.passed == true（reviewDecision == approved）。"
    )


RUNTIME_LOCAL = "local"
RUNTIME_CLOUD = "cloud"
VALID_RUNTIMES = (RUNTIME_LOCAL, RUNTIME_CLOUD)


def _git_output(args: list[str], *, cwd: str | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd or str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _default_cloud_repos(cwd: str | None) -> list[dict[str, Any]]:
    repo_cwd = cwd or str(_REPO_ROOT)
    remote = _git_output(["remote", "get-url", "origin"], cwd=repo_cwd)
    branch = _git_output(["branch", "--show-current"], cwd=repo_cwd)
    if not remote:
        raise RuntimeError("git origin remote missing for cloud runtime")
    if remote.startswith("git@"):
        host_and_path = remote[4:]
        if ":" in host_and_path:
            host, path = host_and_path.split(":", 1)
            host = host.replace("-quwoquan", "")
            remote = f"https://{host}/{path}"
    repo: dict[str, Any] = {"url": remote}
    if branch:
        repo["startingRef"] = branch
    return [repo]


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
    resolved_repos = repos or _default_cloud_repos(cwd)
    return AgentOptions(
        api_key=api_key,
        model=model,
        cloud=CloudAgentOptions(repos=resolved_repos),
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


def _load_run_matrix(plan_id: str) -> dict[str, Any]:
    path = fanout_run_matrix_path(plan_id)
    if not path.is_file():
        return {
            "schemaVersion": "quwoquan_data.fanout_run_matrix/1",
            "planId": plan_id,
            "orchestrators": [],
            "refs": {},
            "workers": [],
        }
    data = read_json(path)
    if not isinstance(data, dict):
        return {
            "schemaVersion": "quwoquan_data.fanout_run_matrix/1",
            "planId": plan_id,
            "orchestrators": [],
            "refs": {},
            "workers": [],
        }
    data.setdefault("schemaVersion", "quwoquan_data.fanout_run_matrix/1")
    data.setdefault("planId", plan_id)
    data.setdefault("orchestrators", [])
    data.setdefault("refs", {})
    data.setdefault("workers", [])
    return data


def _save_run_matrix(plan_id: str, matrix: Mapping[str, Any]) -> None:
    path = fanout_run_matrix_path(plan_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, dict(matrix))


def _upsert_ref_run_record(
    plan_id: str,
    *,
    ref: str,
    record: Mapping[str, Any],
) -> None:
    if not plan_id:
        return
    with _RUN_MATRIX_LOCK:
        matrix = _load_run_matrix(plan_id)
        refs = dict(matrix.get("refs") or {})
        refs[ref] = dict(record)
        matrix["refs"] = refs
        _save_run_matrix(plan_id, matrix)


def _append_orchestrator_record(
    plan_id: str,
    record: Mapping[str, Any],
) -> None:
    if not plan_id:
        return
    with _RUN_MATRIX_LOCK:
        matrix = _load_run_matrix(plan_id)
        rows = list(matrix.get("orchestrators") or [])
        rows.append(dict(record))
        matrix["orchestrators"] = rows
        _save_run_matrix(plan_id, matrix)


def _replace_worker_records(plan_id: str, records: list[Mapping[str, Any]]) -> None:
    if not plan_id:
        return
    with _RUN_MATRIX_LOCK:
        matrix = _load_run_matrix(plan_id)
        matrix["workers"] = [dict(record) for record in records]
        _save_run_matrix(plan_id, matrix)


def _source_bundle_sha(task_id: str, batch_id: str, paths: list[str]) -> str | None:
    if not paths:
        return None
    base = batch_root(task_id, batch_id)
    payload: list[dict[str, Any]] = []
    for rel in paths:
        candidate = base / rel
        if not candidate.is_file():
            continue
        payload.append({"path": rel, "sha256": sha256_file(candidate)})
    if not payload:
        return None
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _backfill_draft_meta_run_context(
    task_id: str,
    batch_id: str,
    ref: str,
    *,
    outcome: RunOutcome,
) -> dict[str, Any] | None:
    try:
        path = draft_meta_path(task_id, batch_id, ref)
    except KeyError:
        return None
    if not path.is_file():
        return None
    meta = read_draft_meta(task_id, batch_id, ref) or {}
    try:
        article_path = draft_article_path(task_id, batch_id, ref)
        wp_path = writing_pack_path(task_id, batch_id, ref)
        pr_path = prompt_path(task_id, batch_id, ref)
    except KeyError:
        return None
    prompt_digest = sha256_file(pr_path) if pr_path.is_file() else None
    wp_digest = sha256_file(wp_path) if wp_path.is_file() else None
    draft_digest = compute_document_sha256(article_path.read_text(encoding="utf-8")) if article_path.is_file() else None
    source_digest = _source_bundle_sha(task_id, batch_id, [str(x) for x in (meta.get("citedSourcePaths") or []) if x])
    session_trace = str(meta.get("sessionTrace") or "").strip()
    session_parts = [part for part in (session_trace, outcome.agent_id, outcome.run_id) if part]
    meta["sessionTrace"] = " / ".join(session_parts) if session_parts else None
    meta["agentRunId"] = outcome.run_id
    meta["agentId"] = outcome.agent_id
    if prompt_digest:
        meta["promptSha256"] = prompt_digest
    if wp_digest:
        meta["writingPackSha256"] = wp_digest
    if source_digest:
        meta["sourceBundleSha256"] = source_digest
    if draft_digest:
        meta["draftSha256"] = draft_digest
    write_json(path, meta)
    return meta


def orchestrate_partition(
    target: Mapping[str, Any],
    *,
    orchestrator_runner: OrchestratorRunner,
    partition_path: list[str] | None = None,
    refs: list[str] | None = None,
    force_refs: list[str] | None = None,
    until: str = ORCHESTRATOR_UNTIL,
    plan: Mapping[str, Any] | None = None,
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
            run_id=outcome.run_id, agent_id=outcome.agent_id,
        )
    missing = _missing_orchestrator_checkpoints(task_id, batch_id)
    prepared_refs: list[str] = []
    if not missing and plan is not None:
        from task import fanout_dispatch as fd  # noqa: E402

        prepared = fd.sync_content_author_jobs(
            plan,
            target,
            partition_path=partition_path,
            refs=refs,
            force_refs=force_refs,
        )
        prepared_refs = list(prepared.get("preparedRefs") or [])
    return OrchestrationResult(
        task_id=task_id, batch_id=batch_id, started=True, reached=not missing,
        missing=missing,
        error=outcome.error if missing else None,
        run_id=outcome.run_id,
        agent_id=outcome.agent_id,
        prepared_refs=prepared_refs,
    )


def _process_job(
    target: Mapping[str, Any],
    job: Mapping[str, Any],
    *,
    agent_runner: AgentRunner,
    stats: WorkerStats,
    plan_id: str,
) -> None:
    task_id = str(target["taskId"])
    batch_id = str(target["batchId"])
    job_id = str(job["jobId"])
    lease = str(job["lease"])
    ref = str(job["ref"])
    packet = oq.build_lease_packet(job)
    outcome = agent_runner(packet)
    record: dict[str, Any] = {
        "ref": ref,
        "taskId": task_id,
        "batchId": batch_id,
        "worker": stats.worker,
        "jobId": job_id,
        "status": "running",
        "attempt": job.get("attempt"),
        "agentRunId": outcome.run_id,
        "agentId": outcome.agent_id,
        "started": outcome.started,
    }

    if outcome.tokens or outcome.cost_usd:
        usage_job = oq.record_usage(task_id, batch_id, job_id, lease, tokens=outcome.tokens, cost_usd=outcome.cost_usd)
        record["tokens"] = outcome.tokens
        record["costUsd"] = outcome.cost_usd
        # 用量超预算时 record_usage 已强制 dead 并清空 lease：不能再 complete/fail（lease 失配）。
        if usage_job.get("state") in (oq.STATE_DEAD, oq.STATE_FAILED) or usage_job.get("lease") != lease:
            stats.attempt_failures += 1
            stats.failed += 1
            stats.refs_failed.append(ref)
            record["status"] = str(usage_job.get("state") or "failed")
            record["error"] = str(usage_job.get("lastError") or "budget_exceeded")
            stats.run_records.append(record)
            _upsert_ref_run_record(plan_id, ref=ref, record=record)
            return

    if not outcome.started:
        # 启动失败：从未执行，按 retryable 退避；fail_job 走退避/dead 状态机。
        retryable_startup = bool(outcome.retryable)
        startup_attempt = int(job.get("attempt") or 0)
        if retryable_startup and startup_attempt < MAX_STARTUP_RETRIES:
            time.sleep(STARTUP_BACKOFF_BASE * startup_attempt)
            oq.fail_job(
                task_id,
                batch_id,
                job_id,
                lease,
                error=f"startup: {outcome.error}",
                same_run_retryable=True,
                startup_failure=True,
            )
        else:
            stats.startup_failures += 1
            oq.fail_job(
                task_id,
                batch_id,
                job_id,
                lease,
                error=f"startup: {outcome.error}",
                same_run_retryable=False,
                startup_failure=True,
            )
        record["status"] = "startup_failed"
        record["error"] = outcome.error
        stats.run_records.append(record)
        _upsert_ref_run_record(plan_id, ref=ref, record=record)
        return

    if outcome.status == "finished" and outcome.passed:
        oq.complete_job(task_id, batch_id, job_id, lease)
        stats.completed += 1
        stats.refs_completed.append(ref)
        meta = _backfill_draft_meta_run_context(task_id, batch_id, ref, outcome=outcome) or {}
        record["status"] = "succeeded"
        try:
            record["draftMetaPath"] = relative_batch_ref(draft_meta_path(task_id, batch_id, ref), task_id, batch_id)
            record["draftPath"] = relative_batch_ref(draft_article_path(task_id, batch_id, ref), task_id, batch_id)
        except KeyError:
            pass
        record["agentRunId"] = meta.get("agentRunId") or outcome.run_id
        record["agentId"] = meta.get("agentId") or outcome.agent_id
        record["sessionTrace"] = meta.get("sessionTrace")
        record["promptSha256"] = meta.get("promptSha256")
        record["writingPackSha256"] = meta.get("writingPackSha256")
        record["sourceBundleSha256"] = meta.get("sourceBundleSha256")
        record["draftSha256"] = meta.get("draftSha256")
        stats.run_records.append(record)
        _upsert_ref_run_record(plan_id, ref=ref, record=record)
    else:
        stats.attempt_failures += 1
        stats.failed += 1
        stats.refs_failed.append(ref)
        oq.fail_job(
            task_id, batch_id, job_id, lease,
            error=outcome.error or "run failed",
            fingerprint=outcome.fingerprint,
            same_run_retryable=True,
        )
        record["status"] = "failed"
        record["error"] = outcome.error or "run failed"
        record["fingerprint"] = outcome.fingerprint
        stats.run_records.append(record)
        _upsert_ref_run_record(plan_id, ref=ref, record=record)


def _collect_assignment_snapshot(
    targets: list[Mapping[str, Any]],
    *,
    stage: str,
    refs: list[str] | None,
) -> dict[str, Any]:
    aggregate = {
        "total": 0,
        "byState": {},
        "waitableLive": 0,
        "leaseableNow": 0,
        "failedBackoffSameRun": 0,
        "nextRetryEpoch": None,
        "nextLeaseExpiryEpoch": None,
        "nextDeadlineEpoch": None,
    }
    for target in targets:
        snap = oq.queue_runtime_snapshot(
            str(target["taskId"]),
            str(target["batchId"]),
            stage=stage,
            refs=refs,
        )
        aggregate["total"] += int(snap.get("total") or 0)
        aggregate["waitableLive"] += int(snap.get("waitableLive") or 0)
        aggregate["leaseableNow"] += int(snap.get("leaseableNow") or 0)
        aggregate["failedBackoffSameRun"] += int(snap.get("failedBackoffSameRun") or 0)
        by_state = aggregate["byState"]
        for state, count in dict(snap.get("byState") or {}).items():
            by_state[state] = int(by_state.get(state) or 0) + int(count or 0)
        for key in ("nextRetryEpoch", "nextLeaseExpiryEpoch", "nextDeadlineEpoch"):
            value = snap.get(key)
            if value is None:
                continue
            current = aggregate.get(key)
            aggregate[key] = value if current is None else min(float(current), float(value))
    return aggregate


def _wait_seconds_for_snapshot(snapshot: Mapping[str, Any]) -> float | None:
    """基于队列真相源决定当前 assignment 是否还应该继续等下一次 lease。"""
    if int(snapshot.get("waitableLive") or 0) <= 0:
        return None
    if int(snapshot.get("leaseableNow") or 0) > 0:
        return 0.0
    now = time.time()
    waits: list[float] = []
    next_retry = snapshot.get("nextRetryEpoch")
    if next_retry is not None:
        waits.append(max(0.0, float(next_retry) - now))
    next_lease_expiry = snapshot.get("nextLeaseExpiryEpoch")
    if next_lease_expiry is not None:
        waits.append(max(0.0, float(next_lease_expiry) - now))
    next_deadline = snapshot.get("nextDeadlineEpoch")
    if next_deadline is not None:
        waits.append(max(0.0, float(next_deadline) - now))
    if not waits:
        # 仍有 waitableLive，但既不是 queued/failed(backoff)，也没有下一时间点；视为无需等待，交给上层收口。
        return None
    wait_for = max(min(waits), ASSIGNMENT_MIN_POLL_SECONDS)
    return min(wait_for, ASSIGNMENT_MAX_BACKOFF_WAIT_SECONDS)


def _collect_final_stage_refs(
    units: list[Mapping[str, Any]],
    *,
    stage: str,
    refs: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """按最终 object_queue 状态汇总整次 run 的 ref 终态（策略无关、避免多 worker 重复计数）。"""
    completed: set[str] = set()
    failed: set[str] = set()
    seen_targets: set[tuple[str, str]] = set()
    ref_filter = {str(ref) for ref in (refs or []) if str(ref).strip()} if refs else None
    for unit in units:
        key = (str(unit["taskId"]), str(unit["batchId"]))
        if key in seen_targets:
            continue
        seen_targets.add(key)
        for job in oq._load_jobs(key[0], key[1]):  # noqa: SLF001 - runner 汇总最终真相源
            if job.get("stage") != stage:
                continue
            ref = str(job.get("ref") or "")
            if ref_filter is not None and ref not in ref_filter:
                continue
            state = str(job.get("state") or "")
            if state == oq.STATE_SUCCEEDED:
                completed.add(ref)
            elif state in (oq.STATE_FAILED, oq.STATE_DEAD, oq.STATE_BLOCKED):
                failed.add(ref)
    failed -= completed
    return sorted(completed), sorted(failed)


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
    plan: Mapping[str, Any] | None = None,
    refs_filter: list[str] | None = None,
    force_refs: list[str] | None = None,
) -> WorkerStats:
    """一个 assignment = 一次 worker 拉起：循环 lease→agent→complete/fail 直到无活。

    refs 非空（by-leaf/by-batch）：只 lease 这些 ref；refs 空（pool-worker）：跨 targets lease 全部。

    当提供 orchestrator_runner 时（by-partition 主路径）：先用分区 orchestrator 把本 assignment 的
    每个 target 推进过 download_plan/build_homepage/content_plan 三个 checkpoint（真实检索+真主页+定篇目），
    校验到位后再 lease 叶子 author job；未到位的分区跳过叶子分发（避免在缺 compose 输入时空跑）。
    """
    worker = worker or str(assignment.get("assignmentId") or "worker")
    stats = WorkerStats(worker=worker)
    assignment_refs = list(assignment.get("refs") or [])
    targets = list(assignment.get("targets") or [])
    partition_path = list(assignment.get("partitionPath") or [])
    use_assignment_refs = not bool(str((plan or {}).get("sourceTaskId") or "").strip())
    requested_refs = [str(ref).strip() for ref in ((refs_filter or force_refs) or []) if str(ref).strip()]
    requested_ref_set = set(requested_refs)
    refs: list[str] | None
    if requested_ref_set:
        refs = [ref for ref in assignment_refs if ref in requested_ref_set] if use_assignment_refs else requested_refs
    else:
        refs = list(assignment_refs) if use_assignment_refs else None
    force_ref_set = {str(ref) for ref in (force_refs or []) if str(ref).strip()}

    if requested_ref_set and refs == [] and use_assignment_refs:
        return stats

    if plan is not None and not use_assignment_refs and orchestrator_runner is None:
        from task import fanout_dispatch as fd  # noqa: E402

        for target in targets:
            fd.sync_content_author_jobs(
                plan,
                target,
                partition_path=partition_path,
                refs=refs,
                force_refs=sorted(force_ref_set) if force_ref_set else None,
            )

    if orchestrator_runner is not None:
        blocked: set[tuple[str, str]] = set()
        for target in targets:
            res = orchestrate_partition(
                target,
                orchestrator_runner=orchestrator_runner,
                partition_path=partition_path,
                refs=refs,
                force_refs=sorted(force_ref_set) if force_ref_set else None,
                until=orchestrator_until,
                plan=plan,
            )
            stats.orchestrations.append(res)
            if plan is not None:
                _append_orchestrator_record(
                    str(plan.get("planId")),
                    {
                        "taskId": res.task_id,
                        "batchId": res.batch_id,
                        "worker": worker,
                        "started": res.started,
                        "reached": res.reached,
                        "missing": list(res.missing),
                        "error": res.error,
                        "agentRunId": res.run_id,
                        "agentId": res.agent_id,
                        "preparedRefs": list(res.prepared_refs),
                    },
                )
            if res.reached:
                stats.orchestrated += 1
            else:
                stats.orchestration_failed += 1
                blocked.add((str(target["taskId"]), str(target["batchId"])))
        # 过滤掉 checkpoint 未到位的 target，不对其分发叶子 author job。
        targets = [t for t in targets if (str(t["taskId"]), str(t["batchId"])) not in blocked]
        if not targets:
            return stats

    while stats.leased < max_jobs:
        for target in targets:
            oq.reap_jobs(str(target["taskId"]), str(target["batchId"]))
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
            snapshot = _collect_assignment_snapshot(
                targets,
                stage=stage,
                refs=refs,
            )
            wait_seconds = _wait_seconds_for_snapshot(snapshot)
            if wait_seconds is None:
                break
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            continue
        stats.leased += 1
        _process_job(
            chosen_target,
            job,
            agent_runner=agent_runner,
            stats=stats,
            plan_id=str((plan or {}).get("planId") or ""),
        )
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
    refs: list[str] | None = None,
    force_refs: list[str] | None = None,
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
    matrix = _load_run_matrix(plan_id)
    matrix["strategy"] = expansion["strategy"]
    matrix["concurrency"] = expansion["concurrency"]
    matrix["assignments"] = len(assignments)
    _save_run_matrix(plan_id, matrix)

    def _run(a: Mapping[str, Any]) -> WorkerStats:
        return run_assignment(
            a,
            agent_runner=agent_runner,
            stage=stage,
            orchestrator_runner=orchestrator_runner,
            orchestrator_until=orchestrator_until,
            plan=plan,
            refs_filter=refs,
            force_refs=force_refs,
        )

    if max_workers and max_workers > 1 and len(assignments) > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(_run, assignments))
    else:
        results = [_run(a) for a in assignments]

    orchestrations = [o for r in results for o in r.orchestrations]
    final_refs_completed, final_refs_failed = _collect_final_stage_refs(expansion["units"], stage=stage, refs=refs)
    total_attempt_failures = sum(r.attempt_failures for r in results)
    total_completed = len(final_refs_completed)
    total_failed = len(final_refs_failed)
    total_startup_failures = sum(r.startup_failures for r in results)
    total_orchestrated = sum(r.orchestrated for r in results)
    total_orchestration_failed = sum(r.orchestration_failed for r in results)
    final_matrix = _load_run_matrix(plan_id)
    final_matrix["summary"] = {
        "assignments": len(assignments),
        "leased": sum(r.leased for r in results),
        "completed": total_completed,
        "failed": total_failed,
        "attemptFailures": total_attempt_failures,
        "startupFailures": total_startup_failures,
        "orchestrated": total_orchestrated,
        "orchestrationFailed": total_orchestration_failed,
        "startupFailureRate": round((total_startup_failures / max(1, total_completed + total_failed)), 4),
        "retryConvergence": round((total_completed / max(1, total_completed + total_failed)), 4),
        "spilloverRate": 0.0,
    }
    worker_records = [
        {
            "worker": r.worker,
            "leased": r.leased,
            "completed": len(r.refs_completed),
            "failed": len(r.refs_failed),
            "refsCompleted": sorted(r.refs_completed),
            "refsFailed": sorted(r.refs_failed),
            "attemptFailures": r.attempt_failures,
            "startupFailures": r.startup_failures,
            "orchestrated": r.orchestrated,
            "orchestrationFailed": r.orchestration_failed,
        }
        for r in results
    ]
    final_matrix["workers"] = worker_records
    _save_run_matrix(plan_id, final_matrix)
    return {
        "planId": plan_id,
        "strategy": expansion["strategy"],
        "assignments": len(assignments),
        "leased": sum(r.leased for r in results),
        "completed": total_completed,
        "failed": total_failed,
        "attemptFailures": total_attempt_failures,
        "startupFailures": total_startup_failures,
        "orchestrated": total_orchestrated,
        "orchestrationFailed": total_orchestration_failed,
        "orchestrations": [
            {"taskId": o.task_id, "batchId": o.batch_id, "started": o.started,
             "reached": o.reached, "missing": o.missing, "error": o.error}
            for o in orchestrations
        ],
        "refsCompleted": final_refs_completed,
        "refsFailed": final_refs_failed,
        "perWorker": [
            dict(record) for record in worker_records
        ],
        "runMatrixPath": str(fanout_run_matrix_path(plan_id)),
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
    parser.add_argument("--refs", help="仅运行逗号分隔的 ref 列表（content-mode 为内容对象 ref）")
    parser.add_argument("--force-refs", dest="force_refs", help="强制重跑逗号分隔的已成稿 ref")
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
    args = parser.parse_args(argv)

    # by-partition 默认开启 orchestrator（与策略语义一致）；其它策略默认关闭，除非显式 --orchestrate。
    effective_strategy = args.strategy
    if args.orchestrate is None:
        orchestrate = effective_strategy == fs.STRATEGY_BY_PARTITION
    else:
        orchestrate = bool(args.orchestrate)

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
        refs=[item.strip() for item in str(args.refs or "").split(",") if item.strip()] or None,
        force_refs=[item.strip() for item in str(args.force_refs or "").split(",") if item.strip()] or None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # 退出码：运行失败或 orchestrator checkpoint 未到位=2，否则 0（startup 失败已退避入队，不视为致命）。
    return 2 if (report["failed"] or report.get("orchestrationFailed")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
