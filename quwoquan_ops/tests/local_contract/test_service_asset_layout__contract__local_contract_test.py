from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "quwoquan_service/service_asset_profiles.json"
VERIFIER = (
    ROOT / "quwoquan_service/scripts/verify/verify_service_layout.py"
)


class ServiceAssetLayoutContractTest(unittest.TestCase):
    def test_commercial_service_asset_gate_passes(self) -> None:
        result = subprocess.run(
            ["python3", str(VERIFIER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertIn("source-build-workload closure", result.stdout)

    def test_every_service_directory_has_exactly_one_typed_profile(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        assets = registry["assets"]
        ids = [item["id"] for item in assets]
        disk = sorted(
            path.name
            for path in (ROOT / "quwoquan_service/services").iterdir()
            if path.is_dir()
        )

        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids), disk)
        self.assertEqual(
            {
                item["profile"]
                for item in assets
            },
            set(registry["profiles"]),
        )


if __name__ == "__main__":
    unittest.main()
