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
        self.assertIn("load_target_uat_binding", source)
        self.assertNotIn("write_passed_case_result", source)

    def test_local_gamma_release_consumer_uses_exact_readiness_identity(self) -> None:
        result = local_gamma_release_consumer.run_release_consumer(
            identity=_gamma_release_identity(),
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["mutationPolicy"], "read_only")
        self.assertEqual(result["releaseId"], "release-gamma-a")
        self.assertEqual(result["importRunId"], "import-gamma-a")
        self.assertEqual(result["verifyRunId"], "verify-gamma-a")
        self.assertEqual(result["command"], [])

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
                    "resolve_gamma_evidence_path",
                    side_effect=lambda raw, label: report_path if "report" in label else Path(raw),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_target_uat_binding",
                    return_value=({"releaseId": "release-gamma-a", "releaseDigest": f"sha256:{'1' * 64}", "provider": {"identity": "provider-gamma"}}, "sha256:" + "9" * 64),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "target_uat_binding_digest",
                    return_value="sha256:" + "9" * 64,
                ),
                mock.patch.object(
                    Path, "read_bytes", return_value=b"{}"
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
                        "--target-uat-binding",
                        "env/gamma/runs/release-consumer/target-uat-binding.json",
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
                    "resolve_gamma_evidence_path",
                    side_effect=lambda raw, label: report_path if "report" in label else Path(raw),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_target_uat_binding",
                    return_value=({"releaseId": "release-gamma-a", "releaseDigest": f"sha256:{'1' * 64}", "provider": {"identity": "provider-gamma"}}, "sha256:" + "9" * 64),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "target_uat_binding_digest",
                    return_value="sha256:" + "9" * 64,
                ),
                mock.patch.object(
                    Path, "read_bytes", return_value=b"{}"
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
                        "--target-uat-binding",
                        "env/gamma/runs/release-consumer/target-uat-binding.json",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                self.assertEqual(local_gamma_release_consumer.main(), 0)

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report["schema"], "quwoquan.gamma-release-consumer-diagnostic.v1")
        self.assertEqual(report["mutationPolicy"], "read_only")
        self.assertEqual(report["exitCode"], 0)
        self.assertEqual(report["releaseId"], "release-gamma-a")
        self.assertNotIn("status", report)
        self.assertNotIn("baselineId", report)

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
                    "resolve_gamma_evidence_path",
                    side_effect=lambda raw, label: report_path if "report" in label else Path(raw),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_target_uat_binding",
                    return_value=({"releaseId": "release-gamma-a", "releaseDigest": f"sha256:{'1' * 64}", "provider": {"identity": "provider-gamma"}}, "sha256:" + "9" * 64),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "target_uat_binding_digest",
                    return_value="sha256:" + "9" * 64,
                ),
                mock.patch.object(
                    Path, "read_bytes", return_value=b"{}"
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
                        "--target-uat-binding",
                        "env/gamma/runs/release-consumer/target-uat-binding.json",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                self.assertEqual(local_gamma_release_consumer.main(), 2)

            consumer.assert_not_called()
            self.assertFalse(report_path.exists())

    def test_local_gamma_consumer_does_not_rerun_release_orchestration(self) -> None:
        source = Path(local_gamma_release_consumer.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"quwoquan_data/scripts/cli.py"', source)
        self.assertNotIn('"ship"', source)
        self.assertIn("load_release_content_identity", source)
        self.assertIn("load_target_uat_binding", source)

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
                    "resolve_gamma_evidence_path",
                    side_effect=lambda raw, label: report_path if "report" in label else Path(raw),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "load_target_uat_binding",
                    return_value=({"releaseId": "release-gamma-a", "releaseDigest": f"sha256:{'1' * 64}", "provider": {"identity": "provider-gamma"}}, "sha256:" + "9" * 64),
                ),
                mock.patch.object(
                    local_gamma_release_consumer,
                    "target_uat_binding_digest",
                    return_value="sha256:" + "9" * 64,
                ),
                mock.patch.object(
                    Path, "read_bytes", return_value=b"{}"
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
                        "--target-uat-binding",
                        "env/gamma/runs/release-consumer/target-uat-binding.json",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                status = local_gamma_release_consumer.main()

        self.assertEqual(status, 2)
        consumer.assert_not_called()
        self.assertFalse(report_path.exists())

    def test_local_gamma_existing_readiness_is_not_reexecuted(self) -> None:
        with mock.patch.object(local_gamma_release_consumer.subprocess, "run") as run:
            result = local_gamma_release_consumer.run_release_consumer(
                identity=_gamma_release_identity(),
            )
        run.assert_not_called()
        self.assertEqual(result["status"], "passed")

    def test_local_gamma_runtime_refs_ignore_environment_aliases(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"QWQ_DATA_RELEASE_ID": "parallel-release", "QWQ_GAMMA_IMPORT_RUN_ID": "parallel-import"},
            clear=False,
        ):
            result = local_gamma_release_consumer.run_release_consumer(identity=_gamma_release_identity())
        self.assertEqual(result["releaseId"], "release-gamma-a")
        self.assertEqual(result["importRunId"], "import-gamma-a")

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
        self.assertNotIn("quwoquan_data/scripts/cli.py", source)

    def test_local_gamma_release_consumer_has_no_subprocess_output_channel(self) -> None:
        result = local_gamma_release_consumer.run_release_consumer(identity=_gamma_release_identity())
        self.assertEqual(result["outputTail"], "")
        self.assertEqual(result["command"], [])

    def test_local_gamma_release_consumer_strict_endpoint_checks_uses_scope_runtime_refs(self) -> None:
        with (
            mock.patch.object(
                local_gamma_release_consumer.sys,
                "argv",
                ["run_local_gamma_release_consumer_api.py", "--enabled-domain", "content",
                 "--target-uat-binding", "env/gamma/runs/release-consumer/target-uat-binding.json"],
            ),
            self.assertRaises(SystemExit) as raised,
        ):
            local_gamma_release_consumer.main()

        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
