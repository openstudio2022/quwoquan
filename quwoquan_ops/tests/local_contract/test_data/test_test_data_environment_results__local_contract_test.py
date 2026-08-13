"""Exact handoff acceptance of three environment CaseResult bundles.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t3
spec_ref: specs/feature-tree/runtime/runtime-testinfra/test-data-provisioning-and-isolation/spec.md#gwt-002
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.test_data.model import canonical_digest
from quwoquan_ops.gate.verify_test_data_environment_results import verify


_DIGESTS = {
    "baselineId": "sha256:" + "1" * 64,
    "packageDigest": "sha256:" + "2" * 64,
    "runtimeConfigDigest": "sha256:" + "3" * 64,
    "manifestDigest": "sha256:" + "4" * 64,
    "readinessReceiptDigest": "sha256:" + "5" * 64,
    "requestDigest": "sha256:" + "6" * 64,
    "evidenceDigest": "sha256:" + "7" * 64,
    "candidateBindingDigest": "sha256:" + "8" * 64,
}


def _candidate_digest(environment: str) -> str:
    digit = {"alpha": "8", "beta": "9", "gamma": "a"}[environment]
    return "sha256:" + digit * 64


def _handoff(environment: str) -> dict[str, object]:
    unsigned: dict[str, object] = {
        "schema": "qwq.test_data_handoff",
        "environment": environment,
        "target": f"{environment}-local",
        "sourceRevision": "a" * 40,
        **_DIGESTS,
        "candidateBindingDigest": _candidate_digest(environment),
        "releaseId": "release-1",
        "importRunId": "import-1",
        "readinessPhase": "research",
        "expectedCases": ["case-a", "case-b"],
        "expectedProviderOwners": ["chat_service", "user_service"],
        "expectedProviderCapabilities": ["provider.identity.local_sms"],
        "requiredOperations": ["chat.message.ListMessages"],
        "allowedOperations": [
            "chat.message.ListMessages",
            "chat.message.RecallMessage",
        ],
    }
    return {**unsigned, "handoffDigest": canonical_digest(unsigned)}


def _receipt(
    *,
    result_path: Path,
    environment: str,
    case_id: str,
    kind: str,
    sequence: int,
) -> tuple[str, str]:
    unsigned = {
        "schema": "qwq.test_data_receipt",
        "sequence": sequence,
        "kind": kind,
        "caseId": case_id,
        "testDataInstanceId": f"{environment}-{case_id}",
        "candidateBindingDigest": _candidate_digest(environment),
        "recordedAt": "2026-08-12T00:00:00+00:00",
        "payload": {"caseId": case_id, "kind": kind},
    }
    digest = canonical_digest(unsigned)
    receipt_path = (
        result_path.parent
        / "receipts"
        / environment
        / case_id
        / f"{sequence:06d}-{kind}.json"
    )
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps({**unsigned, "receiptDigest": digest}),
        encoding="utf-8",
    )
    return digest, receipt_path.relative_to(result_path.parent).as_posix()


def _case_result(environment: str, result_path: Path) -> dict[str, object]:
    handoff = _handoff(environment)
    rows: list[dict[str, object]] = []
    for case_id in ("case-a", "case-b"):
        provision_digest, provision_path = _receipt(
            result_path=result_path,
            environment=environment,
            case_id=case_id,
            kind="provision",
            sequence=1,
        )
        test_body_digest, test_body_path = _receipt(
            result_path=result_path,
            environment=environment,
            case_id=case_id,
            kind="test-body",
            sequence=2,
        )
        readback_digest, readback_path = _receipt(
            result_path=result_path,
            environment=environment,
            case_id=case_id,
            kind="readback",
            sequence=3,
        )
        cleanup_digest, cleanup_path = _receipt(
            result_path=result_path,
            environment=environment,
            case_id=case_id,
            kind="cleanup",
            sequence=4,
        )
        rows.append({
            "caseId": case_id,
            "status": "passed",
            "candidateBindingDigest": _candidate_digest(environment),
            "testDataInstanceId": f"{environment}-{case_id}",
            "requestId": f"request-{case_id}",
            "provisionReceiptDigest": provision_digest,
            "provisionReceiptPath": provision_path,
            "testBodyReceiptDigest": test_body_digest,
            "testBodyReceiptPath": test_body_path,
            "readbackReceiptDigests": [readback_digest],
            "readbackReceiptPaths": [readback_path],
            "cleanupReceiptDigests": [cleanup_digest],
            "cleanupReceiptPaths": [cleanup_path],
            "testExecution": {"executed": 1, "failed": 0, "skipped": 0},
        })
    return {
        "schema": "qwq.case_result",
        "status": "passed",
        "preparationStatus": "passed",
        "baselineEligible": True,
        "benchmarkPolicy": "normal",
        "benchmarkOnly": False,
        "executed": 2,
        "skipped": 0,
        "environment": environment,
        "target": f"{environment}-local",
        "candidateBindingDigest": _candidate_digest(environment),
        "sourceRevision": handoff["sourceRevision"],
        "packageDigest": handoff["packageDigest"],
        "runtimeConfigDigest": handoff["runtimeConfigDigest"],
        "releaseId": handoff["releaseId"],
        "manifestDigest": handoff["manifestDigest"],
        "importRunId": handoff["importRunId"],
        "readinessReceiptDigest": handoff["readinessReceiptDigest"],
        "requestDigest": _DIGESTS["requestDigest"],
        "evidenceDigest": handoff["evidenceDigest"],
        "handoffDigest": handoff["handoffDigest"],
        "operationCount": 2,
        "executedOperationIds": ["chat.message.ListMessages"],
        "loadedProviders": ["chat_service", "user_service"],
        "requiredProviders": ["chat_service", "user_service"],
        "requiredProviderCapabilities": ["provider.identity.local_sms"],
        "caseResults": rows,
    }


def _prod_rejection() -> dict[str, object]:
    return {
        "schema": "qwq.case_result",
        "caseId": "prod-test-data-mutation-boundary",
        "status": "GATE_BLOCK",
        "preparationStatus": "GATE_BLOCK",
        "environment": "prod",
        "target": "prod-hosted",
        "executed": 0,
        "skipped": 0,
        "operationCount": 0,
        "executedOperationIds": [],
        "loadedProviders": [],
        "requiredProviders": [],
        "baselineEligible": False,
        "requestDigest": _DIGESTS["requestDigest"],
        "issues": [
            "Prod rejects test-data mutation before Provider discovery, "
            "ActorLease acquisition, or any business operation"
        ],
    }


class TestDataEnvironmentResultsContractTest(unittest.TestCase):
    def test_exact_three_environment_bundle_and_prod_rejection_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prod_path = root / "prod.json"
            prod_path.write_text(json.dumps(_prod_rejection()), encoding="utf-8")
            paths: dict[str, Path] = {}
            handoffs: dict[str, Path] = {}
            for environment in ("alpha", "beta", "gamma"):
                handoff_path = root / f"{environment}-handoff.json"
                handoff_path.write_text(
                    json.dumps(_handoff(environment)),
                    encoding="utf-8",
                )
                handoffs[environment] = handoff_path
                path = root / f"{environment}.json"
                path.write_text(
                    json.dumps(_case_result(environment, path)),
                    encoding="utf-8",
                )
                paths[environment] = path

            issues = verify(
                handoff_paths=handoffs,
                case_result_paths=paths,
                prod_rejection_path=prod_path,
            )

        self.assertEqual(issues, [])

    def test_missing_cleanup_receipt_blocks_the_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prod_path = root / "prod.json"
            prod_path.write_text(json.dumps(_prod_rejection()), encoding="utf-8")
            paths: dict[str, Path] = {}
            handoffs: dict[str, Path] = {}
            for environment in ("alpha", "beta", "gamma"):
                handoff_path = root / f"{environment}-handoff.json"
                handoff_path.write_text(
                    json.dumps(_handoff(environment)),
                    encoding="utf-8",
                )
                handoffs[environment] = handoff_path
                path = root / f"{environment}.json"
                result = _case_result(environment, path)
                if environment == "gamma":
                    result["caseResults"][0]["cleanupReceiptDigests"] = []
                path.write_text(json.dumps(result), encoding="utf-8")
                paths[environment] = path

            issues = verify(
                handoff_paths=handoffs,
                case_result_paths=paths,
                prod_rejection_path=prod_path,
            )

        self.assertTrue(any("lifecycle receipt closure" in issue for issue in issues))

    def test_handoff_digest_and_case_instance_reuse_block_the_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prod_path = root / "prod.json"
            prod_path.write_text(json.dumps(_prod_rejection()), encoding="utf-8")
            paths: dict[str, Path] = {}
            handoffs: dict[str, Path] = {}
            for environment in ("alpha", "beta", "gamma"):
                handoff_path = root / f"{environment}-handoff.json"
                handoff_path.write_text(
                    json.dumps(_handoff(environment)),
                    encoding="utf-8",
                )
                handoffs[environment] = handoff_path
                path = root / f"{environment}.json"
                result = _case_result(environment, path)
                if environment == "beta":
                    result["handoffDigest"] = "sha256:" + "f" * 64
                    result["caseResults"][1]["testDataInstanceId"] = result[
                        "caseResults"
                    ][0]["testDataInstanceId"]
                path.write_text(json.dumps(result), encoding="utf-8")
                paths[environment] = path

            issues = verify(
                handoff_paths=handoffs,
                case_result_paths=paths,
                prod_rejection_path=prod_path,
            )

        self.assertTrue(any("identity drifts from handoff" in issue for issue in issues))
        self.assertTrue(any("reuse a testDataInstanceId" in issue for issue in issues))

    def test_required_operation_and_provider_capability_closures_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prod_path = root / "prod.json"
            prod_path.write_text(json.dumps(_prod_rejection()), encoding="utf-8")
            paths: dict[str, Path] = {}
            handoffs: dict[str, Path] = {}
            for environment in ("alpha", "beta", "gamma"):
                handoff = _handoff(environment)
                handoff_path = root / f"{environment}-handoff.json"
                handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
                handoffs[environment] = handoff_path
                result_path = root / f"{environment}.json"
                result = _case_result(environment, result_path)
                if environment == "gamma":
                    result["executedOperationIds"] = ["chat.message.RecallMessage"]
                    result["requiredProviderCapabilities"] = []
                result_path.write_text(json.dumps(result), encoding="utf-8")
                paths[environment] = result_path

            issues = verify(
                handoff_paths=handoffs,
                case_result_paths=paths,
                prod_rejection_path=prod_path,
            )

        self.assertTrue(any("handoff closure" in issue for issue in issues))
        self.assertTrue(any("Provider capability closure" in issue for issue in issues))

    def test_noncanonical_and_mismatched_embedded_receipt_digests_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prod_path = root / "prod.json"
            prod_path.write_text(json.dumps(_prod_rejection()), encoding="utf-8")
            paths: dict[str, Path] = {}
            handoffs: dict[str, Path] = {}
            for environment in ("alpha", "beta", "gamma"):
                handoff_path = root / f"{environment}-handoff.json"
                handoff_path.write_text(
                    json.dumps(_handoff(environment)),
                    encoding="utf-8",
                )
                handoffs[environment] = handoff_path
                result_path = root / f"{environment}.json"
                result = _case_result(environment, result_path)
                if environment == "beta":
                    result["caseResults"][0]["provisionReceiptDigest"] = (
                        "sha256:" + "G" * 64
                    )
                    embedded = {
                        "schema": "qwq.test_data_receipt",
                        "sequence": 1,
                        "kind": "test-body",
                    }
                    result["caseResults"][1]["testBodyReceipt"] = {
                        **embedded,
                        "receiptDigest": canonical_digest(embedded),
                    }
                result_path.write_text(json.dumps(result), encoding="utf-8")
                paths[environment] = result_path

            issues = verify(
                handoff_paths=handoffs,
                case_result_paths=paths,
                prod_rejection_path=prod_path,
            )

        self.assertTrue(any("not canonical sha256" in issue for issue in issues))
        self.assertTrue(any("does not match its document" in issue for issue in issues))

    def test_legal_digest_without_receipt_bytes_and_unsafe_path_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prod_path = root / "prod.json"
            prod_path.write_text(json.dumps(_prod_rejection()), encoding="utf-8")
            paths: dict[str, Path] = {}
            handoffs: dict[str, Path] = {}
            for environment in ("alpha", "beta", "gamma"):
                handoff_path = root / f"{environment}-handoff.json"
                handoff_path.write_text(
                    json.dumps(_handoff(environment)),
                    encoding="utf-8",
                )
                handoffs[environment] = handoff_path
                result_path = root / f"{environment}.json"
                result = _case_result(environment, result_path)
                if environment == "alpha":
                    result["caseResults"][0].pop("provisionReceiptPath")
                    result["caseResults"][0]["provisionReceiptDigest"] = (
                        "sha256:" + "a" * 64
                    )
                if environment == "beta":
                    result["caseResults"][0]["cleanupReceiptPaths"] = [
                        "../outside-receipt.json"
                    ]
                result_path.write_text(json.dumps(result), encoding="utf-8")
                paths[environment] = result_path

            issues = verify(
                handoff_paths=handoffs,
                case_result_paths=paths,
                prod_rejection_path=prod_path,
            )

        self.assertTrue(any("has no document or path" in issue for issue in issues))
        self.assertTrue(any("receipt cannot be loaded" in issue for issue in issues))

    def test_benchmark_candidate_and_incomplete_prod_rejection_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prod = _prod_rejection()
            prod["target"] = "prod-local"
            prod["baselineEligible"] = True
            prod_path = root / "prod.json"
            prod_path.write_text(json.dumps(prod), encoding="utf-8")
            paths: dict[str, Path] = {}
            handoffs: dict[str, Path] = {}
            for environment in ("alpha", "beta", "gamma"):
                handoff_path = root / f"{environment}-handoff.json"
                handoff_path.write_text(
                    json.dumps(_handoff(environment)),
                    encoding="utf-8",
                )
                handoffs[environment] = handoff_path
                result_path = root / f"{environment}.json"
                result = _case_result(environment, result_path)
                if environment == "alpha":
                    result["benchmarkPolicy"] = "serial-no-cache"
                    result["benchmarkOnly"] = True
                result_path.write_text(json.dumps(result), encoding="utf-8")
                paths[environment] = result_path

            issues = verify(
                handoff_paths=handoffs,
                case_result_paths=paths,
                prod_rejection_path=prod_path,
            )

        self.assertTrue(any("full green release run" in issue for issue in issues))
        self.assertTrue(any("Prod mutation-boundary" in issue for issue in issues))
