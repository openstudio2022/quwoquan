"""local_contract: 运行时 API path 去版本探针正负例（httptest，不依赖 live 密钥）。"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    ROOT / "quwoquan_ops/cli/probes/verify_api_path_runtime_unversioned.py"
)


def _load_module():
    name = "verify_api_path_runtime_unversioned"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclass 在 exec 时需要 sys.modules 已登记。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

_LEGACY_PREFIX = "/" + "v1" + "/"


class _FixtureHandler(BaseHTTPRequestHandler):
    """模拟网关：无版本 path 业务可达，版本段 path 一律 404。"""

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _write(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/healthz":
            self._write(200, b'{"ok":true}')
            return
        if path == "/config/app":
            self._write(200, b'{"app":"fixture"}')
            return
        if path.startswith(_LEGACY_PREFIX):
            self._write(404, b'{"error":"not_found"}')
            return
        self._write(404, b"local-gamma mirror route is not ready")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or "0")
        _ = self.rfile.read(length) if length else b""
        if path == "/search":
            # rankingVersion 字段值为 search-v1（非 HTTP path），保持与生产信封一致。
            self._write(200, b'{"hits":[],"rankingVersion":"search-v1"}')
            return
        if path.startswith(_LEGACY_PREFIX):
            self._write(404, b'{"error":"not_found"}')
            return
        self._write(404, b"local-gamma mirror route is not ready")


class ApiPathRuntimeUnversionedContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_module()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address[:2]
        cls.base_url = f"http://{host}:{port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_versioned_helper_builds_legacy_path(self) -> None:
        path = self.mod._versioned("config/app")
        self.assertEqual(path, "/" + "v1" + "/config/app")
        self.assertTrue(path.startswith("/" + "v1" + "/"))

    def test_fixture_gateway_passes_default_matrix(self) -> None:
        report = self.mod.run_probes(self.base_url, retry_attempts=1)
        self.assertTrue(report["passed"], msg=json.dumps(report["failures"], ensure_ascii=False))
        names = {item["name"]: item for item in report["results"]}
        self.assertEqual(names["config_app_unversioned"]["status"], 200)
        self.assertEqual(names["config_app_versioned_must_404"]["status"], 404)
        self.assertEqual(names["content_feed_versioned_must_404"]["status"], 404)
        self.assertEqual(names["search_unversioned"]["status"], 200)
        self.assertEqual(names["search_versioned_must_404"]["status"], 404)

    def test_versioned_path_returning_200_is_failure(self) -> None:
        class BadHandler(_FixtureHandler):
            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path.startswith(_LEGACY_PREFIX):
                    self._write(200, b'{"legacy":true}')
                    return
                super().do_GET()

        server = ThreadingHTTPServer(("127.0.0.1", 0), BadHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address[:2]
            report = self.mod.run_probes(
                f"http://{host}:{port}",
                cases=[
                    self.mod.ProbeCase(
                        "legacy_must_404",
                        "GET",
                        self.mod._versioned("config/app"),
                        "http_404",
                    )
                ],
                retry_attempts=1,
            )
            self.assertFalse(report["passed"])
            self.assertTrue(
                any("expected HTTP 404" in item for item in report["failures"]),
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_unversioned_gateway_catchall_is_failure(self) -> None:
        class CatchAll404(_FixtureHandler):
            def do_GET(self) -> None:  # noqa: N802
                self._write(404, b"local-gamma mirror route is not ready")

        server = ThreadingHTTPServer(("127.0.0.1", 0), CatchAll404)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address[:2]
            report = self.mod.run_probes(
                f"http://{host}:{port}",
                cases=[
                    self.mod.ProbeCase(
                        "config_app",
                        "GET",
                        "/config/app",
                        "ok_or_business",
                    )
                ],
                retry_attempts=1,
            )
            self.assertFalse(report["passed"])
            self.assertTrue(
                any("matcher" in item or "not-found" in item for item in report["failures"]),
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_base_url_with_version_segment_fails_closed(self) -> None:
        report = self.mod.run_probes(
            self.base_url + "/" + "v1",
            cases=[],
            retry_attempts=1,
        )
        self.assertFalse(report["passed"])
        self.assertTrue(
            any("version segment" in item for item in report["failures"]),
        )


if __name__ == "__main__":
    unittest.main()
