# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-002
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.prod import hosted_release_ledger


class HostedReleaseReceiptContractTest(unittest.TestCase):
    _DIGEST = "sha256:" + "a" * 64

    def _candidate(self) -> dict[str, str]:
        return {
            "imageDigest": self._DIGEST,
            "configDigest": self._DIGEST,
            "contractGraphDigest": self._DIGEST,
            "adapterDigest": self._DIGEST,
        }

    def _commit(
        self,
        *,
        state_dir: Path,
        stage: str,
        decision: str,
        generation: int,
        from_image: str = "image-v1",
        to_image: str = "image-v2",
    ) -> tuple[dict[str, str], dict[str, object]]:
        result = hosted_release_ledger.commit(
            state_dir,
            {
                "schema": "prod-hosted-release-transition-request",
                "service": "mainline",
                "fromImage": from_image,
                "toImage": to_image,
                "fromConfig": "config-v1",
                "toConfig": "config-v2",
                "step": {"gray-initial": "5", "carry-on": "25", "full": "100"}[stage],
                "stage": stage,
                "decision": decision,
                "rollbackOutcome": (
                    decision
                    if decision in {"rolled_back", "rollback_failed"}
                    else "not_triggered"
                ),
                "manifestDigest": self._DIGEST,
                **self._candidate(),
                "expectedGeneration": generation,
                "sloReadback": {"values": {"errorRate": 0.001}},
                "postChecks": [
                    {
                        "name": "hosted-health",
                        "status": "passed",
                        "receiptDigest": self._DIGEST,
                    }
                ],
                "lastGoodTarget": {"image": "image-v1", "config": "config-v1"},
                "verifiedAt": "2026-07-26T00:00:00Z",
            },
        )
        return dict(result["state"]), dict(result["receipt"])

    def test_gray_carry_on_and_full_receipts_bind_immutable_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            first, gray_receipt = self._commit(
                state_dir=state_dir,
                stage="gray-initial",
                decision="continue",
                generation=0,
            )
            second, carry_receipt = self._commit(
                state_dir=state_dir,
                stage="carry-on",
                decision="continue",
                generation=1,
            )
            third, full_receipt = self._commit(
                state_dir=state_dir,
                stage="full",
                decision="continue",
                generation=2,
            )
            readback = hosted_release_ledger.fetch(state_dir, "mainline")

        self.assertEqual(
            [first["stage"], second["stage"], third["stage"]],
            ["gray-initial", "carry-on", "full"],
        )
        for receipt, expected_generation in (
            (gray_receipt, 1),
            (carry_receipt, 2),
            (full_receipt, 3),
        ):
            self.assertEqual(
                {
                    "imageDigest": receipt["imageDigest"],
                    "configDigest": receipt["configDigest"],
                    "contractGraphDigest": receipt["contractGraphDigest"],
                    "adapterDigest": receipt["adapterDigest"],
                },
                self._candidate(),
            )
            self.assertEqual(receipt["committedGeneration"], expected_generation)
            self.assertEqual(
                receipt["lastGoodTarget"],
                {"image": "image-v1", "config": "config-v1"},
            )
            self.assertEqual(
                receipt["postChecks"],
                [
                    {
                        "name": "hosted-health",
                        "status": "passed",
                        "receiptDigest": self._DIGEST,
                    }
                ],
            )
            self.assertEqual(receipt["decision"], "continue")
        self.assertEqual(readback["authority"], "prod-hosted-service-plane")
        self.assertEqual(readback["receipt"], full_receipt)
        self.assertEqual(
            readback["receiptRef"],
            f"receipt:hosted:{full_receipt['receiptId']}",
        )

    def test_successful_and_failed_rollback_are_distinct_receipt_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            _, success = self._commit(
                state_dir=state_dir,
                stage="full",
                decision="rolled_back",
                generation=0,
                from_image="image-v2",
                to_image="image-v1",
            )
            _, failure = self._commit(
                state_dir=state_dir,
                stage="full",
                decision="rollback_failed",
                generation=1,
            )

        self.assertEqual(success["decision"], "rolled_back")
        self.assertEqual(success["rollbackOutcome"], "rolled_back")
        self.assertEqual(failure["decision"], "rollback_failed")
        self.assertEqual(failure["rollbackOutcome"], "rollback_failed")


if __name__ == "__main__":
    unittest.main()
