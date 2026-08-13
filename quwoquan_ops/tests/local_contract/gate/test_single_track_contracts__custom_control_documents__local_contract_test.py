# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
"""verify_single_track_contracts 的自定义控制文档单轨合约。

由 test_single_track_contracts__contract__local_contract_test.py（Python 1000
行硬顶治理）按场景拆出：自定义控制文档族拒绝一切人工版本键、解析失败即
阻断、合法版本语义（k8s/pubspec/openapi/乐观锁）不受误伤。测试逐字搬移；
共享 harness 见 tests/support。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.tests.support.single_track_contracts_test_support import (
    ROOT,
    _load_verifier,
    _scan_fixture,
)

class SingleTrackContractsContractTest(unittest.TestCase):
    def test_custom_control_documents_are_scoped_and_current_sources_are_unversioned(
        self,
    ) -> None:
        module = _load_verifier()
        families = {
            "data catalogs": sorted(
                ROOT.glob("quwoquan_data/control_plane/_shared/catalogs/*")
            ),
            "data routing": sorted(
                ROOT.glob("quwoquan_data/control_plane/_shared/routing/*")
            ),
            "reliable task resources": sorted(
                ROOT.glob("quwoquan_service/runtime/reliabletask/resources/*")
            ),
            "service SLO": sorted(
                ROOT.glob("quwoquan_service/services/*/observability/slo/*")
            ),
            "gate policies": sorted(ROOT.glob("quwoquan_ops/policies/gates/*")),
        }
        candidates: list[Path] = []
        for family, paths in families.items():
            documents = [
                path
                for path in paths
                if path.suffix in {".yaml", ".yml", ".json"}
            ]
            self.assertTrue(documents, family)
            candidates.extend(documents)

        candidates.append(
            ROOT
            / "quwoquan_service/services/recommendation-service/internal/recommendation/"
            "recommendation_model_release/infrastructure/model_runtime/scripts/"
            "feature_registry.yaml"
        )
        for path in candidates:
            self.assertTrue(module.is_custom_control_document(path), path)
            inventory = module.Inventory()
            module.scan_file(path, inventory)
            self.assertEqual(
                inventory.counts.get("T1_custom_control_version_field", 0),
                0,
                path,
            )
            self.assertEqual(
                inventory.counts.get("T1_custom_control_parse_error", 0),
                0,
                path,
            )

        deployment = (
            ROOT
            / "quwoquan_service/services/recommendation-service/deploy/base/deployment.yaml"
        )
        self.assertFalse(module.is_custom_control_document(deployment))
        self.assertIn("quwoquan_ops/policies/gates", module.SCAN_ROOTS)
        self.assertFalse(hasattr(module, "ALLOWED_VERSIONISH_FIELD_NAMES"))

    def test_custom_control_documents_reject_all_manual_version_keys(self) -> None:
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_data/control_plane/_shared/catalogs/demo.yaml",
                "version: one\nentries: []\n",
                "version: version",
            ),
            (
                "quwoquan_data/control_plane/_shared/routing/demo.yaml",
                "routing:\n  schemaVersion: one\n",
                "routing.schemaVersion: schemaVersion",
            ),
            (
                "quwoquan_service/runtime/reliabletask/resources/demo.json",
                '{"tasks":[{"policyVersion":"one"}]}\n',
                "tasks[0].policyVersion: policyVersion",
            ),
            (
                "quwoquan_service/services/search-service/observability/slo/demo.yaml",
                "load_model:\n  version: one\n",
                "load_model.version: version",
            ),
            (
                "quwoquan_ops/policies/gates/demo.json",
                '{"baseline":{"catalogVersion":"one"}}\n',
                "baseline.catalogVersion: catalogVersion",
            ),
        )

        for relative_path, text, detail in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, text)
                self.assertEqual(
                    inventory.counts.get("T1_custom_control_version_field"),
                    1,
                )
                self.assertEqual(inventory.findings[0].detail, detail)
                self.assertEqual(
                    inventory.counts.get("T1_forbidden_envelope_field", 0),
                    0,
                )

    def test_custom_control_document_parse_failure_is_blocking(self) -> None:
        module = _load_verifier()
        inventory = _scan_fixture(
            module,
            "quwoquan_ops/policies/gates/broken.json",
            '{"baseline":',
        )
        self.assertEqual(
            inventory.counts.get("T1_custom_control_parse_error"),
            1,
        )
        self.assertEqual(
            inventory.counts.get("T1_custom_control_version_field", 0),
            0,
        )

    def test_legitimate_version_semantics_remain_outside_custom_control_keys(
        self,
    ) -> None:
        module = _load_verifier()
        fixtures = (
            (
                "quwoquan_service/services/content-service/deploy/base/deployment.yaml",
                "apiVersion: apps/v1\nkind: Deployment\n",
            ),
            (
                "quwoquan_ops/policies/gates/provider.json",
                '{"provider":{"apiVersion":"2025-01-01"}}\n',
            ),
            (
                "quwoquan_app/packages/example/pubspec.yaml",
                "name: example\nversion: 1.2.3+4\n",
            ),
            (
                "quwoquan_service/services/content-service/contracts/content/post/fields.yaml",
                "fields:\n  - name: version\n    description: aggregate optimistic lock\n",
            ),
            (
                "quwoquan_service/services/content-service/contracts/media/media_asset/fields.yaml",
                "fields:\n  - name: version\n    description: immutable asset version\n",
            ),
            (
                "quwoquan_service/services/content-service/generated/openapi.yaml",
                "openapi: 3.1.0\ninfo:\n  version: v1\n",
            ),
        )

        for relative_path, text in fixtures:
            with self.subTest(path=relative_path):
                inventory = _scan_fixture(module, relative_path, text)
                self.assertEqual(inventory.findings, [])


if __name__ == "__main__":
    unittest.main()
