from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_app.scripts.gamma import run_local_gamma_release_consumer_api as local_gamma_release_consumer
from quwoquan_app.scripts.gamma import verify_local_gamma_mirror
from quwoquan_ops.cli import stackctl


def gamma_release_identity() -> dict[str, object]:
    return {
        "releaseId": "release-gamma-a",
        "sourceOwner": "quwoquan_data",
        "manifestDigest": "sha256:" + ("1" * 64),
        "mediaManifestDigest": "sha256:" + ("2" * 64),
        "importRunId": "import-gamma-a",
        "verifyRunId": "verify-gamma-a",
        "readinessReceiptRef": (
            "env/gamma/runs/data-release/release-gamma-a/verify-gamma-a/"
            "release-readiness.json"
        ),
    }


def gamma_candidate_identity() -> dict[str, str]:
    return {
        "environment": "gamma",
        "target": "gamma-local",
        "baselineId": "sha256:" + ("3" * 64),
        "attemptId": "attempt-gamma-a",
        "packageDigest": "sha256:" + ("4" * 64),
        "configurationDigest": "sha256:" + ("5" * 64),
        "providerRuntimeDigest": "sha256:" + ("6" * 64),
        "observabilityLogSinkDigest": "sha256:" + ("7" * 64),
        "imageDigest": "sha256:" + ("8" * 64),
    }


