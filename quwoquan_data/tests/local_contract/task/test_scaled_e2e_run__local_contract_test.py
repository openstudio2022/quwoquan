from __future__ import annotations

import argparse
import os
from pathlib import Path

from task import scaled_e2e


def _args(**overrides):
    data = {
        "task": "旅行/地域/四川省/景区/fixture",
        "batch": "batch_1",
        "plan": "plan_1",
        "catalog": None,
        "strategy": "by-batch",
        "concurrency": 2,
        "max_workers": 2,
        "runtime": "local",
        "model": "composer",
        "cwd": "/tmp/workspace",
        "spend_limit": None,
        "cycles": 2,
        "reset_state": False,
        "skip_prepare": False,
        "skip_startup_probe": False,
        "startup_timeout_seconds": 180.0,
        "force_clean_workspace_agent_state": True,
        "source_task": None,
        "source_batch": None,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


def test_scaled_e2e_run_sequences_prepare_author_finalize_verify():
    calls: list[argparse.Namespace] = []

    def invoke(ns):
        calls.append(ns)

    scaled_e2e._handle_scaled_e2e_run(_args(cycles=1), invoke=invoke)

    assert [ns.scaled_e2e_command for ns in calls] == [
        "prepare",
        "fanout-author",
        "author-runner",
        "rollup",
        "finalize",
        "rollup",
        "verify",
    ]
    prepare = calls[0]
    assert prepare.runtime == "local"
    assert prepare.model == "composer"
    assert prepare.cwd == "/tmp/workspace"
    assert prepare.startup_timeout_seconds == 180.0
    assert prepare.force_clean_workspace_agent_state is True
    finalize = calls[4]
    assert finalize.runtime == "local"
    assert finalize.model == "composer"
    assert finalize.cwd == "/tmp/workspace"
    assert finalize.startup_timeout_seconds == 180.0
    assert finalize.force_clean_workspace_agent_state is True


def test_scaled_e2e_run_propagates_source_task_target():
    calls: list[argparse.Namespace] = []

    def invoke(ns):
        calls.append(ns)

    scaled_e2e._handle_scaled_e2e_run(
        _args(
            skip_prepare=True,
            cycles=1,
            source_task="旅行/地域/四川省/景区/源任务",
            source_batch="source_batch_1",
        ),
        invoke=invoke,
    )

    author = next(ns for ns in calls if ns.scaled_e2e_command == "author-runner")
    finalize = next(ns for ns in calls if ns.scaled_e2e_command == "finalize")
    verify = next(ns for ns in calls if ns.scaled_e2e_command == "verify")
    for ns in (author, finalize, verify):
        assert ns.source_task == "旅行/地域/四川省/景区/源任务"
        assert ns.source_batch == "source_batch_1"


def test_scaled_e2e_prepare_uses_managed_local_runtime_and_cwd(monkeypatch, tmp_path):
    from data import baseline as baseline_mod
    from explore import handler as explore_handler

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        scaled_e2e.store,
        "load_spec",
        lambda _task: {"scope": {"region": "四川省", "entityTypes": ["景区"]}},
    )
    monkeypatch.setattr(explore_handler, "handle_explore", lambda _ns: None)
    monkeypatch.setattr(baseline_mod, "handle_baseline", lambda _ns: None)

    def _handle_run(ns):
        captured["cwd"] = os.getcwd()
        captured["ns"] = ns

    monkeypatch.setattr(scaled_e2e.run_mod, "handle_run", _handle_run)

    scaled_e2e.handle_scaled_e2e(
        argparse.Namespace(
            scaled_e2e_command="prepare",
            task="旅行/地域/四川省/景区/fixture",
            batch="batch_1",
            plan="plan_1",
            catalog=None,
            reset_state=False,
            max_workers=2,
            runtime="local",
            model="composer",
            cwd=str(tmp_path),
            startup_timeout_seconds=180.0,
            force_clean_workspace_agent_state=True,
        )
    )

    ns = captured["ns"]
    assert captured["cwd"] == str(tmp_path)
    assert ns.managed is False
    assert ns.runtime == "local"
    assert ns.model == "composer"
    assert ns.until == "produce_compose"
    assert ns.startup_timeout_seconds == 180.0
    assert ns.force_clean_workspace_agent_state is True


def test_scaled_e2e_run_retries_after_verify_failure():
    calls: list[str] = []
    verify_count = 0

    def invoke(ns):
        nonlocal verify_count
        calls.append(ns.scaled_e2e_command)
        if ns.scaled_e2e_command == "verify":
            verify_count += 1
            if verify_count == 1:
                raise SystemExit(1)

    scaled_e2e._handle_scaled_e2e_run(_args(skip_prepare=True, cycles=2), invoke=invoke)

    assert calls.count("fanout-author") == 1
    assert calls.count("author-runner") == 2
    assert calls.count("finalize") == 2
    assert calls.count("verify") == 2


def test_scaled_e2e_run_survives_author_runner_and_finalize_nonzero_exit():
    """WP5 修复契约：author-runner / finalize 的非零退出（如分区 orchestrator 冷启
    Connection refused → fanout_runner rc=2）不得终止 run 的 cycle 闭环；未到位
    分区必须能在下一轮 author-runner 幂等重试，最终由 verify 统一裁决。"""
    calls: list[str] = []
    author_count = 0
    verify_count = 0

    def invoke(ns):
        nonlocal author_count, verify_count
        calls.append(ns.scaled_e2e_command)
        if ns.scaled_e2e_command == "author-runner":
            author_count += 1
            if author_count == 1:
                raise SystemExit(2)
        if ns.scaled_e2e_command == "finalize":
            if author_count == 1:
                raise SystemExit(1)
        if ns.scaled_e2e_command == "verify":
            verify_count += 1
            if verify_count == 1:
                raise SystemExit(1)

    scaled_e2e._handle_scaled_e2e_run(_args(skip_prepare=True, cycles=2), invoke=invoke)

    assert calls.count("author-runner") == 2, calls
    assert calls.count("finalize") == 2, calls
    assert calls.count("verify") == 2, calls


def test_recipe_executor_does_not_mutate_workflow_state_json():
    # 旧 quwoquan_ops/runners/*_resume_loop.sh 曾在编排层直接改写 workflow_state.json
    # （controllerYield/controller_lease），该反模式禁止在唯一编排主干 recipe.py 回归：
    # 编排层只能经 CLI 子命令间接推进 workflow，不得内联篡改状态文件。
    recipe_path = Path(scaled_e2e.__file__).resolve().parent / "recipe.py"
    text = recipe_path.read_text(encoding="utf-8")

    assert "controllerYield" not in text
    assert "activeAgentScheduler" not in text
    assert "controller_lease" not in text
    # workflow 状态只读（batch_workflow_state_path 读取终态），编排层不得直写任何状态文件。
    assert ".write_text(" not in text
    assert "json.dump" not in text
