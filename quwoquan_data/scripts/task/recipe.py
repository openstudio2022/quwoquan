"""qwq-data task run-recipe — 家族包配方执行器（唯一运行编排主干）。

替代旧 quwoquan_ops/runners 家族 shell（homepage_*_to_gate / cs100_* / *_resume_loop）：
配方（control_plane/families/<ref>.recipe.yaml）声明任务来源、契约门、执行主体与
放量验收；本执行器按固定四段主干执行，禁止任何脚本级第二编排真相源：

    ensure-task → contract-gate → execute(scaled_e2e|resume_loop) → readiness

- batch/plan 是运行实例标识，由 CLI 注入（缺省时间戳生成），不进配方；
- 子步骤统一经 `_invoke_cli`（当前解释器 + cli.py 子进程）执行，测试可注入；
- workflow 终态进程内读 batch/_shared/task_workflow_state.json，与 CLI 消费同源。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from _common.execution_branch import current_git_branch
from _common.io import write_json
from _common.paths import (
    CONTROL_PLANE_SHARED_ROOT,
    OUTPUT_ARTIFACTS_ROOT,
    REPO_ROOT,
    batch_workflow_state_path,
    committed_task_root,
    recipe_path,
)
from task import store

_CLI_PATH = Path(__file__).resolve().parents[1] / "cli.py"

# 跨批去重账本默认维度（单一真相源 task.target_selection.DEFAULT_SOURCE_TASK_ID；
# 模块导入期取值避免循环依赖延迟到调用点）。
from task.target_selection import DEFAULT_SOURCE_TASK_ID as _DEFAULT_DEDUP_SOURCE_TASK  # noqa: E402

# 可注入执行点（测试 mock；生产即默认实现）。
InvokeCli = Callable[[list[str]], int]
GEO_HOMEPAGE_PROFILE_RECIPES = {
    "pilot": "content/travel/homepage/pilot",
    "h100": "content/travel/homepage/h100",
    "h1000": "content/travel/homepage/h1000",
    "mw-probe": "content/travel/homepage/mw_probe",
    "mw3-probe": "content/travel/homepage/mw3_probe",
}


def _default_invoke_cli(argv: list[str]) -> int:
    proc = subprocess.run([sys.executable, str(_CLI_PATH), *argv], check=False)
    return int(proc.returncode)


def load_recipe(recipe_ref: str) -> dict[str, Any]:
    path = recipe_path(recipe_ref)
    if not path.is_file():
        raise FileNotFoundError(f"recipeRef '{recipe_ref}' 不存在: {path}")
    doc = store.read_yaml(path)
    if not isinstance(doc, dict) or doc.get("schemaVersion") != store.RECIPE_VERSION:
        raise ValueError(f"recipe '{recipe_ref}' schemaVersion 必须为 {store.RECIPE_VERSION}")
    errors = lint_recipe(doc, recipe_ref)
    if errors:
        raise ValueError(f"recipe '{recipe_ref}' 不合法: " + "; ".join(errors))
    return doc


def lint_recipe(doc: dict[str, Any], recipe_ref: str) -> list[str]:
    """结构校验（与 task_recipe.schema.json 同口径的手写门）。"""
    errors: list[str] = []
    if str(doc.get("recipeId") or "") != recipe_ref:
        errors.append(f"recipeId '{doc.get('recipeId')}' 必须等于引用路径 '{recipe_ref}'")
    for field in ("title", "presetRef", "batchAxes", "task", "execution"):
        if not doc.get(field):
            errors.append(f"缺少必填字段 {field}")
    preset_ref = str(doc.get("presetRef") or "")
    if preset_ref:
        try:
            store.load_preset(preset_ref)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"presetRef 解析失败: {exc}")
    axes = doc.get("batchAxes") or {}
    for key in ("phase", "contentType", "supplyMode"):
        if not str(axes.get(key) or ""):
            errors.append(f"batchAxes.{key} 必填")
    task = doc.get("task") or {}
    if not task.get("taskId") and not task.get("generate"):
        errors.append("task.taskId 与 task.generate 至少声明其一")
    execution = doc.get("execution") or {}
    if str(execution.get("mode") or "") not in {"scaled_e2e", "resume_loop", "fanout_partition"}:
        errors.append("execution.mode 必须是 scaled_e2e | resume_loop | fanout_partition")
    profile = str(doc.get("runtimeProfile") or "")
    if profile and not (CONTROL_PLANE_SHARED_ROOT / f"{profile}.runtime.yaml").is_file():
        errors.append(f"runtimeProfile '{profile}' 不存在于 control_plane/_shared/")
    env = doc.get("env") or {}
    if any(not isinstance(v, str) for v in env.values()):
        errors.append("env 值必须全部为字符串")
    return errors


_INSTRUCTIONS_RECIPE_REF_RE = re.compile(r"run-recipe\s+([A-Za-z0-9_\-./\u4e00-\u9fff]+)")


def lint_family_instructions(families_root: Path | None = None) -> list[str]:
    """instructions↔recipe 防漂移轻量门（归一化收债 5）。

    families/**/*.instructions.md 中引用的 `task run-recipe <ref>` 必须对应
    真实存在的 `<ref>.recipe.yaml`；说明文档漂移（配方改名/退役未同步）即 BLOCK。
    """
    from _common.paths import FAMILIES_ROOT

    root = families_root or FAMILIES_ROOT
    errors: list[str] = []
    if not root.is_dir():
        return errors
    for doc_path in sorted(root.rglob("*.instructions.md")):
        text = doc_path.read_text(encoding="utf-8")
        for ref in _INSTRUCTIONS_RECIPE_REF_RE.findall(text):
            if not (root / f"{ref}.recipe.yaml").is_file():
                errors.append(
                    f"{doc_path.relative_to(root)}: 引用的 recipe '{ref}' 不存在"
                    f"（期望 {ref}.recipe.yaml）"
                )
    return errors


def _apply_runtime_env(recipe: dict[str, Any]) -> None:
    """batchAxes + runtimeProfile + env → 进程环境（已显式声明的外部 env 优先）。"""
    axes = recipe.get("batchAxes") or {}
    os.environ.setdefault("QWQ_BATCH_PHASE", str(axes.get("phase")))
    os.environ.setdefault("QWQ_BATCH_CONTENT_TYPE", str(axes.get("contentType")))
    os.environ.setdefault("QWQ_BATCH_SUPPLY_MODE", str(axes.get("supplyMode")))
    merged: dict[str, str] = {}
    profile = str(recipe.get("runtimeProfile") or "")
    if profile:
        doc = store.read_yaml(CONTROL_PLANE_SHARED_ROOT / f"{profile}.runtime.yaml") or {}
        merged.update({str(k): str(v) for k, v in (doc.get("env") or {}).items()})
    merged.update({str(k): str(v) for k, v in (recipe.get("env") or {}).items()})
    for key, value in merged.items():
        os.environ.setdefault(key, value)


def _apply_runtime_overrides(recipe: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Apply CLI instance parameters without mutating the committed recipe."""

    task = dict(recipe.get("task") or {})
    generate = dict(task.get("generate") or {})
    changed = False
    for arg_name, field in (
        ("discovery", "discovery"),
        ("region", "region"),
        ("name", "name"),
        ("title", "title"),
        ("intent_label", "intentLabel"),
        ("mandatory", "mandatory"),
    ):
        value = getattr(args, arg_name, None)
        if value is None or str(value).strip() == "":
            continue
        generate[field] = str(value).strip()
        changed = True
    limit = getattr(args, "limit", None)
    if limit is not None:
        generate["limit"] = int(limit)
        changed = True
    if not changed:
        return recipe
    if generate:
        task["generate"] = generate
    updated = {**recipe, "task": task}
    if limit is not None:
        contract = dict(updated.get("contract") or {})
        if contract.get("targetObjectCount") is not None:
            contract["targetObjectCount"] = int(limit)
        readiness = dict(updated.get("readiness") or {})
        if readiness.get("target") is not None:
            readiness["target"] = int(limit)
        if readiness.get("dailyTarget") is not None:
            readiness["dailyTarget"] = int(limit)
        updated["contract"] = contract
        updated["readiness"] = readiness
    return updated


