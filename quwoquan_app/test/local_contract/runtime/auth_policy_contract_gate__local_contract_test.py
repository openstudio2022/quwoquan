#!/usr/bin/env python3
"""Auth policy gate must accept stable semantics after ``dart format``."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = (
    REPO_ROOT / "quwoquan_app/scripts/runtime/auth/verify_auth_policy_contract.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_auth_policy_contract_under_test",
        VERIFIER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AuthPolicyContractGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def test_generated_operations_accept_dart_formatter_wrapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory) / "operation_contracts.g.dart"
            generated.write_text(
                """
const appCloudOperationContracts = <String, CloudOperationContract>{
  "content.post.GetPost": CloudOperationContract(
    authMode: "public",
  ),
  "circle.circle_management.gathering_plan.CommitGatheringPlanProposal":
      CloudOperationContract(
        canonicalOperationId:
            "circle.circle_management.gathering_plan.CommitGatheringPlanProposal",
        authMode: "required",
      ),
};
""",
                encoding="utf-8",
            )
            with mock.patch.object(
                self.verifier,
                "OPERATION_CONTRACTS_DART",
                generated,
            ):
                observed = self.verifier.parse_generated_operations()

        self.assertEqual(
            observed,
            {
                "content.post.GetPost": "public",
                "circle.circle_management.gathering_plan.CommitGatheringPlanProposal": "required",
            },
        )


if __name__ == "__main__":
    unittest.main()
