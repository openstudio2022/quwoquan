from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
VERIFIER = APP / "scripts/runtime/verify_cloud_package_boundaries.py"


class CloudPackageBoundariesContractTest(unittest.TestCase):
    def test_package_boundary_gate_passes(self) -> None:
        result = subprocess.run(
            ["python3", str(VERIFIER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout}\nstderr={result.stderr}",
        )

    def test_production_and_alpha_dependency_roots_are_distinct(self) -> None:
        app = yaml.safe_load((APP / "pubspec.yaml").read_text(encoding="utf-8"))
        alpha = yaml.safe_load(
            (APP / "runners/alpha/pubspec.yaml").read_text(encoding="utf-8")
        )
        contracts = yaml.safe_load(
            (
                APP / "packages/quwoquan_cloud_contracts/pubspec.yaml"
            ).read_text(encoding="utf-8")
        )

        self.assertNotIn("quwoquan_cloud_mock", app["dependencies"])
        self.assertIn("quwoquan_cloud_mock", alpha["dependencies"])
        self.assertNotIn("quwoquan_app", contracts["dependencies"])


if __name__ == "__main__":
    unittest.main()