def _geo_region(args: argparse.Namespace) -> str:
    parts = [
        str(getattr(args, "country", "") or "").strip(),
        str(getattr(args, "province", "") or "").strip(),
        str(getattr(args, "city", "") or "").strip(),
        str(getattr(args, "district", "") or "").strip(),
    ]
    return "/".join(part for part in parts if part) or "中国"


def _geo_label(region: str, profile: str) -> str:
    tail = region.split("/")[-1] if region else "中国"
    return f"{tail}景区主页{profile}".replace("_", "").replace("-", "")[:16]


def _resolved_task_id(recipe: dict[str, Any]) -> str:
    task = recipe.get("task") or {}
    task_id = str(task.get("taskId") or "").strip()
    if task_id:
        return task_id
    generate = task.get("generate") or {}
    region = str(generate.get("region") or "中国")
    category = str(generate.get("category") or "景区")
    name = str(generate.get("name") or "")
    return store.build_task_id("travel", "地域", region, category, name)


def _ensure_task(recipe: dict[str, Any], invoke: InvokeCli, *, force: bool) -> str:
    task_id = _resolved_task_id(recipe)
    generate = (recipe.get("task") or {}).get("generate") or {}
    if not generate:
        if not store.spec_exists(task_id):
            raise SystemExit(f"[run-recipe] 任务不存在且配方未声明 generate: {task_id}")
        return task_id
    if store.spec_exists(task_id) and not force:
        return task_id
    argv = [
        "task", "select-targets",
        "--discovery", str(REPO_ROOT / str(generate.get("discovery"))),
        "--limit", str(int(generate.get("limit"))),
        "--reserve-ratio", str(float(generate.get("reserveRatio", 0.2))),
        "--region", str(generate.get("region") or "中国"),
        "--category", str(generate.get("category") or "景区"),
        "--name", str(generate.get("name")),
        "--title", str(generate.get("title") or generate.get("name")),
        "--intent-label", str(generate.get("intentLabel") or generate.get("name")),
        "--preset", str(recipe.get("presetRef")),
        "--entity-articles-per-target", str(int(generate.get("entityArticlesPerTarget", 0))),
        "--entity-homepages-per-target", str(int(generate.get("entityHomepagesPerTarget", 1))),
        "--image-works-per-target", str(int(generate.get("imageWorksPerTarget", 0))),
        "--owner", f"run-recipe {recipe.get('recipeId')}",
        # 跨批去重账本维度显式声明（WP4 dedup 修正）：配方可声明 generate.sourceTask，
        # 缺省全国维度常量；禁止隐式回退到 select-targets 内部缺省造成账本维度漂移。
        "--source-task", str(generate.get("sourceTask") or _DEFAULT_DEDUP_SOURCE_TASK),
        "--write",
    ]
    # mandatory 显式声明即透传（含空串=空 mandatory，覆盖 select-targets 的川西五景缺省；
    # 省级批次 discovery 不含缺省实体时必须显式声明空 mandatory 才能通过选择门）。
    if generate.get("mandatory") is not None:
        argv += ["--mandatory", str(generate.get("mandatory"))]
    if generate.get("sourceReadiness"):
        argv += ["--source-readiness", str(generate.get("sourceReadiness"))]
    if bool(generate.get("allowQuotaShortfall")):
        argv += ["--allow-quota-shortfall"]
        argv += ["--min-batch-completion-mode",
                 str(generate.get("minBatchCompletionMode") or "best_effort_with_reasoned_rejects")]
    if force:
        argv += ["--force"]
    rc = invoke(argv)
    if rc != 0:
        raise SystemExit(f"[run-recipe] select-targets 失败 rc={rc}")
    return task_id


