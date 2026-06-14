from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ProdDeployContractTest(unittest.TestCase):
    def _run_deploy(self, **env_overrides: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "DRY_RUN": "false",
                "PROD_KUBECONFIG": "",
            }
        )
        env.update(env_overrides)
        return subprocess.run(
            ["bash", "agent_ops/deploy/prod/deploy_to_prod.sh"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def test_real_prod_apply_requires_kubeconfig(self) -> None:
        result = self._run_deploy(PROD_KUBECONFIG="")
        self.assertEqual(result.returncode, 2)
        self.assertIn("PROD_KUBECONFIG is required for real prod apply", result.stderr)

    def test_real_prod_apply_rejects_invalid_base64_kubeconfig(self) -> None:
        result = self._run_deploy(PROD_KUBECONFIG="not-base64")
        self.assertEqual(result.returncode, 2)
        self.assertIn("PROD_KUBECONFIG must be base64-encoded kubeconfig content", result.stderr)


if __name__ == "__main__":
    unittest.main()
