from __future__ import annotations

import argparse
import json

from _common import python_runtime as pr
from env import handler as env_handler


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

    report = pr.cursor_startup_probe_suite(model="composer-2.5", attempts=4)

    assert report["successCount"] == 1
    assert report["authFailures"] == 1
    assert report["true5xxCount"] == 1
    assert report["bridgeDisconnectCount"] == 1
    assert report["ready"] is False
    assert "Cursor auth failures observed" in "\n".join(report["issues"])


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

    report = pr.cursor_startup_probe_suite(model="composer-2.5", attempts=2)

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
        "schemaVersion": "quwoquan_data.cursor_startup_probe_suite/1",
        "attempts": 2,
        "successCount": 2,
        "authFailures": 0,
        "true5xxRate": 0.0,
        "bridgeDisconnectRate": 0.0,
        "startupLatencyP95": 1.25,
        "ready": True,
        "issues": [],
    }
    monkeypatch.setattr(env_handler, "cursor_startup_probe_suite", lambda **_kwargs: dict(report))
    out = tmp_path / "cursor_probe.json"

    env_handler.handle_cursor_probe(
        argparse.Namespace(
            model="composer-2.5",
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
