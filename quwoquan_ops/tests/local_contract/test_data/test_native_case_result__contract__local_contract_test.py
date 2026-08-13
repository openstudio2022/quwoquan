"""Contracts for source-owned native Provider CaseResult emission."""
from __future__ import annotations

import copy
import hashlib
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
                    command=_non_user_acceptance_marker_command(),
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
            self.assertEqual(
                result["cleanupReceipt"],
                "receipt:cleanup-native-contract-target",
            )
            self.assertEqual(
                result["observabilityRefs"],
                {
                    "logs": [
                        "log:provider.success",
                        "log:provider.validation",
                    ],
                    "traces": [
                        "trace:provider.success",
                        "trace:provider.validation",
                    ],
                    "metrics": [
                        "metric:provider.success",
                        "metric:provider.validation",
                    ],
                },
            )

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

    def test_api_integration_uses_the_same_observed_marker_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            result_path = Path(temporary_dir) / "case-results.json"
            environment = _execution_environment(
                result_path,
                layer="api_integration",
            )
            with mock.patch.dict(os.environ, environment, clear=True):
                exit_code = native_case_result.run_native_harness(
                    command=_non_user_acceptance_marker_command(),
                    target="native-contract-target",
                )

            self.assertEqual(exit_code, 0)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["networkBoundary"], "remote_protocol")
            self.assertEqual(
                result["cleanupReceipt"],
                "receipt:cleanup-native-contract-target",
            )

    def test_non_user_acceptance_rejects_exit_zero_without_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            result_path = Path(temporary_dir) / "case-results.json"
            environment = _execution_environment(result_path)
            with (
                mock.patch.dict(os.environ, environment, clear=True),
                self.assertRaisesRegex(ValueError, "no assertion markers"),
            ):
                native_case_result.run_native_harness(
                    command=(sys.executable, "-c", "print('exit zero is not proof')"),
                    target="native-contract-target",
                )
            self.assertFalse(result_path.exists())

    def test_non_user_acceptance_assertion_coverage_is_fail_closed(self) -> None:
        invalid_assertions = {
            "missing": ("provider.success",),
            "duplicate": (
                "provider.success",
                "provider.success",
                "provider.validation",
            ),
            "extra": (
                "provider.success",
                "provider.validation",
                "provider.extra",
            ),
        }
        for name, assertion_ids in invalid_assertions.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary_dir:
                result_path = Path(temporary_dir) / "case-results.json"
                environment = _execution_environment(result_path)
                with (
                    mock.patch.dict(os.environ, environment, clear=True),
                    self.assertRaisesRegex(
                        ValueError,
                        "uniquely cover|exactly cover",
                    ),
                ):
                    native_case_result.run_native_harness(
                        command=_non_user_acceptance_marker_command(
                            assertion_ids=assertion_ids,
                        ),
                        target="native-contract-target",
                    )
                self.assertFalse(result_path.exists())

    def test_non_user_acceptance_cleanup_marker_is_fail_closed(self) -> None:
        invalid_cleanup_payloads: dict[
            str,
            tuple[dict[str, object], ...],
        ] = {
            "missing": (),
            "duplicate": (
                _cleanup_marker_payload(),
                _cleanup_marker_payload(),
            ),
            "not_restored": (
                {
                    "status": "pending",
                    "receiptRef": "receipt:cleanup-native-contract-target",
                },
            ),
            "placeholder": (
                {
                    "status": "restored",
                    "receiptRef": "receipt:cleanup-placeholder",
                },
            ),
        }
        for name, cleanup_payloads in invalid_cleanup_payloads.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary_dir:
                result_path = Path(temporary_dir) / "case-results.json"
                environment = _execution_environment(result_path)
                with (
                    mock.patch.dict(os.environ, environment, clear=True),
                    self.assertRaisesRegex(
                        ValueError,
                        "exactly one cleanup marker|status=restored|canonical non-sensitive",
                    ),
                ):
                    native_case_result.run_native_harness(
                        command=_non_user_acceptance_marker_command(
                            cleanup_payloads=cleanup_payloads,
                        ),
                        target="native-contract-target",
                )
                self.assertFalse(result_path.exists())

    def test_non_user_acceptance_marker_references_reject_placeholders(self) -> None:
        invalid_fields: dict[str, object] = {
            "sceneReceiptRef": "receipt:scene-placeholder",
            "logRef": "log:unknown",
            "traceRef": "trace:todo",
            "metricRefs": ["metric:tbd"],
        }
        for field, invalid_value in invalid_fields.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary_dir:
                payloads = [
                    _assertion_marker_payload("provider.success"),
                    _assertion_marker_payload("provider.validation"),
                ]
                payloads[0][field] = invalid_value
                result_path = Path(temporary_dir) / "case-results.json"
                environment = _execution_environment(result_path)
                with (
                    mock.patch.dict(os.environ, environment, clear=True),
                    self.assertRaisesRegex(ValueError, "canonical non-"),
                ):
                    native_case_result.run_native_harness(
                        command=_non_user_acceptance_marker_command(
                            assertion_payloads=tuple(payloads),
                        ),
                        target="native-contract-target",
                    )
                self.assertFalse(result_path.exists())

    def test_user_acceptance_requires_current_sibling_patrol_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            result_path = Path(temporary_dir) / "case-results.json"
            environment = _execution_environment(
                result_path,
                layer="user_acceptance",
            )
            completed = mock.Mock(returncode=0, stdout=b"", stderr=b"")
            with (
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch.object(
                    native_case_result.subprocess,
                    "run",
                    return_value=completed,
                ),
                self.assertRaisesRegex(ValueError, r"\.patrol-report\.json"),
            ):
                native_case_result.run_native_harness(
                    command=(sys.executable, "provider_uat.py"),
                    target="native-contract-target",
                )
            self.assertFalse(result_path.exists())

    def test_user_acceptance_binds_real_patrol_report_and_assertions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            result_path = Path(temporary_dir) / "case-results.json"
            report_path = result_path.with_name(
                "case-results.patrol-report.json"
            )
            environment = _execution_environment(
                result_path,
                layer="user_acceptance",
            )
            report = _passed_patrol_report()
            report_raw = json.dumps(
                report,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")

            def write_report(*_args: object, **_kwargs: object) -> mock.Mock:
                report_path.write_bytes(report_raw)
                return mock.Mock(returncode=0, stdout=b"", stderr=b"")

            with (
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch.object(
                    native_case_result.subprocess,
                    "run",
                    side_effect=write_report,
                ),
            ):
                exit_code = native_case_result.run_native_harness(
                    command=(sys.executable, "provider_uat.py"),
                    target="native-contract-target",
                )

            self.assertEqual(exit_code, 0)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(
                result["caseResults"],
                [
                    {
                        "assertionId": assertion_id,
                        "status": "passed",
                        "logRef": f"log:{assertion_id}",
                        "traceRef": f"trace:{assertion_id}",
                        "metricRefs": [f"metric:{assertion_id}"],
                    }
                    for assertion_id in (
                        "provider.success",
                        "provider.validation",
                    )
                ],
            )
            telemetry = json.loads(
                result_path.with_name(
                    "case-results.native-execution.json"
                ).read_text(encoding="utf-8")
            )
            expected_report_digest = (
                "sha256:" + hashlib.sha256(report_raw).hexdigest()
            )
            self.assertEqual(
                telemetry["patrolReportDigest"],
                expected_report_digest,
            )
            execution_raw = json.dumps(
                telemetry,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            self.assertEqual(
                result["dataDigest"],
                "sha256:" + hashlib.sha256(execution_raw).hexdigest(),
            )

    def test_user_acceptance_binds_report_to_fixed_patrol_journey_target(self) -> None:
        journey_target = (
            "test/user_acceptance/service/user_service/account/authentication_challenge/"
            "provider_journey__user_acceptance_test.dart"
        )
        report = _passed_patrol_report()
        report["target"] = journey_target
        with tempfile.TemporaryDirectory() as temporary_dir:
            result_path = Path(temporary_dir) / "case-results.json"
            report_path = result_path.with_name(
                "case-results.patrol-report.json"
            )
            environment = _execution_environment(
                result_path,
                layer="user_acceptance",
            )

            def write_report(*_args: object, **_kwargs: object) -> mock.Mock:
                report_path.write_text(
                    json.dumps(report, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout=b"", stderr=b"")

            command = (
                sys.executable,
                "quwoquan_ops/ci/provider_conformance/run_provider_patrol_uat.py",
                "--target",
                journey_target,
            )
            with (
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch.object(
                    native_case_result.subprocess,
                    "run",
                    side_effect=write_report,
                ),
            ):
                exit_code = native_case_result.run_native_harness(
                    command=command,
                    target="native-contract-target",
                )

            self.assertEqual(exit_code, 0)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["testTarget"], "native-contract-target")

            report["target"] = (
                "test/user_acceptance/service/user_service/account/authentication_challenge/"
                "other__user_acceptance_test.dart"
            )
            with self.assertRaisesRegex(ValueError, "target"):
                native_case_result._validate_user_acceptance_report(
                    report,
                    environment="alpha",
                    target=journey_target,
                    assertion_ids=("provider.success", "provider.validation"),
                )

    def test_user_acceptance_rejects_exit_zero_without_assertion_evidence(
        self,
    ) -> None:
        report = _passed_patrol_report()
        report.pop("assertions")
        with self.assertRaisesRegex(ValueError, "assertion-level evidence"):
            _run_user_acceptance(report)

    def test_user_acceptance_patrol_report_validation_is_fail_closed(self) -> None:
        invalid_reports: list[tuple[str, dict[str, object], str]] = []

        report = _passed_patrol_report()
        report["suiteId"] = "other_suite"
        invalid_reports.append(("suite", report, "suiteId"))

        report = _passed_patrol_report()
        report["status"] = "failed"
        invalid_reports.append(("status", report, "status must be passed"))

        report = _passed_patrol_report()
        report["runtimeEnv"] = "beta"
        invalid_reports.append(("environment", report, "environment"))

        report = _passed_patrol_report()
        report["composition"] = "mock"
        invalid_reports.append(("composition", report, "composition"))

        report = _passed_patrol_report()
        report["candidateDigest"] = ""
        invalid_reports.append(("candidate", report, "candidateDigest"))

        report = _passed_patrol_report()
        report["devices"][0]["id"] = "unknown"  # type: ignore[index]
        invalid_reports.append(("device", report, "must not be empty or unknown"))

        report = _passed_patrol_report()
        report["runs"] = []
        invalid_reports.append(("run", report, "must be non-empty"))

        report = _passed_patrol_report()
        report["runs"][0]["testExecution"].pop("skipped")  # type: ignore[index,union-attr]
        invalid_reports.append(("skipped", report, "skipped must be 0"))

        report = _passed_patrol_report()
        report["caseResults"][0]["testExecution"]["executed"] = 0  # type: ignore[index]
        invalid_reports.append(("executed", report, "executed must be > 0"))

        for name, invalid, expected_error in invalid_reports:
            with self.subTest(name=name), self.assertRaisesRegex(
                ValueError,
                expected_error,
            ):
                _run_user_acceptance(invalid)


def _execution_environment(
    result_path: Path,
    *,
    layer: str = "local_contract",
) -> dict[str, str]:
    return {
        "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH": str(result_path),
        "QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID": "ext.test.native",
        "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID": "runtime.test.native",
        "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT": "alpha",
        "QWQ_PROVIDER_CONFORMANCE_LAYER": layer,
        "QWQ_PROVIDER_CONFORMANCE_TYPED_PORT": "NativeTestPort",
        "QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF": (
            "quwoquan_service/services/test-service/contracts/test/operations.yaml"
        ),
        "QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST": "sha256:" + "a" * 64,
        "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS": json.dumps(
            ["provider.success", "provider.validation"]
        ),
    }


def _assertion_marker_payload(assertion_id: str) -> dict[str, object]:
    return {
        "assertionId": assertion_id,
        "status": "passed",
        "sceneReceiptRef": f"receipt:scene-{assertion_id}",
        "logRef": f"log:{assertion_id}",
        "traceRef": f"trace:{assertion_id}",
        "metricRefs": [f"metric:{assertion_id}"],
    }


def _cleanup_marker_payload() -> dict[str, object]:
    return {
        "status": "restored",
        "receiptRef": "receipt:cleanup-native-contract-target",
    }


def _non_user_acceptance_marker_command(
    *,
    assertion_ids: tuple[str, ...] = (
        "provider.success",
        "provider.validation",
    ),
    assertion_payloads: tuple[dict[str, object], ...] | None = None,
    cleanup_payloads: tuple[dict[str, object], ...] | None = None,
) -> tuple[str, str, str]:
    assertion_payloads = (
        tuple(_assertion_marker_payload(assertion_id) for assertion_id in assertion_ids)
        if assertion_payloads is None
        else assertion_payloads
    )
    cleanup_payloads = (
        (_cleanup_marker_payload(),)
        if cleanup_payloads is None
        else cleanup_payloads
    )
    stdout_lines = [
        "provider-secret-output",
        *(
            "QWQ_PROVIDER_CONFORMANCE_ASSERTION:"
            + json.dumps(payload, sort_keys=True)
            for payload in assertion_payloads
        ),
    ]
    stderr_lines = [
        "QWQ_PROVIDER_CONFORMANCE_CLEANUP:"
        + json.dumps(payload, sort_keys=True)
        for payload in cleanup_payloads
    ]
    script = ["import sys"]
    script.extend(f"print({line!r})" for line in stdout_lines)
    script.extend(f"print({line!r}, file=sys.stderr)" for line in stderr_lines)
    return sys.executable, "-c", ";".join(script)


def _passed_patrol_report() -> dict[str, object]:
    case_id = "patrol:native-contract-target:emulator-5554"
    test_execution = {
        "framework": "patrol",
        "executed": 1,
        "failed": 0,
        "skipped": 0,
    }
    return {
        "suiteId": "environment_page_smoke",
        "status": "passed",
        "environmentAlias": "alpha-local",
        "runtimeEnv": "alpha",
        "apiContractEnv": "alpha",
        "composition": "production_remote",
        "candidateDigest": "sha256:" + "b" * 64,
        "target": "native-contract-target",
        "devices": [
            {
                "id": "emulator-5554",
                "name": "Android Emulator",
                "targetPlatform": "android-x64",
            }
        ],
        "runs": [
            {
                "device": {
                    "id": "emulator-5554",
                    "targetPlatform": "android-x64",
                },
                "exitCode": 0,
                "timedOut": False,
                "testExecution": copy.deepcopy(test_execution),
                "evidence": {"runDirectory": "env/alpha/runs/patrol/emulator-5554"},
            }
        ],
        "caseResults": [
            {
                "caseId": case_id,
                "status": "passed",
                "deviceId": "emulator-5554",
                "testExecution": copy.deepcopy(test_execution),
            }
        ],
        "assertions": [
            {
                "assertionId": assertion_id,
                "caseId": case_id,
                "status": "passed",
                "logRef": f"log:{assertion_id}",
                "traceRef": f"trace:{assertion_id}",
                "metricRefs": [f"metric:{assertion_id}"],
            }
            for assertion_id in (
                "provider.success",
                "provider.validation",
            )
        ],
    }


def _run_user_acceptance(report: dict[str, object]) -> None:
    with tempfile.TemporaryDirectory() as temporary_dir:
        result_path = Path(temporary_dir) / "case-results.json"
        report_path = result_path.with_name("case-results.patrol-report.json")
        environment = _execution_environment(
            result_path,
            layer="user_acceptance",
        )

        def write_report(*_args: object, **_kwargs: object) -> mock.Mock:
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")

        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(
                native_case_result.subprocess,
                "run",
                side_effect=write_report,
            ),
        ):
            native_case_result.run_native_harness(
                command=(sys.executable, "provider_uat.py"),
                target="native-contract-target",
            )


if __name__ == "__main__":
    unittest.main()
