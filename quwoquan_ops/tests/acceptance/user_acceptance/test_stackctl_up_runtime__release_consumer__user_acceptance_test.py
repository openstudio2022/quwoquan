# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-004
"""场景：local gamma release consumer——canonical release identity 消费、
readiness receipt fail-closed、CaseResult 报告字段、blocked operation 的
metadata 403 语义与 runtime bearer 身份边界。"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_app.scripts.gamma import run_local_gamma_release_consumer_api as local_gamma_release_consumer
from quwoquan_app.scripts.gamma import verify_local_gamma_mirror


def _gamma_release_identity() -> dict[str, object]:
    return {
        "releaseId": "release-gamma-a",
        "sourceOwner": "qwq_data",
        "manifestDigest": f"sha256:{'1' * 64}",
        "mediaManifestDigest": f"sha256:{'2' * 64}",
        "importRunId": "import-gamma-a",
        "verifyRunId": "verify-gamma-a",
        "readinessReceiptRef": (
            "env/gamma/runs/data-release/release-gamma-a/verify-gamma-a/"
            "release-readiness.json"
        ),
    }


def _gamma_candidate_identity() -> dict[str, str]:
    return {
        "environment": "gamma",
        "target": "gamma-local",
        "baselineId": f"sha256:{'3' * 64}",
        "attemptId": "attempt-gamma-a",
        "packageDigest": f"sha256:{'4' * 64}",
        "configurationDigest": f"sha256:{'5' * 64}",
        "providerRuntimeDigest": f"sha256:{'6' * 64}",
        "observabilityLogSinkDigest": f"sha256:{'7' * 64}",
        "imageDigest": f"sha256:{'8' * 64}",
    }


class StackctlUpRuntimeTest(unittest.TestCase):
    def test_local_gamma_content_seed_is_idempotent_and_fail_closed(self) -> None:
        source = Path(local_gamma_release_consumer.__file__).read_text(encoding="utf-8")

        for retired in (
            "seed_content",
            "setup_runtime_fixtures",
            "test_fixtures",
            "mongosh",
            "deleteMany",
        ):
            self.assertNotIn(retired, source)
        self.assertIn("load_release_content_identity", source)
        self.assertIn("load_gamma_execution_identity", source)
        self.assertIn("write_passed_case_result", source)

    def test_local_gamma_video_seed_preserves_work_browser_projection_fields(
        self,
    ) -> None:
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
                identity=_gamma_release_identity(),
            )

        command = run.call_args.args[0]
        self.assertEqual(result["status"], "passed")
        self.assertIn("ship", command)
        self.assertIn("verify", command)
        self.assertEqual(command[command.index("--release-id") + 1], "release-gamma-a")
        self.assertEqual(command[command.index("--import-run-id") + 1], "import-gamma-a")
        self.assertEqual(command[command.index("--run-id") + 1], "verify-gamma-a")
        self.assertNotIn("fixture", " ".join(command))

    def test_local_gamma_relationship_seed_uses_running_stack_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "release_consumer.json"
            with (
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_readiness_path",
                    return_value=Path("/tmp/release-readiness.json"),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_release_content_identity",
                    return_value=_gamma_release_identity(),
                ) as load_identity,
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_gamma_execution_identity",
                    return_value=_gamma_candidate_identity(),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "require_unchanged_identity",
                    return_value=_gamma_candidate_identity(),
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
                    local_gamma_release_consumer,
                    "resolve_release_consumer_report_path",
                    return_value=report_path,
                ),
                mock.patch.object(
                    local_gamma_release_consumer.sys,
                    "argv",
                    [
                        "run_local_gamma_release_consumer_api.py",
                        "--release-readiness",
                        "env/gamma/release-readiness.json",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                result = local_gamma_release_consumer.main()

        self.assertEqual(result, 0)
        load_identity.assert_called_once_with(
            Path("/tmp/release-readiness.json"),
            expected_environment="gamma",
        )

    def test_local_gamma_release_consumer_uses_shared_target_isolated_acceptance_session(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "release-consumer-report.json"
            with (
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_readiness_path",
                    return_value=Path("/tmp/release-readiness.json"),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_release_content_identity",
                    return_value=_gamma_release_identity(),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_gamma_execution_identity",
                    return_value=_gamma_candidate_identity(),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "require_unchanged_identity",
                    return_value=_gamma_candidate_identity(),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "run_release_consumer",
                    return_value={
                        "status": "passed",
                        "mutationPolicy": "read_only",
                        "exitCode": 0,
                        "command": ["ship", "verify"],
                    },
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_release_consumer_report_path",
                    return_value=report_path,
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

        self.assertEqual(set(report), verify_local_gamma_mirror.CASE_RESULT_FIELDS)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["baselineId"], _gamma_candidate_identity()["baselineId"])
        self.assertEqual(report["attemptId"], _gamma_candidate_identity()["attemptId"])
        self.assertEqual(report["executed"], 1)
        self.assertEqual(report["skipped"], 0)
        self.assertEqual(report["failed"], 0)
        self.assertNotIn("release", report)
        self.assertNotIn("auth", report)
        self.assertNotIn("domainSeeds", report)

    def test_local_gamma_seed_only_persists_user_profile_for_authenticated_probes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "release-consumer-seed-report.json"
            with (
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
                    return_value=_gamma_candidate_identity(),
                ),
                mock.patch.object(local_gamma_release_consumer, "run_release_consumer") as consumer,
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_release_consumer_report_path",
                    return_value=report_path,
                ),
                mock.patch.object(
                    local_gamma_release_consumer.sys,
                    "argv",
                    [
                        "run_local_gamma_release_consumer_api.py",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                self.assertEqual(local_gamma_release_consumer.main(), 2)

            consumer.assert_not_called()
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "gate_block")
        self.assertIn("DATA_RELEASE_READINESS_RECEIPT is required", report["reason"])

    def test_local_gamma_content_probe_methods_come_from_contract_graph(self) -> None:
        source = Path(local_gamma_release_consumer.__file__).read_text(encoding="utf-8")

        self.assertIn('"quwoquan_data/scripts/cli.py"', source)
        self.assertIn('"ship"', source)
        self.assertIn('"verify"', source)
        self.assertNotIn("content_route_methods", source)
        self.assertNotIn("/content/comments", source)

    def test_local_gamma_blocked_operation_requires_metadata_enforced_403(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "release-consumer-invalid-environment.json"
            with (
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_readiness_path",
                    return_value=Path("/tmp/release-readiness.json"),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_release_content_identity",
                    side_effect=local_gamma_release_consumer.ReleaseVideoDeliveryError(
                        "Data readiness environment='beta', expected 'gamma'"
                    ),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_gamma_execution_identity",
                    return_value=_gamma_candidate_identity(),
                ),
                mock.patch.object(local_gamma_release_consumer, "run_release_consumer") as consumer,
                mock.patch.object(
                    local_gamma_release_consumer,
                    "resolve_release_consumer_report_path",
                    return_value=report_path,
                ),
                mock.patch.object(
                    local_gamma_release_consumer.sys,
                    "argv",
                    [
                        "run_local_gamma_release_consumer_api.py",
                        "--release-readiness",
                        "env/beta/release-readiness.json",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                status = local_gamma_release_consumer.main()

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(status, 2)
        consumer.assert_not_called()
        self.assertEqual(report["status"], "gate_block")
        self.assertIn("expected 'gamma'", report["reason"])

    def test_local_gamma_blocked_operation_fails_if_it_unexpectedly_accepts(self) -> None:
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
                identity=_gamma_release_identity(),
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exitCode"], 1)
        self.assertIn("import receipt mismatch", result["outputTail"])

    def test_local_gamma_runtime_refs_keep_owner_and_persona_ids_distinct(self) -> None:
        with (
            mock.patch.dict(
                os.environ,
                {
                    "QWQ_DATA_RELEASE_ID": "parallel-release",
                    "QWQ_GAMMA_IMPORT_RUN_ID": "parallel-import",
                },
                clear=False,
            ),
            mock.patch.object(
                local_gamma_release_consumer.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(["ship"], 0, stdout="ok"),
            ) as run,
        ):
            local_gamma_release_consumer.run_release_consumer(identity=_gamma_release_identity())

        command = run.call_args.args[0]
        self.assertIn("release-gamma-a", command)
        self.assertIn("import-gamma-a", command)
        self.assertNotIn("parallel-release", command)
        self.assertNotIn("parallel-import", command)

    def test_local_gamma_comment_setup_uses_current_command_contract(self) -> None:
        source = Path(local_gamma_release_consumer.__file__).read_text(encoding="utf-8")

        for retired in (
            "setup_comment_thread",
            "http_request",
            "Idempotency-Key",
            "attachmentMediaIds",
            "comment-parent",
        ):
            self.assertNotIn(retired, source)

    def test_local_gamma_release_consumer_uses_only_runtime_bearer_identity(self) -> None:
        source = Path(local_gamma_release_consumer.__file__).read_text(encoding="utf-8")

        self.assertNotIn("Authorization", source)
        self.assertNotIn("Bearer", source)
        self.assertNotIn("X-Client-User-Id", source)
        self.assertNotIn("LocalGammaAcceptanceSession", source)
        self.assertIn("DATA_RELEASE_READINESS_RECEIPT", source)

    def test_local_gamma_release_consumer_compose_command_uses_stack_project(self) -> None:
        source = Path(local_gamma_release_consumer.__file__).read_text(encoding="utf-8")

        self.assertNotIn("docker", source)
        self.assertNotIn("compose_command", source)
        self.assertNotIn("mongodb", source)
        self.assertNotIn("mongosh", source)
        self.assertIn("quwoquan_data/scripts/cli.py", source)

    def test_local_gamma_release_consumer_endpoint_checks_marks_scope_externals_out_of_scope(self) -> None:
        long_output = "discarded-prefix" + ("x" * 9000)
        with mock.patch.object(
            local_gamma_release_consumer.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(["ship"], 1, stdout=long_output),
        ):
            result = local_gamma_release_consumer.run_release_consumer(
                identity=_gamma_release_identity(),
            )

        self.assertEqual(len(result["outputTail"]), 8000)
        self.assertNotIn("discarded-prefix", result["outputTail"])
        self.assertEqual(result["status"], "failed")

    def test_local_gamma_release_consumer_strict_endpoint_checks_uses_scope_runtime_refs(self) -> None:
        with (
            mock.patch.object(
                local_gamma_release_consumer.sys,
                "argv",
                ["run_local_gamma_release_consumer_api.py", "--enabled-domain", "content"],
            ),
            self.assertRaises(SystemExit) as raised,
        ):
            local_gamma_release_consumer.main()

        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
