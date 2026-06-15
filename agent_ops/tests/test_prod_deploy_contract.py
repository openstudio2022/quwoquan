from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PLANE_SECRETS = (
    "PROD_EDGE_SSH_KEY",
    "PROD_MEDIA_SSH_KEY",
    "PROD_SERVICE_SSH_KEY",
    "PROD_DATA_SSH_KEY",
    "PROD_OPS_SSH_KEY",
)

FAKE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----"


class ProdDeployContractTest(unittest.TestCase):
    """prod-hosted 已退役 PROD_KUBECONFIG，改为按平面 SSH 凭据 + 硬校验。"""

    def _run_deploy(self, **env_overrides: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        # 清空可能从 CI 环境继承的平面凭据，保证用例确定性。
        for key in PLANE_SECRETS:
            env.pop(key, None)
        env.pop("PROD_KUBECONFIG", None)
        env.update(
            {
                "DRY_RUN": "false",
                "ROLLOUT_STAGE": "gray-initial",
                "IMAGE_VERSION": "img-test",
                "CONFIG_VERSION": "cfg-test",
                "PROD_SSH_HOST": "203.0.113.10",
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

    def test_real_prod_apply_requires_plane_ssh_credentials(self) -> None:
        result = self._run_deploy()
        self.assertEqual(result.returncode, 2, result.stderr)
        # 缺平面凭据必须硬失败（禁止失败放通），并指明缺失的具体平面 secret。
        self.assertIn("PROD_EDGE_SSH_KEY", result.stderr)

    def test_prod_kubeconfig_is_retired_and_rejected(self) -> None:
        result = self._run_deploy(
            PROD_KUBECONFIG="anything",
            PROD_EDGE_SSH_KEY=FAKE_KEY,
            PROD_MEDIA_SSH_KEY=FAKE_KEY,
            PROD_SERVICE_SSH_KEY=FAKE_KEY,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("PROD_KUBECONFIG", result.stderr)

    def test_dry_run_previews_plane_plan_without_credentials(self) -> None:
        result = self._run_deploy(DRY_RUN="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        # 预览必须给出按平面账号的 SSH 发布计划与灰度命名空间。
        self.assertIn("prod-edge-svc", result.stdout)
        self.assertIn("quwoquan-edge-gray", result.stdout)
        # data 平面只读审计，不进 deploy 计划。
        self.assertNotIn("prod-data-svc", result.stdout)


if __name__ == "__main__":
    unittest.main()
