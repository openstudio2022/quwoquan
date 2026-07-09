"""Local contract: 并发横向扩展两件套。

1. Cursor bridge 启动锁默认 per-workspace（解多 clone/多机全局串行），但同 workspace 内仍串行；
   显式 ``QWQ_CURSOR_BRIDGE_LAUNCH_LOCK`` 仍可强制 host-global 共享锁。
2. ``throughput-plan`` 容量推算确定性、量化诚实（单篇耗时 × 通道 → 可达日产 + 约束分层）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from support.task_workflow_fixtures import *  # noqa: F401,F403

from _common.throughput_plan import (
    RUNTIME_CLOUD,
    RUNTIME_LOCAL,
    ThroughputConfig,
    compute_throughput_plan,
)

_CLI = Path(__file__).resolve().parents[3] / "scripts" / "cli.py"


# ---------- bridge 启动锁：per-workspace ----------

def test_bridge_launch_lock_is_per_workspace_by_default(monkeypatch):
    monkeypatch.delenv("QWQ_CURSOR_BRIDGE_LAUNCH_LOCK", raising=False)
    monkeypatch.delenv("QWQ_MANAGED_LOCAL_LOCK_DIR", raising=False)
    a = run_mod._cursor_bridge_launch_lock_path("/work/clone-a")
    b = run_mod._cursor_bridge_launch_lock_path("/work/clone-b")
    a_again = run_mod._cursor_bridge_launch_lock_path("/work/clone-a")
    # 不同 workspace clone 锁文件不同 → 启动可并行；同 workspace 稳定同一锁 → 内部仍串行。
    assert a != b
    assert a == a_again
    assert a.name.startswith("qwq-cursor-bridge-launch-")
    assert a.name.endswith(".lock")


def test_bridge_launch_lock_env_override_forces_shared(monkeypatch):
    monkeypatch.setenv("QWQ_CURSOR_BRIDGE_LAUNCH_LOCK", "/tmp/shared-host-global.lock")
    a = run_mod._cursor_bridge_launch_lock_path("/work/clone-a")
    b = run_mod._cursor_bridge_launch_lock_path("/work/clone-b")
    # 运维显式要求 host-global 串行时，所有 workspace 收敛到同一把锁。
    assert a == b == Path("/tmp/shared-host-global.lock")


def test_bridge_launch_lock_dir_is_redirectable(monkeypatch, tmp_path):
    monkeypatch.delenv("QWQ_CURSOR_BRIDGE_LAUNCH_LOCK", raising=False)
    monkeypatch.setenv("QWQ_MANAGED_LOCAL_LOCK_DIR", str(tmp_path))
    path = run_mod._cursor_bridge_launch_lock_path("/work/clone-a")
    assert path.parent == tmp_path


# ---------- throughput-plan：确定性容量推算 ----------

def test_throughput_plan_blended_matches_validated_channel_estimate():
    # 实测基线（warm 32s / cold 62s / 85% 首过 / 80% 利用）下，十万日产 blended 所需通道 ≈ 验收估算 78。
    plan = compute_throughput_plan(ThroughputConfig(daily_target=100_000, channels=1))
    assert plan.primary_scenario == "blended"
    assert 70 <= plan.required_channels_for_target <= 90
    assert plan.meets_target is False
    labels = {s.label for s in plan.scenarios}
    assert labels == {"warm", "cold", "blended"}


def test_throughput_plan_is_deterministic():
    cfg = ThroughputConfig(daily_target=100_000, channels=42, runtime=RUNTIME_CLOUD)
    first = compute_throughput_plan(cfg).to_report()
    second = compute_throughput_plan(cfg).to_report()
    assert first == second


def test_throughput_plan_scales_linearly_with_channels():
    one = compute_throughput_plan(ThroughputConfig(channels=1))
    eighty = compute_throughput_plan(ThroughputConfig(channels=80))
    per_channel = one.achievable_daily_at_configured_channels
    assert eighty.achievable_daily_at_configured_channels == per_channel * 80
    # 足够通道后可达目标。
    assert eighty.meets_target is True


def test_throughput_plan_local_runtime_reports_machine_fanout():
    plan = compute_throughput_plan(
        ThroughputConfig(daily_target=100_000, channels=3, runtime=RUNTIME_LOCAL,
                         local_bridge_cap_per_machine=3)
    )
    # 单机本地受 bridge 冷启上限封顶，须靠多机横向铺开。
    assert plan.required_local_machines >= 20
    kinds = {c.kind for c in plan.constraints}
    assert "code_addressable" in kinds
    assert "external" in kinds
    assert any("机器" in c.summary for c in plan.constraints if c.kind == "external")


def test_throughput_plan_cloud_runtime_flags_platform_quota():
    plan = compute_throughput_plan(
        ThroughputConfig(daily_target=100_000, channels=1, runtime=RUNTIME_CLOUD)
    )
    assert plan.required_local_machines == plan.required_channels_for_target
    assert any(
        "配额" in c.summary for c in plan.constraints if c.kind == "external"
    )


def test_throughput_plan_normalizes_invalid_input():
    plan = compute_throughput_plan(
        ThroughputConfig(channels=0, first_pass_rate=5.0, utilization=-1.0,
                         runtime="bogus", warm_seconds_per_article=0.0)
    )
    assert plan.config.channels >= 1
    assert plan.config.first_pass_rate <= 1.0
    assert plan.config.utilization > 0.0
    assert plan.config.runtime == RUNTIME_CLOUD
    assert plan.config.warm_seconds_per_article >= 1.0


# ---------- CLI 接线 ----------

def test_cli_throughput_plan_emits_report():
    proc = subprocess.run(
        [sys.executable, str(_CLI), "task", "throughput-plan",
         "--runtime", "cloud", "--channels", "80"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["schemaVersion"] == "quwoquan_data.throughput_plan/1"
    assert report["meetsTarget"] is True
    assert report["input"]["channels"] == 80
    assert {s["label"] for s in report["scenarios"]} == {"warm", "cold", "blended"}


def test_cli_throughput_plan_require_feasible_exit_code():
    proc = subprocess.run(
        [sys.executable, str(_CLI), "task", "throughput-plan",
         "--runtime", "local", "--channels", "1", "--require-feasible"],
        capture_output=True, text=True, timeout=120,
    )
    # 单通道远不可达十万 → require-feasible 非零退出，便于放量门禁。
    assert proc.returncode == 1
