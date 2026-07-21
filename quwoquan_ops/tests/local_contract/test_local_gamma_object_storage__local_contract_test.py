from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.local_beta_object_storage import prepare_local_beta_object_storage
from quwoquan_ops.cli.lib.local_gamma_object_storage import prepare_local_gamma_object_storage
from quwoquan_ops.cli.lib.local_environment_auth import prepare_local_environment_auth


class LocalGammaObjectStorageTest(unittest.TestCase):
    def test_prepares_tls_and_secret_outside_output_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deploy_root = Path(tmp_dir) / "deploy"
            with mock.patch.dict(os.environ, {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)}, clear=False):
                first = prepare_local_gamma_object_storage(edge_port=19130)
                second = prepare_local_gamma_object_storage(edge_port=19130)

            self.assertEqual(first.environment, second.environment)
            self.assertTrue(first.secret_path.is_file())
            self.assertTrue(first.ca_path.is_file())
            self.assertTrue((first.work_root / "certificates/object-storage/minio/public.crt").is_file())
            self.assertEqual(stat.S_IMODE(first.secret_path.stat().st_mode), 0o600)
            self.assertEqual(
                stat.S_IMODE((first.work_root / "certificates/object-storage/minio/private.key").stat().st_mode),
                0o600,
            )
            self.assertEqual(first.environment["LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT"], "gamma-upload.quwoquan-env.test:19130")
            self.assertEqual(first.host_endpoint, "https://gamma-upload.localhost:19130")
            self.assertNotIn(".qwq_output", str(first.secret_path))

    def test_rejects_invalid_edge_port(self) -> None:
        with self.assertRaises(ValueError):
            prepare_local_gamma_object_storage(edge_port=0)

    def test_beta_storage_is_target_isolated_from_gamma(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deploy_root = Path(tmp_dir) / "deploy"
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
                "beta-upload.quwoquan-env.test:18130",
            )
            self.assertEqual(
                beta.host_endpoint,
                "https://beta-upload.localhost:18130",
            )
            self.assertTrue(beta.ca_path.is_file())

    def test_concurrent_beta_preparation_keeps_one_valid_tls_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            environment = os.environ.copy()
            environment["QWQ_DEPLOY_WORK_ROOT"] = str(Path(tmp_dir) / "deploy")
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
            self.assertTrue((cert_root / "ca.crt").is_file())
            self.assertTrue((cert_root / "minio/public.crt").is_file())

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
