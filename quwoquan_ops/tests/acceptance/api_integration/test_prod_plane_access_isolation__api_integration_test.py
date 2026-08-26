from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[4]
ACCESS = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
RUNTIME = ROOT / "quwoquan_ops/environments/prod/runtime.yaml"


def _run(argv: list[str], **env_overrides: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in (
        "PROD_KUBECONFIG",
        "PROD_SSH_KEY_DIR",
        "PROD_EDGE_SSH_KEY_FILE",
        "PROD_MEDIA_SSH_KEY_FILE",
        "PROD_SERVICE_SSH_KEY_FILE",
        "PROD_DATA_SSH_KEY_FILE",
        "PROD_OPS_SSH_KEY_FILE",
        "PROD_EDGE_SSH_KEY_PATH",
        "PROD_MEDIA_SSH_KEY_PATH",
        "PROD_SERVICE_SSH_KEY_PATH",
        "PROD_DATA_SSH_KEY_PATH",
        "PROD_OPS_SSH_KEY_PATH",
    ):
        env.pop(key, None)
    env.update(env_overrides)
    return subprocess.run(argv, cwd=str(ROOT), text=True, capture_output=True, env=env, check=False)


def _write_fake_keypair(key_dir: Path, account: str) -> None:
    key_dir.mkdir(parents=True, exist_ok=True)
    private_key = key_dir / account
    public_key = key_dir / f"{account}.pub"
    private_key.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "fake\n"
        "-----END OPENSSH PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    public_key.write_text(
        f"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI{account} {account}@prod\n",
        encoding="utf-8",
    )


class ProdPlaneAccessIsolationTest(unittest.TestCase):
    """访问隔离契约 / 部署模块交互：四平面访问隔离单一真相源、凭据硬校验、bootstrap 与 deploy dry-run。"""

    # --- 访问隔离契约：访问隔离映射契约 ---
    def test_access_isolation_gate_passes(self) -> None:
        result = _run(["python3", "quwoquan_ops/gate/verify_prod_plane_access_isolation.py"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipIf(yaml is None, "PyYAML required")
    def test_planes_accounts_and_secrets_single_source(self) -> None:
        # spec_ref: specs/feature-tree/runtime/system-topology-and-networking/spec.md#sit-002.t2
        data = yaml.safe_load(ACCESS.read_text(encoding="utf-8"))
        runtime = yaml.safe_load(RUNTIME.read_text(encoding="utf-8"))
        self.assertEqual(data["management"]["purpose"], "ssh-only-management")
        self.assertRegex(data["management"]["sshHost"], r"^[A-Za-z0-9.-]+$")
        self.assertNotIn("sshHost", runtime["targets"]["prod-hosted"])
        self.assertNotIn(
            data["management"]["sshHost"],
            "\n".join(
                str(role.get("host") or "")
                for role in runtime["urlRoles"].values()
            ),
        )
        self.assertEqual(data["management"]["defaultHostId"], "prod-host-01")
        self.assertEqual(
            data["management"]["hosts"][0]["sshHost"],
            data["management"]["sshHost"],
        )
        self.assertEqual(
            set(data["deploymentInstances"]),
            {"prevalidate", "gray", "prod"},
        )
        planes = {p["plane"]: p for p in data["planes"]}
        self.assertEqual(set(planes), {"edge", "media", "service", "data"})
        for plane, spec in planes.items():
            self.assertEqual(spec["account"], f"prod-{plane}-svc")
            self.assertEqual(spec["sshKeySecret"], f"PROD_{plane.upper()}_SSH_KEY")
        # data 平面只读审计，不参与 deploy。
        self.assertEqual(planes["data"]["access"], "read-only-audit")
        self.assertEqual(planes["data"]["governedWorkloads"], [])

    # --- 契约与模块：按平面凭据硬校验（禁止失败放通） ---
    def test_credentials_hard_fail_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/validate_prod_plane_credentials.py",
                    "--stage",
                    "canary",
                ],
                PROD_SSH_KEY_DIR=tmp,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("PROD_SERVICE_SSH_KEY", result.stderr)

    def test_credentials_reject_kubeconfig_reintroduction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            key_dir = Path(tmp)
            for account in ("prod-edge-svc", "prod-media-svc", "prod-service-svc"):
                _write_fake_keypair(key_dir, account)
            result = _run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/validate_prod_plane_credentials.py",
                    "--stage",
                    "canary",
                ],
                PROD_KUBECONFIG="injected",
                PROD_SSH_KEY_DIR=str(key_dir),
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("PROD_KUBECONFIG", result.stderr)

    def test_credentials_can_require_relay_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            key_dir = Path(tmp)
            for account in ("prod-edge-svc", "prod-media-svc", "prod-service-svc", "prod-ops"):
                _write_fake_keypair(key_dir, account)
            result = _run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/validate_prod_plane_credentials.py",
                    "--stage",
                    "canary",
                    "--require-relay",
                ],
                PROD_SSH_KEY_DIR=str(key_dir),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("relay:PROD_OPS_SSH_KEY", result.stdout)

    # --- 部署模块：bootstrap dry-run 渲染去 root 账号 ---
    def test_bootstrap_dry_run_renders_nonroot_accounts(self) -> None:
        result = _run(
            ["bash", "quwoquan_ops/cli/prod/bootstrap_prod_plane_accounts.sh"],
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
        self.assertIn("--shell /bin/bash", result.stdout)
        # 读写平面启用 rootless podman linger；data 平面不建 stack。
        self.assertIn("enable-linger \"prod-service-svc\"", result.stdout)

    # --- 部署模块：prod deploy dry-run 给出按平面 SSH 发布计划 ---
    def test_deploy_dry_run_plane_plan(self) -> None:
        result = _run(
            ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
            DRY_RUN="true",
            ROLLOUT_STAGE="canary",
            IMAGE_TRANSPORT_TAG="transport-test",
            CANDIDATE_DIGEST="sha256:" + ("b" * 64),
            PROD_SSH_HOST="203.0.113.10",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("prod-edge-svc@203.0.113.10", result.stdout)
        self.assertIn("realtime-gateway rtc-service", result.stdout)
        self.assertIn("edge-gray", result.stdout)
        self.assertIn("prod-service-svc@203.0.113.10", result.stdout)
        self.assertIn("service-gray", result.stdout)
        self.assertIn("replica=r0/1", result.stdout)
        self.assertIn("host=prod-host-01", result.stdout)
        self.assertIn("/instances/gray/r0", result.stdout)
        self.assertIn("placementCoverage hosts=1 planeReplicas=", result.stdout)
        self.assertNotIn("prod-data-svc", result.stdout)


if __name__ == "__main__":
    unittest.main()
