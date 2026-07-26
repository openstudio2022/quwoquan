from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
GATE_PATH = (
    ROOT
    / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
    "content-service/gate/verify_report_feedback_four_environment.py"
)
PROBE_PATH = (
    ROOT
    / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
    "content-service/smoke/run_report_feedback_lifecycle_probe.py"
)
PROBE_SUPPORT_PATH = (
    ROOT
    / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
    "content-service/smoke/report_feedback_probe_support.py"
)


def _load_gate_module():
    spec = importlib.util.spec_from_file_location(
        "report_feedback_four_environment_gate_test",
        GATE_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load report feedback gate")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_probe_support_module():
    spec = importlib.util.spec_from_file_location(
        "report_feedback_probe_support_test",
        PROBE_SUPPORT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load report feedback probe support")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_stack_reports(output_root: Path) -> None:
    profiles = {
        "alpha": "smoke",
        "beta": "integration",
        "gamma": "release",
        "prod": "release",
    }
    for index, (environment, profile) in enumerate(profiles.items()):
        _write_json(
            output_root / environment / "runs" / f"stack-{index}" / "report.json",
            {
                "command": "verify",
                "profile": profile,
                "status": "ok",
                "startedAt": f"2026-07-20T00:00:0{index}Z",
            },
        )


def _write_feature_report(
    output_root: Path,
    *,
    environment: str,
    run_id: str,
    mode: str,
    lifecycle_steps: frozenset[str],
    lifecycle_facts: frozenset[str],
) -> None:
    steps = (
        lifecycle_steps
        if mode == "lifecycle"
        else frozenset({"healthz", "list_my_reports_privacy"})
    )
    _write_json(
        output_root
        / environment
        / "runs"
        / run_id
        / "report-feedback-lifecycle.json",
        {
            "schema": "content-report-feedback-lifecycle-probe-report",
            "mode": mode,
            "status": "passed",
            "startedAt": "2026-07-20T00:01:00Z",
            "environment": {"env": environment},
            "steps": [
                {"name": name, "status": "passed"} for name in sorted(steps)
            ],
            "journeyEvidence": {
                name: True for name in sorted(lifecycle_facts)
            },
        },
    )


class _ProbeHandler(BaseHTTPRequestHandler):
    authorization_headers: list[str] = []
    report_items: list[dict[str, object]] = []

    def do_GET(self) -> None:  # noqa: N802
        self.authorization_headers.append(self.headers.get("Authorization", ""))
        if self.path == "/healthz":
            self._send({"status": "ok"})
            return
        if self.path == "/content/users/me/reports?limit=100":
            self._send({"items": self.report_items})
            return
        self.send_error(404)

    def _send(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


class ReportFeedbackEnvironmentEvidenceTest(unittest.TestCase):
    def test_lifecycle_probe_uses_generated_report_route_namespace(self) -> None:
        probe_source = PROBE_PATH.read_text(encoding="utf-8")
        generated_routes = (
            ROOT
            / "quwoquan_service/services/content-service/generated/"
            "trust_safety/report/transport/routes.g.go"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'pathTemplate: "/content/reports"',
            generated_routes,
            "ContractGraph generated route must own the report namespace",
        )
        self.assertIn('"/content/reports"', probe_source)
        self.assertNotIn(
            "/content/trust_safety/reports",
            probe_source,
            "验收探针不得调用已退役的非合同路由",
        )

    def test_local_operator_session_reuses_canonical_acceptance_issuer(self) -> None:
        support = _load_probe_support_module()
        session = support.LocalAcceptanceSession(
            owner_id="fixture_content_report_operator",
            persona_id="fixture_content_report_operator",
            access_token="operator-token",
        )
        with mock.patch.object(
            support,
            "open_local_acceptance_session",
            return_value=session,
        ) as issue:
            actual = support.operator_session(
                environment="gamma",
                base_url="https://gamma-api.quwoquan-env.test:19000",
                resolve_host="127.0.0.1",
                hosted_token_env="unused",
            )

        self.assertIs(actual, session)
        issue.assert_called_once_with(
            "https://gamma-api.quwoquan-env.test:19000",
            environment="gamma",
            target_name="gamma-local",
            profile="content-report-operator",
            subject="fixture_content_report_operator",
            resolve_host="127.0.0.1",
        )

    def test_gate_rejects_generic_stack_reports_without_object_probe(self) -> None:
        gate = _load_gate_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence.txt").write_text("current", encoding="utf-8")
            output_root = root / ".qwq_output/env"
            _write_stack_reports(output_root)
            gate.ROOT = root
            gate.OUTPUT_ROOT = output_root
            gate.REQUIRED_CODE_EVIDENCE = ("evidence.txt",)

            with self.assertRaisesRegex(
                AssertionError,
                "beta stackctl verify 报告缺少同次运行的举报反馈对象级探针",
            ):
                gate.verify()

    def test_gate_rejects_object_probe_from_a_different_stackctl_run(self) -> None:
        gate = _load_gate_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence.txt").write_text("current", encoding="utf-8")
            output_root = root / ".qwq_output/env"
            _write_stack_reports(output_root)
            _write_feature_report(
                output_root,
                environment="beta",
                run_id="feature-from-another-run",
                mode="lifecycle",
                lifecycle_steps=gate.LIFECYCLE_STEPS,
                lifecycle_facts=gate.LIFECYCLE_FACTS,
            )
            gate.ROOT = root
            gate.OUTPUT_ROOT = output_root
            gate.REQUIRED_CODE_EVIDENCE = ("evidence.txt",)

            with self.assertRaisesRegex(
                AssertionError,
                "beta stackctl verify 报告缺少同次运行的举报反馈对象级探针",
            ):
                gate.verify()

    def test_gate_accepts_fresh_stack_and_object_level_evidence(self) -> None:
        gate = _load_gate_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence.txt").write_text("current", encoding="utf-8")
            output_root = root / ".qwq_output/env"
            _write_stack_reports(output_root)
            _write_feature_report(
                output_root,
                environment="beta",
                run_id="stack-1",
                mode="lifecycle",
                lifecycle_steps=gate.LIFECYCLE_STEPS,
                lifecycle_facts=gate.LIFECYCLE_FACTS,
            )
            _write_feature_report(
                output_root,
                environment="gamma",
                run_id="stack-2",
                mode="lifecycle",
                lifecycle_steps=gate.LIFECYCLE_STEPS,
                lifecycle_facts=gate.LIFECYCLE_FACTS,
            )
            _write_feature_report(
                output_root,
                environment="prod",
                run_id="stack-3",
                mode="read-only",
                lifecycle_steps=gate.LIFECYCLE_STEPS,
                lifecycle_facts=gate.LIFECYCLE_FACTS,
            )
            gate.ROOT = root
            gate.OUTPUT_ROOT = output_root
            gate.REQUIRED_CODE_EVIDENCE = ("evidence.txt",)

            evidence = gate.verify()

            self.assertIn("feature", evidence["beta"])
            self.assertIn("feature", evidence["gamma"])
            self.assertIn("feature", evidence["prod"])

    def test_prod_probe_is_read_only_and_does_not_persist_token(self) -> None:
        _ProbeHandler.authorization_headers = []
        _ProbeHandler.report_items = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                report_path = Path(directory) / "report.json"
                env = os.environ.copy()
                env["PROD_ACCEPTANCE_AUTH_TOKEN"] = "test-token-must-not-persist"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(PROBE_PATH),
                        "--env",
                        "prod",
                        "--base-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--report",
                        str(report_path),
                    ],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                report_text = report_path.read_text(encoding="utf-8")
                report = json.loads(report_text)
                self.assertEqual(report["status"], "passed")
                self.assertEqual(report["mode"], "read-only")
                self.assertNotIn("test-token-must-not-persist", report_text)
                self.assertTrue(
                    all(
                        value == "Bearer test-token-must-not-persist"
                        for value in _ProbeHandler.authorization_headers
                    )
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_probe_fails_closed_when_private_reporter_account_leaks(self) -> None:
        _ProbeHandler.authorization_headers = []
        _ProbeHandler.report_items = [
            {
                "id": "report-with-account-leak",
                "reporterAccountId": "account-must-not-be-exposed",
            }
        ]
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                report_path = Path(directory) / "report.json"
                env = os.environ.copy()
                env["PROD_ACCEPTANCE_AUTH_TOKEN"] = "test-token"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(PROBE_PATH),
                        "--env",
                        "prod",
                        "--base-url",
                        f"http://127.0.0.1:{server.server_port}",
                        "--report",
                        str(report_path),
                    ],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(result.returncode, 1)
                report = json.loads(report_path.read_text(encoding="utf-8"))
                self.assertEqual(report["status"], "failed")
                self.assertEqual(report["failureCategory"], "privacy_leak")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            _ProbeHandler.report_items = []

    def test_prod_lifecycle_probe_fails_closed_before_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROBE_PATH),
                    "--env",
                    "prod",
                    "--base-url",
                    "http://127.0.0.1:1",
                    "--mode",
                    "lifecycle",
                    "--report",
                    str(report_path),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["failureCategory"], "unsafe_mode")


if __name__ == "__main__":
    unittest.main()
