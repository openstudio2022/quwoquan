"""家族包配方（run-recipe）契约：仓内配方 lint 全绿、preset 默认值合并、
四段主干调用序列、契约门 BLOCK 语义。

注入 mock invoke，不依赖真实云端。可直接运行：
    python3 quwoquan_data/tests/local_contract/task/test_task_recipe__local_contract_test.py
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# 直跑隔离（pytest 下 conftest 已注入 QWQ_DATA_ROOT 隔离根，此处幂等兜底）。
if "QWQ_DATA_ROOT" not in os.environ and "QWQ_RUNTIME_ROOT" not in os.environ:
    _TMP = tempfile.mkdtemp(prefix="qwq_recipe_test_")
    os.environ["QWQ_DATA_ROOT"] = _TMP

from _common.paths import iter_family_files, FAMILIES_ROOT  # noqa: E402
from task import recipe as recipe_mod  # noqa: E402
from task import store  # noqa: E402

_RECIPE_ENV_KEYS = (
    "QWQ_BATCH_PHASE",
    "QWQ_BATCH_CONTENT_TYPE",
    "QWQ_BATCH_SUPPLY_MODE",
    "QWQ_HOMEPAGE_ONLY_EXECUTION_BRANCH",
    "QWQ_CONTENT_SUPPLY_EXECUTION_BRANCH",
    "QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS",
    "QWQ_MANAGED_AGENT_TIMEOUT_SECONDS",
    "QWQ_ORCHESTRATE_AGENT_TIMEOUT_SECONDS",
    "QWQ_CURSOR_WARM_ATTEMPTS",
)


def _clear_recipe_env() -> dict[str, str | None]:
    saved = {key: os.environ.pop(key, None) for key in _RECIPE_ENV_KEYS}
    return saved


def _restore_recipe_env(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _pilot_spec() -> dict:
    """与 pilot 配方契约匹配的最小 spec（load_spec mock 返回值）。"""
    return {
        "schemaVersion": store.SPEC_VERSION,
        "taskId": "旅行/地域/中国/景区/全国景区主页试点0706a",
        "presetRef": "content/travel/homepage/base",
        "status": "active",
        "workflowPolicy": {
            "executionBranch": "feature/homepage-commercial-lane",
            "targetObjectCount": 25,
        },
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": f"目标{i}"} for i in range(25)]},
    }


def test_family_recipe_files_all_lint_clean():
    """仓内 control_plane/families 每个 .recipe.yaml 都必须 load_recipe 全绿。"""
    refs = [
        str(path.relative_to(FAMILIES_ROOT))[: -len(".recipe.yaml")]
        for path in iter_family_files(".recipe.yaml")
    ]
    assert refs, "families 家族包必须至少有一个配方"
    for ref in refs:
        doc = recipe_mod.load_recipe(ref)
        assert doc["recipeId"] == ref
    for expected in (
        "content/travel/homepage/pilot",
        "content/travel/homepage/h100",
        "content/travel/homepage/h1000",
    ):
        assert expected in refs, f"homepage 家族缺少配方 {expected}: {refs}"


def test_family_preset_files_all_lint_clean():
    """仓内每个 .preset.yaml 都必须可 load 且 presetId 与引用路径一致。"""
    refs = [
        str(path.relative_to(FAMILIES_ROOT))[: -len(".preset.yaml")]
        for path in iter_family_files(".preset.yaml")
    ]
    assert refs, "families 家族包必须至少有一个 preset"
    for ref in refs:
        doc = store.load_preset(ref)
        assert doc["presetId"] == ref, f"presetId 漂移: {ref} -> {doc.get('presetId')}"


def test_homepage_preset_defaults_merge_into_spec():
    raw = {
        "taskId": "旅行/地域/中国/景区/示例",
        "presetRef": "content/travel/homepage/base",
        "content": {"angles": ["独家"]},
    }
    resolved = store.resolve_spec(raw)
    quotas = resolved["content"]["quotas"]
    assert quotas["entityHomepagesPerTarget"] == 1
    assert quotas["entityArticlesPerTarget"] == 0
    assert quotas["imageWorksPerTarget"] == 0
    assert resolved["content"]["modalityContract"] == "separated_research"
    # 显式声明整体覆盖 preset（list 替换语义）。
    assert resolved["content"]["angles"] == ["独家"]
    # 无 presetRef 时原样返回。
    plain = {"taskId": "旅行/地域/中国/景区/裸任务"}
    assert store.resolve_spec(plain) == plain


def test_run_recipe_pilot_backbone_invocation_order(monkeypatch):
    """四段主干：ensure-task(已存在跳过) → 契约门 → env ready → scaled-e2e → readiness。"""
    calls: list[list[str]] = []

    def _invoke(argv: list[str]) -> int:
        calls.append(list(argv))
        return 0

    spec = _pilot_spec()
    monkeypatch.setattr(store, "spec_exists", lambda task_id: True)
    monkeypatch.setattr(store, "load_spec", lambda task_id: spec)
    monkeypatch.setattr(recipe_mod, "current_git_branch", lambda cwd=None: "feature/homepage-commercial-lane")
    monkeypatch.setattr(recipe_mod, "_workflow_status", lambda task_id, batch_id: "succeeded")

    saved = _clear_recipe_env()
    try:
        recipe_mod.handle_run_recipe(
            argparse.Namespace(
                recipe="content/travel/homepage/pilot",
                batch="pilot_test_batch",
                plan="pilot_test_plan",
                stage="run",
                force_task_write=False,
            ),
            invoke=_invoke,
        )
        # 配方 batchAxes 与 runtimeProfile 已注入进程环境。
        assert os.environ["QWQ_BATCH_PHASE"] == "e2e"
        assert os.environ["QWQ_BATCH_CONTENT_TYPE"] == "homepage"
        assert os.environ["QWQ_HOMEPAGE_ONLY_EXECUTION_BRANCH"] == "feature/homepage-commercial-lane"
        assert os.environ["QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS"] == "1"
    finally:
        _restore_recipe_env(saved)

    heads = [tuple(argv[:3]) for argv in calls]
    assert heads == [
        ("env", "ready", "--json"),
        ("task", "scaled-e2e", "run"),
        ("task", "audit-batch", "--task"),
        ("verify", "sdk-monitoring", "--task"),
        ("verify", "scale-readiness", "--task"),
    ], heads
    scaled = calls[1]
    assert scaled[scaled.index("--batch") + 1] == "pilot_test_batch"
    assert scaled[scaled.index("--plan") + 1] == "pilot_test_plan"
    readiness = calls[4]
    assert readiness[readiness.index("--mode") + 1] == "trial"
    assert readiness[readiness.index("--target") + 1] == "25"


def test_readiness_managed_serial_accepts_estimated_ledger_and_skips_fanout_run_matrix(monkeypatch):
    """managed serial（maxWorkers=1，经 resume 循环收口）readiness 契约：

    - readiness.acceptEstimatedTokenLedger=true 时必须把 2026-07-06 裁定显式
      透传给 sdk-monitoring 与 scale-readiness（--accept-estimated-token-ledger），
      禁止靠事后人工旁路；
    - run_matrix.json 是 fanout orchestrator 的证据，managed serial 执行不产生
      该产物，sdk-monitoring 不得携带 --plan 触发 run_matrix 缺失误报。
    """
    calls: list[list[str]] = []
    recipe = recipe_mod.load_recipe("content/travel/homepage/h100")
    assert int((recipe.get("execution") or {}).get("maxWorkers") or 1) == 1
    readiness = dict(recipe.get("readiness") or {})
    readiness["acceptEstimatedTokenLedger"] = True
    recipe = {**recipe, "readiness": readiness}

    with tempfile.TemporaryDirectory(prefix="qwq_recipe_readiness_") as tmp:
        recipe_mod._readiness(
            recipe,
            "旅行/地域/中国/景区/全国景区主页百级0706a",
            "h100_batch",
            "h100_plan",
            lambda argv: calls.append(list(argv)) or 0,
            Path(tmp),
        )

    monitoring = next(argv for argv in calls if argv[:2] == ["verify", "sdk-monitoring"])
    assert "--accept-estimated-token-ledger" in monitoring
    assert "--plan" not in monitoring, "managed serial 无 fanout run_matrix，不得传 --plan"
    scale = next(argv for argv in calls if argv[:2] == ["verify", "scale-readiness"])
    assert "--accept-estimated-token-ledger" in scale


def test_run_recipe_generate_only_stops_after_contract_gate(monkeypatch):
    calls: list[list[str]] = []
    spec = _pilot_spec()
    monkeypatch.setattr(store, "spec_exists", lambda task_id: True)
    monkeypatch.setattr(store, "load_spec", lambda task_id: spec)
    monkeypatch.setattr(recipe_mod, "current_git_branch", lambda cwd=None: "feature/homepage-commercial-lane")

    saved = _clear_recipe_env()
    try:
        recipe_mod.handle_run_recipe(
            argparse.Namespace(
                recipe="content/travel/homepage/pilot",
                batch="", plan="", stage="generate-only", force_task_write=False,
            ),
            invoke=lambda argv: calls.append(list(argv)) or 0,
        )
    finally:
        _restore_recipe_env(saved)
    assert calls == [], "generate-only 不得触发执行/readiness 子命令"


def test_homepage_recipes_keep_mandatory_as_runtime_parameter():
    for ref in ("content/travel/homepage/pilot", "content/travel/homepage/h100"):
        recipe = recipe_mod.load_recipe(ref)
        generate = (recipe.get("task") or {}).get("generate") or {}
        assert "mandatory" not in generate


def test_ensure_task_passes_source_readiness_and_empty_mandatory(monkeypatch):
    """WP5：generate.sourceReadiness 透传 --source-readiness；
    显式空 mandatory（""）也必须透传以覆盖 select-targets 川西五景缺省。"""
    calls: list[list[str]] = []
    monkeypatch.setattr(store, "spec_exists", lambda task_id: False)
    recipe = {
        "recipeId": "content/travel/homepage/prov_test",
        "presetRef": "content/travel/homepage/base",
        "task": {
            "generate": {
                "name": "舟山主页省级试点",
                "discovery": "quwoquan_data/verticals/travel/coverage/中国/浙江省/舟山市.yaml",
                "region": "中国/浙江省/舟山市",
                "limit": 12,
                "mandatory": "",
                "sourceReadiness": "ready",
            }
        },
    }

    recipe_mod._ensure_task(recipe, lambda argv: calls.append(list(argv)) or 0, force=False)

    assert len(calls) == 1
    select = calls[0]
    assert select[:2] == ["task", "select-targets"]
    assert select[select.index("--source-readiness") + 1] == "ready"
    assert select[select.index("--mandatory") + 1] == ""


def test_ensure_task_omits_source_readiness_and_mandatory_when_undeclared(monkeypatch):
    """未声明 sourceReadiness/mandatory 的存量配方不受影响（不注入新参数）。"""
    calls: list[list[str]] = []
    monkeypatch.setattr(store, "spec_exists", lambda task_id: False)
    recipe = {
        "recipeId": "content/travel/homepage/prov_test_default",
        "presetRef": "content/travel/homepage/base",
        "task": {
            "generate": {
                "name": "存量语义回归",
                "discovery": "quwoquan_data/verticals/travel/coverage/discovery_china_scenic_220_20260705.json",
                "limit": 25,
            }
        },
    }

    recipe_mod._ensure_task(recipe, lambda argv: calls.append(list(argv)) or 0, force=False)

    assert len(calls) == 1
    select = calls[0]
    assert "--source-readiness" not in select
    assert "--mandatory" not in select


def test_geo_homepages_delegates_to_run_recipe_with_geo_overrides(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(store, "spec_exists", lambda task_id: False)
    monkeypatch.setattr(recipe_mod, "_contract_gate", lambda recipe, task_id: None)

    recipe_mod.handle_geo_homepages(
        argparse.Namespace(
            profile="pilot",
            country="中国",
            province="四川省",
            city="成都市",
            district="武侯区",
            discovery="quwoquan_data/verticals/travel/coverage/discovery_china_scenic_220_20260705.json",
            limit=7,
            mandatory="武侯祠,黄龙",
            name="",
            title="",
            intent_label="",
            batch="geo_test_batch",
            plan="geo_test_plan",
            stage="generate-only",
            force_task_write=True,
        ),
        invoke=lambda argv: calls.append(list(argv)) or 0,
    )

    assert len(calls) == 1
    select = calls[0]
    assert select[:2] == ["task", "select-targets"]
    assert select[select.index("--region") + 1] == "中国/四川省/成都市/武侯区"
    assert select[select.index("--limit") + 1] == "7"
    assert select[select.index("--name") + 1] == "武侯区景区主页pilot"
    assert select[select.index("--intent-label") + 1] == "武侯区景区主页pilot"
    assert select[select.index("--mandatory") + 1] == "武侯祠,黄龙"


def test_contract_gate_blocks_drift(monkeypatch):
    recipe = recipe_mod.load_recipe("content/travel/homepage/pilot")
    monkeypatch.setattr(recipe_mod, "current_git_branch", lambda cwd=None: "feature/homepage-commercial-lane")

    inactive = _pilot_spec()
    inactive["status"] = "draft"
    monkeypatch.setattr(store, "load_spec", lambda task_id: inactive)
    try:
        recipe_mod._contract_gate(recipe, inactive["taskId"])
        raise AssertionError("status=draft 必须 BLOCK")
    except SystemExit as exc:
        assert "active" in str(exc)

    drifted = _pilot_spec()
    drifted["presetRef"] = "content/travel/article/base"
    monkeypatch.setattr(store, "load_spec", lambda task_id: drifted)
    try:
        recipe_mod._contract_gate(recipe, drifted["taskId"])
        raise AssertionError("presetRef 漂移必须 BLOCK")
    except SystemExit as exc:
        assert "presetRef" in str(exc)

    good = _pilot_spec()
    monkeypatch.setattr(store, "load_spec", lambda task_id: good)
    monkeypatch.setattr(recipe_mod, "current_git_branch", lambda cwd=None: "main")
    try:
        recipe_mod._contract_gate(recipe, good["taskId"])
        raise AssertionError("git 分支不匹配必须 BLOCK")
    except SystemExit as exc:
        assert "git 分支" in str(exc)


def test_resume_until_done_accepts_reasoned_reject_terminal_status(monkeypatch):
    """completed_with_reasoned_rejects 是成功终态：不得空转 resume，直接交 readiness。

    旧代码只认 succeeded，导致 pilot 批次 181 轮空 resume（2h10m 空转）。
    """
    recipe = recipe_mod.load_recipe("content/travel/homepage/pilot")
    calls: list[list[str]] = []
    monkeypatch.setattr(
        recipe_mod, "_workflow_status",
        lambda task_id, batch_id: "completed_with_reasoned_rejects",
    )
    recipe_mod._resume_until_done(
        recipe, "任务", "批次",
        lambda argv: calls.append(list(argv)) or 0,
        sleep_seconds=0,
    )
    assert calls == [], "成功终态不得再触发 task run --resume"


def test_resume_until_done_manual_required_contract_kind_exits(monkeypatch):
    """manual_required 且根因为契约类（含内容配额缺口）→ 立即退出交人工。"""
    recipe = recipe_mod.load_recipe("content/travel/homepage/pilot")
    monkeypatch.setattr(recipe_mod, "_workflow_status", lambda t, b: "manual_required")
    monkeypatch.setattr(recipe_mod, "_workflow_failure_kind", lambda t, b: "contract")
    try:
        recipe_mod._resume_until_done(recipe, "任务", "批次", lambda argv: 0, sleep_seconds=0)
        raise AssertionError("契约类 manual_required 必须退出")
    except SystemExit as exc:
        assert "契约类" in str(exc)


def test_resume_until_done_manual_required_auth_kind_waits_for_key_then_resumes(monkeypatch):
    """manual_required 且根因为凭据/API 限额类 → key 生命周期内置：
    暂停轮询 key 探活（轮换/额度恢复），恢复后自动续跑（收编家目录守护脚本语义）。"""
    recipe = recipe_mod.load_recipe("content/travel/homepage/pilot")
    statuses = iter(["manual_required", "succeeded", "succeeded"])
    key_probes = iter([False, False, True])
    waits: list[float] = []
    resumes: list[list[str]] = []
    monkeypatch.setattr(recipe_mod, "_workflow_status", lambda t, b: next(statuses))
    monkeypatch.setattr(recipe_mod, "_workflow_failure_kind", lambda t, b: "auth")
    recipe_mod._resume_until_done(
        recipe, "任务", "批次",
        lambda argv: resumes.append(list(argv)) or 0,
        sleep_seconds=0,
        probe_cursor_key=lambda: next(key_probes),
        network_wait_sleep=waits.append,
    )
    assert len(waits) == 2, "key 探活两次不通过必须等待两轮退避"
    assert len(resumes) == 1 and resumes[0][:3] == ["task", "run", "--mode"]


def test_resume_until_done_auth_retry_limit_blocks(monkeypatch):
    """凭据恢复等待超过 authRetryLimit → GATE_BLOCK（不无限等 key）。"""
    recipe = {"execution": {"authRetryLimit": 1, "maxAuthorRounds": 10}}
    monkeypatch.setattr(recipe_mod, "_workflow_status", lambda t, b: "manual_required")
    monkeypatch.setattr(recipe_mod, "_workflow_failure_kind", lambda t, b: "auth")
    try:
        recipe_mod._resume_until_done(
            recipe, "任务", "批次", lambda argv: 0,
            sleep_seconds=0,
            probe_cursor_key=lambda: True,
        )
        raise AssertionError("超过 authRetryLimit 必须退出")
    except SystemExit as exc:
        assert "凭据/配额恢复等待超过上限" in str(exc)


def test_resume_until_done_no_progress_watchdog_fails_fast(monkeypatch):
    """no-progress watchdog：连续 noProgressRoundLimit 轮推进指纹无变化且网络正常 → fail-fast。"""
    recipe = {"execution": {"noProgressRoundLimit": 2, "maxAuthorRounds": 50}}
    monkeypatch.setattr(recipe_mod, "_workflow_status", lambda t, b: "waiting_agent")
    monkeypatch.setattr(
        recipe_mod, "_workflow_progress_fingerprint", lambda t, b: "frozen-fingerprint"
    )
    try:
        recipe_mod._resume_until_done(
            recipe, "任务", "批次", lambda argv: 0,
            sleep_seconds=0,
            probe_network=lambda: True,
        )
        raise AssertionError("无进展且网络正常必须 fail-fast")
    except SystemExit as exc:
        assert "no-progress watchdog" in str(exc)


def test_resume_until_done_progress_resets_watchdog(monkeypatch):
    """指纹变化即视为有推进：watchdog 归零，不误杀慢而有进展的批次。"""
    recipe = {"execution": {"noProgressRoundLimit": 2, "maxAuthorRounds": 4}}
    statuses = iter(["waiting_agent", "waiting_agent", "waiting_agent", "waiting_agent",
                     "waiting_agent", "waiting_agent", "succeeded", "succeeded"])
    fingerprints = iter(["a", "b", "c", "d"])
    monkeypatch.setattr(recipe_mod, "_workflow_status", lambda t, b: next(statuses))
    monkeypatch.setattr(
        recipe_mod, "_workflow_progress_fingerprint", lambda t, b: next(fingerprints)
    )
    recipe_mod._resume_until_done(
        recipe, "任务", "批次", lambda argv: 0,
        sleep_seconds=0,
        probe_network=lambda: True,
    )


def test_resume_until_done_manual_required_network_kind_waits_then_resumes(monkeypatch):
    """manual_required 且根因为网络类 → 探测出口自愈后自动 resume（收编体外守护脚本语义）。"""
    recipe = recipe_mod.load_recipe("content/travel/homepage/pilot")
    statuses = iter(["manual_required", "succeeded", "succeeded"])
    probes = iter([False, False, True])
    waits: list[float] = []
    resumes: list[list[str]] = []
    monkeypatch.setattr(recipe_mod, "_workflow_status", lambda t, b: next(statuses))
    monkeypatch.setattr(recipe_mod, "_workflow_failure_kind", lambda t, b: "network")
    recipe_mod._resume_until_done(
        recipe, "任务", "批次",
        lambda argv: resumes.append(list(argv)) or 0,
        sleep_seconds=0,
        probe_network=lambda: next(probes),
        network_wait_sleep=waits.append,
    )
    assert len(waits) == 2, "探测两次不通过必须等待两轮退避"
    assert len(resumes) == 1 and resumes[0][:3] == ["task", "run", "--mode"]


def test_resume_until_done_budget_exceeded_blocks(monkeypatch):
    """resume 循环 wall-clock 预算耗尽 → GATE_BLOCK（防再次无限空转）。"""
    recipe = {"execution": {"resumeBudgetSeconds": 100, "maxAuthorRounds": 10}}
    clock_values = iter([0.0, 200.0])
    monkeypatch.setattr(recipe_mod, "_workflow_status", lambda t, b: "waiting_agent")
    try:
        recipe_mod._resume_until_done(
            recipe, "任务", "批次", lambda argv: 0,
            sleep_seconds=0,
            monotonic=lambda: next(clock_values),
        )
        raise AssertionError("超预算必须退出")
    except SystemExit as exc:
        assert "时间预算" in str(exc)


def test_workflow_failure_kind_classifies_network_vs_contract(monkeypatch):
    """failedObjects/nextAction 文本命中网络标记 → network；否则 contract。"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        state_dir = Path(tmp) / "state"
        state_dir.mkdir()
        state_path = state_dir / "task_workflow_state.json"
        monkeypatch.setattr(
            recipe_mod, "batch_workflow_state_path", lambda t, b: state_path
        )
        state_path.write_text(
            '{"failedObjects": ["黄龙: source discovery infrastructure failure: curl timed out"], "nextAction": ""}',
            encoding="utf-8",
        )
        assert recipe_mod._workflow_failure_kind("任务", "批次") == "network"
        state_path.write_text(
            '{"failedObjects": ["quota shortfall: selected=3 < target=25"], "nextAction": "fix quota"}',
            encoding="utf-8",
        )
        assert recipe_mod._workflow_failure_kind("任务", "批次") == "contract"
        state_path.unlink()
        assert recipe_mod._workflow_failure_kind("任务", "批次") == "contract"


