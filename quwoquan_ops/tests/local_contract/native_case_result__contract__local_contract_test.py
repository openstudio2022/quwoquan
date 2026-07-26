"""Contracts for source-owned native Provider CaseResult emission."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.ci.provider_conformance import native_case_result


class NativeCaseResultContractTest(unittest.TestCase):
    def test_success_emits_result_and_digest_only_execution_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            result_path = Path(temporary_dir) / "case-results.json"
            environment = _execution_environment(result_path)
            with mock.patch.dict(os.environ, environment, clear=True):
                exit_code = native_case_result.run_native_harness(
                    command=(sys.executable, "-c", "print('provider-secret-output')"),
                    target="native-contract-target",
                )

            self.assertEqual(exit_code, 0)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "passed")
            self.assertEqual(
                [item["assertionId"] for item in result["caseResults"]],
                ["provider.success", "provider.validation"],
            )
            self.assertEqual(result["networkBoundary"], "offline_harness")
            self.assertTrue(result["dataDigest"].startswith("sha256:"))
            self.assertTrue(result["cleanupReceipt"].startswith("receipt:cleanup-"))

            telemetry_path = result_path.with_name(
                "case-results.native-execution.json"
            )
            serialized = telemetry_path.read_text(encoding="utf-8")
            self.assertIn("stdoutDigest", serialized)
            self.assertNotIn("provider-secret-output", serialized)

    def test_failed_native_command_does_not_emit_passed_case_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            result_path = Path(temporary_dir) / "case-results.json"
            environment = _execution_environment(result_path)
            with (
                mock.patch.dict(os.environ, environment, clear=True),
                self.assertRaisesRegex(ValueError, "native Provider harness failed"),
            ):
                native_case_result.run_native_harness(
                    command=(sys.executable, "-c", "raise SystemExit(7)"),
                    target="native-contract-target",
                )
            self.assertFalse(result_path.exists())


def _execution_environment(result_path: Path) -> dict[str, str]:
    return {
        "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH": str(result_path),
        "QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID": "ext.test.native",
        "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID": "runtime.test.native",
        "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT": "alpha",
        "QWQ_PROVIDER_CONFORMANCE_LAYER": "local_contract",
        "QWQ_PROVIDER_CONFORMANCE_TYPED_PORT": "NativeTestPort",
        "QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF": (
            "quwoquan_service/services/test-service/contracts/test/operations.yaml"
        ),
        "QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST": "sha256:" + "a" * 64,
        "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS": json.dumps(
            ["provider.success", "provider.validation"]
        ),
    }


if __name__ == "__main__":
    unittest.main()
