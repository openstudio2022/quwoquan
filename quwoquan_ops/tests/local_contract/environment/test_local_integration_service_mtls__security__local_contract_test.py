from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib.local_integration_service_mtls import (
    prepare_local_integration_service_mtls,
)
from quwoquan_ops.cli.lib.public_domain_tls import issue_certificate


ROOT = Path(__file__).resolve().parents[4]


class LocalIntegrationServiceMTLSSecurityTest(unittest.TestCase):
    def test_prepare_issues_valid_pem_and_rejects_empty_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            deploy_root = Path(temporary) / "deploy"
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)},
                clear=False,
            ):
                issue_certificate("gamma-local")
                material = prepare_local_integration_service_mtls(
                    "gamma",
                    "gamma-local",
                )
                reused = prepare_local_integration_service_mtls(
                    "gamma",
                    "gamma-local",
                )

            self.assertEqual(material.environment, reused.environment)
            ca = Path(material.environment["INTEGRATION_SERVICE_MTLS_CA_FILE"])
            cert = Path(
                material.environment["INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE"]
            )
            key = Path(
                material.environment["INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE"]
            )
            self.assertTrue(ca.is_file())
            self.assertTrue(cert.is_file())
            self.assertTrue(key.is_file())
            self.assertGreater(ca.stat().st_size, 0)
            self.assertGreater(cert.stat().st_size, 0)
            self.assertGreater(key.stat().st_size, 0)
            self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
            self.assertNotIn(".qwq_output", str(cert))
            self.assertIn("/secrets/integration-service-mtls/", str(cert))
            self.assertEqual(
                material.environment["INTEGRATION_SERVICE_MTLS_SERVER_NAME"],
                "integration-service",
            )
            verify = subprocess.run(
                ["openssl", "verify", "-CAfile", str(ca), str(cert)],
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr or verify.stdout)

            # Empty PEM must never be accepted as ready material.
            cert.write_bytes(b"")
            cert.chmod(0o600)
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)},
                clear=False,
            ):
                repaired = prepare_local_integration_service_mtls(
                    "gamma",
                    "gamma-local",
                )
            repaired_cert = Path(
                repaired.environment["INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE"]
            )
            self.assertGreater(repaired_cert.stat().st_size, 0)
            self.assertTrue(
                repaired_cert.read_text(encoding="utf-8").startswith(
                    "-----BEGIN CERTIFICATE-----"
                )
            )

    def test_user_service_compose_requires_mtls_host_files(self) -> None:
        compose = (
            ROOT
            / "quwoquan_service/services/user-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "INTEGRATION_SERVICE_MTLS_CA_FILE:?INTEGRATION_SERVICE_MTLS_CA_FILE is required}",
            compose,
        )
        self.assertIn(
            "INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE:?INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE is required}",
            compose,
        )
        self.assertIn(
            "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE:?INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE is required}",
            compose,
        )
        self.assertNotIn(
            "INTEGRATION_SERVICE_MTLS_CA_FILE:-/dev/null",
            compose,
        )
        self.assertIn(
            "INTEGRATION_EXTERNAL_INTERACTION_BASE_URL: \"${INTEGRATION_EXTERNAL_INTERACTION_BASE_URL:-}\"",
            compose,
        )

    def test_material_ready_accepts_libressl_without_checkhost(self) -> None:
        source = (
            ROOT / "quwoquan_ops/cli/lib/local_integration_service_mtls.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"-checkhost"', source)
        self.assertIn("_certificate_binds_client_cn", source)
        self.assertIn("_openssl_bin", source)
        self.assertIn("/opt/homebrew/opt/openssl@3/bin/openssl", source)

    def test_stackctl_binds_mtls_before_content_workload_early_return(self) -> None:
        stackctl = (
            ROOT / "quwoquan_ops/cli/commands/gamma_release_binding.py"
        ).read_text(encoding="utf-8")
        self.assertIn("prepare_local_integration_service_mtls", stackctl)
        bind_fn = stackctl.split(
            "def _bind_formal_local_release_provider_environment(",
            1,
        )[1]
        mtls_index = bind_fn.index("prepare_local_integration_service_mtls")
        content_return_index = bind_fn.index(
            'workload in {"content-release", "content-commercial"}'
        )
        self.assertLess(mtls_index, content_return_index)


if __name__ == "__main__":
    unittest.main()
