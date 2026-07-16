"""The Gamma API proof must consume the release-bound App UAT cases exactly."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.io import write_json  # noqa: E402
from content.release.environment import gamma_homepage_api_verification as subject  # noqa: E402


def _cases(root: Path, release_id: str) -> Path:
    path = root / "env/gamma/runs/data-release" / release_id / "apply-001" / "app_uat_cases.json"
    write_json(
        path,
        {
            "schemaVersion": "quwoquan_data.gamma_app_uat_case_manifest/1",
            "environment": "gamma",
            "releaseId": release_id,
            "runId": "apply-001",
            "importerReportRef": f"env/gamma/runs/data-release/{release_id}/apply-001/homepage-import.json",
            "generatedAt": "2026-07-14T00:00:00Z",
            "cases": [{"entityRef": "地点/景区/普陀山", "homepageId": "homepage-putuo", "title": "普陀山"}],
        },
    )
    return path


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/homepages/homepage-putuo":
            payload = {"_id": "homepage-putuo", "title": "普陀山", "coverUrl": "https://media.test/putuo.jpg"}
        elif self.path == "/v1/homepages/homepage-putuo/introduction":
            payload = {
                "homepageId": "homepage-putuo",
                "displayName": "普陀山",
                "coverUrl": "https://media.test/putuo.jpg",
                "sections": [{"kind": "overview", "title": "概况"}],
            }
        else:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


def test_gamma_homepage_api_verification__reads_dynamic_uat_cases__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release_id = "20260714--travel-homepage-coverage--cn-zhejiang-sichuan--canary-002"
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    cases = _cases(tmp_path, release_id)
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        report = subject.write_gamma_homepage_api_verification(
            release_id=release_id,
            run_id="api-001",
            case_manifest_path=cases,
            output_path=tmp_path / "env/gamma/runs/data-release" / release_id / "api-001/homepage-api-verification.json",
            api_base_url=f"http://127.0.0.1:{server.server_port}",
            insecure_tls=False,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["entities"][0]["homepageId"] == "homepage-putuo"


def test_gamma_homepage_api_verification__rejects_title_drift__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release_id = "20260714--travel-homepage-coverage--cn-zhejiang-sichuan--canary-002"
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    cases = _cases(tmp_path, release_id)
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(subject.GammaHomepageApiVerificationError, match="title mismatch"):
            # A stale case manifest must not be able to validate a different API object.
            payload = json.loads(cases.read_text(encoding="utf-8"))
            payload["cases"][0]["title"] = "错误标题"
            cases.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            subject.write_gamma_homepage_api_verification(
                release_id=release_id,
                run_id="api-002",
                case_manifest_path=cases,
                output_path=tmp_path / "env/gamma/runs/data-release" / release_id / "api-002/homepage-api-verification.json",
                api_base_url=f"http://127.0.0.1:{server.server_port}",
                insecure_tls=False,
            )
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_gamma_homepage_api_verification__uses_explicit_local_resolution__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release_id = "20260714--travel-homepage-coverage--cn-zhejiang-sichuan--canary-002"
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    cases = _cases(tmp_path, release_id)
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        report = subject.write_gamma_homepage_api_verification(
            release_id=release_id,
            run_id="api-003",
            case_manifest_path=cases,
            output_path=tmp_path / "env/gamma/runs/data-release" / release_id / "api-003/homepage-api-verification.json",
            api_base_url=f"http://gamma-api.test:{server.server_port}",
            insecure_tls=False,
            resolve_host="127.0.0.1",
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["apiResolveHost"] == "127.0.0.1"


def test_gamma_homepage_api_verification__rejects_non_ip_resolution__local_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release_id = "20260714--travel-homepage-coverage--cn-zhejiang-sichuan--canary-002"
    monkeypatch.setattr(subject, "OUTPUT_ROOT", tmp_path)
    cases = _cases(tmp_path, release_id)

    with pytest.raises(subject.GammaHomepageApiVerificationError, match="must be an IP address"):
        subject.write_gamma_homepage_api_verification(
            release_id=release_id,
            run_id="api-004",
            case_manifest_path=cases,
            output_path=tmp_path / "env/gamma/runs/data-release" / release_id / "api-004/homepage-api-verification.json",
            api_base_url="https://gamma-api.test:19000",
            insecure_tls=True,
            resolve_host="not-an-ip",
        )
