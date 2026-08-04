# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-003

from __future__ import annotations

import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_app.scripts.gamma import verify_local_gamma_mirror


def _canonical_running_attempt(
    target: str,
    workload: str,
) -> dict[str, object]:
    image_digest = "sha256:" + "2" * 64
    return {
        "schema": "stackctl-local-startup-attempt",
        "attemptId": f"attempt-{target}",
        "env": target.removesuffix("-local"),
        "target": target,
        "status": "running",
        "workload": workload,
        "composeProject": f"quwoquan_{target.removesuffix('-local')}_release_test",
        "configurationDigest": "sha256:" + "1" * 64,
        "imageTransportTag": image_digest,
        "imageComposition": {"imageVersion": image_digest, "images": {}},
    }


class StackctlRuntimeReceiptSingleTrackContractTest(unittest.TestCase):
    def test_health_scope_uses_canonical_current_startup_attempt(self) -> None:
        cases = (
            ("alpha-local", "content-release", "content-consumer"),
            ("beta-local", "content-commercial", "content-commercial"),
            ("gamma-local", "full", "full"),
        )
        for target, workload, expected_scope in cases:
            with self.subTest(target=target, workload=workload):
                attempt = _canonical_running_attempt(target, workload)
                with mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=attempt,
                ):
                    actual_scope = stackctl._current_runtime_health_scope(target)

                self.assertEqual(actual_scope, expected_scope)

    def test_health_scope_ignores_retired_environment_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            process_dir = Path(temporary_dir)
            run_root = process_dir / "old-run"
            run_root.mkdir()
            (process_dir / "stack.state").write_text(
                "workload=content-commercial\n",
                encoding="utf-8",
            )
            (process_dir / "stack_status.json").write_text(
                '{"status":"passed","workload":"content-commercial"}',
                encoding="utf-8",
            )
            (process_dir / "content-release.json").write_text(
                '{"workload":"content-release"}',
                encoding="utf-8",
            )
            (process_dir / "local_run.json").write_text(
                json.dumps({"runRoot": str(run_root)}),
                encoding="utf-8",
            )
            (run_root / "report.json").write_text(
                json.dumps(
                    {
                        "command": "up",
                        "resolvedTarget": "alpha-local",
                        "workload": "content-commercial",
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "target_process_dir",
                    return_value=process_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=None,
                ),
            ):
                actual_scope = stackctl._current_runtime_health_scope("alpha-local")

        self.assertEqual(actual_scope, "full")

    def test_stopped_or_drifted_current_attempt_fails_closed(self) -> None:
        stopped = _canonical_running_attempt("gamma-local", "content-commercial")
        stopped["status"] = "stopped"
        drifted = _canonical_running_attempt("gamma-local", "content-commercial")
        drifted["target"] = "beta-local"
        malformed = _canonical_running_attempt("gamma-local", "content-commercial")
        malformed["configurationDigest"] = "not-a-digest"

        for attempt in (stopped, drifted, malformed):
            with self.subTest(attempt=attempt):
                with mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=attempt,
                ):
                    actual_scope = stackctl._current_runtime_health_scope(
                        "gamma-local"
                    )

                self.assertEqual(actual_scope, "full")

    def test_control_consumers_contain_no_retired_receipt_identity(self) -> None:
        sources = (
            inspect.getsource(stackctl._current_runtime_health_scope),
            inspect.getsource(stackctl._load_gamma_runtime_image_composition),
        )

        for source in sources:
            for retired_identity in (
                "stack.state",
                "stack_status.json",
                "content-release.json",
                "local_run.json",
                "report.json",
                "runtimeEnv",
                "startup_attempt_path",
            ):
                self.assertNotIn(retired_identity, source)

    def test_gamma_verifier_consumes_canonical_startup_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            report_path = root / "report.json"
            startup_path = root / "startup_attempt.json"
            t3_path = root / "t3.json"
            t4_path = root / "t4.json"
            configuration_digest = "sha256:" + "1" * 64
            image_digest = "sha256:" + "2" * 64
            startup_path.write_text(
                json.dumps(
                    {
                        "schema": "stackctl-local-startup-attempt",
                        "status": "running",
                        "target": "gamma-local",
                        "env": "gamma",
                        "composeProject": "quwoquan_gamma_release_test",
                        "workload": "content-release",
                        "configurationDigest": configuration_digest,
                        "imageTransportTag": image_digest,
                        "imageComposition": {
                            "imageVersion": image_digest,
                            "images": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            t3_path.write_text('{"status":"passed"}', encoding="utf-8")
            t4_path.write_text('{"status":"passed"}', encoding="utf-8")
            argv = [
                "verify_local_gamma_mirror.py",
                "--report",
                str(report_path),
                "--startup-receipt",
                str(startup_path),
                "--t3-report",
                str(t3_path),
                "--t4-report",
                str(t4_path),
                "--configuration-digest",
                configuration_digest,
            ]
            with mock.patch.object(sys, "argv", argv):
                exit_code = verify_local_gamma_mirror.main()

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["startupAttempt"]["target"], "gamma-local")
        self.assertNotIn("stack", report)

    def test_gamma_runtime_sources_contain_no_retired_receipt_identity(self) -> None:
        root = Path(__file__).resolve().parents[3]
        sources = (
            root
            / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
            root
            / "quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py",
            root / "quwoquan_ops/cli/stackctl.py",
        )

        for source_path in sources:
            source = source_path.read_text(encoding="utf-8")
            for retired_identity in (
                "LOCAL_GAMMA_STACK_STATUS_REPORT",
                "stack_status.json",
                "--stack-report",
            ):
                self.assertNotIn(retired_identity, source)


if __name__ == "__main__":
    unittest.main()
