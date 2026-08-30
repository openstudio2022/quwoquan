#!/usr/bin/env python3
"""生产 Remote 单路径门禁的 local_contract。"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = (
    REPO_ROOT
    / "quwoquan_app"
    / "scripts"
    / "runtime" / "cloud" / "verify_production_data_source_single_path.py"
)

MANAGED_OVERRIDE = (
    "providerScopeOverrides: [\n"
    "  authSessionControllerProvider.overrideWith(\n"
    "    _PatrolAuthSessionController.new,\n"
    "  ),\n"
    "]\n"
)
EMPTY_OVERRIDE = "providerScopeOverrides: const []\n"


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_production_data_source_single_path", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductionDataSourceSinglePathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def test_canonical_patrol_composition_is_accepted(self) -> None:
        self.assertEqual(
            self.verifier.patrol_provider_scope_override_issues(
                MANAGED_OVERRIDE + EMPTY_OVERRIDE
            ),
            [],
        )

    def test_extra_override_site_is_rejected(self) -> None:
        issues = self.verifier.patrol_provider_scope_override_issues(
            MANAGED_OVERRIDE + EMPTY_OVERRIDE + EMPTY_OVERRIDE
        )
        self.assertEqual(len(issues), 1)

    def test_business_provider_injection_is_rejected(self) -> None:
        injected = (
            "providerScopeOverrides: [\n"
            "  postRepositoryProvider.overrideWithValue(_FakeRepository()),\n"
            "]\n"
        )
        issues = self.verifier.patrol_provider_scope_override_issues(
            injected + EMPTY_OVERRIDE
        )
        self.assertEqual(len(issues), 1)

    def test_forbidden_runtime_selectors_stay_declared(self) -> None:
        # 判据的禁令面不得被悄悄削弱。
        for symbol in (
            "AppDataSourceMode",
            "appDataSourceModeProvider",
            "mockDataSourceActiveProvider",
            "cloudRepositoryImplForMode",
        ):
            self.assertIn(symbol, self.verifier.FORBIDDEN_SYMBOLS)
        for token in ("quwoquan_cloud_mock", "runners/alpha"):
            self.assertIn(token, self.verifier.FORBIDDEN_RUNTIME_TOKENS)

    def test_retired_mock_composition_is_absent_from_the_tree(self) -> None:
        self.assertFalse(self.verifier.RETIRED_AGGREGATE_MOCK_PACKAGE.exists())
        retired_runner = self.verifier.APP / "runners" / "alpha"
        self.assertFalse((retired_runner / "pubspec.yaml").exists())

    def test_gate_currently_passes_on_the_real_tree(self) -> None:
        self.assertEqual(self.verifier.main(), 0)


if __name__ == "__main__":
    unittest.main()
