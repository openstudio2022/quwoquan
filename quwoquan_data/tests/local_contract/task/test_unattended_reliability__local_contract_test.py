"""P6 无人托管可靠性契约：错峰冷启释放器 + per-worker warm bridge + 冷启并发上限 +
吞吐/connection-refused 量化 + cloud orchestrator 硬超时看门狗。

注入 mock，不依赖真实云端。可直接运行：
    python3 quwoquan_data/tests/local_contract/task/test_unattended_reliability__local_contract_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
REPO_ROOT = DATA_ROOT.parent
for _path in (DATA_ROOT, SCRIPTS_ROOT, REPO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = tempfile.mkdtemp(prefix="qwq_p6_reliability_test_")
os.environ["QWQ_RUNTIME_ROOT"] = str(Path(_TMP) / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(Path(_TMP) / "tasks")
os.environ["QWQ_STARTUP_PROBE_BACKOFF_SECONDS"] = "0"
os.environ["QWQ_STARTUP_PROBE_MAX_ATTEMPTS"] = "1"
# 错峰真睡置 0，保持契约测试快速确定（间隔语义用注入时钟单独断言）。
os.environ["QWQ_FANOUT_WORKER_STAGGER_SECONDS"] = "0"

from _common import fanout_plan as fp  # noqa: E402
from _common.io import read_json  # noqa: E402
from _common.paths import fanout_run_matrix_path  # noqa: E402
from task import fanout_dispatch as fd  # noqa: E402
from task import object_queue as oq  # noqa: E402
from task import fanout_runner as fr  # noqa: E402


def _frozen(plan_id: str, names: list[str]) -> dict:
    plan = fp.new_plan(plan_id, "四川景点主页", "travel", defaults={"entityType": "地点/景区"})
    fp.add_partition(plan, "四川省")
    fp.add_leaves(plan, ["四川省"], [{"name": n} for n in names])
    fp.freeze_plan(plan, confirmed=True)
    fp.save_plan(plan)
    return plan


def test_cold_start_releaser_spaces_successive_cold_starts():
    """错峰冷启：相邻放行间至少间隔 min_interval（注入时钟，不真睡）。"""
    now = {"t": 0.0}
    slept: list[float] = []

    def _clock() -> float:
        return now["t"]

    def _sleep(seconds: float) -> None:
        slept.append(seconds)
        now["t"] += seconds

    releaser = fr._ColdStartReleaser(10.0, sleep=_sleep, clock=_clock)
    assert releaser.wait() == 0.0  # 第一个 worker 立即放行
    # 第二个 worker 紧接着到达（时间未推进）→ 必须错峰等满 10s。
    waited = releaser.wait()
    assert waited == 10.0
    assert slept == [10.0]
    assert releaser.releases == 2
    assert releaser.total_wait_seconds == 10.0


def test_cold_start_releaser_zero_interval_never_waits():
    releaser = fr._ColdStartReleaser(0.0)
    assert releaser.wait() == 0.0
    assert releaser.wait() == 0.0
    assert releaser.releases == 2
    assert releaser.total_wait_seconds == 0.0


def test_is_connection_refused_classification():
    assert fr._is_connection_refused("Bridge request failed: ConnectError: [Errno 61] Connection refused")
    assert fr._is_connection_refused("ConnectError while launching bridge")
    assert fr._is_connection_refused("connection reset by peer")
    assert not fr._is_connection_refused("gate not approved")
    assert not fr._is_connection_refused(None)


def test_run_assignment_invokes_cold_start_gate_and_prewarm_once():
    """run_assignment 进 lease 循环前：错峰放行一次 + per-worker 预建 warm bridge 一次，并记入 stats。"""
    gate_calls = {"n": 0}
    prewarm_calls = {"n": 0}

    def _gate() -> float:
        gate_calls["n"] += 1
        return 3.5

    def _prewarm() -> fr.RunOutcome:
        prewarm_calls["n"] += 1
        return fr.RunOutcome(started=True, status="finished", passed=True)

    def _agent(_packet):
        raise AssertionError("no jobs to lease in empty assignment")

    stats = fr.run_assignment(
        {"assignmentId": "w0", "targets": [], "refs": []},
        agent_runner=_agent,
        cold_start_gate=_gate,
        prewarm_runner=_prewarm,
    )
    assert gate_calls["n"] == 1
    assert prewarm_calls["n"] == 1
    assert stats.prewarmed is True
    assert stats.cold_start_wait_seconds == 3.5
    assert stats.prewarm_error is None


def test_run_assignment_records_prewarm_failure_without_crashing():
    def _prewarm() -> fr.RunOutcome:
        return fr.RunOutcome(
            started=False,
            error="Bridge request failed: ConnectError: [Errno 61] Connection refused",
            retryable=True,
        )

    stats = fr.run_assignment(
        {"assignmentId": "w0", "targets": [], "refs": []},
        agent_runner=lambda _p: fr.RunOutcome(started=True, status="finished", passed=True),
        prewarm_runner=_prewarm,
    )
    assert stats.prewarmed is False
    assert "Connection refused" in (stats.prewarm_error or "")


def test_run_fanout_report_quantifies_throughput_and_connection_refused():
    plan = _frozen("r_p6_throughput", ["九寨沟"])
    fd.dispatch(plan, strategy="by-leaf", concurrency=1)

    def runner(_packet):
        return fr.RunOutcome(
            started=True,
            status="error",
            passed=False,
            error="Bridge request failed: ConnectError: [Errno 61] Connection refused",
            fingerprint="fp-cr",
        )

    original_backoff = oq._backoff_seconds
    try:
        oq._backoff_seconds = lambda attempt: 0.01
        report = fr.run_fanout("r_p6_throughput", agent_runner=runner, strategy="by-leaf", concurrency=1)
    finally:
        oq._backoff_seconds = original_backoff

    assert report["connectionRefused"] >= 1
    throughput = report["throughput"]
    assert "elapsedSeconds" in throughput
    assert throughput["maxWorkersRequested"] == 0
    assert throughput["connectionRefused"] >= 1
    matrix = read_json(fanout_run_matrix_path("r_p6_throughput"))
    assert matrix["summary"]["connectionRefused"] >= 1
    assert "throughput" in matrix["summary"]


def test_run_fanout_clamps_parallel_workers_to_cold_start_cap():
    """冷启并发上限：max_workers 远超 cap 时，实际并发收敛到 cap（对齐 concurrency=2-3）。"""
    plan = _frozen("r_p6_cap", ["九寨沟", "稻城亚丁", "峨眉山", "都江堰"])
    fd.dispatch(plan, strategy="by-leaf", concurrency=4)

    def runner(_packet):
        return fr.RunOutcome(started=True, status="finished", passed=True)

    report = fr.run_fanout(
        "r_p6_cap",
        agent_runner=runner,
        strategy="by-leaf",
        concurrency=4,
        max_workers=10,
        cold_start_max_workers=2,
    )
    throughput = report["throughput"]
    assert throughput["maxWorkersRequested"] == 10
    assert throughput["maxWorkersEffective"] == 2
    assert throughput["coldStartCap"] == 2
    assert report["completed"] == 4


def test_default_orchestrator_runner_cloud_has_hard_timeout_watchdog():
    """cloud orchestrator 硬超时看门狗：agent 调用挂起时按 retryable 超时返回，不永久阻塞。"""
    import types

    class _CursorAgentError(Exception):
        is_retryable = False

    class _Agent:
        @staticmethod
        def prompt(_prompt, _opts):
            time.sleep(30)  # 模拟云端挂起
            return types.SimpleNamespace(status="finished", id="late", agent_id="late-agent")

    def _AgentOptions(**kw):
        return kw

    def _CloudAgentOptions(**kw):
        return ("cloud", kw)

    def _LocalAgentOptions(**kw):
        return ("local", kw)

    fake = types.SimpleNamespace(
        Agent=_Agent,
        CursorAgentError=_CursorAgentError,
        AgentOptions=_AgentOptions,
        CloudAgentOptions=_CloudAgentOptions,
        LocalAgentOptions=_LocalAgentOptions,
    )
    previous = sys.modules.get("cursor_sdk")
    sys.modules["cursor_sdk"] = fake
    # 地板下放 + 超时下放，让看门狗在 0.5s 内触发（生产默认 60s 地板不变）。
    os.environ["QWQ_ORCHESTRATE_AGENT_TIMEOUT_FLOOR_SECONDS"] = "0.5"
    os.environ["QWQ_ORCHESTRATE_AGENT_TIMEOUT_SECONDS"] = "0.5"
    original_git_output = fr._git_output
    try:
        fr._git_output = lambda args, cwd=None: (
            "https://github.com/openstudio2022/quwoquan.git"
            if args[:3] == ["remote", "get-url", "origin"]
            else "dev1.0"
        )
        packet = fr.build_orchestrator_packet({"taskId": "t/x", "batchId": "fanout_x"})
        started = time.time()
        outcome = fr.default_orchestrator_runner(
            packet, api_key="k", runtime=fr.RUNTIME_CLOUD, cwd=str(REPO_ROOT)
        )
        elapsed = time.time() - started
        assert elapsed < 5, elapsed
    finally:
        fr._git_output = original_git_output
        os.environ.pop("QWQ_ORCHESTRATE_AGENT_TIMEOUT_SECONDS", None)
        os.environ.pop("QWQ_ORCHESTRATE_AGENT_TIMEOUT_FLOOR_SECONDS", None)
        if previous is None:
            del sys.modules["cursor_sdk"]
        else:
            sys.modules["cursor_sdk"] = previous
    assert outcome.started is True
    assert outcome.status == "error"
    assert outcome.retryable is True
    assert "timed out" in (outcome.error or "")


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"P6 unattended reliability tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