def _contract_gate(recipe: dict[str, Any], task_id: str) -> None:
    contract = recipe.get("contract") or {}
    spec = store.load_spec(task_id)
    errors: list[str] = []
    declared_preset = store.spec_preset_ref(spec)
    if declared_preset != str(recipe.get("presetRef") or ""):
        errors.append(f"task.presetRef={declared_preset!r} 与配方 presetRef={recipe.get('presetRef')!r} 不一致")
    if bool(contract.get("requireActiveStatus", True)) and str(spec.get("status") or "") != "active":
        errors.append(f"task status 必须 active，实得 {spec.get('status')!r}")
    expected_branch = str(contract.get("executionBranch") or "")
    if expected_branch:
        workflow = spec.get("workflowPolicy") or {}
        actual_branch = str(workflow.get("executionBranch") or "")
        if actual_branch != expected_branch:
            errors.append(f"workflowPolicy.executionBranch={actual_branch!r} != {expected_branch!r}")
        git_branch = current_git_branch(cwd=REPO_ROOT)
        if git_branch != expected_branch:
            errors.append(f"当前 git 分支={git_branch!r} != 契约分支 {expected_branch!r}")
    target = int(contract.get("targetObjectCount") or 0)
    if target:
        workflow = spec.get("workflowPolicy") or {}
        actual = int(workflow.get("targetObjectCount") or 0)
        if actual != target:
            errors.append(f"workflowPolicy.targetObjectCount={actual} != {target}")
        selected = _selected_count(task_id, spec)
        if not bool(contract.get("allowSelectionShortfall")) and selected < target:
            errors.append(f"selection shortfall: selected={selected} < target={target}")
    if errors:
        raise SystemExit("[run-recipe] 契约门 BLOCK: " + "; ".join(errors))


def _selected_count(task_id: str, spec: dict[str, Any]) -> int:
    selection_path = committed_task_root(task_id) / "_shared" / "target_selection.json"
    if selection_path.is_file():
        payload = json.loads(selection_path.read_text(encoding="utf-8"))
        return int(payload.get("selectedCount") or 0)
    scope = spec.get("scope") or {}
    return len(scope.get("coverageTargets") or [])


def _workflow_status(task_id: str, batch_id: str) -> str:
    state_path = batch_workflow_state_path(task_id, batch_id)
    if not state_path.is_file():
        return "missing"
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return "unreadable"
    return str(data.get("status") or "unknown")


# workflow 成功终态：succeeded 与「按 reasoned-reject 完成门收口」的批次同为成功，
# 后者由 readiness（scale-readiness trial 模式）继续裁决，不得在 resume 循环空转。
_SUCCESS_WORKFLOW_STATUSES = frozenset({"succeeded", "completed_with_reasoned_rejects"})

# manual_required 根因分类：命中网络类标记 → 可自愈（带退避自动重试）；
# 否则视为配额/契约类 → 立即退出交人工。标记与 run.py/auto research 落盘文案同源。
_NETWORK_FAILURE_MARKERS = (
    "network_unreachable",
    "network unreachable",
    "no_progress_timeout",
    "infrastructure failure",
    "connection refused",
    "connection reset",
    "timed out",
    "timeout",
    "curl",
    "dns",
    "retry_source_discovery",
    # stale/orphan auto research 恢复出的 manual_required 是幂等可续跑的
    "resume will revalidate checkpoint",
)

# 网络自愈探测端点：批次主源（zh.wikipedia）+ Commons；任一可达即认为出口恢复。
_NETWORK_PROBE_URLS = (
    "https://zh.wikipedia.org/w/api.php?action=query&format=json",
    "https://commons.wikimedia.org/w/api.php?action=query&format=json",
)

# 凭据/API 限额类失败标记（key 生命周期内置：403/limit 自动暂停 → 探活恢复自动续跑）。
# 与 _common.cursor_credentials.is_cursor_auth_error 同向；此处补充 API 限流/额度文案。
# 刻意不用裸 "quota"：内容配额（quota shortfall: selected<target）是契约类，须交人工。
_AUTH_FAILURE_MARKERS = (
    "authfailure",
    "credential invalid",
    "unauthorized",
    "invalid api key",
    "plan_required",
    "plan required",
    "forbidden",
    "usage limit",
    "usage_limit",
    "rate limit",
    "rate_limit",
    "spend limit reached",
    "quota exceeded",
    "quota_exceeded",
    "insufficient_quota",
    "http 403",
    "status 403",
    "(auth)",
)


