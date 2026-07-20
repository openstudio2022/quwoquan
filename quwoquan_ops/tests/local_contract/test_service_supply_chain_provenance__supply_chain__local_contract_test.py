from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class ServiceSupplyChainProvenanceContractTest(unittest.TestCase):
    def test_github_actions_are_pinned_and_critical_paths_are_owned(self) -> None:
        result = subprocess.run(
            ["python3", "quwoquan_ops/gate/verify_github_supply_chain.py"],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_realtime_gateway_package_has_source_digest_and_spdx_sbom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package_dir = Path(directory)
            (package_dir / "report.json").write_text(
                json.dumps({"provenance": {}}),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_service/scripts/runtime/generate_service_supply_chain.py",
                    "--service",
                    "realtime-gateway",
                    "--env",
                    "gamma",
                    "--package-dir",
                    str(package_dir),
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            report = json.loads(
                (package_dir / "report.json").read_text(encoding="utf-8")
            )
            source = report["provenance"]["source"]
            self.assertEqual(
                source["buildContext"],
                "quwoquan_service",
            )
            self.assertRegex(source["sourceTreeSha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(source["dockerfileSha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertGreater(source["sourceFileCount"], 0)

            sbom = json.loads(
                (package_dir / "sbom.spdx.json").read_text(encoding="utf-8")
            )
            self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
            self.assertTrue(
                any(
                    package["name"] == "realtime-gateway"
                    for package in sbom["packages"]
                )
            )
            self.assertTrue(
                any(
                    relation["relationshipType"] == "DEPENDS_ON"
                    for relation in sbom["relationships"]
                )
            )


if __name__ == "__main__":
    unittest.main()
