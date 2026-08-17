from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.local_beta_object_storage import prepare_local_beta_object_storage
from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology
from quwoquan_ops.cli.lib.local_gamma_object_storage import prepare_local_gamma_object_storage
from quwoquan_ops.cli.lib.local_environment_object_storage import (
    package_build_object_storage_environment,
)
from quwoquan_ops.cli.lib.local_environment_auth import prepare_local_environment_auth


class LocalGammaObjectStorageTest(unittest.TestCase):
    def test_package_build_values_are_target_scoped_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir, mock.patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": str(Path(tmp_dir) / "output")},
            clear=False,
        ):
            values = package_build_object_storage_environment(
                target_name="alpha-local"
            )
        self.assertEqual(
            values["LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT"],
            "https://127.0.0.1",
        )
        self.assertEqual(
            values["LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_ID"],
            "package-build-only",
        )
        self.assertIn(
            "alpha-local",
            values["LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE"],
        )
        self.assertTrue(
            values["LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE"].endswith(
                "/package/tls/root.crt"
            )
        )

    def test_all_local_upload_authorities_use_the_target_object_storage_edge(self) -> None:
        topology = load_environment_topology()
        expected = {
            "alpha-local": "https://upload.alpha.quwoquan.com:17130",
            "beta-local": "https://upload.beta.quwoquan.com:18130",
            "gamma-local": "https://upload.gamma.quwoquan.com:19130",
        }

        for target_name, upload_base in expected.items():
            with self.subTest(target=target_name):
                target = get_target(topology, target_name)
                self.assertEqual(target["publicBases"]["mediaUpload"], upload_base)

    def test_all_local_content_runtimes_presign_https_uploads(self) -> None:
        service_root = ROOT / "quwoquan_service/services/content-service"
        for environment in ("alpha", "beta", "gamma"):
            with self.subTest(environment=environment):
                config = yaml.safe_load(
                    (service_root / "environments" / environment / "config.yaml").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertIs(
                    config["overrides"]["sys.content-service.oss.use_ssl"],
                    True,
                )

    def _write_public_certificate(self, deploy_root: Path, target: str) -> None:
        certificate_root = deploy_root / target / "certificates"
        certificate_root.mkdir(parents=True)
        (certificate_root / "fullchain.pem").write_text(
            f"public-certificate-{target}\n",
            encoding="utf-8",
        )
        (certificate_root / "privkey.pem").write_text(
            f"private-key-{target}\n",
            encoding="utf-8",
        )
        (certificate_root / "root.crt").write_text(
            f"root-certificate-{target}\n",
            encoding="utf-8",
        )

    def test_prepares_public_tls_and_secret_outside_output_and_is_idempotent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deploy_root = Path(tmp_dir) / "deploy"
            self._write_public_certificate(deploy_root, "gamma-local")
            with mock.patch.dict(os.environ, {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)}, clear=False):
                first = prepare_local_gamma_object_storage(edge_port=19130)
                second = prepare_local_gamma_object_storage(edge_port=19130)

            self.assertEqual(first.environment, second.environment)
            self.assertTrue(first.secret_path.is_file())
            self.assertTrue(first.certificate_path.is_file())
            self.assertTrue(first.private_key_path.is_file())
            self.assertTrue((first.work_root / "certificates/object-storage/minio/public.crt").is_file())
            self.assertEqual(stat.S_IMODE(first.secret_path.stat().st_mode), 0o600)
            self.assertEqual(
                stat.S_IMODE((first.work_root / "certificates/object-storage/minio/private.key").stat().st_mode),
                0o600,
            )
            self.assertEqual(first.environment["LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT"], "upload.gamma.quwoquan.com:19130")
            self.assertNotIn("LOCAL_GAMMA_OBJECT_STORAGE_CDN_DOMAIN", first.environment)
            self.assertEqual(first.host_endpoint, "https://upload.gamma.quwoquan.com:19130")
            self.assertEqual(
                Path(first.environment["LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE"]).resolve(),
                (deploy_root / "gamma-local/certificates/root.crt").resolve(),
            )
            self.assertEqual(
                first.root_certificate_path.resolve(),
                (deploy_root / "gamma-local/certificates/root.crt").resolve(),
            )
            self.assertNotIn(".qwq_output", str(first.secret_path))

    def test_rejects_invalid_edge_port(self) -> None:
        with self.assertRaises(ValueError):
            prepare_local_gamma_object_storage(edge_port=0)

    def test_beta_storage_is_target_isolated_from_gamma(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deploy_root = Path(tmp_dir) / "deploy"
            self._write_public_certificate(deploy_root, "beta-local")
            self._write_public_certificate(deploy_root, "gamma-local")
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)},
                clear=False,
            ):
                beta = prepare_local_beta_object_storage(edge_port=18130)
                gamma = prepare_local_gamma_object_storage(edge_port=19130)

            self.assertNotEqual(beta.secret_path, gamma.secret_path)
            self.assertIn("beta-local", str(beta.secret_path))
            self.assertIn("gamma-local", str(gamma.secret_path))
            self.assertEqual(
                beta.environment["BETA_OBJECT_STORAGE_ENDPOINT"],
                "upload.beta.quwoquan.com:18130",
            )
            self.assertEqual(
                beta.host_endpoint,
                "https://upload.beta.quwoquan.com:18130",
            )
            self.assertTrue(beta.certificate_path.is_file())

    def test_concurrent_beta_preparation_keeps_one_valid_tls_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            environment = os.environ.copy()
            deploy_root = Path(tmp_dir) / "deploy"
            self._write_public_certificate(deploy_root, "beta-local")
            environment["QWQ_DEPLOY_WORK_ROOT"] = str(deploy_root)
            environment["PYTHONPATH"] = str(ROOT)
            command = [
                sys.executable,
                "-c",
                (
                    "from quwoquan_ops.cli.lib.local_beta_object_storage "
                    "import prepare_local_beta_object_storage; "
                    "prepare_local_beta_object_storage(edge_port=18130)"
                ),
            ]
            first = subprocess.Popen(
                command,
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            second = subprocess.Popen(
                command,
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            first_stdout, first_stderr = first.communicate(timeout=30)
            second_stdout, second_stderr = second.communicate(timeout=30)

            self.assertEqual(first.returncode, 0, first_stdout + first_stderr)
            self.assertEqual(second.returncode, 0, second_stdout + second_stderr)
            cert_root = (
                Path(tmp_dir)
                / "deploy"
                / "beta-local"
                / "certificates"
                / "object-storage"
            )
            self.assertTrue((cert_root / "minio/public.crt").is_file())
            self.assertFalse((cert_root / "ca.crt").exists())

    def test_prepares_stable_auth_secrets_outside_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deploy_root = Path(tmp_dir) / "deploy"
            with mock.patch.dict(os.environ, {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)}, clear=False):
                first = prepare_local_environment_auth("gamma", "gamma-local")
                second = prepare_local_environment_auth("gamma", "gamma-local")

            self.assertEqual(first.environment, second.environment)
            self.assertTrue(first.secret_path.is_file())
            self.assertEqual(stat.S_IMODE(first.secret_path.stat().st_mode), 0o600)
            self.assertNotIn(".qwq_output", str(first.secret_path))
            self.assertGreaterEqual(
                len(
                    first.environment[
                        "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET"
                    ]
                ),
                32,
            )

    def test_migrates_existing_auth_secret_with_only_code_ref_key_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deploy_root = Path(tmp_dir) / "deploy"
            secret_path = deploy_root / "gamma-local" / "secrets" / "auth.env"
            secret_path.parent.mkdir(parents=True)
            secret_path.write_text(
                "jwt_secret=existing-jwt\n"
                "device_ticket_secret=existing-device\n",
                encoding="utf-8",
            )
            secret_path.chmod(0o600)
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)},
                clear=False,
            ):
                migrated = prepare_local_environment_auth("gamma", "gamma-local")
                repeated = prepare_local_environment_auth("gamma", "gamma-local")

            self.assertEqual(migrated.environment, repeated.environment)
            self.assertIn("existing-jwt", migrated.environment.values())
            self.assertIn("existing-device", migrated.environment.values())
            contents = secret_path.read_text(encoding="utf-8")
            self.assertEqual(contents.count("otp_code_ref_key_b64="), 1)
            self.assertEqual(
                contents.count("account_closure_subject_hmac_secret="),
                1,
            )
            self.assertEqual(stat.S_IMODE(secret_path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