def _workflow_failure_kind(task_id: str, batch_id: str) -> str:
    """读取 workflow state 的失败证据并分类：auth | network | contract。

    auth 判定先于 network：凭据/配额类文案（403/limit）更特异，且其恢复
    路径（等 key 轮换/额度恢复）与网络自愈（等出口恢复）不同。
    """
    state_path = batch_workflow_state_path(task_id, batch_id)
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return "contract"
    texts = [str(item) for item in (data.get("failedObjects") or [])]
    texts.append(str(data.get("nextAction") or ""))
    blob = " ".join(texts).casefold()
    if any(marker in blob for marker in _AUTH_FAILURE_MARKERS):
        return "auth"
    if any(marker in blob for marker in _NETWORK_FAILURE_MARKERS):
        return "network"
    return "contract"


def _workflow_progress_fingerprint(task_id: str, batch_id: str) -> str:
    """workflow 推进指纹（no-progress watchdog 依据）。

    取 status/waitingCheckpoint/currentStage 与 completed/failed 对象计数：
    任一变化即视为有推进；连续多轮完全一致且网络正常 → stage 级无进展。
    """
    state_path = batch_workflow_state_path(task_id, batch_id)
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return "no-state"
    parts = [
        str(data.get("status") or ""),
        str(data.get("waitingCheckpoint") or ""),
        str(data.get("currentStage") or data.get("stage") or ""),
        str(len(data.get("completedObjects") or [])),
        str(len(data.get("failedObjects") or [])),
        str(len(data.get("stageResults") or data.get("stages") or [])),
        str(data.get("updatedAt") or ""),
    ]
    return "|".join(parts)


def _probe_network_ready(urls: tuple[str, ...] = _NETWORK_PROBE_URLS) -> bool:
    for url in urls:
        proc = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "20", url],
            capture_output=True,
            check=False,
        )
        code = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
        if proc.returncode == 0 and code[:1] in {"2", "3"}:
            return True
    return False


def _load_frozen_fanout_plan(plan_id: str, task_id: str) -> dict[str, Any]:
    """fanout_partition 前置门：计划必须已冻结且 sourceTaskId 指向配方任务。

    sourceTaskId 是分区 task 继承 preset/content/acceptance/workflowPolicy 与
    content-ref author 模式的前提；不一致会让分区退化为默认多模态契约。
    """
    from _common import fanout_plan as fp

    plan = fp.load_plan(plan_id)
    if plan is None:
        raise SystemExit(
            f"[run-recipe] fanout_partition 需要已冻结计划 --plan {plan_id}"
            "（先 task decompose init/load/freeze）"
        )
    if str(plan.get("status")) != "frozen":
        raise SystemExit(f"[run-recipe] 计划未冻结: {plan_id} status={plan.get('status')}")
    plan_source = str(plan.get("sourceTaskId") or "").strip()
    if plan_source != task_id:
        raise SystemExit(
            f"[run-recipe] 计划 sourceTaskId={plan_source!r} 必须等于配方任务 {task_id!r}"
            "（decompose init --source-task-id 声明）"
        )
    return plan


def _execute(
    recipe: dict[str, Any],
    task_id: str,
    batch_id: str,
    plan_id: str,
    invoke: InvokeCli,
) -> None:
    execution = recipe.get("execution") or {}
    mode = str(execution.get("mode"))
    runtime = str(execution.get("runtime") or "local")
    model = str(execution.get("model") or "composer")
    timeout = float(execution.get("startupTimeoutSeconds") or 240)
    if mode == "fanout_partition":
        # WP5 拓扑 A/B：decompose 冻结计划 → fanout by-partition（分区 orchestrator 推进
        # download/build_homepage/content_plan checkpoint → author 叶子）→ 逐分区 finalize
        # → verify --plan 多分区聚合。不带 --source-task/--source-batch：带上会塌缩成
        # source-content-pool（源任务串行）而绕过分区编排；源批次也不参与 resume 循环。
        _load_frozen_fanout_plan(plan_id, task_id)
        argv = [
            "task", "scaled-e2e", "run",
            "--task", task_id,
            "--batch", batch_id,
            "--plan", plan_id,
            "--strategy", str(execution.get("strategy") or "by-partition"),
            "--concurrency", str(int(execution.get("concurrency") or 2)),
            "--max-workers", str(int(execution.get("maxWorkers") or 2)),
            "--runtime", runtime,
            "--model", model,
            "--cwd", str(REPO_ROOT),
            "--cycles", str(int(execution.get("cycles") or 3)),
            "--startup-timeout-seconds", str(timeout),
            "--skip-prepare",
        ]
        prefetch = int(execution.get("downloadPrefetchConcurrency") or 0)
        if prefetch > 0:
            argv += ["--download-prefetch", str(prefetch)]
        if bool(execution.get("forceCleanWorkspaceAgentState", True)):
            argv.append("--force-clean-workspace-agent-state")
        rc = invoke(argv)
        if rc != 0:
            # execute 非零（如 scaled-e2e verify 严格口径未过）不在此终止：
            # recipe 语义是 execute → readiness，GO/NO-GO 由 readiness 判定
            # （trial+failOnNoGo=false 记录证据放行；strict 仍会 NO-GO 非零退出）。
            print(
                f"[run-recipe] fanout_partition scaled-e2e rc={rc}"
                "（交由 readiness 判定 GO/NO-GO）",
                file=sys.stderr,
            )
        return
    if mode == "scaled_e2e":
        argv = [
            "task", "scaled-e2e", "run",
            "--task", task_id,
            "--batch", batch_id,
            "--plan", plan_id,
            "--strategy", "by-partition",
            "--concurrency", str(int(execution.get("concurrency") or 2)),
            "--max-workers", str(int(execution.get("maxWorkers") or 1)),
            "--runtime", runtime,
            "--model", model,
            "--cwd", str(REPO_ROOT),
            "--cycles", str(int(execution.get("cycles") or 3)),
            "--startup-timeout-seconds", str(timeout),
            "--source-task", task_id,
            "--source-batch", batch_id,
        ]
        if bool(execution.get("forceCleanWorkspaceAgentState", True)):
            argv.append("--force-clean-workspace-agent-state")
        rc = invoke(argv)
        # rc==10 为 workflow「尚未收口、可续跑」的既有约定；交给 resume 循环兜底。
        if rc not in (0, 10) and _workflow_status(task_id, batch_id) != "succeeded":
            raise SystemExit(f"[run-recipe] scaled-e2e rc={rc} 且 workflow 未成功")
    _resume_until_done(recipe, task_id, batch_id, invoke)


