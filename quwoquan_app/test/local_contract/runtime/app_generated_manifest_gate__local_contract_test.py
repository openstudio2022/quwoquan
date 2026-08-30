#!/usr/bin/env python3
"""App generated-manifest gate keeps independent emitter modes isolated."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = (
    REPO_ROOT
    / "quwoquan_app/scripts/runtime/codegen/verify_app_generated_manifest.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_app_generated_manifest_under_test",
        VERIFIER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AppGeneratedManifestGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.service = Path(self.temp_directory.name) / "quwoquan_service"
        self.generator_root = self.service / "tools/codegen_app_metadata"
        self.generator_root.mkdir(parents=True)
        (self.generator_root / "main.go").write_text(
            "func main() { initializeContractGraphBundle() }\n",
            encoding="utf-8",
        )
        (self.service / "Makefile").write_text(
            "codegen-app-shell-navigation:\n"
            "\tgo run ./tools/codegen_app_metadata "
            "--shell-navigation-metadata-only\n\n",
            encoding="utf-8",
        )
        (self.generator_root / "app_launch_contract_codegen.go").write_text(
            "func loadLaunchContract() { os.ReadFile(artifactPath); "
            "os.ReadFile(launchPath) }\n",
            encoding="utf-8",
        )
        (self.generator_root / "app_launch_contract_render.go").write_text(
            "func checkOutputs() { os.ReadFile(path); os.ReadFile(manifestPath) }\n",
            encoding="utf-8",
        )
        (self.generator_root / "app_launch_contract_validation.go").write_text(
            "func validateLaunchContract() {}\n",
            encoding="utf-8",
        )

    def verify_boundary(self) -> None:
        with (
            mock.patch.object(self.verifier, "GENERATOR_ROOT", self.generator_root),
            mock.patch.object(self.verifier, "SERVICE", self.service),
        ):
            self.verifier.verify_emitter_boundary()

    def test_app_launch_contract_mode_accepts_only_declared_inputs_and_outputs(self) -> None:
        self.verify_boundary()

    def test_app_launch_contract_mode_rejects_undeclared_side_input(self) -> None:
        loader = self.generator_root / "app_launch_contract_codegen.go"
        loader.write_text(
            loader.read_text(encoding="utf-8")
            + 'func loadSideInput() { os.ReadFile("side_input.yaml") }\n',
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            AssertionError,
            "App launch loader 只能读取两份 canonical metadata",
        ):
            self.verify_boundary()

    def test_cloud_emitter_read_still_fails_closed(self) -> None:
        (self.generator_root / "operation_codegen.go").write_text(
            "func loadSideInput() { os.ReadFile(\"side_input.yaml\") }\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            AssertionError,
            "App emitter 禁止读取 Graph/lock 之外的文件: operation_codegen.go",
        ):
            self.verify_boundary()


if __name__ == "__main__":
    unittest.main()
