"""ship 灌库后 entity-service 免停服重载触发契约。"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import json
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def test_trigger_entity_reload_posts_metadata_route_and_writes_report(monkeypatch):
    """契约：POST {base}/v1/homepages:reload（ReloadHomepageState），结果落审计报告。"""
    import ship.handler as mod

    calls: list[list[str]] = []

    def _fake_run(argv, capture_output=False, check=False):
        calls.append(list(argv))
        return subprocess.CompletedProcess(
            argv, 0, stdout=b'{"homepagesBefore":2,"homepagesAfter":5,"snapshotSize":5}\n200', stderr=b""
        )

    with tempfile.TemporaryDirectory(prefix="qwq_ship_reload_") as tmp:
        tmp_path = Path(tmp)
        monkeypatch.setattr(mod, "PUBLISH_ROOT", tmp_path)
        monkeypatch.setattr(mod.subprocess, "run", _fake_run)
        report = mod._trigger_entity_reload("http://localhost:18084/", release_id="rel_test_001")

        assert report is not None and report.is_file()
        assert calls and "http://localhost:18084/v1/homepages:reload" in calls[0]
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["ok"] is True
        assert data["httpStatus"] == "200"
        assert data["endpoint"].endswith("/v1/homepages:reload")


def test_trigger_entity_reload_end_to_end_real_http_roundtrip(monkeypatch):
    """端到端一跳：真 curl 子进程 POST 真 HTTP 端点（回环），不再 mock subprocess。

    与 entity-service tests/api_integration 的 handler 侧证据拼接后，
    ship --entity-reload-url → POST /v1/homepages:reload → 内存合并 全链闭环。
    """
    import ship.handler as mod

    seen: dict = {}

    class _ReloadHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            seen["path"] = self.path
            seen["method"] = "POST"
            body = json.dumps({"homepagesBefore": 1, "homepagesAfter": 3, "snapshotSize": 3}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # 静默测试日志
            return

    server = HTTPServer(("127.0.0.1", 0), _ReloadHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="qwq_ship_reload_") as tmp:
            monkeypatch.setattr(mod, "PUBLISH_ROOT", Path(tmp))
            report = mod._trigger_entity_reload(
                f"http://127.0.0.1:{port}", release_id="rel_test_e2e"
            )
            assert seen == {"path": "/v1/homepages:reload", "method": "POST"}
            data = json.loads(report.read_text(encoding="utf-8"))
            assert data["ok"] is True
            assert data["httpStatus"] == "200"
            assert '"homepagesAfter": 3' in data["response"] or '"homepagesAfter":3' in data["response"]
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_trigger_entity_reload_failure_is_reported_not_silent(monkeypatch, capsys):
    """重载失败必须显式 WARNING + 报告 ok=false，不得静默吞掉。"""
    import ship.handler as mod

    def _fake_run(argv, capture_output=False, check=False):
        return subprocess.CompletedProcess(argv, 0, stdout=b"\n000", stderr=b"connection refused")

    with tempfile.TemporaryDirectory(prefix="qwq_ship_reload_") as tmp:
        tmp_path = Path(tmp)
        monkeypatch.setattr(mod, "PUBLISH_ROOT", tmp_path)
        monkeypatch.setattr(mod.subprocess, "run", _fake_run)
        report = mod._trigger_entity_reload("http://localhost:18084", release_id="rel_test_002")

        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["ok"] is False
        err = capsys.readouterr().err
        assert "reload failed" in err