def _resume_until_done(
    recipe: dict[str, Any],
    task_id: str,
    batch_id: str,
    invoke: InvokeCli,
    *,
    sleep_seconds: float = 2.0,
    probe_network: Callable[[], bool] | None = None,
    probe_cursor_key: Callable[[], bool] | None = None,
    monotonic: Callable[[], float] | None = None,
    network_wait_sleep: Callable[[float], None] | None = None,
) -> None:
    """author resume 主循环：workflow 未收口时反复 `task run --resume` 直至终态。

    终态语义：
    - succeeded / completed_with_reasoned_rejects → 成功，交 readiness 继续裁决；
    - failed → 立即退出；
    - manual_required → 按根因分类：
      - 网络类：等待出口自愈后继续 resume（带退避与次数上限）；
      - 凭据/配额类（auth）：key 生命周期内置——暂停并轮询 key 探活
        （keyfile 轮换/额度恢复 → /v1/me 200），恢复后自动续跑；
      - 契约类：立即退出交人工。
    no-progress watchdog：连续 noProgressRoundLimit 轮 workflow 推进指纹无变化
    且网络正常 → fail-fast（防止无限空转烧预算）。
    循环整体受 wall-clock 预算约束（execution.resumeBudgetSeconds 或
    QWQ_RESUME_LOOP_BUDGET_SECONDS，0=不限）。
    """
    execution = recipe.get("execution") or {}
    max_rounds = int(execution.get("maxAuthorRounds") or 200)
    runtime = str(execution.get("runtime") or "local")
    model = str(execution.get("model") or "composer")
    timeout = float(execution.get("startupTimeoutSeconds") or 240)
    budget_seconds = float(
        execution.get("resumeBudgetSeconds")
        or os.environ.get("QWQ_RESUME_LOOP_BUDGET_SECONDS", "0")
        or 0
    )
    network_retry_limit = int(execution.get("networkRetryLimit") or 24)
    network_retry_delay = float(execution.get("networkRetryDelaySeconds") or 300.0)
    auth_retry_limit = int(execution.get("authRetryLimit") or 12)
    auth_retry_delay = float(execution.get("authRetryDelaySeconds") or 300.0)
    no_progress_round_limit = int(execution.get("noProgressRoundLimit") or 6)
    probe = probe_network or _probe_network_ready
    probe_key = probe_cursor_key or _probe_cursor_key_ready_default
    clock = monotonic or time.monotonic
    wait = network_wait_sleep or time.sleep
    started = clock()
    network_retries = 0
    auth_retries = 0
    last_fingerprint = ""
    no_progress_rounds = 0

    def _budget_exceeded() -> bool:
        return bool(budget_seconds) and (clock() - started) > budget_seconds

    for round_no in range(1, max_rounds + 1):
        if _budget_exceeded():
            raise SystemExit(
                f"[run-recipe] resume 循环超出时间预算 {budget_seconds:.0f}s（round={round_no}）"
            )
        status = _workflow_status(task_id, batch_id)
        if status in _SUCCESS_WORKFLOW_STATUSES:
            return
        if status == "failed":
            raise SystemExit(f"[run-recipe] workflow 终态 {status}（round={round_no}）")
        if status == "manual_required":
            kind = _workflow_failure_kind(task_id, batch_id)
            if kind == "auth":
                auth_retries += 1
                if auth_retries > auth_retry_limit:
                    raise SystemExit(
                        f"[run-recipe] 凭据/配额恢复等待超过上限 {auth_retry_limit}（round={round_no}）"
                    )
                print(
                    f"[run-recipe] manual_required 根因=凭据/配额类，暂停等待 key 轮换/额度恢复"
                    f"（第 {auth_retries}/{auth_retry_limit} 次）",
                    flush=True,
                )
                while not probe_key():
                    if _budget_exceeded():
                        raise SystemExit(
                            f"[run-recipe] key 恢复等待超出时间预算 {budget_seconds:.0f}s"
                        )
                    wait(auth_retry_delay)
            elif kind == "network":
                network_retries += 1
                if network_retries > network_retry_limit:
                    raise SystemExit(
                        f"[run-recipe] 网络类失败自动重试超过上限 {network_retry_limit}（round={round_no}）"
                    )
                print(
                    f"[run-recipe] manual_required 根因=网络类，等待出口自愈后自动 resume"
                    f"（第 {network_retries}/{network_retry_limit} 次）",
                    flush=True,
                )
                while not probe():
                    if _budget_exceeded():
                        raise SystemExit(
                            f"[run-recipe] 网络自愈等待超出时间预算 {budget_seconds:.0f}s"
                        )
                    wait(network_retry_delay)
            else:
                raise SystemExit(
                    f"[run-recipe] workflow 终态 manual_required（round={round_no}，根因=契约类，交人工）"
                )
        argv = [
            "task", "run", "--mode", "single",
            "--task", task_id,
            "--batch", batch_id,
            "--managed",
            "--runtime", runtime,
            "--agent-provider", "cursor_sdk",
            "--model", model,
            "--max-workers", str(int(execution.get("maxWorkers") or 1)),
            "--resume",
            "--startup-timeout-seconds", str(timeout),
        ]
        if bool(execution.get("forceCleanWorkspaceAgentState", True)):
            argv.append("--force-clean-workspace-agent-state")
        rc = invoke(argv)
        status = _workflow_status(task_id, batch_id)
        if status in _SUCCESS_WORKFLOW_STATUSES:
            return
        if rc not in (0, 10) and status not in {"manual_required"}:
            raise SystemExit(f"[run-recipe] resume round={round_no} rc={rc}")
        # no-progress watchdog：推进指纹连续无变化且网络正常 → fail-fast。
        fingerprint = _workflow_progress_fingerprint(task_id, batch_id)
        if fingerprint == last_fingerprint:
            no_progress_rounds += 1
            if no_progress_rounds >= no_progress_round_limit and probe():
                raise SystemExit(
                    f"[run-recipe] no-progress watchdog：连续 {no_progress_rounds} 轮无推进"
                    f"且网络正常（round={round_no}），fail-fast 交人工归因"
                )
        else:
            no_progress_rounds = 0
            last_fingerprint = fingerprint
        time.sleep(sleep_seconds)
    raise SystemExit(f"[run-recipe] author resume 超过最大轮数 {max_rounds}")


