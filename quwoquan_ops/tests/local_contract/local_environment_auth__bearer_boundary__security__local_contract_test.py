"""Non-production auth must use public OTP and canonical accounts.

spec_ref: specs/feature-tree/spec.md#uat-009
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import local_environment_auth


class LocalEnvironmentAuthBoundaryTest(unittest.TestCase):
    def test_direct_acceptance_token_issuer_is_retired(self) -> None:
        self.assertFalse(
            hasattr(local_environment_auth, "open_local_acceptance_session")
        )
        root = Path(__file__).resolve().parents[3]
        self.assertFalse(
            (
                root
                / "quwoquan_service/services/user-service/cmd/acceptance-session/main.go"
            ).exists()
        )

    def test_runtime_auth_material_stays_in_external_target_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work_root = Path(directory)
            with mock.patch.object(
                local_environment_auth,
                "deployment_target_path_in_work_root",
                return_value=work_root / "alpha-local/secrets/auth.env",
            ):
                auth = local_environment_auth.prepare_local_environment_auth(
                    "alpha",
                    "alpha-local",
                    deployment_work_root=work_root,
                )
            self.assertNotIn("ACCESS_TOKEN", auth.environment)
            self.assertNotIn("QWQ_ACCEPTANCE_OWNER_ID", auth.environment)
            self.assertEqual(auth.secret_path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