class LocalGammaCommentSeedContractTest(unittest.TestCase):
    def test_release_consumer_has_no_fixture_post_projection_or_comment_mutation(self) -> None:
        source = Path(local_gamma_release_consumer.__file__).read_text(encoding="utf-8")

        for retired in (
            "fixture_post_to_doc",
            "seed_content",
            "setup_comment_thread",
            "setup_runtime_fixtures",
            "mongosh",
            "/content/comments",
        ):
            self.assertNotIn(retired, source)
        self.assertIn("load_release_content_identity", source)
        self.assertIn("load_gamma_execution_identity", source)
        self.assertIn("write_passed_case_result", source)

    def test_release_consumer_command_is_bound_to_receipt_identity(self) -> None:
        completed = subprocess.CompletedProcess(
            ["quwoquan_data/scripts/cli.py"],
            0,
            stdout="release verification passed",
        )
        with mock.patch.object(
            local_gamma_release_consumer.subprocess,
            "run",
            return_value=completed,
        ) as run:
            result = local_gamma_release_consumer.run_release_consumer(
                identity=gamma_release_identity(),
            )

        command = run.call_args.args[0]
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["mutationPolicy"], "read_only")
        self.assertEqual(
            command[command.index("--release-id") + 1],
            "release-gamma-a",
        )
        self.assertEqual(
            command[command.index("--import-run-id") + 1],
            "import-gamma-a",
        )
        self.assertEqual(command[command.index("--run-id") + 1], "verify-gamma-a")
        self.assertNotIn("fixture", " ".join(command))

    def test_release_consumer_success_report_is_read_only_and_release_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "release_consumer.json"
            with (
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_release_consumer_report_path",
                    return_value=report_path,
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_readiness_path",
                    return_value=Path("/tmp/release-readiness.json"),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_release_content_identity",
                    return_value=gamma_release_identity(),
                ) as load_identity,
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_gamma_execution_identity",
                    return_value=gamma_candidate_identity(),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "require_unchanged_identity",
                    return_value=gamma_candidate_identity(),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "run_release_consumer",
                    return_value={
                        "status": "passed",
                        "mutationPolicy": "read_only",
                        "exitCode": 0,
                    },
                ),
                mock.patch.object(
                    local_gamma_release_consumer.sys,
                    "argv",
                    [
                        "run_local_gamma_release_consumer_api.py",
                        "--release-readiness",
                        "env/gamma/runs/data-release/release-gamma-a/"
                        "verify-gamma-a/release-readiness.json",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                self.assertEqual(local_gamma_release_consumer.main(), 0)

            report = json.loads(report_path.read_text(encoding="utf-8"))

        load_identity.assert_called_once_with(
            Path("/tmp/release-readiness.json"),
            expected_environment="gamma",
        )
        self.assertEqual(set(report), verify_local_gamma_mirror.CASE_RESULT_FIELDS)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["baselineId"], gamma_candidate_identity()["baselineId"])
        self.assertEqual(report["attemptId"], gamma_candidate_identity()["attemptId"])
        self.assertEqual(report["executed"], 1)
        self.assertEqual(report["skipped"], 0)
        self.assertEqual(report["failed"], 0)
        self.assertNotIn("release", report)
        self.assertNotIn("domainSeeds", report)

    def test_release_consumer_missing_readiness_fails_closed_without_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "release_consumer.json"
            with (
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_release_consumer_report_path",
                    return_value=report_path,
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_readiness_path",
                    side_effect=local_gamma_release_consumer.ReleaseVideoDeliveryError(
                        "DATA_RELEASE_READINESS_RECEIPT is required"
                    ),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_gamma_execution_identity",
                    return_value=gamma_candidate_identity(),
                ),
                mock.patch.object(local_gamma_release_consumer, "run_release_consumer") as consumer,
                mock.patch.object(
                    local_gamma_release_consumer.sys,
                    "argv",
                    ["run_local_gamma_release_consumer_api.py", "--report", str(report_path)],
                ),
            ):
                self.assertEqual(local_gamma_release_consumer.main(), 2)

            report = json.loads(report_path.read_text(encoding="utf-8"))

        consumer.assert_not_called()
        self.assertEqual(report["status"], "gate_block")
        self.assertIn("DATA_RELEASE_READINESS_RECEIPT is required", report["reason"])

    def test_release_consumer_rejects_environment_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "release_consumer.json"
            with (
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_release_consumer_report_path",
                    return_value=report_path,
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_readiness_path",
                    return_value=Path("/tmp/release-readiness.json"),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_gamma_execution_identity",
                    return_value=gamma_candidate_identity(),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_release_content_identity",
                    side_effect=local_gamma_release_consumer.ReleaseVideoDeliveryError(
                        "Data readiness environment='beta', expected 'gamma'"
                    ),
                ),
                mock.patch.object(local_gamma_release_consumer, "run_release_consumer") as consumer,
                mock.patch.object(
                    local_gamma_release_consumer.sys,
                    "argv",
                    ["run_local_gamma_release_consumer_api.py", "--report", str(report_path)],
                ),
            ):
                self.assertEqual(local_gamma_release_consumer.main(), 2)

        consumer.assert_not_called()

    def test_release_consumer_failure_is_not_downgraded(self) -> None:
        failed = subprocess.CompletedProcess(
            ["quwoquan_data/scripts/cli.py"],
            1,
            stdout="GATE_BLOCK: import receipt mismatch",
        )
        with mock.patch.object(
            local_gamma_release_consumer.subprocess,
            "run",
            return_value=failed,
        ):
            result = local_gamma_release_consumer.run_release_consumer(
                identity=gamma_release_identity(),
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exitCode"], 1)
        self.assertIn("GATE_BLOCK", result["outputTail"])

    def test_gamma_integration_profile_does_not_restore_release_consumer_fixture_probe(self) -> None:
        commands = stackctl._selected_profile_commands(
            "gamma",
            "gamma-local",
            stackctl.VerificationProfile.INTEGRATION,
        )

        names = {str(command["name"]) for command in commands}
        argv = " ".join(
            str(part)
            for command in commands
            for part in command.get("argv", [])
        )
        self.assertIn("filter-catalog-active-release", names)
        self.assertNotIn("gamma-local-release-consumer", names)
        self.assertNotIn("run_local_gamma_release_consumer_api.py", argv)


if __name__ == "__main__":
    unittest.main()
