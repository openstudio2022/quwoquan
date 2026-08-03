"""API-only nonprod data provisioning purity contract.

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.gate.verify_nonprod_business_data_provisioning import (
    scan_repository,
)


class NonprodBusinessDataProvisioningContractTest(unittest.TestCase):
    def test_empty_tree_is_pure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(scan_repository(Path(directory)), [])

    def test_runtime_manifest_and_prod_recipe_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / (
                "quwoquan_service/contracts/metadata/_shared/test_fixtures/"
                "app_gamma_seed_manifest.json"
            )
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}\n", encoding="utf-8")
            prod = root / "quwoquan_ops/environments/prod/runtime.yaml"
            prod.parent.mkdir(parents=True)
            prod.write_text("datasetEpoch: forbidden\n", encoding="utf-8")

            issues = scan_repository(root)

            self.assertTrue(any("app_gamma_seed_manifest" in issue for issue in issues))
            self.assertTrue(any("datasetEpoch" in issue for issue in issues))

    def test_nonprod_binding_allows_governed_adapter_but_deploy_rejects_in_process_adapter(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / (
                "quwoquan_service/services/user-service/environments/alpha/config.yaml"
            )
            config.parent.mkdir(parents=True)
            config.write_text(
                "adapter: ext.auth.carrier_one_tap_protocol_fixture\n",
                encoding="utf-8",
            )
            self.assertEqual(scan_repository(root), [])

            deploy = root / (
                "quwoquan_service/services/user-service/"
                "environments/alpha/deploy/compose.yaml"
            )
            deploy.parent.mkdir(parents=True)
            deploy.write_text(
                "IN_PROCESS_ADAPTER: protocol_fixture\n",
                encoding="utf-8",
            )

            issues = scan_repository(root)

            self.assertTrue(any("protocol_fixture" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
