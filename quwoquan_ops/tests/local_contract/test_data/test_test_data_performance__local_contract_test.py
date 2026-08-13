"""Comparable green-run performance budget contracts.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t3
"""

from __future__ import annotations

import itertools
import unittest
from pathlib import Path

from quwoquan_ops.gate.verify_test_data_performance import (
    compare,
    require_independent_report_paths,
)

_RUN_IDS = itertools.count(1)


def _run(
    *,
    preparation: int,
    total: int,
    receipt: int,
    capability: int,
    baseline: bool = False,
) -> dict:
    run_id = next(_RUN_IDS)
    lifecycle = {
        "testExecution": {"executed": 1, "failed": 0, "skipped": 0},
        "provisionReceiptDigest": "sha256:" + "9" * 64,
        "testBodyReceiptDigest": "sha256:" + "a" * 64,
        "readbackReceiptDigests": ["sha256:" + "b" * 64],
        "cleanupReceiptDigests": ["sha256:" + "c" * 64],
    }
    return {
        "schema": "qwq.case_result",
        "runId": f"run-{run_id}",
        "status": "passed",
        "preparationStatus": "passed",
        "baselineEligible": True,
        "executed": 2,
        "skipped": 0,
        "caseResults": [
            {"caseId": "case-a", "status": "passed", **lifecycle},
            {"caseId": "case-b", "status": "passed", **lifecycle},
        ],
        "target": "gamma-local",
        "environment": "gamma",
        "candidateBindingDigest": "sha256:" + "1" * 64,
        "requestDigest": "sha256:" + "2" * 64,
        "evidenceDigest": "sha256:" + "3" * 64,
        "handoffDigest": "sha256:" + "4" * 64,
        "sourceRevision": "a" * 40,
        "packageDigest": "sha256:" + "5" * 64,
        "runtimeConfigDigest": "sha256:" + "6" * 64,
        "releaseId": "release-1",
        "manifestDigest": "sha256:" + "7" * 64,
        "importRunId": "import-1",
        "readinessReceiptDigest": "sha256:" + "8" * 64,
        "machineFingerprint": "sha256:" + "3" * 64,
        "benchmarkPolicy": "serial-no-cache" if baseline else "normal",
        "benchmarkOnly": baseline,
        "rootWorkerCount": 1 if baseline else 4,
        "maxObservedConcurrency": 1 if baseline else 2,
        "executedOperationIds": ["chat.message.ListMessages"],
        "operationCount": 1,
        "requestCollectionMs": 0,
        "providerDiscoveryMs": 0,
        "planningMs": 0,
        "actorProvisionMs": 0,
        "dataPreparationMs": preparation,
        "criticalPathMs": preparation,
        "receiptWriteMs": receipt,
        "controlPlaneOverheadMs": 0,
        "totalMs": total,
        "loadedProviders": ["chat_service", "user_service"],
        "requiredProviders": ["chat_service", "user_service"],
        "capabilityTimings": [
            {
                "capabilityKey": "chat.message.direct_conversation_with_messages",
                "ownerService": "chat_service",
                "requestId": "request-chat",
                "provisionMs": capability,
                "readbackMs": 0,
                "cleanupMs": 0,
                "operationCount": 0,
            },
            {
                "capabilityKey": "user.acceptance.authenticated_actors",
                "ownerService": "user_service",
                "requestId": "request-user",
                "provisionMs": 0,
                "readbackMs": 0,
                "cleanupMs": 0,
                "operationCount": 0,
            }
        ],
    }


