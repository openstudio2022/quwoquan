# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-003
# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
"""Contract tests for the fail-closed account-enforcement Gamma UAT rail."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as patrol_smoke


ROOT = Path(__file__).resolve().parents[4]
CONTROLLED_SUBJECT_DIGEST = "sha256:" + "c" * 64
VALIDATOR_PATH = (
    ROOT
    / "quwoquan_ops"
    / "tests"
    / "acceptance"
    / "user_acceptance"
    / "service_ops"
    / "product-ops-service"
    / "gamma"
    / "account_enforcement_gamma_uat.py"
)
SPEC = importlib.util.spec_from_file_location(
    "account_enforcement_gamma_uat",
    VALIDATOR_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load account-enforcement Gamma UAT validator")
uat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(uat)


@contextmanager
def output_root(path: Path) -> Iterator[None]:
    previous = os.environ.get("QWQ_OUTPUT_ROOT")
    os.environ["QWQ_OUTPUT_ROOT"] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("QWQ_OUTPUT_ROOT", None)
        else:
            os.environ["QWQ_OUTPUT_ROOT"] = previous


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def journey_receipt(root: Path, run_id: str, digest: str) -> dict[str, Any]:
    artifact_refs: list[dict[str, str]] = []
    by_kind: dict[str, str] = {}
    for kind in uat.EXPECTED_ARTIFACT_KINDS:
        ref = f"artifacts/{kind}.json"
        artifact_path = write_json(
            root / ref,
            {
                "schema": uat.EVIDENCE_SCHEMA,
                "kind": kind,
                "status": "captured",
                "runId": run_id,
                "candidateDigest": digest,
                "capturedAt": "2026-07-29T00:00:00Z",
                "facts": {"observed": True},
            },
        )
        artifact_refs.append(
            {
                "kind": kind,
                "path": ref,
                "sha256": "sha256:"
                + hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                "mediaType": "application/json",
            }
        )
        by_kind[kind] = ref
    return {
        "schema": uat.JOURNEY_SCHEMA,
        "status": "passed",
        "environment": "gamma",
        "target": "gamma-local",
        "composition": "production_remote",
        "runId": run_id,
        "candidateDigest": digest,
        "commitSha": "a" * 40,
        "capturedAt": "2026-07-29T00:00:00Z",
        "specRefs": list(uat.EXPECTED_SPEC_REFS),
        "authorization": {
            "oidcVerified": True,
            "missingCredentialStatus": 401,
            "invalidCredentialStatus": 401,
            "insufficientScopeStatus": 403,
            "distinctOperatorCount": 2,
            "operationScopes": dict(uat.EXPECTED_OPERATION_SCOPES),
            "receiptRef": by_kind["authorization"],
        },
        "storage": {
            "backend": "postgresql",
            "transactionAtomic": True,
            "outboxAtomic": True,
            "receiptRef": by_kind["storage"],
        },
        "userAccount": {
            "remoteComposition": True,
            "controlledSubjectDigest": CONTROLLED_SUBJECT_DIGEST,
            "servicePrincipal": "product-ops-service",
            "serviceScope": "user.account.enforcement.write",
            "suspendReceiptRef": by_kind["user-account-suspend"],
            "restoreReceiptRef": by_kind["user-account-restore"],
            "oldCredentialStatus": 403,
            "oldCredentialErrorCode": "USER.AUTH.account_suspended",
            "newSessionStatus": "passed",
        },
        "moderation": {
            "caseId": "moderation-case",
            "status": "approved",
            "approvalCount": 2,
            "decisionId": "suspend-decision",
            "deliveryStatus": "delivered",
            "receiptRef": by_kind["moderation"],
        },
        "appeal": {
            "caseId": "appeal-case",
            "status": "approved",
            "approvalCount": 2,
            "decisionId": "restore-decision",
            "deliveryStatus": "delivered",
            "receiptRef": by_kind["appeal"],
        },
        "faultInjection": {
            "recoverableFailureObserved": True,
            "recoverableAttemptCount": 2,
            "terminalCaseId": "terminal-case",
            "terminalDecisionId": "terminal-decision",
            "terminalDeliveryStatus": "dead_letter",
            "deadLetterContainsPII": False,
            "sameDecisionRecovery": True,
            "recoveredDecisionId": "terminal-decision",
            "retryGenerationBefore": 3,
            "retryGenerationAfter": 4,
            "finalDeliveryStatus": "delivered",
            "receiptRef": by_kind["fault-injection"],
        },
        "readiness": {
            "terminalStatus": "gate_block",
            "recoveredStatus": "healthy",
            "pendingAgeWithinSlo": True,
            "receiptRef": by_kind["readiness"],
        },
        "observability": {
            "traceAligned": True,
            "decisionTraceAligned": True,
            "metricRefs": [
                by_kind["metric-delivery"],
                by_kind["metric-dlq"],
                by_kind["metric-readiness"],
            ],
            "logRef": by_kind["log-readback"],
            "alertRef": by_kind["alert-readback"],
            "dlqReadbackRef": by_kind["dlq-readback"],
            "crossDomainLagMilliseconds": 120,
        },
        "cleanup": {
            "accountState": "active",
            "newSessionStatus": "passed",
            "unresolvedDeadLetterCount": 0,
            "appRestrictionCleared": True,
            "receiptRef": by_kind["cleanup"],
        },
        "artifactRefs": artifact_refs,
    }


def device_report(phase: str, digest: str) -> dict[str, Any]:
    marker = (
        {
            "phase": "suspended",
            "candidateDigest": digest,
            "remoteCode": "USER.AUTH.account_suspended",
            "sessionCredentialsCleared": True,
            "restrictionSurfaceVisible": True,
        }
        if phase == "suspended"
        else {
            "phase": "restored",
            "candidateDigest": digest,
            "remoteProfileRead": True,
            "sessionAuthenticated": True,
            "safeHomeVisible": True,
        }
    )
    devices = [
        {
            "id": "physical-android",
            "targetPlatform": "android-arm64",
            "emulator": False,
        },
        {"id": "physical-iphone", "targetPlatform": "ios", "emulator": False},
    ]
    return {
        "status": "passed",
        "runtimeEnv": "gamma",
        "apiContractEnv": "gamma",
        "composition": "production_remote",
        "target": uat.EXPECTED_DEVICE_TARGETS[phase],
        "candidateDigest": digest,
        "controlledSubjectDigest": CONTROLLED_SUBJECT_DIGEST,
        "sessionSource": "provided_remote_session",
        "devices": devices,
        "runs": [
            {
                "exitCode": 0,
                "timedOut": False,
                "evidence": {"accountEnforcement": marker},
            }
            for _device in devices
        ],
        "caseResults": [
            {
                "status": "passed",
                "testExecution": {"executed": 1, "failed": 0},
                "evidence": {"accountEnforcement": marker},
            }
            for _device in devices
        ],
    }


class AccountEnforcementGammaUATContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.run_id = "gamma-uat-20260729"
        self.digest = "sha256:" + "b" * 64

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_complete_evidence_emits_twelve_passed_case_results(self) -> None:
        receipt = journey_receipt(self.root, self.run_id, self.digest)
        journey_path = write_json(self.root / "journey.json", receipt)
        suspended_path = write_json(
            self.root / "suspended.json",
            device_report("suspended", self.digest),
        )
        restored_path = write_json(
            self.root / "restored.json",
            device_report("restored", self.digest),
        )
        with output_root(self.root):
            result = uat.aggregate_case_result(
                manifest_path=uat.DEFAULT_MANIFEST,
                run_id=self.run_id,
                candidate_digest=self.digest,
                journey_path=journey_path,
                journey_ref="journey.json",
                suspended_path=suspended_path,
                suspended_ref="suspended.json",
                restored_path=restored_path,
                restored_ref="restored.json",
            )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["assertionIds"], list(uat.EXPECTED_ASSERTIONS))
        self.assertEqual(len(result["caseResults"]), 12)
        self.assertTrue(all(case["status"] == "passed" for case in result["caseResults"]))

    def test_missing_inputs_emit_gate_block_with_no_passed_cases(self) -> None:
        report = self.root / "gate-block.json"
        with output_root(self.root):
            exit_code = uat.main(["--report", str(report)])
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "gate_block")
        self.assertEqual(payload["caseResults"], [])

    def test_scope_negative_case_cannot_be_promoted_to_pass(self) -> None:
        receipt = journey_receipt(self.root, self.run_id, self.digest)
        receipt["authorization"]["insufficientScopeStatus"] = 200
        with output_root(self.root), self.assertRaises(uat.EvidenceError):
            uat.validate_journey_receipt(
                receipt,
                manifest=uat.load_manifest(),
                run_id=self.run_id,
                candidate_digest=self.digest,
            )

    def test_tampered_evidence_artifact_is_rejected_by_digest(self) -> None:
        receipt = journey_receipt(self.root, self.run_id, self.digest)
        first_ref = receipt["artifactRefs"][0]["path"]
        write_json(self.root / first_ref, {"status": "tampered"})
        with output_root(self.root), self.assertRaises(uat.EvidenceError):
            uat.validate_journey_receipt(
                receipt,
                manifest=uat.load_manifest(),
                run_id=self.run_id,
                candidate_digest=self.digest,
            )

    def test_emulator_only_matrix_is_rejected(self) -> None:
        report = device_report("suspended", self.digest)
        for device in report["devices"]:
            device["emulator"] = True
        with self.assertRaises(uat.EvidenceError):
            uat.validate_device_report(
                report,
                phase="suspended",
                candidate_digest=self.digest,
                controlled_subject_digest=CONTROLLED_SUBJECT_DIGEST,
            )

    def test_sensitive_credential_material_is_rejected(self) -> None:
        receipt = journey_receipt(self.root, self.run_id, self.digest)
        receipt["observability"]["authorizationHeader"] = "Bearer secret"
        with output_root(self.root), self.assertRaises(uat.EvidenceError):
            uat.validate_journey_receipt(
                receipt,
                manifest=uat.load_manifest(),
                run_id=self.run_id,
                candidate_digest=self.digest,
            )

    def test_patrol_runner_dry_run_cannot_produce_account_enforcement_pass(self) -> None:
        report = self.root / "dry-run-device-report.json"
        environment = dict(os.environ)
        environment["QWQ_OUTPUT_ROOT"] = str(self.root)
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py",
                "--report",
                str(report),
                "--target",
                uat.EXPECTED_DEVICE_TARGETS["suspended"],
                "--runtime-env",
                "gamma",
                "--api-contract-env",
                "gamma",
                "--candidate-digest",
                self.digest,
                "--dry-run",
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(payload["status"], "gate_block")
        self.assertIn("forbids dry-run", payload["failureReason"])

    def test_device_phase_without_controlled_credentials_is_gate_block(self) -> None:
        report = self.root / "missing-credentials-device-report.json"
        environment = dict(os.environ)
        environment["QWQ_OUTPUT_ROOT"] = str(self.root)
        for name in (
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_SUSPENDED_ACCESS_TOKEN",
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_SUSPENDED_REFRESH_TOKEN",
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_OWNER_ID",
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_PERSONA_ID",
        ):
            environment.pop(name, None)
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(
                    VALIDATOR_PATH.parent.parent
                    / "smoke"
                    / "run_account_enforcement_device_matrix.py"
                ),
                "--phase",
                "suspended",
                "--candidate-digest",
                self.digest,
                "--device-id",
                "physical-device",
                "--report",
                str(report),
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(payload["status"], "gate_block")
        self.assertEqual(payload["caseResults"], [])
        self.assertIn("missing controlled", payload["failureReason"])

    def test_account_target_never_falls_back_to_anonymous_gamma_session(self) -> None:
        args = argparse.Namespace(
            env_name="local-gamma",
            target=uat.EXPECTED_DEVICE_TARGETS["suspended"],
            persisted_device_session=False,
        )
        self.assertFalse(patrol_smoke._uses_runtime_anonymous_session(args))

    def test_patrol_marker_is_bound_to_the_same_candidate(self) -> None:
        marker = {
            "phase": "restored",
            "candidateDigest": self.digest,
            "remoteProfileRead": True,
            "sessionAuthenticated": True,
            "safeHomeVisible": True,
        }
        log = self.root / "patrol.log"
        log.write_text(
            patrol_smoke.ACCOUNT_ENFORCEMENT_EVIDENCE_PREFIX
            + json.dumps(marker, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        self.assertEqual(
            patrol_smoke._read_account_enforcement_evidence(
                log,
                phase="restored",
                candidate_digest=self.digest,
            ),
            marker,
        )
        self.assertEqual(
            patrol_smoke._read_account_enforcement_evidence(
                log,
                phase="restored",
                candidate_digest="sha256:" + "d" * 64,
            ),
            {},
        )

    def test_gamma_release_profile_hook_is_blocking_and_release_only(self) -> None:
        command = stackctl._account_enforcement_gamma_uat_profile_command(
            "gamma-local",
            stackctl.VerificationProfile.RELEASE,
            self.root,
        )
        self.assertIsNotNone(command)
        assert command is not None
        self.assertTrue(command["stopOnFailure"])
        self.assertIn(
            stackctl.ACCOUNT_ENFORCEMENT_GAMMA_UAT_MANIFEST,
            command["argv"],
        )
        self.assertIsNone(
            stackctl._account_enforcement_gamma_uat_profile_command(
                "gamma-local",
                stackctl.VerificationProfile.INTEGRATION,
                self.root,
            )
        )

    def test_stackctl_verify_action_preserves_gate_block(self) -> None:
        report_dir = self.root / "stackctl"
        environment = dict(os.environ)
        environment["QWQ_OUTPUT_ROOT"] = str(self.root)
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "quwoquan_ops/cli/stackctl.py",
                "--output-format",
                "json",
                "account-enforcement-uat",
                "--report-dir",
                str(report_dir),
                "--action",
                "verify",
                "--run-id",
                self.run_id,
                "--candidate-digest",
                self.digest,
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        payload = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
        case_result = json.loads(
            (report_dir / "case-result.json").read_text(encoding="utf-8")
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(payload["status"], "gate_block")
        self.assertEqual(case_result["status"], "gate_block")
        self.assertEqual(case_result["caseResults"], [])


if __name__ == "__main__":
    unittest.main()
