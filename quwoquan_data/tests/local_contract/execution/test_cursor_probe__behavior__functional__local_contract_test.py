from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from types import SimpleNamespace

from core import cursor_startup_probe as pr
from core import cursor_startup_cache as cache
from content.execution.preflight import handler as preflight_handler


def test_cursor_sdk_dependency_pin_matches_repaired_runtime() -> None:
    data_root = Path(__file__).resolve().parents[3]
    requirements = data_root / "requirements.txt"
    pins = {
        line.strip()
        for line in requirements.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "cursor-sdk==1.0.26" in pins
    sdk_boundary = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            data_root / "scripts/core/cursor_startup_probe.py",
            data_root / "scripts/content/execution/agent/agent_runner.py",
            data_root / "scripts/content/execution/controller/preflight.py",
        )
    )
    assert "cursor_sdk._tool_callback" not in sdk_boundary
    assert "_patch_cursor_sdk_tool_callback_token" not in sdk_boundary
    assert "ModelSelection(" in sdk_boundary


def test_cursor_startup_probe_suite_classifies_auth_5xx_and_bridge(monkeypatch):
    payloads = iter(
        [
            {
                "ready": True,
                "status": "finished",
                "attemptCount": 1,
            },
            {
                "ready": False,
                "status": "error",
                "error": "Internal server error",
                "errorClass": "InternalServerError",
                "errorCode": "internal",
                "httpStatus": 500,
                "attemptCount": 1,
            },
            {
                "ready": False,
                "status": "error",
                "error": "Unauthorized: invalid API key",
                "httpStatus": 401,
                "attemptCount": 1,
            },
            {
                "ready": False,
                "status": "error",
                "error": "Bridge request failed: ConnectError: [Errno 61] Connection refused",
                "errorClass": "NetworkError",
                "attemptCount": 1,
            },
        ]
    )
    monkeypatch.setattr(
        pr,
        "cursor_startup_probe",
        lambda **_kwargs: next(payloads),
    )

    report = pr.cursor_startup_probe_suite(model="composer", attempts=4)

    assert report["successCount"] == 1
    assert report["authFailures"] == 1
    assert report["true5xxCount"] == 1
    assert report["bridgeDisconnectCount"] == 1
    assert report["ready"] is False
    assert "Cursor auth failures observed" in "\n".join(report["issues"])


def test_cursor_startup_probe_suite_realizes_runtime_policy_concurrency(monkeypatch):
    def _ready_probe(**_kwargs):
        time.sleep(0.02)
        return {"ready": True, "status": "finished", "attemptCount": 1}

    monkeypatch.setattr(pr, "cursor_startup_probe", _ready_probe)

    report = pr.cursor_startup_probe_suite(model="composer", attempts=6)

    assert report["successCount"] == 6
    assert report["effectiveConcurrency"] == min(
        6,
        pr.active_runtime_policy().cursor_bridge_instances,
    )
    assert report["unrecoveredFailures"] == 0
    assert [row["attempt"] for row in report["results"]] == list(range(1, 7))


def test_cursor_workspace_probe_suite_realizes_four_isolated_lanes(
    monkeypatch,
    tmp_path,
):
    workspaces = tuple(
        tmp_path / carrier
        for carrier in ("homepage", "article", "image", "video")
    )
    for workspace in workspaces:
        workspace.mkdir()

    def _ready_probe(*, cwd, **_kwargs):
        time.sleep(0.02)
        return {
            "ready": True,
            "status": "finished",
            "agentId": f"agent-{cwd.name}",
            "runId": f"run-{cwd.name}",
            "sdkVersion": "1.0.26",
        }

    monkeypatch.setattr(pr, "cursor_startup_probe", _ready_probe)

    report = pr.cursor_workspace_probe_suite(
        workspaces=workspaces,
        model="auto",
    )

    assert report["ready"] is True
    assert report["successCount"] == 4
    assert report["effectiveConcurrency"] == 4
    assert {row["workspace"] for row in report["runs"]} == {
        "homepage",
        "article",
        "image",
        "video",
    }
    assert all(row["agentId"] and row["runId"] for row in report["runs"])


def test_cached_cursor_startup_probe_reuses_recent_ready_result(monkeypatch, tmp_path):
    """preflight 降本：TTL 内复用最近一次成功 startup probe（43s→秒级）。"""
    cache_path = tmp_path / "env" / "cursor_startup_probe_cache.json"
    monkeypatch.setattr(cache, "cursor_startup_probe_cache_path", lambda: cache_path)
    monkeypatch.setenv("CURSOR_API_KEY", "key_cachetest_abcdef12")
    calls: list[int] = []

    def _probe(**_kwargs):
        calls.append(1)
        return {"ready": True, "successCount": 1, "issues": []}

    monkeypatch.setattr(cache, "cursor_startup_probe", _probe)
    first = cache.cached_cursor_startup_probe(model="composer", runtime="local", timeout_seconds=45)
    second = cache.cached_cursor_startup_probe(model="composer", runtime="local", timeout_seconds=45)
    assert len(calls) == 1, "TTL 内第二次必须命中缓存，不得重发探测"
    assert first.get("cacheHit") is None and second.get("cacheHit") is True

    # 换 model → 缓存键不同，必须重新探测。
    cache.cached_cursor_startup_probe(model="gpt", runtime="local", timeout_seconds=45)
    assert len(calls) == 2

    # TTL=0 关闭缓存。
    monkeypatch.setattr(
        cache,
        "active_runtime_policy",
        lambda: SimpleNamespace(cursor_startup_probe_cache_ttl_seconds=0),
    )
    cache.cached_cursor_startup_probe(model="composer", runtime="local", timeout_seconds=45)
    assert len(calls) == 3


