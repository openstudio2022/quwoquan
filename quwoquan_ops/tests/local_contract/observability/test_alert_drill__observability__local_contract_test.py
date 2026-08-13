"""告警演练脚本的链路契约。

被测对象：`quwoquan_ops/tools/alert_drill.py`——向 Alertmanager v2 API 注入
带演练标记的合成告警、轮询确认 active、证据落盘；Alertmanager 不可达或
告警未出现在 active 列表时显式失败，不合成成功。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DRILL_PATH = REPO_ROOT / "quwoquan_ops/tools/alert_drill.py"


def _load_drill():
    spec = importlib.util.spec_from_file_location("alert_drill_under_test", DRILL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


drill = _load_drill()


class _FakeAlertmanager:
    """接收注入并在 active 列表回放；echo_active=False 模拟告警丢失。"""

    def __init__(self, echo_active: bool = True):
        self.injected: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                fake.injected.extend(payload)
                self.send_response(200)
                self.end_headers()

            def do_GET(self):  # noqa: N802
                body = json.dumps(fake.injected if echo_active else []).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._httpd.server_port}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()


def test_drill_delivers_synthetic_alert_and_writes_evidence(monkeypatch, tmp_path):
    fake = _FakeAlertmanager()
    monkeypatch.setenv("ALERTMANAGER_URL", fake.url)
    monkeypatch.delenv("PLATFORM_OPS_URL", raising=False)
    monkeypatch.setattr(drill, "EVIDENCE_DIR", tmp_path / "alert-drill")
    monkeypatch.setattr(drill.time, "sleep", lambda _seconds: None)
    try:
        exit_code = drill.main()
    finally:
        fake.close()

    assert exit_code == 0
    injected = fake.injected[0]
    assert injected["labels"]["alertname"] == drill.DRILL_ALERT_NAME
    assert injected["labels"]["drill"] == "true"
    assert injected["endsAt"] > injected["startsAt"], "演练告警必须自动过期"
    evidence_files = list((tmp_path / "alert-drill").glob("*.json"))
    assert len(evidence_files) == 1
    evidence = json.loads(evidence_files[0].read_text(encoding="utf-8"))
    assert evidence["alertmanagerReceived"] is True
    assert str(evidence["platformOpsIngested"]).startswith("skipped")


def test_drill_fails_when_alert_never_becomes_active(monkeypatch, tmp_path):
    fake = _FakeAlertmanager(echo_active=False)
    monkeypatch.setenv("ALERTMANAGER_URL", fake.url)
    monkeypatch.delenv("PLATFORM_OPS_URL", raising=False)
    monkeypatch.setattr(drill, "EVIDENCE_DIR", tmp_path / "alert-drill")
    monkeypatch.setattr(drill.time, "sleep", lambda _seconds: None)
    try:
        exit_code = drill.main()
    finally:
        fake.close()

    assert exit_code == 1
    evidence_files = list((tmp_path / "alert-drill").glob("*.json"))
    assert len(evidence_files) == 1
    assert (
        json.loads(evidence_files[0].read_text(encoding="utf-8"))["alertmanagerReceived"]
        is False
    )


def test_drill_requires_alertmanager_url(monkeypatch):
    monkeypatch.delenv("ALERTMANAGER_URL", raising=False)
    assert drill.main() == 2


def test_drill_fails_fast_when_alertmanager_unreachable(monkeypatch, tmp_path):
    monkeypatch.setenv("ALERTMANAGER_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(drill, "EVIDENCE_DIR", tmp_path / "alert-drill")
    assert drill.main() == 1
