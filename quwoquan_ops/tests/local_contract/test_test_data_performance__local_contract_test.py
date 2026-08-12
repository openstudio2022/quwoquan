"""Comparable green-run performance budget contracts.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t3
"""

from __future__ import annotations

import unittest

from quwoquan_ops.gate.verify_test_data_performance import compare


def _run(*, preparation: int, total: int, receipt: int, capability: int) -> dict:
    return {
        "status": "passed",
        "baselineEligible": True,
        "target": "gamma-local",
        "environment": "gamma",
        "candidateBindingDigest": "sha256:" + "1" * 64,
        "requestDigest": "sha256:" + "2" * 64,
        "machineFingerprint": "sha256:" + "3" * 64,
        "requestCollectionMs": 0,
        "providerDiscoveryMs": 0,
        "planningMs": 0,
        "actorProvisionMs": 0,
        "dataPreparationMs": preparation,
        "criticalPathMs": preparation,
        "receiptWriteMs": receipt,
        "totalMs": total,
        "loadedProviders": ["chat_service", "user_service"],
        "requiredProviders": ["chat_service", "user_service"],
        "capabilityTimings": [
            {
                "capabilityKey": "chat.message.direct_conversation_with_messages",
                "provisionMs": capability,
                "readbackMs": 0,
                "cleanupMs": 0,
            }
        ],
    }


class TestDataPerformanceContractTest(unittest.TestCase):
    def test_parallel_report_uses_measured_wall_time_not_summed_branch_work(
        self,
    ) -> None:
        baseline = tuple(
            _run(preparation=300, total=500, receipt=10, capability=100)
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
            _run(preparation=300, total=500, receipt=10, capability=120)
            for _ in range(5)
        )
        candidate = tuple(
            _run(preparation=100, total=300, receipt=5, capability=100)
            for _ in range(5)
        )
        self.assertEqual(compare(baseline, candidate), [])

    def test_quality_and_latency_regressions_block(self) -> None:
        baseline = tuple(
            _run(preparation=300, total=500, receipt=10, capability=100)
            for _ in range(5)
        )
        candidate_rows = [
            _run(preparation=200, total=450, receipt=20, capability=130)
            for _ in range(5)
        ]
        candidate_rows[0]["loadedProviders"] = [
            "assistant_service",
            "chat_service",
            "user_service",
        ]
        issues = compare(baseline, tuple(candidate_rows))
        self.assertTrue(any("50%" in issue for issue in issues))
        self.assertTrue(any("30%" in issue for issue in issues))
        self.assertTrue(any("5%" in issue for issue in issues))
        self.assertTrue(any("requested closure" in issue for issue in issues))
        self.assertTrue(any("20%" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
