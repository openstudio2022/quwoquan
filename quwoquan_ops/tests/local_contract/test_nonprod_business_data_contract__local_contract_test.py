"""Typed dataset and ContractGraph binding tests.

spec_ref: specs/feature-tree/spec.md#uat-009
"""

from __future__ import annotations

import unittest

from quwoquan_ops.cli.lib.nonprod_business_data import (
    ContractOperationCatalog,
    NONPROD_PAGING_BOUNDARY,
    NONPROD_REFERENCE_CONTENT_INTERACTION,
    NONPROD_REFERENCE_IDENTITY,
    NONPROD_RELIABILITY_RECOVERY,
    compute_dataset_epoch,
    dataset_recipes,
    idempotency_key,
)


class NonprodBusinessDataContractTest(unittest.TestCase):
    def test_all_recipe_operations_exist_in_contract_graph(self) -> None:
        ContractOperationCatalog().require_recipes(dataset_recipes())

    def test_required_dataset_cardinalities_are_exact(self) -> None:
        self.assertEqual(
            dict(NONPROD_REFERENCE_IDENTITY.expected_counts),
            {
                "accounts": 6,
                "personas": 7,
                "followDirections": 8,
                "mutualPairs": 1,
                "greetingStates": 3,
                "blockRecoveryScenarios": 1,
            },
        )
        self.assertEqual(
            dict(NONPROD_REFERENCE_CONTENT_INTERACTION.expected_counts)[
                "activeComments"
            ],
            34,
        )
        self.assertEqual(
            dict(NONPROD_PAGING_BOUNDARY.expected_counts)["createdComments"], 182
        )
        self.assertEqual(
            dict(NONPROD_RELIABILITY_RECOVERY.expected_counts)[
                "syncBoundaryMessages"
            ],
            501,
        )

    def test_epoch_and_idempotency_key_bind_candidate(self) -> None:
        epoch = compute_dataset_epoch(
            target="alpha-local",
            baseline_id="sha256:" + "1" * 64,
            package_digest="sha256:" + "2" * 64,
            release_digest="sha256:" + "3" * 64,
            recipe_digest=NONPROD_REFERENCE_IDENTITY.digest,
        )
        self.assertEqual(len(epoch), 64)
        key = idempotency_key(
            target="alpha-local",
            dataset_epoch=epoch,
            dataset_id=NONPROD_REFERENCE_IDENTITY.dataset_id,
            actor_role="primary",
            operation="FollowUser",
            step="01",
        )
        self.assertTrue(key.startswith("alpha-local/" + epoch + "/"))

    def test_prod_dataset_epoch_is_forbidden(self) -> None:
        with self.assertRaisesRegex(ValueError, "only for Alpha/Beta/Gamma"):
            compute_dataset_epoch(
                target="prod-sim",
                baseline_id="sha256:" + "1" * 64,
                package_digest="sha256:" + "2" * 64,
                release_digest="sha256:" + "3" * 64,
                recipe_digest="sha256:" + "4" * 64,
            )


if __name__ == "__main__":
    unittest.main()
