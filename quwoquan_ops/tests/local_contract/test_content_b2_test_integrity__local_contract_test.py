from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT
    / "quwoquan_service/scripts/verify/verify_content_b2_test_integrity.py"
)
SPEC = importlib.util.spec_from_file_location(
    "verify_content_b2_test_integrity",
    SCRIPT,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
integrity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = integrity
SPEC.loader.exec_module(integrity)


class ContentB2TestIntegrityTest(unittest.TestCase):
    def test_repository_bindings_are_executable_and_complete(self) -> None:
        report = integrity.verify_integrity()

        self.assertEqual(report.checked_objects, 10)
        self.assertGreater(report.checked_bindings, 0)
        self.assertEqual(report.issues, ())

    def test_deleted_go_function_binding_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metadata_root = Path(directory) / "content"
            shutil.copytree(integrity.METADATA_CONTENT, metadata_root)
            contract_path = metadata_root / "media_asset/tests/contract.yaml"
            contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
            contract["tests"][0]["go_func"] = "TestDeletedMediaContractEvidence"
            contract_path.write_text(
                yaml.safe_dump(contract, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            report = integrity.verify_integrity(
                metadata_content_root=metadata_root,
            )

        self.assertTrue(
            any("TestDeletedMediaContractEvidence" in issue for issue in report.issues)
        )


if __name__ == "__main__":
    unittest.main()