class TestDataPerformanceContractTest(unittest.TestCase):
    def test_five_baseline_and_candidate_paths_must_be_independent(self) -> None:
        baseline = [Path(f"/tmp/baseline-{index}.json") for index in range(5)]
        candidate = [Path(f"/tmp/candidate-{index}.json") for index in range(5)]
        require_independent_report_paths(baseline, candidate)

        with self.assertRaisesRegex(ValueError, "baseline.*independent"):
            require_independent_report_paths(
                [baseline[0], baseline[0], *baseline[2:]],
                candidate,
            )
        with self.assertRaisesRegex(ValueError, "baseline/candidate"):
            require_independent_report_paths(
                baseline,
                [baseline[0], *candidate[1:]],
            )

    def test_parallel_report_uses_measured_wall_time_not_summed_branch_work(
        self,
    ) -> None:
        baseline = tuple(
            _run(
                preparation=300,
                total=500,
                receipt=10,
                capability=100,
                baseline=True,
            )
            for _ in range(5)
        )
        candidate_rows = [
            _run(preparation=200, total=300, receipt=5, capability=100)
            for _ in range(5)
        ]
        for row in candidate_rows:
            row["criticalPathMs"] = 1
        issues = compare(baseline, tuple(candidate_rows))
        self.assertTrue(any("50%" in issue for issue in issues))

    def test_five_comparable_green_runs_meet_reduction_budgets(self) -> None:
        baseline = tuple(
            _run(
                preparation=300,
                total=500,
                receipt=10,
                capability=120,
                baseline=True,
            )
            for _ in range(5)
        )
        candidate = tuple(
            _run(preparation=100, total=300, receipt=5, capability=100)
            for _ in range(5)
        )
        self.assertEqual(compare(baseline, candidate), [])

    def test_quality_and_latency_regressions_block(self) -> None:
        baseline = tuple(
            _run(
                preparation=300,
                total=500,
                receipt=10,
                capability=100,
                baseline=True,
            )
            for _ in range(5)
        )
        candidate_rows = [
            _run(preparation=200, total=450, receipt=20, capability=130)
            for _ in range(5)
        ]
        for row in candidate_rows:
            row["loadedProviders"] = [
                "assistant_service",
                "chat_service",
                "user_service",
            ]
            row["executedOperationIds"] = ["chat.message.SendMessage"]
        issues = compare(baseline, tuple(candidate_rows))
        self.assertTrue(any("50%" in issue for issue in issues))
        self.assertTrue(any("30%" in issue for issue in issues))
        self.assertTrue(any("5%" in issue for issue in issues))
        self.assertTrue(any("requested closure" in issue for issue in issues))
        self.assertTrue(any("operation closure" in issue for issue in issues))
        self.assertTrue(any("20%" in issue for issue in issues))

    def test_discovery_planning_and_no_mutation_control_p95_are_budgeted(self) -> None:
        baseline = tuple(
            _run(
                preparation=300,
                total=500,
                receipt=10,
                capability=100,
                baseline=True,
            )
            for _ in range(5)
        )
        candidate_rows = [
            _run(preparation=100, total=300, receipt=5, capability=100)
            for _ in range(5)
        ]
        candidate_rows[-1]["providerDiscoveryMs"] = 300
        candidate_rows[-1]["planningMs"] = 250
        candidate_rows[-1]["controlPlaneOverheadMs"] = 1001

        issues = compare(baseline, tuple(candidate_rows))

        self.assertTrue(any("discovery+planning p95" in issue for issue in issues))
        self.assertTrue(any("no-mutation control-plane p95" in issue for issue in issues))

    def test_baseline_policy_cannot_be_reused_as_environment_candidate(self) -> None:
        baseline = tuple(
            _run(
                preparation=300,
                total=500,
                receipt=10,
                capability=100,
                baseline=True,
            )
            for _ in range(5)
        )
        candidate = tuple(
            _run(preparation=100, total=300, receipt=5, capability=100)
            for _ in range(5)
        )
        baseline[0]["benchmarkOnly"] = False
        candidate[0]["benchmarkPolicy"] = "serial-no-cache"

        issues = compare(baseline, candidate)

        self.assertTrue(any("benchmark-only policy" in issue for issue in issues))
        self.assertTrue(any("normal execution policy" in issue for issue in issues))

    def test_incomplete_case_or_capability_evidence_is_rejected(self) -> None:
        baseline = tuple(
            _run(
                preparation=300,
                total=500,
                receipt=10,
                capability=100,
                baseline=True,
            )
            for _ in range(5)
        )
        candidate = tuple(
            _run(preparation=100, total=300, receipt=5, capability=100)
            for _ in range(5)
        )
        candidate[0]["caseResults"] = []
        candidate[0]["capabilityTimings"] = []

        with self.assertRaisesRegex(ValueError, "business-case set"):
            compare(baseline, candidate)

    def test_non_mapping_timing_and_zero_baseline_regression_are_rejected(self) -> None:
        baseline = tuple(
            _run(
                preparation=300,
                total=500,
                receipt=10,
                capability=0,
                baseline=True,
            )
            for _ in range(5)
        )
        candidate = tuple(
            _run(preparation=100, total=300, receipt=5, capability=1)
            for _ in range(5)
        )
        issues = compare(baseline, candidate)
        self.assertTrue(any("20%" in issue for issue in issues))

        candidate[0]["capabilityTimings"][0] = "not-an-object"
        with self.assertRaisesRegex(ValueError, "must be an object"):
            compare(baseline, candidate)

    def test_schema_run_identity_concurrency_and_lifecycle_are_enforced(self) -> None:
        baseline = tuple(
            _run(
                preparation=300,
                total=500,
                receipt=10,
                capability=120,
                baseline=True,
            )
            for _ in range(5)
        )
        candidate = tuple(
            _run(preparation=100, total=300, receipt=5, capability=100)
            for _ in range(5)
        )
        candidate[0]["schema"] = "wrong"
        candidate[1]["runId"] = candidate[0]["runId"]
        candidate[2]["caseResults"][0]["cleanupReceiptDigests"] = []

        with self.assertRaisesRegex(ValueError, "run identities"):
            compare(baseline, candidate)

        candidate[1]["runId"] = "replacement-run"
        with self.assertRaisesRegex(ValueError, "schema or lifecycle"):
            compare(baseline, candidate)

        candidate[0]["schema"] = "qwq.case_result"
        with self.assertRaisesRegex(ValueError, "case lifecycle"):
            compare(baseline, candidate)

        candidate[2]["caseResults"][0]["cleanupReceiptDigests"] = [
            "sha256:" + "c" * 64
        ]
        candidate[3]["maxObservedConcurrency"] = 1
        issues = compare(baseline, candidate)
        self.assertTrue(any("normal execution policy" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
