from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import local_environment_auth


class _Response:
    def __init__(self, status: int, payload: dict[str, object]) -> None:
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class LocalEnvironmentAuthBearerBoundarySecurityLocalContractTest(unittest.TestCase):
    def test_acceptance_session_uses_standard_issuer_and_keeps_bearer_out_of_repr(self) -> None:
        token = "local-test-bearer"
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "accessToken": token,
                    "ownerId": "fixture_user_current",
                    "personaId": "fixture_user_current",
                }
            ),
            stderr="",
        )
        auth = local_environment_auth.LocalEnvironmentAuth(
            environment={"AUTH_JWT_SECRET": "test-secret"},
            secret_path=Path("/tmp/auth.env"),
        )
        with (
            mock.patch.object(
                local_environment_auth,
                "_load_acceptance_principal",
                return_value=("fixture_user_current", "fixture_user_current"),
            ),
            mock.patch.object(local_environment_auth, "prepare_local_environment_auth", return_value=auth),
            mock.patch.object(local_environment_auth.subprocess, "run", return_value=completed) as run,
        ):
            session = local_environment_auth.open_local_acceptance_session(
                "https://gamma-api.quwoquan-env.test:19000",
                environment="gamma",
                target_name="gamma-local",
            )

        self.assertNotIn(token, repr(session))
        self.assertEqual(session.owner_id, "fixture_user_current")
        self.assertEqual(session.persona_id, "fixture_user_current")
        command = run.call_args.args[0]
        self.assertEqual(command, ["go", "run", "./services/user-service/cmd/acceptance-session"])
        self.assertNotIn(token, " ".join(command))
        self.assertEqual(run.call_args.kwargs["env"]["QWQ_LOCAL_ACCEPTANCE_TARGET"], "gamma-local")

    def test_authenticated_request_has_only_bearer_identity(self) -> None:
        session = local_environment_auth.LocalAcceptanceSession(
            owner_id="uo_local_gamma",
            persona_id="usp_local_gamma",
            access_token="local-test-bearer",
        )
        response = _Response(200, {"items": []})
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(
            local_environment_auth.request,
            "build_opener",
            return_value=opener,
        ):
            payload = local_environment_auth.request_local_environment_json(
                "https://gamma-api.quwoquan-env.test:19000",
                path="/content/feed?type=premium&limit=5",
                session=session,
            )

        request_obj = opener.open.call_args.args[0]
        self.assertEqual(payload, {"items": []})
        self.assertEqual(request_obj.get_header("Authorization"), "Bearer local-test-bearer")
        self.assertIsNone(request_obj.get_header("X-client-user-id"))
        self.assertIsNone(request_obj.get_header("X-test-auth-token"))

    def test_operation_path_with_colon_preserves_base_host(self) -> None:
        session = local_environment_auth.LocalAcceptanceSession(
            owner_id="data-release-operator",
            persona_id="data-release-operator",
            access_token="local-test-bearer",
        )
        response = _Response(200, {"homepagesAfter": 3})
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(
            local_environment_auth.request,
            "build_opener",
            return_value=opener,
        ):
            payload = local_environment_auth.request_local_environment_json(
                "http://127.0.0.1:18290",
                path="/homepages:reload",
                session=session,
                method="POST",
            )

        request_obj = opener.open.call_args.args[0]
        self.assertEqual(payload, {"homepagesAfter": 3})
        self.assertEqual(request_obj.full_url, "http://127.0.0.1:18290/homepages:reload")

    def test_beta_and_gamma_use_isolated_secret_roots_and_issuers(self) -> None:
        with mock.patch.object(
            local_environment_auth,
            "_load_or_create_secrets",
            return_value={
                "jwt_secret": "jwt",
                "device_ticket_secret": "device",
                "otp_code_ref_key_b64": "code-ref",
            },
        ):
            beta = local_environment_auth.prepare_local_environment_auth(
                "beta",
                "beta-local",
            )
            gamma = local_environment_auth.prepare_local_environment_auth(
                "gamma",
                "gamma-local",
            )

        self.assertNotEqual(beta.secret_path, gamma.secret_path)
        self.assertEqual(beta.environment["AUTH_JWT_ISSUER"], "quwoquan.beta.local")
        self.assertEqual(gamma.environment["AUTH_JWT_ISSUER"], "quwoquan.gamma.local")

    def test_rejects_cross_environment_target_pair(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported local environment target"):
            local_environment_auth.prepare_local_environment_auth("beta", "gamma-local")

    def test_run_scoped_subject_is_bound_to_both_actor_dimensions(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "accessToken": "local-test-bearer",
                    "ownerId": "premium-pool-seed-run-001",
                    "personaId": "premium-pool-seed-run-001",
                }
            ),
            stderr="",
        )
        auth = local_environment_auth.LocalEnvironmentAuth(
            environment={"AUTH_JWT_SECRET": "test-secret"},
            secret_path=Path("/tmp/auth.env"),
        )
        with (
            mock.patch.object(local_environment_auth, "prepare_local_environment_auth", return_value=auth),
            mock.patch.object(local_environment_auth.subprocess, "run", return_value=completed) as run,
        ):
            session = local_environment_auth.open_local_acceptance_session(
                "https://gamma-api.quwoquan-env.test:19000",
                environment="gamma",
                target_name="gamma-local",
                subject="premium-pool-seed-run-001",
            )

        self.assertEqual(session.owner_id, "premium-pool-seed-run-001")
        self.assertEqual(session.persona_id, "premium-pool-seed-run-001")
        process_env = run.call_args.kwargs["env"]
        self.assertEqual(
            process_env["QWQ_ACCEPTANCE_OWNER_ID"],
            "premium-pool-seed-run-001",
        )
        self.assertEqual(
            process_env["QWQ_ACCEPTANCE_PERSONA_ID"],
            "premium-pool-seed-run-001",
        )

    def test_run_scoped_subject_rejects_noncanonical_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "subject is invalid"):
            local_environment_auth.open_local_acceptance_session(
                "https://gamma-api.quwoquan-env.test:19000",
                environment="gamma",
                target_name="gamma-local",
                subject="../../shared-actor",
            )

    def test_non_loopback_transport_is_rejected_before_a_request(self) -> None:
        with self.assertRaisesRegex(ValueError, "loopback"):
            local_environment_auth.open_local_acceptance_session(
                "https://gamma-api.quwoquan-env.test:19000",
                environment="gamma",
                target_name="gamma-local",
                resolve_host="10.0.0.1",
            )

    def test_acceptance_session_rejects_invalid_issuer_response(self) -> None:
        auth = local_environment_auth.LocalEnvironmentAuth(
            environment={"AUTH_JWT_SECRET": "test-secret"},
            secret_path=Path("/tmp/auth.env"),
        )
        completed = mock.Mock(returncode=0, stdout="not-json", stderr="")
        with (
            mock.patch.object(
                local_environment_auth,
                "_load_acceptance_principal",
                return_value=("fixture_user_current", "fixture_user_current"),
            ),
            mock.patch.object(local_environment_auth, "prepare_local_environment_auth", return_value=auth),
            mock.patch.object(local_environment_auth.subprocess, "run", return_value=completed),
        ):
            with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
                local_environment_auth.open_local_acceptance_session(
                    "https://gamma-api.quwoquan-env.test:19000",
                    environment="gamma",
                    target_name="gamma-local",
                )


if __name__ == "__main__":
    unittest.main()
