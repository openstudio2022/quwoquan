from __future__ import annotations

from quwoquan_app.test.local_contract.runtime.cloud_runtime_single_path_gate__local_contract_test import (
    CloudRuntimeSinglePathGateTest as _CloudRuntimeSinglePathGateTest,
)


class TestCloudRuntimeSinglePathCompanion(_CloudRuntimeSinglePathGateTest):
    def test_graphql_method_without_specialized_descriptor_is_rejected(self) -> None:
        canonical_id = "gateway.persisted_query_execution.SearchPage"
        failures: list[str] = []

        owned = self.verifier._check_graphql_method_owners(
            self.app_root,
            {
                "gatewayPersistedQueryExecutionSearchPage": (
                    self.verifier.GeneratedMethodMetadata(
                        canonical_id,
                        "gateway",
                        "graphql",
                    )
                )
            },
            failures,
        )

        self.assertEqual(owned, 0)
        self.assertTrue(
            any(
                "exactly one specialized generated descriptor" in failure
                for failure in failures
            ),
            failures,
        )