def test_cached_cursor_startup_probe_never_caches_failure(monkeypatch, tmp_path):
    cache_path = tmp_path / "env" / "cursor_startup_probe_cache.json"
    monkeypatch.setattr(cache, "cursor_startup_probe_cache_path", lambda: cache_path)
    monkeypatch.setenv("CURSOR_API_KEY", "key_cachetest_abcdef12")
    calls: list[int] = []

    def _probe(**_kwargs):
        calls.append(1)
        return {"ready": False, "successCount": 0, "issues": ["Cursor startup probe never succeeded"]}

    monkeypatch.setattr(cache, "cursor_startup_probe", _probe)
    cache.cached_cursor_startup_probe(model="composer", runtime="local", timeout_seconds=45)
    cache.cached_cursor_startup_probe(model="composer", runtime="local", timeout_seconds=45)
    assert len(calls) == 2, "失败结果不得缓存，必须重新探测"
    assert not cache_path.exists()


def test_cursor_startup_probe_cache_is_repo_runtime_cache_not_execution_output():
    from core.paths import DATA_LOCAL_ROOT

    path = cache.cursor_startup_probe_cache_path()
    assert path == DATA_LOCAL_ROOT / "cache/cursor/cursor_startup_probe_cache.json"
    assert "/tasks/" not in path.as_posix()


def test_cursor_startup_timeout_is_not_counted_as_true_5xx(monkeypatch):
    """终态 timeout（即便冷启动子尝试见过 5xx）必须归 startupTimeout，不计 true5xx。"""
    payloads = iter(
        [
            # 冷启动期间 2 次子尝试见 5xx，但整次探针最终在预算内被超时切断。
            {
                "ready": False,
                "started": False,
                "status": "timeout",
                "errorClass": "TimeoutExpired",
                "errorCode": "timeout",
                "httpStatus": None,
                "attemptCount": 3,
                "attempts": [
                    {"ready": False, "status": "error", "errorClass": "InternalServerError", "httpStatus": 500},
                    {"ready": False, "status": "error", "errorClass": "InternalServerError", "httpStatus": 503},
                ],
            },
            {
                "ready": False,
                "started": False,
                "status": "timeout",
                "errorClass": "TimeoutExpired",
                "errorCode": "timeout",
                "httpStatus": None,
                "attemptCount": 1,
                "attempts": [],
            },
        ]
    )
    monkeypatch.setattr(pr, "cursor_startup_probe", lambda **_kwargs: next(payloads))

    report = pr.cursor_startup_probe_suite(model="composer", attempts=2)

    assert report["startupTimeoutCount"] == 2
    assert report["startupTimeoutRate"] == 1.0
    assert report["true5xxCount"] == 0
    assert report["true5xxRate"] == 0.0
    # 冷启动 5xx 仍如实记录在诊断字段，不参与 true5xx 归因。
    assert report["coldStart5xxObservedCount"] == 1
    assert report["successCount"] == 0
    rows = report["results"]
    assert all(row["primaryClass"] == "startupTimeout" for row in rows)
    assert all(row["true5xx"] is False for row in rows)
    joined = "\n".join(report["issues"])
    assert "true 5xx rate" not in joined
    assert "startup timeout rate" in joined.casefold()


def test_cursor_probe_cli_writes_report(monkeypatch, tmp_path, capsys):
    report = {
        "schema": "quwoquan_data.cursor_startup_probe_suite",
        "attempts": 2,
        "successCount": 2,
        "authFailures": 0,
        "true5xxRate": 0.0,
        "bridgeDisconnectRate": 0.0,
        "startupLatencyP95": 1.25,
        "ready": True,
        "issues": [],
    }
    monkeypatch.setattr(preflight_handler, "cursor_startup_probe_suite", lambda **_kwargs: dict(report))
    out = tmp_path / "cursor_probe.json"

    preflight_handler.handle_cursor_probe(
        argparse.Namespace(
            model="composer",
            runtime="local",
            attempts=2,
            startup_timeout_seconds=1.0,
            cwd=None,
            report_out=str(out),
            json=False,
        )
    )

    assert json.loads(out.read_text(encoding="utf-8"))["ready"] is True
    printed = capsys.readouterr().out
    assert "[env cursor-probe] READY" in printed
