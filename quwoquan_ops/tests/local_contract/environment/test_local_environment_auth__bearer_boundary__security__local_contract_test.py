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
            user_key = auth.environment[
                "USER_RESEARCH_IDENTITY_ATTESTATION_KEY_BASE64"
            ]
            self.assertEqual(
                user_key,
                auth.environment[
                    "CONTENT_RESEARCH_IDENTITY_ATTESTATION_KEY_BASE64"
                ],
            )
            self.assertEqual(len(base64.b64decode(user_key, validate=True)), 32)
            allowlist = json.loads(
                auth.environment[
                    "USER_RESEARCH_IDENTITY_ACCOUNT_ID_ALLOWLIST_JSON"
                ]
            )
            managed = json.loads(
                auth.environment["USER_MANAGED_ACCEPTANCE_IDENTITY_JSON"]
            )
            self.assertEqual(allowlist, [managed["accountId"]])
            self.assertTrue(managed["accountId"].startswith("uo_01_ph_"))
            binding = work_root / "alpha-local/secrets/research-identity-binding.json"
            self.assertEqual(binding.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("accessToken", managed)
            self.assertNotIn("refreshToken", managed)

    def test_research_identity_binding_is_target_deterministic_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work_root = Path(directory)
            first = local_environment_auth.materialize_local_research_identity_binding(
                environment="alpha",
                target_name="alpha-local",
                deployment_work_root=work_root,
            )
            second = local_environment_auth.materialize_local_research_identity_binding(
                environment="alpha",
                target_name="alpha-local",
                deployment_work_root=work_root,
            )
            self.assertEqual(first, second)
            self.assertEqual(
                first["accountId"],
                local_environment_auth._deterministic_phone_owner_id(
                    "alpha-local", first["phone"]
                ),
            )
            path = work_root / "alpha-local/secrets/research-identity-binding.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["accountId"] = "uo_01_ph_0000_00000000000000000000000000"
            path.write_text(json.dumps(payload), encoding="utf-8")
            path.chmod(0o600)
            with self.assertRaisesRegex(RuntimeError, "GATE_BLOCK"):
                local_environment_auth.load_local_research_identity_binding(
                    environment="alpha",
                    target_name="alpha-local",
                    deployment_work_root=work_root,
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