def _frozen_plan(plan_id: str, source_task_id: str) -> dict:
    return {"planId": plan_id, "status": "frozen", "sourceTaskId": source_task_id}


def test_load_frozen_fanout_plan_blocks_unfrozen_and_source_mismatch(monkeypatch):
    """fanout_partition 前置门：计划必须冻结且 sourceTaskId 等于配方任务。"""
    from _common import fanout_plan as fp

    monkeypatch.setattr(fp, "load_plan", lambda plan_id: None)
    try:
        recipe_mod._load_frozen_fanout_plan("缺失计划", "任务A")
        raise AssertionError("计划缺失必须 BLOCK")
    except SystemExit as exc:
        assert "已冻结计划" in str(exc)

    monkeypatch.setattr(fp, "load_plan", lambda plan_id: {"planId": plan_id, "status": "draft", "sourceTaskId": "任务A"})
    try:
        recipe_mod._load_frozen_fanout_plan("草稿计划", "任务A")
        raise AssertionError("未冻结必须 BLOCK")
    except SystemExit as exc:
        assert "未冻结" in str(exc)

    monkeypatch.setattr(fp, "load_plan", lambda plan_id: _frozen_plan(plan_id, "任务B"))
    try:
        recipe_mod._load_frozen_fanout_plan("错源计划", "任务A")
        raise AssertionError("sourceTaskId 漂移必须 BLOCK")
    except SystemExit as exc:
        assert "sourceTaskId" in str(exc)

    monkeypatch.setattr(fp, "load_plan", lambda plan_id: _frozen_plan(plan_id, "任务A"))
    plan = recipe_mod._load_frozen_fanout_plan("好计划", "任务A")
    assert plan["status"] == "frozen"