def _probe_cursor_key_ready_default() -> bool:
    from _common.cursor_credentials import probe_cursor_key_ready

    return probe_cursor_key_ready()


def _partition_slug(partition_path: list[str]) -> str:
    raw = "_".join(str(part) for part in partition_path if str(part).strip()) or "root"
    return re.sub(r"[^\w\u4e00-\u9fff]+", "_", raw).strip("_") or "root"


def _fanout_partition_readiness(
    recipe: dict[str, Any],
    task_id: str,
    plan_id: str,
    invoke: InvokeCli,
    artifacts_dir: Path,
) -> None:
    """fanout_partition 多分区聚合 readiness（WP5）。

    真相源是各分区 task/batch 的 runtime 证据（源任务批次不承载 workflow），
    所以 audit-batch / sdk-monitoring / scale-readiness 逐分区执行后聚合裁决；
    全部单元评完再统一 BLOCK，保证失败分区一次性全量可见。
    """
    from _common import fanout_plan as fp
    from _common import fanout_strategies as fs

    readiness = recipe.get("readiness") or {}
    accept_estimated_ledger = bool(readiness.get("acceptEstimatedTokenLedger"))
    plan = _load_frozen_fanout_plan(plan_id, task_id)
    units = fs.expand_units(plan)
    if not units:
        raise SystemExit(f"[run-recipe] fanout readiness: 计划 {plan_id} 无分区单元")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    daily_target = int(readiness.get("dailyTarget") or 0)
    min_pass_rate = float(readiness.get("minPassRate") or 0.9)
    mode = str(readiness.get("mode") or "commercial")
    # sdk-monitoring 自带 strict/non-strict 双模式（gate 公开语义）：
    # trial 只记录监控卫生证据（历史累计计数器在多轮 resume 批次必然非零），
    # commercial 保持 --strict 硬失败。audit-batch 产物门在两种模式下都硬性。
    monitoring_strict = mode != "trial"
    rows: list[dict[str, Any]] = []
    hard_failures: list[str] = []
    nogo_units: list[str] = []
    for unit in units:
        unit_task = str(unit["taskId"])
        unit_batch = str(unit["batchId"])
        partition_path = [str(p) for p in (unit.get("partitionPath") or [])]
        slug = _partition_slug(partition_path)
        label = "/".join(partition_path) or unit_task
        unit_target = len(unit.get("leaves") or [])
        audit_rc = invoke(["task", "audit-batch", "--task", unit_task, "--batch", unit_batch, "--write", "--json"])
        monitoring_argv = [
            "verify", "sdk-monitoring",
            "--task", unit_task, "--batch", unit_batch,
            "--plan", plan_id,
        ]
        if accept_estimated_ledger:
            monitoring_argv.append("--accept-estimated-token-ledger")
        monitoring_argv += [
            "--report-out", str(artifacts_dir / f"sdk_monitoring_{slug}.json"),
        ]
        if monitoring_strict:
            monitoring_argv.append("--strict")
        monitoring_rc = invoke(monitoring_argv)
        scale_argv = [
            "verify", "scale-readiness",
            "--task", unit_task, "--batch", unit_batch,
            "--daily-target", str(daily_target or unit_target or 1),
            "--target", str(unit_target or 1),
            "--min-pass-rate", str(min_pass_rate),
            "--mode", mode,
        ]
        if accept_estimated_ledger:
            scale_argv.append("--accept-estimated-token-ledger")
        scale_argv += ["--report-out", str(artifacts_dir / f"scale_readiness_{slug}.json")]
        scale_rc = invoke(scale_argv)
        passed = audit_rc == 0 and monitoring_rc == 0 and scale_rc == 0
        rows.append(
            {
                "partition": label,
                "taskId": unit_task,
                "batchId": unit_batch,
                "leafCount": unit_target,
                "auditRc": audit_rc,
                "sdkMonitoringRc": monitoring_rc,
                "scaleReadinessRc": scale_rc,
                "passed": passed,
            }
        )
        if audit_rc != 0 or monitoring_rc != 0:
            hard_failures.append(f"{label}: audit={audit_rc} monitoring={monitoring_rc}")
        if scale_rc != 0:
            nogo_units.append(label)
    aggregate = {
        "schemaVersion": "quwoquan_data.fanout_readiness_aggregate/1",
        "createdAt": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "planId": plan_id,
        "sourceTaskId": task_id,
        "unitCount": len(rows),
        "passedUnits": sum(1 for row in rows if row["passed"]),
        "units": rows,
        "decision": "GO" if not hard_failures and not nogo_units else "NO-GO",
    }
    aggregate_path = artifacts_dir / "fanout_readiness_aggregate.json"
    write_json(aggregate_path, aggregate)
    print(f"[run-recipe] fanout readiness aggregate → {aggregate_path} decision={aggregate['decision']}")
    if hard_failures:
        raise SystemExit("[run-recipe] fanout readiness 硬失败: " + "; ".join(hard_failures))
    if nogo_units and bool(readiness.get("failOnNoGo", True)):
        raise SystemExit("[run-recipe] fanout scale-readiness NO-GO: " + "; ".join(nogo_units))


