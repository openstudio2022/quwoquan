"""stackctl nonprod data orchestration contract.

spec_ref: specs/feature-tree/spec.md#uat-009
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib.nonprod_data_verification import (
    INPUT_SCHEMA,
    run_nonprod_business_data_verification,
)


def _manifest() -> dict[str, object]:
    return {
        "baselineId": "sha256:" + "1" * 64,
        "sourceRevision": "a" * 40,
        "packageDigest": "sha256:" + "2" * 64,
        "runtimeConfigDigest": "sha256:" + "3" * 64,
        "release": {
            "candidate": {
                "releaseId": "west-lake-canonical-20260729",
                "releaseDigest": "sha256:" + "4" * 64,
            }
        },
    }


def _readiness() -> dict[str, object]:
    return {
        "passed": True,
        "environment": "alpha",
        "releaseId": "west-lake-canonical-20260729",
        "manifestDigest": "sha256:" + "4" * 64,
        "importRunId": "import-alpha-1",
        "postIds": ["post-a", "post-b", "post-c"],
    }


def _evidence() -> dict[str, object]:
    def bound(name: str) -> dict[str, object]:
        return {
            "status": "passed",
            "attemptId": f"attempt-{name}",
            "baselineId": "sha256:" + "1" * 64,
            "packageDigest": "sha256:" + "2" * 64,
            "caseResultRef": f"case-results/{name}.json",
            "adapterId": f"ext.acceptance.{name}",
            "implementationStatus": "sandbox",
            "networkBoundary": "https_remote",
        }

    return {
        "schema": INPUT_SCHEMA,
        "baselineId": "sha256:" + "1" * 64,
        "packageDigest": "sha256:" + "2" * 64,
        "releaseDigest": "sha256:" + "4" * 64,
        "shareProviderReceiptIds": ["share-1", "share-2", "share-3"],
        "providerConformance": {
            name: bound(name)
            for name in (
                "identityOtp",
                "assistantModel",
                "pushDelivery",
                "rtcMedia",
            )
        },
        "reliabilityEvidence": {
            name: bound(name)
            for name in (
                "expiredSession",
                "projectionDelay",
                "cleanupRecovery",
            )
        },
    }


class NonprodDataVerificationContractTest(unittest.TestCase):
    def test_missing_evidence_is_gate_block_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_nonprod_business_data_verification(
                environment="alpha",
                target="alpha-local",
                base_url="https://api.alpha.quwoquan.local:17000",
                candidate_manifest=_manifest(),
                release_readiness=_readiness(),
                evidence_path=root / "missing.json",
                report_dir=root / "report",
            )
        self.assertEqual(result["status"], "GATE_BLOCK")
        self.assertEqual(result["executed"], 0)
        self.assertEqual(result["skipped"], 0)

    def test_six_recipes_produce_one_candidate_bound_case_result(self) -> None:
        receipt = {
            "status": "passed",
            "baselineId": "sha256:" + "1" * 64,
            "packageDigest": "sha256:" + "2" * 64,
            "releaseDigest": "sha256:" + "4" * 64,
            "datasetId": "dataset",
            "datasetEpoch": "e" * 64,
            "retentionClass": "candidate_bound",
            "cleanupState": "retained",
        }
        run_receipt = {
            **receipt,
            "retentionClass": "run_bound",
            "cleanupState": "cleaned",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence.json"
            evidence.write_text(json.dumps(_evidence()), encoding="utf-8")
            with mock.patch(
                "quwoquan_ops.cli.lib.nonprod_data_verification.NonprodDataProvisioner"
            ) as provisioner_type:
                provisioner = provisioner_type.return_value
                provisioner.provision_reference_identity.return_value = receipt
                provisioner.provision_reference_content_interaction.return_value = receipt
                provisioner.provision_reference_circle_chat.return_value = receipt
                provisioner.provision_reference_assistant_notification_rtc.return_value = receipt
                provisioner.run_paging_boundary.return_value = run_receipt
                provisioner.run_reliability_recovery.return_value = run_receipt
                result = run_nonprod_business_data_verification(
                    environment="alpha",
                    target="alpha-local",
                    base_url="https://api.alpha.quwoquan.local:17000",
                    candidate_manifest=_manifest(),
                    release_readiness=_readiness(),
                    evidence_path=evidence,
                    report_dir=root / "report",
                )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["executed"], 6)
        self.assertEqual(result["skipped"], 0)


if __name__ == "__main__":
    unittest.main()
