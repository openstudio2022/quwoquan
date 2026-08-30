"""stackctl 观测辅助函数的行为契约。

被测对象：
- `_materialize_local_portal_root`：本地 Portal 静态站点物化（现场构建 /
  显式占位两分支，绝不留静默空根）。
- `_prometheus_scrape_inspection`：inspect --scope metrics 的指标面实查
  （targets 健康分布 + 核心 series 存在性；不可达显式 error，不合成健康态）。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
STACKCTL_PATH = REPO_ROOT / "quwoquan_ops/cli/stackctl.py"
# 现场构建分支以真实 vite 可执行文件是否在仓内工具链上为前置：缺席只说明这台机器
# 判不了 Portal 构建，不是物化契约漂移。占位分支不依赖工具链，始终逐条判。
VITE_BINARY = REPO_ROOT / "quwoquan_ops/portal/node_modules/.bin/vite"


def _load_stackctl():
    if "stackctl_under_test" in sys.modules:
        return sys.modules["stackctl_under_test"]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location("stackctl_under_test", STACKCTL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


stackctl = _load_stackctl()


# ── portal 物化 ────────────────────────────────────────────


def test_portal_root_falls_back_to_explicit_placeholder(monkeypatch, tmp_path):
    monkeypatch.delenv("QWQ_DEPLOY_WORK_ROOT", raising=False)
    portal_root = tmp_path / "portal"
    portal_root.mkdir()
    topology = stackctl.load_environment_topology()

    outcome = stackctl._materialize_local_portal_root(
        topology, "gamma-local", portal_root
    )

    assert outcome == "placeholder"
    index = portal_root / "index.html"
    assert index.is_file()
    content = index.read_text(encoding="utf-8")
    assert "尚未构建" in content
    assert "不承载任何业务数据" in content


@pytest.mark.skipif(
    not VITE_BINARY.is_file(),
    reason="仓内 portal node 工具链未安装（quwoquan_ops/portal/node_modules/.bin/vite）",
)
def test_portal_root_copies_vite_build_output(monkeypatch, tmp_path):
    deploy_root = tmp_path / "deploy"
    build_output = deploy_root / "gamma-local" / "build" / "ops-portal"
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy_root))
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs.get("env") or {}
        build_output.mkdir(parents=True, exist_ok=True)
        (build_output / "index.html").write_text("<html>built</html>", encoding="utf-8")
        (build_output / "assets").mkdir(exist_ok=True)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(stackctl.subprocess, "run", fake_run)
    portal_root = tmp_path / "portal"
    portal_root.mkdir()
    topology = stackctl.load_environment_topology()

    outcome = stackctl._materialize_local_portal_root(
        topology, "gamma-local", portal_root
    )

    assert outcome == "built"
    assert (portal_root / "index.html").read_text(encoding="utf-8") == "<html>built</html>"
    assert (portal_root / "assets").is_dir()
    # base URL 必须来自 publicBases 派生，禁止手写域名。
    build_env = captured["env"]
    assert build_env["QWQ_DEPLOY_TARGET"] == "gamma-local"
    assert build_env["VITE_PRODUCT_OPS_BASE_URL"].startswith("https://ops.gamma.")
    assert build_env["VITE_CONTENT_SERVICE_BASE_URL"].startswith("https://api.gamma.")


def test_portal_root_build_failure_still_leaves_placeholder(monkeypatch, tmp_path):
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(tmp_path / "deploy"))

    def failing_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="boom")

    monkeypatch.setattr(stackctl.subprocess, "run", failing_run)
    portal_root = tmp_path / "portal"
    portal_root.mkdir()
    topology = stackctl.load_environment_topology()

    outcome = stackctl._materialize_local_portal_root(
        topology, "gamma-local", portal_root
    )

    assert outcome == "placeholder"
    assert (portal_root / "index.html").is_file()


# ── Prometheus 巡检 ────────────────────────────────────────


class _FakePrometheus:
    def __init__(self, targets_payload: dict, query_results: dict[str, list]):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path.startswith("/api/v1/targets"):
                    body = json.dumps(targets_payload).encode("utf-8")
                elif self.path.startswith("/api/v1/query"):
                    series = None
                    for name, result in query_results.items():
                        if name in self.path:
                            series = result
                    body = json.dumps(
                        {"data": {"result": series if series is not None else []}}
                    ).encode("utf-8")
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
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


def test_prometheus_inspection_reports_ok_when_targets_up_and_series_present():
    fake = _FakePrometheus(
        {"data": {"activeTargets": [
            {"health": "up", "labels": {"job": "quwoquan-service-plane", "instance": "content-service:18080"}},
        ]}},
        {
            "http_server_requests_total": [{"value": [0, "42"]}],
            "recommendation_feed_impressed_total": [{"value": [0, "7"]}],
            "ops_telemetry_ingest_events_total": [{"value": [0, "9"]}],
        },
    )
    try:
        inspection = stackctl._prometheus_scrape_inspection(fake.url)
    finally:
        fake.close()
    assert inspection["status"] == "ok"
    assert inspection["targets"] == {"active": 1, "down": []}
    assert all(inspection["coreSeriesPresent"].values())


def test_prometheus_inspection_degrades_on_down_target_or_missing_series():
    fake = _FakePrometheus(
        {"data": {"activeTargets": [
            {"health": "down", "labels": {"job": "quwoquan-edge-plane", "instance": "api-edge:18079"}, "lastError": "connection refused"},
        ]}},
        {"http_server_requests_total": []},
    )
    try:
        inspection = stackctl._prometheus_scrape_inspection(fake.url)
    finally:
        fake.close()
    assert inspection["status"] == "degraded"
    assert inspection["targets"]["down"][0]["instance"] == "api-edge:18079"
    assert inspection["coreSeriesPresent"]["http_server_requests_total"] is False


def test_prometheus_inspection_is_explicit_error_when_unreachable():
    inspection = stackctl._prometheus_scrape_inspection("http://127.0.0.1:9")
    assert inspection["status"] == "error"
    assert "reason" in inspection
