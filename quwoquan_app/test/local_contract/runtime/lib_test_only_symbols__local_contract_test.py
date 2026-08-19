#!/usr/bin/env python3
"""Production lib must reject the retired runtime-config test backdoor."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = (
    REPO_ROOT
    / "quwoquan_app/scripts/runtime/architecture/verify_lib_no_test_only_symbols.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_lib_no_test_only_symbols_under_test",
        VERIFIER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LibTestOnlySymbolsGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.app_lib = Path(self.temp_directory.name) / "lib"
        self.app_lib.mkdir(parents=True)

    def write_source(self, source: str) -> None:
        path = self.app_lib / "runtime/config/cloud_runtime_config.dart"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def test_production_hydration_entrypoint_is_allowed(self) -> None:
        self.write_source(
            "void hydrateFromNativeRuntimePackage(Map<String, String> value) {}"
        )

        self.assertEqual(self.verifier.collect_violations(self.app_lib), [])

    def test_public_test_hydration_entrypoint_is_rejected(self) -> None:
        self.write_source(
            "void hydrateFromNativeRuntimePackageForTest("
            "Map<String, String> value) {}"
        )

        violations = self.verifier.collect_violations(self.app_lib)
        self.assertTrue(
            any("hydrateFromNativeRuntimePackageForTest" in item for item in violations)
        )

    def test_private_force_switch_is_rejected(self) -> None:
        self.write_source("bool _forceNativeRuntimePackageForTest = true;")

        violations = self.verifier.collect_violations(self.app_lib)
        self.assertTrue(
            any("_forceNativeRuntimePackageForTest" in item for item in violations)
        )


if __name__ == "__main__":
    unittest.main()