def _readiness(
    recipe: dict[str, Any],
    task_id: str,
    batch_id: str,
    plan_id: str,
    invoke: InvokeCli,
    artifacts_dir: Path,
) -> None:
    readiness = recipe.get("readiness") or {}
    if not readiness:
        return
    execution = recipe.get("execution") or {}
    if str(execution.get("mode") or "") == "fanout_partition":
        _fanout_partition_readiness(recipe, task_id, plan_id, invoke, artifacts_dir)
        return
    # 2026-07-06 裁定：本地 cursor_sdk bridge 不回传 usage，estimated 账本可准出，
    # 但必须由配方 readiness.acceptEstimatedTokenLedger 显式声明，禁止静默放宽。
    accept_estimated_ledger = bool(readiness.get("acceptEstimatedTokenLedger"))
    # run_matrix.json 是 fanout orchestrator 的运行证据；managed serial（maxWorkers=1，
    # 经 resume 循环收口）不产生该产物，传 --plan 会触发 run_matrix 缺失误报。
    fanout_execution = int(execution.get("maxWorkers") or 1) > 1
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    rc = invoke(["task", "audit-batch", "--task", task_id, "--batch", batch_id, "--write", "--json"])
    if rc != 0:
        raise SystemExit(f"[run-recipe] audit-batch rc={rc}")
    monitoring_argv = [
        "verify", "sdk-monitoring",
        "--task", task_id, "--batch", batch_id,
    ]
    if fanout_execution:
        monitoring_argv += ["--plan", plan_id]
    if accept_estimated_ledger:
        monitoring_argv.append("--accept-estimated-token-ledger")
    monitoring_argv += [
        "--report-out", str(artifacts_dir / "sdk_monitoring.json"),
        "--strict",
    ]
    rc = invoke(monitoring_argv)
    if rc != 0:
        raise SystemExit(f"[run-recipe] sdk-monitoring rc={rc}")
    target = int(readiness.get("target") or 0)
    scale_argv = [
        "verify", "scale-readiness",
        "--task", task_id, "--batch", batch_id,
        "--daily-target", str(int(readiness.get("dailyTarget") or target or 1)),
        "--target", str(target or 1),
        "--min-pass-rate", str(float(readiness.get("minPassRate") or 0.9)),
        "--mode", str(readiness.get("mode") or "commercial"),
    ]
    if accept_estimated_ledger:
        scale_argv.append("--accept-estimated-token-ledger")
    scale_argv += ["--report-out", str(artifacts_dir / "scale_readiness.json")]
    rc = invoke(scale_argv)
    if bool(readiness.get("failOnNoGo", True)) and rc != 0:
        raise SystemExit(f"[run-recipe] scale-readiness rc={rc}")


def default_batch_id(recipe_ref: str) -> str:
    stem = recipe_ref.rsplit("/", 1)[-1]
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stem}_real_{stamp}"


