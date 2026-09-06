from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from quwoquan_ops.cli.prod import validate_prod_plane_credentials as credentials


ROOT = Path(__file__).resolve().parents[4]
ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"

PLANE_KEY_HINTS = (
    "PROD_SSH_KEY_DIR",
    "PROD_EDGE_SSH_KEY_FILE",
    "PROD_MEDIA_SSH_KEY_FILE",
    "PROD_SERVICE_SSH_KEY_FILE",
    "PROD_DATA_SSH_KEY_FILE",
    "PROD_OPS_SSH_KEY_FILE",
)


class ProdDeployContractTest(unittest.TestCase):
    """prod-hosted 已退役 PROD_KUBECONFIG，改为按平面 SSH 凭据 + 硬校验。"""

    def _write_release_manifest(self, path: Path) -> None:
        payload = {
            "schema": "release-evidence-manifest",
            "status": "main-admitted",
            "releaseCompositionId": "sha256:" + "b" * 64,
            "artifactDigest": "sha256:" + "c" * 64,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def _run_deploy(self, **env_overrides: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        # 清空可能从 CI 环境继承的平面凭据，保证用例确定性。
        for key in PLANE_KEY_HINTS:
            env.pop(key, None)
        env.pop("PROD_KUBECONFIG", None)
        env.pop("SERVICE", None)
        env.update(
            {
                "DRY_RUN": "false",
                "ROLLOUT_STAGE": "canary",
                "IMAGE_TRANSPORT_TAG": "transport-test",
                "PREVIOUS_IMAGE_TRANSPORT_TAG": "transport-previous",
                "CANDIDATE_DIGEST": "sha256:" + ("b" * 64),
                "SERVICE": "service-plane",
            }
        )
        env.update(env_overrides)
        with tempfile.TemporaryDirectory() as tmp:
            release_manifest = Path(tmp) / "release-manifest.json"
            web_trust = Path(tmp) / "web-runtime-config-trust.json"
            web_package = Path(tmp) / "web-runtime-config-package.json"
            self._write_release_manifest(release_manifest)
            web_trust.write_text("{}\n", encoding="utf-8")
            web_package.write_text("{}\n", encoding="utf-8")
            manifest = json.loads(release_manifest.read_text(encoding="utf-8"))
            env.setdefault("RELEASE_EVIDENCE_DIGEST", manifest["artifactDigest"])
            if env.get("DRY_RUN") != "true":
                env.setdefault("RELEASE_MANIFEST", str(release_manifest))
                env.setdefault("QWQ_WEB_RUNTIME_CONFIG_TRUST_PATH", str(web_trust))
                env.setdefault("QWQ_WEB_RUNTIME_CONFIG_PACKAGE_PATH", str(web_package))
            return subprocess.run(
                ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

    def _make_key_dir(self) -> tempfile.TemporaryDirectory[str]:
        tmp = tempfile.TemporaryDirectory()
        key_dir = Path(tmp.name)
        marker_kind = "OPEN" + "SSH PRIVATE KEY"
        private_key_fixture = (
            f"-----BEGIN {marker_kind}-----\n"
            "fake\n"
            f"-----END {marker_kind}-----\n"
        )
        for account in ("prod-edge-svc", "prod-media-svc", "prod-service-svc"):
            (key_dir / account).write_text(
                private_key_fixture,
                encoding="utf-8",
            )
            (key_dir / f"{account}.pub").write_text(
                f"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI{account} {account}@prod\n",
                encoding="utf-8",
            )
        return tmp

    def test_runtime_assembled_private_key_marker_is_validator_valid(self) -> None:
        with self._make_key_dir() as tmp:
            for account in ("prod-edge-svc", "prod-media-svc", "prod-service-svc"):
                self.assertTrue(
                    credentials._looks_like_private_key_file(Path(tmp) / account)
                )

    def test_real_prod_apply_requires_plane_ssh_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_deploy(PROD_SSH_KEY_DIR=tmp)
            self.assertEqual(result.returncode, 2, result.stderr)
            # 缺平面凭据必须硬失败（禁止失败放通），并指明缺失的具体平面 secret。
            self.assertIn("PROD_SERVICE_SSH_KEY", result.stderr)

    def test_prod_kubeconfig_is_retired_and_rejected(self) -> None:
        with self._make_key_dir() as tmp:
            result = self._run_deploy(
                PROD_KUBECONFIG="anything",
                PROD_SSH_KEY_DIR=tmp,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("PROD_KUBECONFIG", result.stderr)

    def test_dry_run_previews_plane_plan_without_credentials(self) -> None:
        result = self._run_deploy(DRY_RUN="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        # 预览必须给出 service plane 的 SSH 发布计划与灰度命名空间。
        self.assertIn("prod-service-svc", result.stdout)
        self.assertIn("quwoquan-service-gray-r0", result.stdout)
        self.assertIn("prod-edge-svc", result.stdout)
        self.assertIn("quwoquan-edge-gray-r0", result.stdout)
        self.assertIn("replica=r0/1", result.stdout)
        self.assertIn("host=prod-host-01", result.stdout)
        self.assertIn("/instances/gray/r0", result.stdout)
        self.assertIn(
            "credential_root='/home/prod-service-svc/credentials'",
            result.stdout,
        )
        self.assertIn('push_env="$credential_dir/push.env"', result.stdout)
        self.assertIn("INTEGRATION_PUSH_APNS_KEY_ID", result.stdout)
        self.assertIn("integration push credentials preflight ok", result.stdout)
        # data 平面只读审计，不进 deploy 计划。
        self.assertNotIn("prod-data-svc", result.stdout)


if __name__ == "__main__":
    unittest.main()