def test_execute_fanout_partition_invokes_scaled_e2e_without_source_task(monkeypatch):
    """fanout_partition 执行契约：scaled-e2e run 必须 --skip-prepare 且不带
    --source-task/--source-batch（带上会塌缩成源任务串行，绕过分区编排）；
    成功后不得进入 managed serial resume 循环。"""
    calls: list[list[str]] = []
    monkeypatch.setattr(recipe_mod, "_load_frozen_fanout_plan", lambda plan_id, task_id: _frozen_plan(plan_id, task_id))
    monkeypatch.setattr(
        recipe_mod, "_resume_until_done",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("fanout_partition 不得进入 resume 循环")),
    )
    recipe = {
        "execution": {
            "mode": "fanout_partition",
            "strategy": "by-partition",
            "concurrency": 2,
            "maxWorkers": 2,
            "cycles": 4,
            "runtime": "local",
            "model": "composer",
            "startupTimeoutSeconds": 240,
        }
    }
    recipe_mod._execute(recipe, "任务A", "批次A", "计划A", lambda argv: calls.append(list(argv)) or 0)

    assert len(calls) == 1
    argv = calls[0]
    assert argv[:3] == ["task", "scaled-e2e", "run"]
    assert "--skip-prepare" in argv
    assert "--source-task" not in argv and "--source-batch" not in argv
    assert argv[argv.index("--plan") + 1] == "计划A"
    assert argv[argv.index("--strategy") + 1] == "by-partition"
    assert argv[argv.index("--max-workers") + 1] == "2"
    assert argv[argv.index("--cycles") + 1] == "4"

    # execute 非零（聚合 verify 未过）不得在此终止：GO/NO-GO 由 readiness 判定
    # （trial+failOnNoGo=false 记录证据放行；strict 仍 NO-GO 非零退出）。
    recipe_mod._execute(recipe, "任务A", "批次A", "计划A", lambda argv: 1)