def handle_run_recipe(args: argparse.Namespace, invoke: InvokeCli | None = None) -> None:
    invoke = invoke or _default_invoke_cli
    recipe_ref = str(args.recipe).strip().strip("/")
    recipe = load_recipe(recipe_ref)
    recipe = _apply_runtime_overrides(recipe, args)
    _apply_runtime_env(recipe)
    batch_id = str(getattr(args, "batch", "") or "") or default_batch_id(recipe_ref)
    plan_id = str(getattr(args, "plan", "") or "") or f"{batch_id}__plan"
    stage = str(getattr(args, "stage", "run") or "run")

    task_id = _ensure_task(recipe, invoke, force=bool(getattr(args, "force_task_write", False)))
    _contract_gate(recipe, task_id)
    print(f"[run-recipe] {recipe_ref} task={task_id} batch={batch_id} plan={plan_id} stage={stage}")
    if stage == "generate-only":
        return
    axes = recipe.get("batchAxes") or {}
    artifacts_dir = (
        OUTPUT_ARTIFACTS_ROOT
        / "content_runs"
        / str(axes.get("phase"))
        / str(axes.get("contentType"))
        / batch_id
    )
    if stage == "readiness-only":
        _readiness(recipe, task_id, batch_id, plan_id, invoke, artifacts_dir)
        return
    rc = invoke(["env", "ready", "--json", "--model",
                 str((recipe.get("execution") or {}).get("model") or "composer"),
                 "--runtime", str((recipe.get("execution") or {}).get("runtime") or "local"),
                 "--startup-timeout-seconds",
                 str(float((recipe.get("execution") or {}).get("startupTimeoutSeconds") or 240))])
    if rc != 0:
        raise SystemExit(f"[run-recipe] env ready rc={rc}")
    # 跑批保护协议：执行前落 runtime 保护清单（frozen plan / release / workflow
    # state / lease），供外部治理代理在清理前读取；写失败不阻断批次。
    try:
        from _common import ops_governance as og

        og.write_runtime_protection_manifest(task_id, batch_id, plan_id=plan_id)
    except Exception as exc:  # noqa: BLE001
        print(f"[run-recipe] runtime protection manifest write failed: {exc}", file=sys.stderr)
    _execute(recipe, task_id, batch_id, plan_id, invoke)
    _readiness(recipe, task_id, batch_id, plan_id, invoke, artifacts_dir)
    print(f"[run-recipe] DONE {recipe_ref} batch={batch_id}")


def handle_geo_homepages(args: argparse.Namespace, invoke: InvokeCli | None = None) -> None:
    profile = str(getattr(args, "profile", "") or "pilot")
    recipe_ref = GEO_HOMEPAGE_PROFILE_RECIPES[profile]
    region = _geo_region(args)
    label = str(getattr(args, "intent_label", "") or "").strip() or _geo_label(region, profile)
    name = str(getattr(args, "name", "") or "").strip() or f"{region.split('/')[-1]}景区主页{profile}"
    handle_run_recipe(
        argparse.Namespace(
            recipe=recipe_ref,
            batch=getattr(args, "batch", None),
            plan=getattr(args, "plan", None),
            stage=getattr(args, "stage", "run"),
            force_task_write=getattr(args, "force_task_write", False),
            discovery=getattr(args, "discovery", None),
            limit=getattr(args, "limit", None),
            region=region,
            name=name,
            title=str(getattr(args, "title", "") or "").strip() or name,
            intent_label=label,
            mandatory=getattr(args, "mandatory", None),
        ),
        invoke=invoke,
    )


def register_recipe_parser(sub: argparse._SubParsersAction) -> None:
    pr = sub.add_parser(
        "run-recipe",
        help="按家族包配方执行 ensure-task→契约门→执行→readiness（旧 runner shell 的唯一替代主干）",
    )
    pr.add_argument("recipe", help="recipeRef：families/ 相对路径去 .recipe.yaml 后缀，如 content/travel/homepage/h100")
    pr.add_argument("--batch", help="批次 id（缺省 <recipe末段>_real_<UTC时间戳>）")
    pr.add_argument("--plan", help="fanout planId（缺省 <batch>__plan）")
    pr.add_argument(
        "--stage",
        choices=["run", "generate-only", "readiness-only"],
        default="run",
        help="run=全链；generate-only=只生成任务并过契约门；readiness-only=只跑放量验收",
    )
    pr.add_argument("--force-task-write", dest="force_task_write", action="store_true",
                    help="generate 任务已存在时覆盖重写")
    pr.add_argument("--discovery", help="运行实例覆盖 discovery 相对/绝对路径")
    pr.add_argument("--limit", type=int, help="运行实例覆盖目标数量，并同步 readiness target")
    pr.add_argument("--region", help="运行实例覆盖地域标签")
    pr.add_argument("--name", help="运行实例覆盖任务名")
    pr.add_argument("--title", help="运行实例覆盖任务标题")
    pr.add_argument("--intent-label", dest="intent_label", help="运行实例覆盖批次 intentLabel")
    pr.add_argument("--mandatory", help="运行实例 mandatory 覆盖，逗号分隔")
    pr.set_defaults(handler=handle_run_recipe)

    pg = sub.add_parser(
        "geo-homepages",
        help="按国家/省/市区聚合现有 homepage recipe 主干（select-targets→run-recipe→readiness）",
    )
    pg.add_argument(
        "--profile",
        choices=sorted(GEO_HOMEPAGE_PROFILE_RECIPES),
        default="pilot",
        help="复用的 homepage recipe profile",
    )
    pg.add_argument("--country", default="中国")
    pg.add_argument("--province")
    pg.add_argument("--city")
    pg.add_argument("--district")
    pg.add_argument("--discovery", help="覆盖 discovery 文件路径")
    pg.add_argument("--limit", type=int, help="覆盖目标数量，并同步 readiness target")
    pg.add_argument("--mandatory", help="运行实例 mandatory，逗号分隔")
    pg.add_argument("--name", help="覆盖任务名")
    pg.add_argument("--title", help="覆盖任务标题")
    pg.add_argument("--intent-label", dest="intent_label", help="覆盖批次 intentLabel")
    pg.add_argument("--batch", help="批次 id")
    pg.add_argument("--plan", help="fanout planId")
    pg.add_argument(
        "--stage",
        choices=["run", "generate-only", "readiness-only"],
        default="run",
    )
    pg.add_argument("--force-task-write", dest="force_task_write", action="store_true")
    pg.set_defaults(handler=handle_geo_homepages)
