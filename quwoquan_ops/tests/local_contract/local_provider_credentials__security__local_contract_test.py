from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib.local_provider_credentials import (
    prepare_local_provider_credentials,
)


class LocalProviderCredentialsSecurityLocalContractTest(unittest.TestCase):
    def test_materializer_writes_mode_600_outside_repo_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            work_root = Path(temporary_dir)
            with mock.patch.dict(os.environ, {"QWQ_DEPLOY_WORK_ROOT": str(work_root)}):
                values = prepare_local_provider_credentials(
                    environment="alpha",
                    target_name="alpha-local",
                )
            secret_path = work_root / "alpha-local" / "secrets" / "external-providers.env"
            self.assertTrue(secret_path.is_file())
            self.assertEqual(stat.S_IMODE(secret_path.stat().st_mode), 0o600)
            self.assertNotIn(".qwq_output", str(secret_path))
            self.assertIn("CONTENT_EMBEDDING_FIXTURE_API_KEY", values)
            self.assertTrue(values["CONTENT_EMBEDDING_FIXTURE_API_KEY"])
            serialized = json.dumps({"keys": sorted(values)}, sort_keys=True)
            for value in values.values():
                self.assertNotIn(value, serialized)

    def test_materializer_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            work_root = Path(temporary_dir)
            with mock.patch.dict(os.environ, {"QWQ_DEPLOY_WORK_ROOT": str(work_root)}):
                first = prepare_local_provider_credentials(
                    environment="beta",
                    target_name="beta-local",
                )
                second = prepare_local_provider_credentials(
                    environment="beta",
                    target_name="beta-local",
                )
            self.assertEqual(first, second)

    def test_gamma_materializes_fixture_credentials_without_topology_endpoints(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            work_root = Path(temporary_dir)
            with mock.patch.dict(os.environ, {"QWQ_DEPLOY_WORK_ROOT": str(work_root)}):
                values = prepare_local_provider_credentials(
                    environment="gamma",
                    target_name="gamma-local",
                )

            secret_path = (
                work_root / "gamma-local" / "secrets" / "external-providers.env"
            )
            self.assertTrue(secret_path.is_file())
            self.assertIn("ASSISTANT_MODEL_API_KEY", values)
            self.assertNotIn("CONTENT_EMBEDDING_FIXTURE_ENDPOINT", values)
            self.assertNotIn("CONTENT_EMBEDDING_FIXTURE_API_KEY", values)
            self.assertNotIn("PRODUCT_OPS_ELASTICSEARCH_ENDPOINT", values)

    def test_prod_credentials_are_never_materialized(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "only for Alpha/Beta/Gamma substitute environments",
        ):
            prepare_local_provider_credentials(
                environment="prod",
                target_name="prod-local",
            )


if __name__ == "__main__":
    unittest.main()
