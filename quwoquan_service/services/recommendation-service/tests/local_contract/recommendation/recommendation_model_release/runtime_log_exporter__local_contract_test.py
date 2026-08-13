# spec_ref: specs/feature-tree/platform-ops-governance/observability-and-alerting/log-metric-trace-unification/spec.md#gwt-001
"""runtime log exporter 合约：与 Go HTTPRuntimeLogExporter 同语义。

覆盖：fail-closed 配置、幂等 spool、成功投递清空、瞬时失败退避重试、
永久失败死信、TTL 死信，以及 handler 产出的 observability.slim wire 形状。
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from api.runtime_log_exporter import (
    RuntimeLogExporter,
    RuntimeLogHandler,
    _SpooledBatch,
    _utc_now,
)


def _record(severity: str = "ERROR") -> dict[str, str]:
    now = _utc_now().isoformat().replace("+00:00", "Z")
    return {
        "schema": "observability.slim",
        "recordId": "r.test",
        "occurredAt": now,
        "observedAt": now,
        "logKind": "exception",
        "severity": severity,
        "signal": "service.exception.runtime",
        "message": "test",
        "resourceSourceType": "service",
        "resourceService": "recommendation-service",
        "errorCode": "SERVICE.RUNTIME.test",
    }


class _Server:
    """最小同步 HTTP 服务：按预设状态码应答并记录请求头。"""

    def __init__(self, status: int):
        self.status = status
        self.requests: list[dict[str, str]] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                server.requests.append(
                    {
                        "Idempotency-Key": self.headers.get("Idempotency-Key", ""),
                        "X-Runtime-Log-Ingest-Token": self.headers.get(
                            "X-Runtime-Log-Ingest-Token", ""
                        ),
                    }
                )
                self.send_response(server.status)
                self.end_headers()

            def log_message(self, *_args):
                return

        self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._httpd.server_port}/ops/runtime-logs"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()


def test_partial_configuration_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        RuntimeLogExporter("https://logs.example", "", str(tmp_path))
    disabled = RuntimeLogExporter("", "", "")
    assert not disabled.enabled


def test_delivered_batch_leaves_spool_with_idempotency_and_token(tmp_path: Path) -> None:
    server = _Server(200)
    try:
        exporter = RuntimeLogExporter(server.url, "machine-token", str(tmp_path))
        record = _record()
        exporter.export([record])
        exporter.export([record])  # 同 payload 幂等，不产生第二个 spool 文件
        assert len(list(tmp_path.glob("*.json"))) == 1
        exporter.flush_once()
        assert list(tmp_path.glob("*.json")) == []
        assert len(server.requests) == 1
        assert len(server.requests[0]["Idempotency-Key"]) == 64
        assert server.requests[0]["X-Runtime-Log-Ingest-Token"] == "machine-token"
    finally:
        server.close()


def test_transient_failure_schedules_backoff_retry(tmp_path: Path) -> None:
    server = _Server(503)
    try:
        exporter = RuntimeLogExporter(server.url, "machine-token", str(tmp_path))
        exporter.export([_record("WARN")])
        exporter.flush_once()
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        batch = _SpooledBatch.from_json(files[0].read_text(encoding="utf-8"))
        assert batch.attempts == 1
        assert batch.next_attempt_at > _utc_now()
        assert batch.last_failure == "http_503"
    finally:
        server.close()


def test_permanent_failure_moves_to_dead_letter(tmp_path: Path) -> None:
    server = _Server(422)
    try:
        exporter = RuntimeLogExporter(server.url, "machine-token", str(tmp_path))
        exporter.export([_record()])
        exporter.flush_once()
        assert list(tmp_path.glob("*.json")) == []
        assert len(list((tmp_path / "dead-letter").glob("*.json"))) == 1
    finally:
        server.close()


def test_ttl_expired_batch_moves_to_dead_letter(tmp_path: Path) -> None:
    server = _Server(200)
    try:
        exporter = RuntimeLogExporter(server.url, "machine-token", str(tmp_path))
        exporter.export([_record()])
        path = next(tmp_path.glob("*.json"))
        batch = _SpooledBatch.from_json(path.read_text(encoding="utf-8"))
        batch.expires_at = _utc_now() - timedelta(hours=1)
        path.write_text(batch.to_json(), encoding="utf-8")
        exporter.flush_once()
        assert list(tmp_path.glob("*.json")) == []
        assert len(list((tmp_path / "dead-letter").glob("*.json"))) == 1
        assert not server.requests
    finally:
        server.close()


def test_handler_emits_observability_slim_wire_shape(tmp_path: Path) -> None:
    exporter = RuntimeLogExporter(
        "http://127.0.0.1:9/unreachable", "machine-token", str(tmp_path)
    )
    handler = RuntimeLogHandler(exporter, environment="gamma")
    record = logging.LogRecord(
        name="api.score",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="model runtime %s failed",
        args=("scorer",),
        exc_info=None,
    )
    handler.emit(record)
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    batch = json.loads(files[0].read_text(encoding="utf-8"))
    fields = batch["records"][0]
    assert fields["schema"] == "observability.slim"
    assert fields["logKind"] == "exception"
    assert fields["severity"] == "ERROR"
    assert fields["signal"] == "service.exception.runtime"
    assert fields["message"] == "model runtime scorer failed"
    assert fields["resourceSourceType"] == "service"
    assert fields["resourceService"] == "recommendation-service"
    assert fields["resourceEnvironment"] == "gamma"
    assert fields["errorCode"] == "RECOMMENDATION.SYSTEM.model_runtime_exception"
    assert fields["recordId"].startswith("r.")


def test_info_level_records_are_not_exported(tmp_path: Path) -> None:
    exporter = RuntimeLogExporter(
        "http://127.0.0.1:9/unreachable", "machine-token", str(tmp_path)
    )
    handler = RuntimeLogHandler(exporter, environment="gamma")
    record = logging.LogRecord(
        name="api.score",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="routine",
        args=(),
        exc_info=None,
    )
    if handler.level <= record.levelno:
        handler.emit(record)
    assert list(tmp_path.glob("*.json")) == []
