from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.gate import verify_github_supply_chain


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

    def test_production_workflow_uses_real_arm64_runner_without_retired_label(
        self,
    ) -> None:
        workflow = ROOT / ".github" / "workflows" / "deploy-prod-auto.yml"
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("runs-on: [self-hosted, macOS, ARM64]", text)
        self.assertNotIn("prod-release", text)

    def test_retired_prod_runner_label_fails_closed(self) -> None:
        production = ROOT / ".github" / "workflows" / "deploy-prod-auto.yml"
        forged = production.read_text(encoding="utf-8").replace(
            "runs-on: [self-hosted, macOS, ARM64]",
            "runs-on: [self-hosted, macOS, prod-release]",
        )
        original_read_text = Path.read_text

        def read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path == production:
                return forged
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(Path, "read_text", autospec=True, side_effect=read_text):
            failures = (
                verify_github_supply_chain.verify_production_execution_isolation()
            )

        self.assertTrue(
            any("retired prod-release runner label" in failure for failure in failures),
            failures,
        )
        self.assertTrue(
            any(
                "missing production isolation control: "
                "runs-on: [self-hosted, macOS, ARM64]" in failure
                for failure in failures
            ),
            failures,
        )

if __name__ == "__main__":
    unittest.main()