def test_fanout_partition_readiness_aggregates_per_unit(monkeypatch):
    """fanout_partition readiness 契约：逐分区 audit-batch / sdk-monitoring(--plan)
    / scale-readiness，全部单元评完聚合裁决并落 fanout_readiness_aggregate.json。"""
    from _common import fanout_strategies as fs

    units = [
        {"taskId": "任务A__p1", "batchId": "fanout_计划A", "partitionPath": ["浙江省", "舟山市", "普陀区"],
         "leaves": [{"ref": f"r{i}"} for i in range(3)]},
        {"taskId": "任务A__p2", "batchId": "fanout_计划A", "partitionPath": ["浙江省", "舟山市", "定海区"],
         "leaves": [{"ref": f"s{i}"} for i in range(2)]},
    ]
    monkeypatch.setattr(recipe_mod, "_load_frozen_fanout_plan", lambda plan_id, task_id: _frozen_plan(plan_id, task_id))
    monkeypatch.setattr(fs, "expand_units", lambda plan: units)
    recipe = {
        "execution": {"mode": "fanout_partition"},
        "readiness": {"mode": "trial", "minPassRate": 0.85, "acceptEstimatedTokenLedger": True},
    }
    calls: list[list[str]] = []
    with tempfile.TemporaryDirectory(prefix="qwq_fanout_readiness_") as tmp:
        recipe_mod._readiness(recipe, "任务A", "批次A", "计划A", lambda argv: calls.append(list(argv)) or 0, Path(tmp))
        import json as _json

        aggregate = _json.loads((Path(tmp) / "fanout_readiness_aggregate.json").read_text(encoding="utf-8"))

    audits = [argv for argv in calls if argv[:2] == ["task", "audit-batch"]]
    monitorings = [argv for argv in calls if argv[:2] == ["verify", "sdk-monitoring"]]
    scales = [argv for argv in calls if argv[:2] == ["verify", "scale-readiness"]]
    assert len(audits) == len(monitorings) == len(scales) == 2
    for argv in monitorings:
        assert argv[argv.index("--plan") + 1] == "计划A"
        assert "--accept-estimated-token-ledger" in argv
        # trial 只记录监控卫生证据（多轮 resume 批次历史计数器必然非零）；
        # --strict 硬失败留给 commercial。
        assert "--strict" not in argv
    # per-unit target=叶子数。
    assert scales[0][scales[0].index("--target") + 1] == "3"
    assert scales[1][scales[1].index("--target") + 1] == "2"
    assert aggregate["decision"] == "GO"
    assert aggregate["unitCount"] == 2 and aggregate["passedUnits"] == 2

    # scale-readiness NO-GO 且 failOnNoGo 缺省 true → BLOCK。
    def _invoke_nogo(argv: list[str]) -> int:
        return 1 if argv[:2] == ["verify", "scale-readiness"] else 0

    with tempfile.TemporaryDirectory(prefix="qwq_fanout_readiness_") as tmp:
        try:
            recipe_mod._readiness(recipe, "任务A", "批次A", "计划A", _invoke_nogo, Path(tmp))
            raise AssertionError("NO-GO 必须 BLOCK")
        except SystemExit as exc:
            assert "NO-GO" in str(exc)

    # commercial 模式必须保持 sdk-monitoring --strict 硬失败语义。
    commercial = {
        "execution": {"mode": "fanout_partition"},
        "readiness": {"mode": "commercial", "acceptEstimatedTokenLedger": True},
    }
    commercial_calls: list[list[str]] = []
    with tempfile.TemporaryDirectory(prefix="qwq_fanout_readiness_") as tmp:
        recipe_mod._readiness(
            commercial, "任务A", "批次A", "计划A",
            lambda argv: commercial_calls.append(list(argv)) or 0, Path(tmp),
        )
    for argv in commercial_calls:
        if argv[:2] == ["verify", "sdk-monitoring"]:
            assert "--strict" in argv


