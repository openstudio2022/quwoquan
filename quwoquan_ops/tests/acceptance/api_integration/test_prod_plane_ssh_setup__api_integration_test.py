from __future__ import annotations

import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


class ProdPlaneSshSetupTest(unittest.TestCase):
    """T2：本地 prod 平面 SSH key 生成与映射产物输出。"""

    def test_generate_mode_writes_mapping_and_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            key_dir = tmp_path / "keys"
            mapping_out = tmp_path / "plane_key_map.json"
            instructions_out = tmp_path / "runner_key_setup.md"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.py",
                    "--mode",
                    "generate",
                    "--key-dir",
                    str(key_dir),
                    "--mapping-out",
                    str(mapping_out),
                    "--instructions-out",
                    str(instructions_out),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            mapping = json.loads(mapping_out.read_text(encoding="utf-8"))
            self.assertEqual(mapping["host"], "118.31.239.122")
            self.assertEqual(
                [account["account"] for account in mapping["accounts"]],
                ["prod-edge-svc", "prod-media-svc", "prod-service-svc"],
            )
            for account in mapping["accounts"]:
                self.assertTrue(Path(account["privateKeyPath"]).is_file())
                self.assertTrue(Path(account["publicKeyPath"]).is_file())
            instructions = instructions_out.read_text(encoding="utf-8")
            self.assertIn("prod 私钥不再进入 GitHub Actions secrets", instructions)
            self.assertIn("PROD_SERVICE_SSH_KEY", instructions)
            self.assertIn("--github-prune-obsolete-secrets", instructions)

    def test_generate_mode_can_include_relay_and_readonly_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            key_dir = tmp_path / "keys"
            mapping_out = tmp_path / "plane_key_map.json"
            instructions_out = tmp_path / "runner_key_setup.md"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.py",
                    "--mode",
                    "generate",
                    "--all-accounts",
                    "--key-dir",
                    str(key_dir),
                    "--mapping-out",
                    str(mapping_out),
                    "--instructions-out",
                    str(instructions_out),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            mapping = json.loads(mapping_out.read_text(encoding="utf-8"))
            self.assertEqual(
                [account["account"] for account in mapping["accounts"]],
                [
                    "prod-edge-svc",
                    "prod-media-svc",
                    "prod-service-svc",
                    "prod-ops",
                    "prod-data-svc",
                ],
            )

    def test_generate_mode_can_prune_obsolete_github_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            key_dir = tmp_path / "keys"
            mapping_out = tmp_path / "plane_key_map.json"
            instructions_out = tmp_path / "runner_key_setup.md"
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            log_file = tmp_path / "gh_secret_calls.log"
            fake_gh = fake_bin / "gh"
            fake_gh.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import pathlib, sys",
                        f"log = pathlib.Path({str(log_file)!r})",
                        "args = sys.argv[1:]",
                        "if args[:2] == ['secret', 'list']:",
                        "    print('PROD_KUBECONFIG\\t2026-01-01T00:00:00Z')",
                        "    print('PROD_EDGE_SSH_KEY\\t2026-01-01T00:00:00Z')",
                        "    print('PROD_SERVICE_SSH_KEY\\t2026-01-01T00:00:00Z')",
                        "    print('GAMMA_BASE_URL\\t2026-01-01T00:00:01Z')",
                        "    raise SystemExit(0)",
                        "with log.open('a', encoding='utf-8') as fh:",
                        "    fh.write('ARGS=' + ' '.join(args) + '\\n')",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.py",
                    "--mode",
                    "generate",
                    "--key-dir",
                    str(key_dir),
                    "--mapping-out",
                    str(mapping_out),
                    "--instructions-out",
                    str(instructions_out),
                    "--github-prune-obsolete-secrets",
                    "--github-repo",
                    "openstudio2022/quwoquan",
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            log = log_file.read_text(encoding="utf-8")
            self.assertNotIn("secret set", log)
            self.assertIn("ARGS=secret delete PROD_EDGE_SSH_KEY --repo openstudio2022/quwoquan --app actions", log)
            self.assertIn("ARGS=secret delete PROD_SERVICE_SSH_KEY --repo openstudio2022/quwoquan --app actions", log)
            self.assertIn("ARGS=secret delete PROD_KUBECONFIG --repo openstudio2022/quwoquan --app actions", log)
            self.assertIn("ARGS=secret delete GAMMA_BASE_URL --repo openstudio2022/quwoquan --app actions", log)

    def test_generate_mode_can_export_encrypted_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            key_dir = tmp_path / "keys"
            mapping_out = tmp_path / "plane_key_map.json"
            instructions_out = tmp_path / "runner_key_setup.md"
            bundle_out = tmp_path / "prod_ssh_keys.tar.enc"
            env = os.environ.copy()
            env["PROD_SSH_BUNDLE_PASSPHRASE"] = "test-passphrase"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/setup_prod_plane_ssh_access.py",
                    "--mode",
                    "generate",
                    "--all-accounts",
                    "--key-dir",
                    str(key_dir),
                    "--mapping-out",
                    str(mapping_out),
                    "--instructions-out",
                    str(instructions_out),
                    "--export-encrypted-bundle",
                    "--bundle-out",
                    str(bundle_out),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            decrypted_tar = tmp_path / "prod_ssh_keys.tar"
            decrypt = subprocess.run(
                [
                    "openssl",
                    "enc",
                    "-d",
                    "-aes-256-cbc",
                    "-pbkdf2",
                    "-in",
                    str(bundle_out),
                    "-out",
                    str(decrypted_tar),
                    "-pass",
                    "env:PROD_SSH_BUNDLE_PASSPHRASE",
                ],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(decrypt.returncode, 0, decrypt.stdout + decrypt.stderr)
            extract_dir = tmp_path / "bundle"
            extract_dir.mkdir()
            with tarfile.open(decrypted_tar, "r") as tar:
                tar.extractall(extract_dir, filter="data")
            manifest = json.loads(
                (extract_dir / "prod-ssh-bundle" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["host"], "118.31.239.122")
            self.assertEqual(len(manifest["accounts"]), 5)
            self.assertTrue((extract_dir / "prod-ssh-bundle" / "prod-service-svc").is_file())


if __name__ == "__main__":
    unittest.main()
