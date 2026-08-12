"""Provider Patrol assertion evidence must come from the current real case.

spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""

from __future__ import annotations

import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.ci.provider_conformance import native_case_result
from quwoquan_ops.ci.provider_conformance import run_provider_patrol_uat as subject


SMS_ASSERTIONS = (
    "provider.auth",
    "provider.callback_ordering",
    "provider.idempotency",
    "provider.network_dns",
    "provider.observability",
    "provider.redaction",
    "provider.retry",
    "provider.success",
    "provider.throttle",
    "provider.timeout",
    "provider.validation",
    "provider.sms_delivery",
)


def _identity() -> subject.ProviderPatrolRuntimeIdentity:
    digest = "sha256:" + "a" * 64
    return subject.ProviderPatrolRuntimeIdentity(
        environment="alpha",
        target="alpha-local",
        public_bases={},
        baseline_id=digest,
        source_revision="b" * 40,
        package_digest=digest,
        image_digest=digest,
        runtime_config_digest=digest,
        environment_runtime_digest=digest,
        provider_runtime_digest=digest,
        elasticsearch_binding_digest=digest,
        elasticsearch_image_digest=digest,
        elasticsearch_compose_digest=digest,
        elasticsearch_cluster_ref="target:alpha-local/elasticsearch",
        release_id="release-alpha",
        release_digest=digest,
        attempt_id="attempt-alpha",
        local_capture_sms_enabled=True,
    )


def _passed_report(root: Path) -> tuple[Path, dict[str, object], Path]:
    target = (
        "test/user_acceptance/service/user_service/account/"
        "authentication_challenge/sms_otp_provider__user_acceptance_test.dart"
    )
    device_id = "emulator-5554"
    case_id = f"patrol:{target}:{device_id}"
    run_directory = root / "runs" / device_id
    run_directory.mkdir(parents=True)
    log_path = run_directory / "patrol.log"
    log_path.write_text(
        "Patrol test completed: 1 test passed, 0 failed, 0 skipped\n",
        encoding="utf-8",
    )
    execution = {
        "framework": "patrol",
        "executed": 1,
        "failed": 0,
        "skipped": 0,
    }
    relative_root = root.relative_to(subject.ROOT).as_posix()
    relative_run = run_directory.relative_to(subject.ROOT).as_posix()
    relative_log = log_path.relative_to(subject.ROOT).as_posix()
    report: dict[str, object] = {
        "suiteId": "environment_page_smoke",
        "status": "passed",
        "environmentAlias": "alpha-local",
        "runtimeEnv": "alpha",
        "apiContractEnv": "alpha",
        "composition": "production_remote",
        "target": target,
        "candidateDigest": _identity().baseline_id,
        "evidenceRoot": f"{relative_root}/runs",
        "devices": [
            {"id": device_id, "targetPlatform": "android-x64"},
        ],
        "runs": [
            {
                "device": {"id": device_id, "targetPlatform": "android-x64"},
                "exitCode": 0,
                "timedOut": False,
                "testExecution": deepcopy(execution),
                "evidence": {
                    "runDirectory": relative_run,
                    "rawLogPath": relative_log,
                },
            }
        ],
        "caseResults": [
            {
                "caseId": case_id,
                "status": "passed",
                "deviceId": device_id,
                "testExecution": deepcopy(execution),
                "evidence": {"patrolLogPath": relative_log},
            }
        ],
    }
    report_path = root / "provider.patrol-report.json"
    report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    return report_path, report, log_path


class ProviderPatrolAssertionEvidenceContractTest(unittest.TestCase):
    def _temporary_output(self) -> tempfile.TemporaryDirectory[str]:
        parent = subject.ROOT / ".qwq_output/env/alpha/runs"
        parent.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(
            prefix="provider-patrol-assertions-",
            dir=parent,
        )

    def test_sms_declaration_is_dynamic_unique_and_exactly_twelve(self) -> None:
        environment = {
            "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID": "identity.sms.otp",
            "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS": json.dumps(SMS_ASSERTIONS),
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            self.assertEqual(
                subject._declared_provider_assertion_ids(),
                SMS_ASSERTIONS,
            )

        invalid = {
            "missing": SMS_ASSERTIONS[:-1],
            "duplicate": (*SMS_ASSERTIONS[:-1], SMS_ASSERTIONS[0]),
            "unsafe": (*SMS_ASSERTIONS[:-1], " identity.sms.otp"),
        }
        for label, assertion_ids in invalid.items():
            with self.subTest(label=label), mock.patch.dict(
                os.environ,
                {
                    "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID": "identity.sms.otp",
                    "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS": json.dumps(
                        assertion_ids
                    ),
                },
                clear=False,
            ), self.assertRaises(ValueError):
                subject._declared_provider_assertion_ids()

    def test_real_passed_case_generates_exact_native_consumable_assertions(self) -> None:
        with self._temporary_output() as temporary:
            report_path, report, _ = _passed_report(Path(temporary))
            subject._bind_runtime_evidence_to_patrol_report(
                report_path,
                identity=_identity(),
                binding=None,
                assertion_ids=SMS_ASSERTIONS,
                sensitive_values=("13800138000", "123456", "broker-token"),
            )
            updated = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(
                [item["assertionId"] for item in updated["assertions"]],
                list(SMS_ASSERTIONS),
            )
            self.assertEqual(len(updated["assertions"]), 12)
            self.assertEqual(
                {item["caseId"] for item in updated["assertions"]},
                {report["caseResults"][0]["caseId"]},  # type: ignore[index]
            )
            rendered = json.dumps(updated, ensure_ascii=False)
            for sensitive in ("13800138000", "123456", "broker-token"):
                self.assertNotIn(sensitive, rendered)
            case_results, observability = (
                native_case_result._validate_user_acceptance_report(
                    updated,
                    environment="alpha",
                    target=str(report["target"]),
                    assertion_ids=SMS_ASSERTIONS,
                )
            )
            self.assertEqual(len(case_results), 12)
            self.assertTrue(observability["logs"])
            self.assertTrue(observability["traces"])
            self.assertTrue(observability["metrics"])

    def test_android_and_ios_matrix_binds_every_real_case(self) -> None:
        with self._temporary_output() as temporary:
            root = Path(temporary)
            report_path, report, _ = _passed_report(root)
            execution = {
                "framework": "patrol",
                "executed": 1,
                "failed": 0,
                "skipped": 0,
            }
            ios_device_id = "ios-simulator-1"
            ios_run = root / "runs" / ios_device_id
            ios_run.mkdir(parents=True)
            ios_log = ios_run / "patrol.log"
            ios_log.write_text(
                "Patrol test completed: 1 test passed, 0 failed, 0 skipped\n",
                encoding="utf-8",
            )
            ios_case_id = f"patrol:{report['target']}:{ios_device_id}"
            report["devices"].append(  # type: ignore[union-attr]
                {"id": ios_device_id, "targetPlatform": "ios"}
            )
            report["runs"].append(  # type: ignore[union-attr]
                {
                    "device": {"id": ios_device_id, "targetPlatform": "ios"},
                    "exitCode": 0,
                    "timedOut": False,
                    "testExecution": deepcopy(execution),
                    "evidence": {
                        "runDirectory": ios_run.relative_to(subject.ROOT).as_posix(),
                        "rawLogPath": ios_log.relative_to(subject.ROOT).as_posix(),
                    },
                }
            )
            report["caseResults"].append(  # type: ignore[union-attr]
                {
                    "caseId": ios_case_id,
                    "status": "passed",
                    "deviceId": ios_device_id,
                    "testExecution": deepcopy(execution),
                    "evidence": {
                        "patrolLogPath": ios_log.relative_to(subject.ROOT).as_posix(),
                    },
                }
            )
            report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")

            subject._bind_runtime_evidence_to_patrol_report(
                report_path,
                identity=_identity(),
                binding=None,
                assertion_ids=SMS_ASSERTIONS,
            )
            updated = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {item["targetPlatform"] for item in updated["devices"]},
                {"android-x64", "ios"},
            )
            self.assertTrue(
                all(
                    item["logRef"].startswith("log:patrol-matrix:")
                    for item in updated["assertions"]
                )
            )
            native_case_result._validate_user_acceptance_report(
                updated,
                environment="alpha",
                target=str(report["target"]),
                assertion_ids=SMS_ASSERTIONS,
            )

    def test_failed_skipped_missing_log_or_sensitive_evidence_never_rewrites_report(
        self,
    ) -> None:
        cases = ("failed", "skipped", "missing-log", "sensitive-log")
        for label in cases:
            with self.subTest(label=label), self._temporary_output() as temporary:
                report_path, report, log_path = _passed_report(Path(temporary))
                if label == "failed":
                    report["runs"][0]["testExecution"]["failed"] = 1  # type: ignore[index]
                    report["caseResults"][0]["testExecution"]["failed"] = 1  # type: ignore[index]
                elif label == "skipped":
                    report["runs"][0]["testExecution"]["skipped"] = 1  # type: ignore[index]
                    report["caseResults"][0]["testExecution"]["skipped"] = 1  # type: ignore[index]
                elif label == "missing-log":
                    log_path.unlink()
                else:
                    log_path.write_text("broker-token\n", encoding="utf-8")
                report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
                before = report_path.read_bytes()

                with self.assertRaises(ValueError):
                    subject._bind_runtime_evidence_to_patrol_report(
                        report_path,
                        identity=_identity(),
                        binding=None,
                        assertion_ids=SMS_ASSERTIONS,
                        sensitive_values=("broker-token",),
                    )
                self.assertEqual(report_path.read_bytes(), before)

    def test_base64_encoded_define_cannot_escape_sensitive_log_gate(self) -> None:
        with self._temporary_output() as temporary:
            report_path, report, log_path = _passed_report(Path(temporary))
            define = "QWQ_PROVIDER_UAT_SMS_PHONE=19912345678"
            log_path.write_bytes(base64.b64encode(define.encode("utf-8")) + b"\n")
            report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
            before = report_path.read_bytes()

            with self.assertRaisesRegex(ValueError, "protected UAT value"):
                subject._bind_runtime_evidence_to_patrol_report(
                    report_path,
                    identity=_identity(),
                    binding=None,
                    assertion_ids=SMS_ASSERTIONS,
                    sensitive_values=(define,),
                )
            self.assertEqual(report_path.read_bytes(), before)

    def test_existing_assertions_are_never_trusted_or_overwritten(self) -> None:
        with self._temporary_output() as temporary:
            report_path, report, _ = _passed_report(Path(temporary))
            report["assertions"] = [
                {
                    "assertionId": item,
                    "caseId": "forged",
                    "status": "passed",
                }
                for item in SMS_ASSERTIONS
            ]
            report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
            before = report_path.read_bytes()

            with self.assertRaisesRegex(ValueError, "fresh passed source report"):
                subject._bind_runtime_evidence_to_patrol_report(
                    report_path,
                    identity=_identity(),
                    binding=None,
                    assertion_ids=SMS_ASSERTIONS,
                )
            self.assertEqual(report_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
