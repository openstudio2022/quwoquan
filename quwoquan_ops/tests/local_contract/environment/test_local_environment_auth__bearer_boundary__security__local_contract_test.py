"""Non-production auth must use public OTP and canonical accounts.

spec_ref: specs/feature-tree/spec.md#uat-009
"""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import local_environment_auth


class LocalEnvironmentAuthBoundaryTest(unittest.TestCase):
    def test_http_error_survives_generator_context_without_frozen_masking(
        self,
    ) -> None:
        @contextmanager
        def scope():
            yield

        error = local_environment_auth.LocalEnvironmentHTTPError(
            method="POST",
            path="/chat/conversations",
            status=403,
        )
        with self.assertRaises(
            local_environment_auth.LocalEnvironmentHTTPError
        ) as raised:
            with scope():
                raise error

        self.assertIs(raised.exception, error)
        self.assertEqual(raised.exception.status, 403)
        self.assertNotIn("token", str(raised.exception).lower())

    def test_direct_acceptance_token_issuer_is_retired(self) -> None:
        self.assertFalse(
            hasattr(local_environment_auth, "open_local_acceptance_session")
        )
        root = Path(__file__).resolve().parents[4]
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
                side_effect=lambda root, target, *parts: (
                    Path(root) / target / Path(*parts)
                ),
            ):
                auth = local_environment_auth.prepare_local_environment_auth(
                    "alpha",
                    "alpha-local",
                    deployment_work_root=work_root,
                )
            self.assertNotIn("ACCESS_TOKEN", auth.environment)
            self.assertNotIn("QWQ_ACCEPTANCE_OWNER_ID", auth.environment)
            self.assertEqual(auth.secret_path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(any("RESEARCH_IDENTITY" in key for key in auth.environment))
            self.assertNotIn("USER_MANAGED_ACCEPTANCE_IDENTITY_JSON", auth.environment)
            self.assertEqual(auth.environment["AUTH_JWT_ISSUER"], "quwoquan.alpha.local")
            keys = json.loads(auth.environment["OTP_CODE_REF_KEYS_JSON"])
            active_key = auth.environment["OTP_CODE_REF_ACTIVE_KEY_VERSION"]
            self.assertEqual(len(base64.b64decode(keys[active_key], validate=True)), 32)
            self.assertFalse((work_root / "alpha-local/secrets/research-identity-binding.json").exists())

    def test_research_issuers_are_retired_and_auth_remains_target_isolated(self) -> None:
        for name in ("materialize_local_research_identity_binding", "load_local_research_identity_binding"):
            self.assertFalse(hasattr(local_environment_auth, name))
        with tempfile.TemporaryDirectory() as directory:
            work_root = Path(directory)
            first = local_environment_auth.prepare_local_environment_auth(
                "alpha", "alpha-local", deployment_work_root=work_root,
            )
            repeated = local_environment_auth.load_local_environment_auth(
                "alpha", "alpha-local", deployment_work_root=work_root,
            )
            other = local_environment_auth.prepare_local_environment_auth(
                "beta", "beta-local", deployment_work_root=work_root,
            )
            self.assertEqual(first.environment, repeated.environment)
            self.assertNotEqual(first.environment["AUTH_JWT_SECRET"], other.environment["AUTH_JWT_SECRET"])
            first.secret_path.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, "must use mode 0600"):
                local_environment_auth.load_local_environment_auth(
                    "alpha", "alpha-local", deployment_work_root=work_root,
                )
    def test_read_only_loader_never_creates_missing_auth_material(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret_path = Path(directory) / "alpha-local/secrets/auth.env"
            with mock.patch.object(
                local_environment_auth,
                "deployment_target_path_in_work_root",
                return_value=secret_path,
            ):
                with self.assertRaisesRegex(RuntimeError, "GATE_BLOCK"):
                    local_environment_auth.load_local_environment_auth(
                        "alpha",
                        "alpha-local",
                        deployment_work_root=directory,
                    )
            self.assertFalse(secret_path.exists())

    def test_prod_auth_does_not_materialize_or_expose_research_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work_root = Path(directory)
            with mock.patch.object(
                local_environment_auth,
                "deployment_target_path_in_work_root",
                side_effect=lambda root, target, *parts: (
                    Path(root) / target / Path(*parts)
                ),
            ):
                auth = local_environment_auth.prepare_local_environment_auth(
                    "prod",
                    "prod-sim",
                    deployment_work_root=work_root,
                )
            self.assertNotIn(
                "USER_RESEARCH_IDENTITY_ACCOUNT_ID_ALLOWLIST_JSON",
                auth.environment,
            )
            self.assertNotIn(
                "USER_MANAGED_ACCEPTANCE_IDENTITY_JSON",
                auth.environment,
            )
            self.assertFalse(
                (work_root / "prod-sim/secrets/research-identity-binding.json").exists()
            )


if __name__ == "__main__":
    unittest.main()
