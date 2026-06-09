"""fanout_runner contract tests（注入 mock agent_runner，不依赖真实云端）。

覆盖：lease→complete 回写、run 失败分流、startup 失败退避、usage 回写、端到端 drain。

可直接运行：python3 quwoquan_data/tests/orchestrate/test_fanout_runner.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
REPO_ROOT = DATA_ROOT.parent
for _path in (DATA_ROOT, SCRIPTS_ROOT, REPO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = tempfile.mkdtemp(prefix="qwq_fanout_runner_test_")
os.environ["QWQ_RUNTIME_ROOT"] = str(Path(_TMP) / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(Path(_TMP) / "tasks")

from _common import fanout_plan as fp  # noqa: E402
from task import fanout_dispatch as fd  # noqa: E402
from task import object_queue as oq  # noqa: E402
from agent_ops.runners import fanout_runner as fr  # noqa: E402


def _frozen(plan_id: str, names: list[str]) -> dict:
    plan = fp.new_plan(plan_id, "四川景点主页", "travel", defaults={"entityType": "地点/景区"})
    fp.add_partition(plan, "四川省")
    fp.add_leaves(plan, ["四川省"], [{"name": n} for n in names])
    fp.freeze_plan(plan, confirmed=True)
    fp.save_plan(plan)
    return plan


def test_all_pass_completes_all():
    plan = _frozen("r_pass", ["九寨沟", "稻城亚丁"])
    fd.dispatch(plan, strategy="flat-pool", concurrency=1)

    def runner(_packet):
        return fr.RunOutcome(started=True, status="finished", passed=True, tokens=100, cost_usd=0.01)

    report = fr.run_fanout("r_pass", agent_runner=runner, strategy="flat-pool", concurrency=1)
    assert report["completed"] == 2
    assert report["failed"] == 0
    sc = "旅行/地域/四川省/四川景点主页"
    summary = oq.queue_summary(sc, "fanout_r_pass")
    assert summary["byState"].get("succeeded") == ["地点_景区__九寨沟", "地点_景区__稻城亚丁"]


def test_run_failure_marks_failed_or_dead():
    plan = _frozen("r_fail", ["九寨沟"])
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)

    def runner(_packet):
        return fr.RunOutcome(started=True, status="error", passed=False, error="gate not approved",
                             fingerprint="fp1")

    report = fr.run_fanout("r_fail", agent_runner=runner, strategy="by-leaf", concurrency=1)
    assert report["failed"] >= 1
    sc = "旅行/地域/四川省/四川景点主页"
    # maxAttempts 默认 2：单次失败后应为 failed（退避）或 dead，不应 succeeded
    summary = oq.queue_summary(sc, "fanout_r_fail")
    assert "succeeded" not in summary["byState"]


def test_startup_failure_does_not_complete():
    plan = _frozen("r_startup", ["九寨沟"])
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)

    def runner(_packet):
        return fr.RunOutcome(started=False, error="CURSOR_API_KEY missing", retryable=False)

    report = fr.run_fanout("r_startup", agent_runner=runner, strategy="by-leaf", concurrency=1)
    assert report["completed"] == 0
    assert report["startupFailures"] >= 1


def test_usage_recorded_and_budget_enforced():
    plan = fp.new_plan("r_budget", "四川景点主页", "travel",
                       defaults={"entityType": "地点/景区", "budget": {"maxWallClockSeconds": 1200, "maxAttempts": 2, "tokenBudget": 50}})
    fp.add_partition(plan, "四川省")
    fp.add_leaves(plan, ["四川省"], [{"name": "九寨沟"}])
    fp.freeze_plan(plan, confirmed=True)
    fp.save_plan(plan)
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)

    def runner(_packet):
        # 用量超 tokenBudget=50 → record_usage 强制 dead；passed 也不应 complete
        return fr.RunOutcome(started=True, status="finished", passed=True, tokens=200)

    fr.run_fanout("r_budget", agent_runner=runner, strategy="by-leaf", concurrency=1)
    sc = "旅行/地域/四川省/四川景点主页"
    summary = oq.queue_summary(sc, "fanout_r_budget")
    # 预算超支强制 dead，complete 应失败（lease 已失效）→ 不进 succeeded
    assert "succeeded" not in summary["byState"]
    notes = oq.list_notifications(sc, "fanout_r_budget")
    assert any(n.get("event") == "budget_exceeded" for n in notes)


def test_orchestrator_packet_has_no_prose_and_targets_checkpoints():
    packet = fr.build_orchestrator_packet(
        {"taskId": "旅行/地域/四川省/x", "batchId": "fanout_x"},
        partition_path=["四川省"], refs=["地点_景区__九寨沟"],
    )
    assert packet["role"] == "orchestrator"
    assert packet["checkpoints"] == list(fr.ORCHESTRATOR_CHECKPOINTS)
    assert packet["until"] == fr.ORCHESTRATOR_UNTIL
    # 合约只含命令/checkpoint 语义/禁止项，不得含成文正文句子。
    contract = packet["executionContract"]
    assert "workflow run" in contract["command"]
    assert set(contract["checkpointSemantics"]) == set(fr.ORCHESTRATOR_CHECKPOINTS)
    assert any("CC" in f or "纯色块" in f for f in contract["forbidden"])


def test_by_partition_orchestrates_then_authors_leaves():
    plan = _frozen("r_orch", ["九寨沟", "稻城亚丁"])
    fd.dispatch(plan, strategy="by-partition", concurrency=1)
    sc = "旅行/地域/四川省/四川景点主页"

    # orchestrator 校验：注入「已到位」的 workflow_state（三 checkpoint 完成），再分发叶子。
    from task.run import load_workflow_state, save_workflow_state
    state = load_workflow_state(sc, "fanout_r_orch")
    state["completed"] = list(fr.ORCHESTRATOR_CHECKPOINTS)
    save_workflow_state(state)

    seen_roles: list[str] = []

    def orch(_packet):
        seen_roles.append("orchestrator")
        return fr.RunOutcome(started=True, status="finished", passed=True)

    def leaf(_packet):
        seen_roles.append("leaf")
        return fr.RunOutcome(started=True, status="finished", passed=True)

    report = fr.run_fanout(
        "r_orch", agent_runner=leaf, orchestrator_runner=orch,
        strategy="by-partition", concurrency=1,
    )
    assert report["orchestrated"] == 1
    assert report["orchestrationFailed"] == 0
    assert report["completed"] == 2  # checkpoint 到位后叶子被授权
    assert "orchestrator" in seen_roles and "leaf" in seen_roles


def test_orchestrator_checkpoint_gap_blocks_leaf_dispatch():
    plan = _frozen("r_orch_gap", ["九寨沟"])
    fd.dispatch(plan, strategy="by-partition", concurrency=1)
    # 不预置 workflow_state（三 checkpoint 未完成）→ orchestrate 校验不通过 → 不分发叶子。

    leaf_calls = {"n": 0}

    def orch(_packet):
        return fr.RunOutcome(started=True, status="finished", passed=True)

    def leaf(_packet):
        leaf_calls["n"] += 1
        return fr.RunOutcome(started=True, status="finished", passed=True)

    report = fr.run_fanout(
        "r_orch_gap", agent_runner=leaf, orchestrator_runner=orch,
        strategy="by-partition", concurrency=1,
    )
    assert report["orchestrationFailed"] == 1
    assert report["completed"] == 0
    assert leaf_calls["n"] == 0  # checkpoint 未到位，叶子不被空跑


def test_orchestrator_startup_failure_blocks_leaf_dispatch():
    plan = _frozen("r_orch_startup", ["九寨沟"])
    fd.dispatch(plan, strategy="by-partition", concurrency=1)

    def orch(_packet):
        return fr.RunOutcome(started=False, error="CURSOR_API_KEY missing", retryable=False)

    def leaf(_packet):
        raise AssertionError("leaf must not run when orchestrator failed to start")

    report = fr.run_fanout(
        "r_orch_startup", agent_runner=leaf, orchestrator_runner=orch,
        strategy="by-partition", concurrency=1,
    )
    assert report["orchestrationFailed"] == 1
    assert report["completed"] == 0
    assert report["orchestrations"][0]["started"] is False


def test_runtime_selects_local_cwd_vs_cloud_repos():
    """_build_agent_options：local 走 cwd（本机写仓库），cloud 走 repos（clone VM）。"""
    import types

    captured: dict[str, dict] = {}

    def _AgentOptions(**kw):
        captured["agent"] = kw
        return kw

    def _LocalAgentOptions(**kw):
        captured["local"] = kw
        return ("local", kw)

    def _CloudAgentOptions(**kw):
        captured["cloud"] = kw
        return ("cloud", kw)

    fake = types.SimpleNamespace(
        AgentOptions=_AgentOptions,
        LocalAgentOptions=_LocalAgentOptions,
        CloudAgentOptions=_CloudAgentOptions,
    )
    sys.modules["cursor_sdk"] = fake
    try:
        local_opts = fr._build_agent_options(
            api_key="k", model="composer-2.5", runtime=fr.RUNTIME_LOCAL, cwd="/repo", repos=None
        )
        assert local_opts["local"] == ("local", {"cwd": "/repo"})
        assert "cloud" not in local_opts
        cloud_opts = fr._build_agent_options(
            api_key="k", model="composer-2.5", runtime=fr.RUNTIME_CLOUD, cwd=None,
            repos=[{"repository": "r"}],
        )
        assert cloud_opts["cloud"] == ("cloud", {"repos": [{"repository": "r"}]})
        assert "local" not in cloud_opts
    finally:
        del sys.modules["cursor_sdk"]


def test_missing_key_blocks_both_runtimes():
    """无 CURSOR_API_KEY 时 local/cloud 均启动失败（不会偷偷本机裸跑）。"""
    saved = os.environ.pop("CURSOR_API_KEY", None)
    try:
        for rt in fr.VALID_RUNTIMES:
            out = fr.default_agent_runner({"ref": "x"}, runtime=rt, api_key=None)
            assert out.started is False
    finally:
        if saved is not None:
            os.environ["CURSOR_API_KEY"] = saved


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"fanout_runner tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
