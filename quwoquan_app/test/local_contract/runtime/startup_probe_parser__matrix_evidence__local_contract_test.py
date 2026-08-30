# spec_ref: specs/feature-tree/spec.md#uat-003
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
#
# 由 1000 行硬顶从 startup_probe_parser__local_contract_test.py 拆出：
# 本文件承接矩阵证据校验场景组（execution input 候选唯一性、执行前置条件、
# readback 证据、observability readback 绑定、20 次真实 runtime 样本）；
# 测试逐字搬移。

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))
sys.path.insert(0, str(APP_DIR / "scripts/runtime/platform"))
sys.path.insert(0, str(APP_DIR / "test/support/runtime/launcher"))

from run_dual_platform_usability_matrix import (
    _load_execution_input,
    _validate_execution_preconditions,
)
import verify_startup_environment_matrix as startup_matrix
from verify_startup_environment_matrix import (
    _validate_observability_evidence,
    _validate_readback_evidence,
    _validate_runtime_evidence,
)


class StartupProbeParserContractTest(unittest.TestCase):
    def test_execution_input_requires_unique_real_candidate_cases(self) -> None:
        digest = "sha256:" + "b" * 64
        payload = {
            "schema": "qwq.startup-matrix-execution-input",
            "baselineId": "baseline-001",
            "releaseId": "release-001",
            "releaseDigest": digest,
            "cases": [
                {
                    "environment": "prod",
                    "target": "prod-hosted",
                    "platform": "ios",
                    "deviceId": "iphone-real-001",
                    "deviceKind": "physical",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "execution.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            cases = _load_execution_input(
                path,
                baseline_id="baseline-001",
                release_id="release-001",
                release_digest=digest,
            )
            self.assertEqual(cases[0]["deviceId"], "iphone-real-001")

            payload["cases"][0]["deviceKind"] = "simulator"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "physical device"):
                _load_execution_input(
                    path,
                    baseline_id="baseline-001",
                    release_id="release-001",
                    release_digest=digest,
                )

    def test_execution_preconditions_gate_block_missing_release_inputs(self) -> None:
        case = {
            "environment": "beta",
            "target": "beta-local",
            "platform": "android",
            "deviceId": "android-emulator-001",
            "deviceKind": "emulator",
            "install": False,
        }
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GATE_BLOCK"):
                _validate_execution_preconditions(case)

    def test_readback_evidence_requires_real_non_skipped_case_result(self) -> None:
        digest = "sha256:" + "c" * 64
        payload = {
            "schema": startup_matrix.READBACK_EVIDENCE_SCHEMA,
            "status": "passed",
            "baselineId": "baseline-001",
            "releaseId": "release-001",
            "releaseDigest": digest,
            "environment": "gamma",
            "target": "gamma-local",
            "platform": "android",
            "deviceId": "android-real-001",
            "effectiveLaunchManifestDigest": digest,
            "required": 1,
            "executed": 1,
            "skipped": 0,
            "failed": 0,
            "specRefs": list(startup_matrix.SPEC_REFS),
            "caseResults": [
                {
                    "caseId": "readback",
                    "status": "passed",
                    "testExecution": {
                        "executed": 1,
                        "skipped": 0,
                        "failed": 0,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "android.readback.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_readback_evidence(
                path,
                expected_environment="gamma",
                expected_target="gamma-local",
                expected_platform="android",
                expected_effective_manifest_digest=digest,
                expected_baseline_id="baseline-001",
                expected_release_id="release-001",
                expected_release_digest=digest,
            )
            self.assertEqual(issues, [])

            payload["executed"] = 0
            payload["skipped"] = 1
            path.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_readback_evidence(
                path,
                expected_environment="gamma",
                expected_target="gamma-local",
                expected_platform="android",
                expected_effective_manifest_digest=digest,
                expected_baseline_id="baseline-001",
                expected_release_id="release-001",
                expected_release_digest=digest,
            )
            self.assertTrue(any("executed" in issue for issue in issues))
            self.assertTrue(any("skipped" in issue for issue in issues))

    def test_observability_readback_binds_attempt_device_and_candidate(self) -> None:
        digest = "sha256:" + "f" * 64
        payload = {
            "schema": startup_matrix.OBSERVABILITY_EVIDENCE_SCHEMA,
            "status": "passed",
            "environment": "beta",
            "target": "beta-local",
            "baselineId": "baseline-001",
            "releaseId": "release-001",
            "releaseDigest": digest,
            "effectiveLaunchManifestDigest": digest,
            "attemptIds": ["attempt-beta-01", "attempt-beta-02"],
            "deviceIds": ["emulator-5554", "android-real-001"],
            "telemetryBackend": "product-ops-event-record",
            "backendReceiptRef": "beta/telemetry-readback.json",
            "required": 2,
            "executed": 2,
            "skipped": 0,
            "failed": 0,
            "specRefs": list(startup_matrix.SPEC_REFS),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observability.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_observability_evidence(
                path,
                expected_environment="beta",
                expected_target="beta-local",
                expected_effective_manifest_digest=digest,
                expected_baseline_id="baseline-001",
                expected_release_id="release-001",
                expected_release_digest=digest,
                expected_attempt_ids=["attempt-beta-01", "attempt-beta-02"],
                expected_device_ids=["emulator-5554", "android-real-001"],
            )
            self.assertEqual(issues, [])

            payload["attemptIds"][1] = "unknown"
            payload["backendReceiptRef"] = ""
            path.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_observability_evidence(
                path,
                expected_environment="beta",
                expected_target="beta-local",
                expected_effective_manifest_digest=digest,
                expected_baseline_id="baseline-001",
                expected_release_id="release-001",
                expected_release_digest=digest,
                expected_attempt_ids=["attempt-beta-01", "attempt-beta-02"],
                expected_device_ids=["emulator-5554", "android-real-001"],
            )
            self.assertTrue(any("attemptIds" in issue for issue in issues))
            self.assertTrue(any("backendReceiptRef" in issue for issue in issues))

    def test_runtime_matrix_requires_each_of_twenty_real_samples(self) -> None:
        digest = "sha256:" + "a" * 64
        sample = {
            "runtimeEnv": "prod",
            "runtimeTarget": "prod-hosted",
            "platform": "ios",
            "passed": True,
            "attemptId": "attempt_real_01",
            "rendererFirstFrameMs": 900,
            "safeTerminalMs": 1200,
            "reportedSafeTerminalMs": 1190,
            "nativeReceivedSafeTerminalMs": 1210,
            "watchdogOutcome": "safe_terminal",
            "canonicalTerminal": "routerShell",
            "launchProvenance": "release_package",
            "runtimeConfigSupplyMode": "external_runtime_package",
            "runtimeConfigurationState": "complete",
            "missingDefineKeys": "",
            "failureCode": "",
            "startupSequenceMotionCurrent": True,
            "effectiveLaunchManifestDigest": digest,
            "telemetryAcknowledged": True,
            "sceneLaunchUsed": True,
            "sceneStarted": True,
            "sceneLauncher": "xcrun_devicectl",
        }
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "ios.json"
            report.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "samples": [
                            {
                                **sample,
                                "attemptId": f"attempt_real_{index:02d}",
                            }
                            for index in range(20)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            issues, _ = _validate_runtime_evidence(
                report,
                expected_environment="prod",
                expected_target="prod-hosted",
                expected_platform="ios",
                expected_effective_manifest_digest=digest,
                minimum_runs=20,
            )
            self.assertEqual(issues, [])

            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["samples"][7]["attemptId"] = "unknown"
            report.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_runtime_evidence(
                report,
                expected_environment="prod",
                expected_target="prod-hosted",
                expected_platform="ios",
                expected_effective_manifest_digest=digest,
                minimum_runs=20,
            )
            self.assertTrue(any("attemptId missing" in issue for issue in issues))

            payload["samples"][7]["attemptId"] = "attempt_real_07"
            payload["samples"][7]["sceneStarted"] = False
            report.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_runtime_evidence(
                report,
                expected_environment="prod",
                expected_target="prod-hosted",
                expected_platform="ios",
                expected_effective_manifest_digest=digest,
                minimum_runs=20,
            )
            self.assertTrue(any("iOS scene did not start" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
