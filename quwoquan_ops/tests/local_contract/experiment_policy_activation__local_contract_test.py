# spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import experiment_policy_activation as activation


class ExperimentPolicyActivationLocalContractTest(unittest.TestCase):
    def test_create_is_package_bound_exact_and_never_persists_bearer(self) -> None:
        create_result = {
            "id": "search_ranking",
            "key": "search_ranking",
            "status": "running",
            "experimentRevision": 1,
        }
        catalog = {
            "items": [
                {
                    **create_result,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                }
            ]
        }
        with (
            mock.patch.object(
                activation,
                "active_deployment_candidate",
                return_value={"baselineId": "sha256:" + "a" * 64},
            ),
            mock.patch.object(
                activation,
                "load_candidate_manifest",
                return_value={
                    "packageDigest": "sha256:" + "b" * 64,
                    "sourceRevision": "revision-1",
                },
            ),
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="sensitive-bearer",
            ),
            mock.patch.object(
                activation,
                "root_certificate_path",
                return_value=Path("/tmp/root.crt"),
            ),
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[(201, create_result), (200, catalog)],
            ) as request_json,
        ):
            receipt = activation.activate_search_experiment_policy(
                environment="alpha",
                target="alpha-local",
                product_ops_base_url="https://ops.alpha.quwoquan.local:17010",
            )

        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["operation"], "created")
        self.assertEqual(receipt["caseResult"]["executed"], 1)
        self.assertEqual(receipt["caseResult"]["skipped"], 0)
        self.assertNotIn("sensitive-bearer", json.dumps(receipt))
        create_call = request_json.call_args_list[0].kwargs
        self.assertEqual(create_call["method"], "POST")
        self.assertIn("Idempotency-Key", create_call["headers"])
        self.assertNotIn("Authorization", create_call["headers"])

    def test_existing_exact_policy_is_reused_without_second_source(self) -> None:
        catalog = {
            "items": [
                {
                    "id": "search_ranking",
                    "key": "search_ranking",
                    "status": "running",
                    "experimentRevision": 3,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                }
            ]
        }
        with (
            mock.patch.object(
                activation,
                "active_deployment_candidate",
                return_value={"baselineId": "sha256:" + "a" * 64},
            ),
            mock.patch.object(
                activation,
                "load_candidate_manifest",
                return_value={"packageDigest": "sha256:" + "b" * 64},
            ),
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="token",
            ),
            mock.patch.object(
                activation,
                "root_certificate_path",
                return_value=Path("/tmp/root.crt"),
            ),
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[(409, {"code": "OPS.USER.version_conflict"}), (200, catalog)],
            ),
        ):
            receipt = activation.activate_search_experiment_policy(
                environment="gamma",
                target="gamma-local",
                product_ops_base_url="https://ops.gamma.quwoquan.local:19010",
            )
        self.assertEqual(receipt["operation"], "reused")
        self.assertEqual(receipt["policy"]["experimentRevision"], 3)

    def test_prod_is_rejected_before_any_credential_is_minted(self) -> None:
        with (
            mock.patch.object(
                activation, "mint_local_product_ops_operator_token"
            ) as mint,
            self.assertRaisesRegex(
                activation.ExperimentPolicyActivationError,
                "Alpha/Beta/Gamma",
            ),
        ):
            activation.activate_search_experiment_policy(
                environment="prod",
                target="prod-sim",
                product_ops_base_url="https://ops.quwoquan.com",
            )
        mint.assert_not_called()


if __name__ == "__main__":
    unittest.main()