def test_family_instructions_recipe_refs_all_exist():
    """收债 5：仓内 instructions.md 引用的 run-recipe ref 必须真实存在。"""
    errors = recipe_mod.lint_family_instructions()
    assert errors == [], errors


def test_lint_family_instructions_blocks_dangling_recipe_ref():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        family = root / "content" / "travel" / "homepage"
        family.mkdir(parents=True)
        (family / "ok.recipe.yaml").write_text("recipeId: content/travel/homepage/ok\n", encoding="utf-8")
        (family / "homepage.instructions.md").write_text(
            "运行：qwq-data task run-recipe content/travel/homepage/ok\n"
            "旧配方：qwq-data task run-recipe content/travel/homepage/retired\n",
            encoding="utf-8",
        )
        errors = recipe_mod.lint_family_instructions(root)
        assert len(errors) == 1
        assert "content/travel/homepage/retired" in errors[0]


def test_lint_recipe_rejects_structural_drift():
    doc = recipe_mod.load_recipe("content/travel/homepage/pilot")
    bad = dict(doc)
    bad["recipeId"] = "content/travel/homepage/别名"
    errors = recipe_mod.lint_recipe(bad, "content/travel/homepage/pilot")
    assert any("recipeId" in e for e in errors)

    bad_mode = dict(doc)
    bad_mode["execution"] = {"mode": "shell_loop"}
    errors = recipe_mod.lint_recipe(bad_mode, "content/travel/homepage/pilot")
    assert any("execution.mode" in e for e in errors)

    bad_env = dict(doc)
    bad_env["env"] = {"K": 1}
    errors = recipe_mod.lint_recipe(bad_env, "content/travel/homepage/pilot")
    assert any("env" in e for e in errors)


if __name__ == "__main__":
    class _MonkeyPatch:
        def __init__(self) -> None:
            self._saved: list[tuple[object, str, object]] = []

        def setattr(self, target: object, name: str, value: object) -> None:
            self._saved.append((target, name, getattr(target, name)))
            setattr(target, name, value)

        def undo(self) -> None:
            for target, name, value in reversed(self._saved):
                setattr(target, name, value)
            self._saved.clear()

    failures = 0
    for fn_name, fn in sorted(
        (k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)
    ):
        mp = _MonkeyPatch()
        try:
            fn(mp) if fn.__code__.co_argcount else fn()
            print(f"PASS {fn_name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {fn_name}: {exc}")
        finally:
            mp.undo()
    raise SystemExit(1 if failures else 0)
