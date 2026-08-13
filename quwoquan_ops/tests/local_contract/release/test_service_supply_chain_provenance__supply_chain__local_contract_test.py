from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


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

if __name__ == "__main__":
    unittest.main()
