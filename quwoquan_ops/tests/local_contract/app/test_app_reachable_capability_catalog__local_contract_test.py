"""App 可达能力闭包必须由 canonical contracts 派生，不能手工维护中央清单。"""

from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path

from quwoquan_ops.cli.lib.app_reachable_capability_catalog import (
    derive_app_reachable_capability_catalog,
)

ROOT = Path(__file__).resolve().parents[4]


class AppReachableCapabilityCatalogTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
    def test_local_id_ambiguity_is_not_silently_resolved(self) -> None:
        operations = ({'localId': 'Same', 'id': 'a.Same'}, {'localId': 'Same', 'id': 'b.Same'})
        with patch('quwoquan_ops.cli.lib.app_reachable_capability_catalog.load_client_contract_operations', return_value=operations):
            with self.assertRaisesRegex(ValueError, 'local_id_ambiguous'):
                derive_app_reachable_capability_catalog(ROOT)

    def test_declarations_do_not_claim_native_or_startup_bindings(self) -> None:
        catalog = derive_app_reachable_capability_catalog(ROOT)
        self.assertEqual(catalog['bindingCompleteness'], 'GATE_BLOCK')
        self.assertEqual(catalog['nativeBindingEvidenceStatus'], 'unverified')
        self.assertEqual(catalog['startupBindingEvidenceStatus'], 'unverified')
        self.assertIn('gateway.persisted_query_execution.SearchPage', catalog['graphqlDescriptorCanonicalOperationIds'])

    def test_surface_local_ids_resolve_to_client_contracts(self) -> None:
        catalog = derive_app_reachable_capability_catalog(ROOT)
        self.assertEqual(catalog["missingSurfaceLocalIds"], ())
        self.assertGreaterEqual(catalog["surfaceLocalOperationCount"], 300)
        self.assertGreaterEqual(
            catalog["clientContractOperationCount"],
            catalog["surfaceLocalOperationCount"],
        )
        self.assertTrue(
            set(catalog["surfaceCanonicalOperationIds"]).issubset(
                set(catalog["clientCanonicalOperationIds"])
            )
        )

    def test_graphql_realtime_and_platform_are_part_of_the_union(self) -> None:
        catalog = derive_app_reachable_capability_catalog(ROOT)
        self.assertIn(
            "gateway.persisted_query_execution.ExecutePersistedGraphQLQuery",
            catalog["graphqlCanonicalOperationIds"],
        )
        self.assertGreaterEqual(len(catalog["graphqlCanonicalOperationIds"]), 5)
        self.assertGreaterEqual(len(catalog["realtimeEventRefs"]), 20)
        self.assertIn("chat.message.MessageSent", catalog["realtimeEventRefs"])
        self.assertIn("camera", catalog["platformCapabilityFlags"])
        self.assertIn("pushDelivery", catalog["platformCapabilityFlags"])
        self.assertGreaterEqual(catalog["objectCount"], 70)


if __name__ == "__main__":
    unittest.main()
