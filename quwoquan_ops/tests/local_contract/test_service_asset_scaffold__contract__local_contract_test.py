from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCAFFOLD = ROOT / "quwoquan_ops/gate/scaffold/new_service_fullstack.sh"


class ServiceAssetScaffoldContractTest(unittest.TestCase):
    def test_profile_and_domain_are_mandatory_before_any_write(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(SCAFFOLD),
                "--name",
                "contract-probe-service",
                "--domain",
                "contract-probe",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--profile must be", result.stderr)
        self.assertFalse(
            (
                ROOT
                / "quwoquan_service/services/contract-probe-service"
            ).exists()
        )

    def test_scaffold_declares_canonical_build_and_config_contract(self) -> None:
        text = SCAFFOLD.read_text(encoding="utf-8")

        for token in (
            "go-domain-source",
            "go-control-plane-source",
            "tests/local_contract",
            "tests/api_integration",
            "tests/adapter_conformance",
            "tests/support",
            ".qwq_output/build/",
            "bootstrap_service_config_layout.sh",
            "service_asset_profiles.json",
            "deploy/Dockerfile",
        ):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
