"""WP1 无进展快速失败契约：网络断路器 + curl 短路 + auto research 无进展 watchdog。

覆盖：
- NetworkFailureBreaker host 分桶、阈值打开、成功复位、短路计数；
- network_io.curl_json/curl_text 网络级退出码计入断路器并在打开后秒级短路；
- write_auto_research_plans 并行路径 stage 无进展超时 → 可续跑 partialRun +
  networkOutage(noProgress=true)，剩余实体进 remainingEntityIds。
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

if "QWQ_DATA_ROOT" not in os.environ and "QWQ_OUTPUT_ROOT" not in os.environ:
    os.environ["QWQ_DATA_ROOT"] = tempfile.mkdtemp(prefix="qwq_netff_test_")

from content.source.research.network_breaker import (  # noqa: E402
    NETWORK_CURL_EXIT_CODES,
    BREAKER,
    NetworkFailureBreaker,
    stage_no_progress_timeout_seconds,
)
from content.source.research import network_breaker  # noqa: E402
from core.runtime_policy import active_runtime_policy  # noqa: E402

MEDIAWIKI_TIMEOUT_SECONDS = active_runtime_policy().provider_timeouts.mediawiki_seconds


def test_breaker_opens_per_host_after_threshold_and_resets_on_success():
    breaker = NetworkFailureBreaker(threshold=3)
    wiki = "https://zh.wikipedia.org/w/api.php?action=query"
    commons = "https://commons.wikimedia.org/w/api.php"
    for _ in range(2):
        breaker.record_network_failure(wiki)
    assert not breaker.is_open(wiki), "未达阈值不得打开"
    breaker.record_network_failure(wiki)
    assert breaker.is_open(wiki), "连续 3 次网络失败必须打开"
    assert not breaker.is_open(commons), "host 分桶：其它 host 不受影响"
    snapshot = breaker.snapshot()
    assert snapshot["openHosts"] == ["zh.wikipedia.org"]
    assert snapshot["shortCircuitedRequests"]["zh.wikipedia.org"] >= 1
    breaker.record_success(wiki)
    assert not breaker.is_open(wiki), "任一成功必须复位该 host"


def test_curl_layer_reports_network_exit_codes_and_short_circuits(monkeypatch):
    import content.source.research.network_io as rp

    BREAKER.reset()
    monkeypatch.setenv("QWQ_AUTO_RESEARCH_NETWORK_BREAKER_THRESHOLD", "2")
    calls: list[str] = []

    class _Proc:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode
            self.stdout = b""
            self.stderr = b""

    def _fake_run(argv, capture_output=True, check=False):
        calls.append(argv[-1])
        return _Proc(28)  # curl 28 = operation timeout（网络级）

    breaker = NetworkFailureBreaker(threshold=2)
    monkeypatch.setattr("content.source.research.network_breaker.BREAKER", breaker)
    monkeypatch.setattr(rp.network_breaker, "BREAKER", breaker, raising=False)
    monkeypatch.setattr(rp.subprocess, "run", _fake_run)
    url = "https://zh.wikipedia.org/w/api.php?a=1"
    assert rp.curl_json(url, timeout=MEDIAWIKI_TIMEOUT_SECONDS) == {}
    assert rp.curl_json(url, timeout=MEDIAWIKI_TIMEOUT_SECONDS) == {}
    assert len(calls) == 2
    # 阈值已到：第三次不再执行 curl（秒级短路）。
    assert rp.curl_json(url, timeout=MEDIAWIKI_TIMEOUT_SECONDS) == {}
    assert rp.curl_text(url, timeout=MEDIAWIKI_TIMEOUT_SECONDS) == ""
    assert len(calls) == 2, "断路器打开后必须短路，不得继续消耗 curl max-time"
    assert 28 in NETWORK_CURL_EXIT_CODES


def test_curl_layer_content_failure_does_not_open_breaker(monkeypatch):
    import content.source.research.network_io as rp

    class _Proc:
        returncode = 22  # HTTP 4xx/5xx（内容级，非网络级）
        stdout = b""
        stderr = b""

    breaker = NetworkFailureBreaker(threshold=1)
    monkeypatch.setattr(rp.network_breaker, "BREAKER", breaker, raising=False)
    monkeypatch.setattr(rp.subprocess, "run", lambda *a, **k: _Proc())
    url = "https://zh.wikipedia.org/w/api.php?a=1"
    for _ in range(3):
        assert rp.curl_json(url, timeout=MEDIAWIKI_TIMEOUT_SECONDS) == {}
    assert breaker.snapshot()["openHosts"] == [], "内容级失败不得打开断路器"


def test_stage_no_progress_timeout_runtime_policy_contract(monkeypatch):
    assert stage_no_progress_timeout_seconds() == 900.0
    monkeypatch.setattr(
        network_breaker,
        "active_runtime_policy",
        lambda: replace(active_runtime_policy(), stage_no_progress_timeout_seconds=120),
    )
    assert stage_no_progress_timeout_seconds() == 120.0


def test_write_auto_research_plans_no_progress_timeout_yields_resumable_outage(monkeypatch, tmp_path):
    """并行 wave 中所有实体都卡死（模拟网络黑洞）→ watchdog 中断且可续跑。"""
    monkeypatch.setenv("QWQ_DATA_ROOT", str(tmp_path))
    # 2s 预算：给高负载下的线程调度留余量（worker 卡 10s，断言上限 8s，时序仍充裕）。
    monkeypatch.setattr(
        network_breaker,
        "active_runtime_policy",
        lambda: replace(active_runtime_policy(), stage_no_progress_timeout_seconds=2),
    )
    import importlib

    import core.paths as paths_mod
    importlib.reload(paths_mod)
    import content.source.research.auto_plan_public as app
    importlib.reload(app)

    release = threading.Event()

    def _stuck_impl(execution_id, entity_ids, **kwargs):
        # 第一批 worker 卡住（等待 release），其余在队列中会被 cancel。
        release.wait(timeout=10)
        return {
            "updated": [],
            "issues": [],
            "candidates": [],
            "imageCollections": [],
            "sourceUnavailable": [],
        }

    monkeypatch.setattr(app, "_write_auto_research_plans_impl", _stuck_impl)
    monkeypatch.setattr(app, "prepare_source_plan", lambda *a, **k: None)
    started = time.monotonic()
    execution_id = "20260712--travel-homepage-outage--cn-test--canary-001"
    report = app.write_auto_research_plans(
        execution_id,
        ["实体甲", "实体乙", "实体丙"],
        entity_type="地点/景区",
        max_workers=2,
    )
    elapsed = time.monotonic() - started
    release.set()
    assert report.get("partialRun") is True
    assert report.get("partialReason") == "stage_no_progress_timeout"
    outage = report.get("networkOutage") or {}
    assert outage.get("noProgress") is True
    assert report.get("remainingEntityIds"), "剩余实体必须回队列供 resume"
    assert elapsed < 8, "watchdog 必须在预算量级内中断，不得挂满 curl 超时"


def test_wave_budget_short_circuits_curl_after_deadline(monkeypatch):
    """串行路径兜底：wave wall-clock 预算耗尽后 curl 层直接短路。"""
    import content.source.research.network_io as rp
    from content.source.research import network_breaker as nb

    calls: list[str] = []

    class _Proc:
        returncode = 0
        stdout = b"{}"
        stderr = b""

    monkeypatch.setattr(rp.subprocess, "run", lambda *a, **k: calls.append(1) or _Proc())
    nb.start_wave_budget(3600)
    try:
        assert rp.curl_json(
            "https://zh.wikipedia.org/w/api.php",
            timeout=MEDIAWIKI_TIMEOUT_SECONDS,
        ) == {}
        assert len(calls) == 1
        nb.start_wave_budget(0.0)  # 预算 0 = 立即耗尽（模拟 deadline 过期）
        # budget=0 语义为关闭；用极小预算 + 等待代替。
        nb.start_wave_budget(0.01)
        import time as _t

        _t.sleep(0.05)
        assert rp.curl_json(
            "https://zh.wikipedia.org/w/api.php",
            timeout=MEDIAWIKI_TIMEOUT_SECONDS,
        ) == {}
        assert len(calls) == 1, "预算耗尽后必须短路，不得再执行 curl"
        assert nb.wave_budget_exceeded() is True
    finally:
        nb.clear_wave_budget()


if __name__ == "__main__":
    raise SystemExit(os.system(f"{sys.executable} -m pytest {__file__} -q") >> 8)
