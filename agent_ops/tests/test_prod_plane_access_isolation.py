from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[2]
ACCESS = ROOT / "deploy/shared/prod_plane_access_isolation.yaml"


def _run(argv: list[str], **env_overrides: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in (
        "PROD_KUBECONFIG",
        "PROD_EDGE_SSH_KEY",
        "PROD_MEDIA_SSH_KEY",
        "PROD_SERVICE_SSH_KEY",
        "PROD_DATA_SSH_KEY",
        "PROD_OPS_SSH_KEY",
    ):
        env.pop(key, None)
    env.update(env_overrides)
    return subprocess.run(argv, cwd=str(ROOT), text=True, capture_output=True, env=env, check=False)


class ProdPlaneAccessIsolationTest(unittest.TestCase):
    """T1 契约 / T2 模块交互：四平面访问隔离单一真相源、凭据硬校验、bootstrap 与 deploy dry-run。"""

    # --- T1：访问隔离映射契约 ---
    def test_access_isolation_gate_passes(self) -> None:
        result = _run(["python3", "agent_ops/gate/verify_prod_plane_access_isolation.py"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipIf(yaml is None, "PyYAML required")
    def test_planes_accounts_and_secrets_single_source(self) -> None:
        data = yaml.safe_load(ACCESS.read_text(encoding="utf-8"))
        planes = {p["plane"]: p for p in data["planes"]}
        self.assertEqual(set(planes), {"edge", "media", "service", "data"})
        for plane, spec in planes.items():
            self.assertEqual(spec["account"], f"prod-{plane}-svc")
            self.assertEqual(spec["sshKeySecret"], f"PROD_{plane.upper()}_SSH_KEY")
        # data 平面只读审计，不参与 deploy。
        self.assertEqual(planes["data"]["access"], "read-only-audit")
        self.assertEqual(planes["data"]["governedWorkloads"], [])

    # --- T1/T2：按平面凭据硬校验（禁止失败放通） ---
    def test_credentials_hard_fail_when_missing(self) -> None:
        result = _run(
            [
                "python3",
                "agent_ops/deploy/prod/validate_prod_plane_credentials.py",
                "--stage",
                "gray-initial",
            ]
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("PROD_EDGE_SSH_KEY", result.stderr)

    def test_credentials_reject_kubeconfig_reintroduction(self) -> None:
        key = "-----BEGIN OPENSSH PRIVATE KEY-----\nx\n-----END OPENSSH PRIVATE KEY-----"
        result = _run(
            [
                "python3",
                "agent_ops/deploy/prod/validate_prod_plane_credentials.py",
                "--stage",
                "gray-initial",
            ],
            PROD_KUBECONFIG="injected",
            PROD_EDGE_SSH_KEY=key,
            PROD_MEDIA_SSH_KEY=key,
            PROD_SERVICE_SSH_KEY=key,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("PROD_KUBECONFIG", result.stderr)

    # --- T2：bootstrap dry-run 渲染去 root 账号 ---
    def test_bootstrap_dry_run_renders_nonroot_accounts(self) -> None:
        result = _run(
            ["bash", "agent_ops/deploy/prod/bootstrap_prod_plane_accounts.sh"],
            DRY_RUN="true",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for account in (
            "prod-ops",
            "prod-edge-svc",
            "prod-media-svc",
            "prod-service-svc",
            "prod-data-svc",
        ):
            self.assertIn(account, result.stdout)
        # 读写平面启用 rootless podman linger；data 平面不建 stack。
        self.assertIn("enable-linger \"prod-service-svc\"", result.stdout)

    # --- T2：prod deploy dry-run 给出按平面 SSH 发布计划 ---
    def test_deploy_dry_run_plane_plan(self) -> None:
        result = _run(
            ["bash", "agent_ops/deploy/prod/deploy_to_prod.sh"],
            DRY_RUN="true",
            ROLLOUT_STAGE="gray-initial",
            IMAGE_VERSION="img",
            CONFIG_VERSION="cfg",
            PROD_SSH_HOST="203.0.113.10",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("prod-edge-svc@203.0.113.10", result.stdout)
        self.assertIn("quwoquan-edge-gray", result.stdout)
        self.assertNotIn("prod-data-svc", result.stdout)


if __name__ == "__main__":
    unittest.main()
