from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from quwoquan_ops.cli.lib import local_environment_auth
from quwoquan_ops.cli.lib.local_environment_auth import (
    LocalAcceptanceActor,
    LocalAcceptanceSession,
)


def _actor() -> LocalAcceptanceActor:
    return LocalAcceptanceActor(
        role="primary",
        session=LocalAcceptanceSession(
            owner_id="owner-1",
            persona_id="persona-1",
            access_token="access-secret",
            refresh_token="refresh-secret",
        ),
        challenge_id="challenge-1",
        account_state="active",
        identity_origin="phone",
    )


class LocalEnvironmentTestDataAuthContractTest(unittest.TestCase):
    def test_identity_set_is_target_scoped_mode_0600_and_grows_deterministically(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            secret_root = Path(directory) / "gamma-local" / "secrets"
            path = secret_root / "test-data-identity-set.json"
            with mock.patch.object(
                local_environment_auth,
                "_test_data_identity_set_path",
                return_value=(secret_root, path),
            ):
                first = local_environment_auth.materialize_test_data_identity_set(
                    environment="gamma",
                    target_name="gamma-local",
                    identity_set_id="typed-instance-a",
                    actor_count=1,
                )
                second = local_environment_auth.materialize_test_data_identity_set(
                    environment="gamma",
                    target_name="gamma-local",
                    identity_set_id="typed-instance-a",
                    actor_count=2,
                )

            self.assertEqual(first, second)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "qwq.test_data_identity_set.v1")
            self.assertEqual(payload["target"], "gamma-local")
            phones = payload["identitySetPhones"]["typed-instance-a"]
            self.assertEqual(len(phones), 2)
            self.assertEqual(len(phones), len(set(phones)))
            self.assertNotIn("datasetEpoch", payload)
            self.assertNotIn("accessToken", path.read_text(encoding="utf-8"))
            self.assertNotIn("refreshToken", path.read_text(encoding="utf-8"))

    def test_typed_session_derives_an_instance_bound_identity_set(self) -> None:
        actor = _actor()
        with (
            mock.patch.object(
                local_environment_auth,
                "materialize_test_data_identity_set",
            ) as materialize,
            mock.patch.object(
                local_environment_auth,
                "open_local_phone_acceptance_session",
                return_value=actor,
            ) as open_phone,
        ):
            actual = local_environment_auth.open_test_data_acceptance_session(
                "https://api.gamma.quwoquan.com",
                environment="gamma",
                target_name="gamma-local",
                test_data_instance_id="case-run-123",
                actor_role="primary",
                actor_index=0,
            )

        identity_scope = hashlib.sha256(b"case-run-123").hexdigest()
        identity_set_id = "typed-" + identity_scope[:40]
        self.assertIs(actual, actor)
        materialize.assert_called_once_with(
            environment="gamma",
            target_name="gamma-local",
            identity_set_id=identity_set_id,
            actor_count=1,
        )
        open_phone.assert_called_once_with(
            "https://api.gamma.quwoquan.com",
            environment="gamma",
            target_name="gamma-local",
            test_data_instance_id=identity_scope,
            identity_set_id=identity_set_id,
            actor_role="primary",
            actor_index=0,
            timeout_seconds=30.0,
        )

    def test_new_case_instance_cannot_reuse_an_identity_set(self) -> None:
        observed: list[str] = []

        def record(**kwargs: object) -> None:
            observed.append(str(kwargs["identity_set_id"]))

        with (
            mock.patch.object(
                local_environment_auth,
                "materialize_test_data_identity_set",
                side_effect=record,
            ),
            mock.patch.object(
                local_environment_auth,
                "open_local_phone_acceptance_session",
                return_value=_actor(),
            ),
        ):
            for instance_id in ("case-result-a", "case-result-b"):
                local_environment_auth.open_test_data_acceptance_session(
                    "https://api.gamma.quwoquan.com",
                    environment="gamma",
                    target_name="gamma-local",
                    test_data_instance_id=instance_id,
                    actor_role="primary",
                    actor_index=0,
                )

        self.assertEqual(len(observed), 2)
        self.assertNotEqual(observed[0], observed[1])

    def test_actor_auth_uses_instance_bound_deterministic_otp_idempotency(self) -> None:
        instance_scope = hashlib.sha256(b"case-run-123").hexdigest()
        responses = [
            {"challengeId": "challenge-1"},
            {
                "ownerId": "owner-1",
                "activePersona": {"personaId": "persona-1"},
                "accessToken": "access-1",
                "refreshToken": "refresh-1",
                "accountState": "active",
                "identityOrigin": "phone",
            },
        ] * 2
        with (
            mock.patch.object(
                local_environment_auth,
                "_test_data_actor_phone",
                return_value="+999300000001000",
            ),
            mock.patch.object(local_environment_auth, "_clear_local_otp_send_throttle"),
            mock.patch.object(
                local_environment_auth,
                "request_local_environment_public_json",
                side_effect=responses,
            ) as public_request,
            mock.patch.object(
                local_environment_auth,
                "request_local_environment_json",
                return_value={"ownerId": "owner-1"},
            ),
            mock.patch(
                "quwoquan_ops.cli.lib.local_sms_provider_debug.read_latest_debug_otp",
                return_value=SimpleNamespace(code="123456"),
            ),
        ):
            for _ in range(2):
                local_environment_auth.open_local_phone_acceptance_session(
                    "https://api.gamma.quwoquan.com",
                    environment="gamma",
                    target_name="gamma-local",
                    test_data_instance_id=instance_scope,
                    identity_set_id="typed-instance",
                    actor_role="primary",
                    actor_index=0,
                )

        send_calls = public_request.call_args_list[::2]
        idempotency_keys = [
            call.kwargs["headers"]["Idempotency-Key"] for call in send_calls
        ]
        self.assertEqual(len(set(idempotency_keys)), 1)
        expected = hashlib.sha256(
            (
                f"gamma-local/{instance_scope}/"
                "user.acceptance.authenticated_actors/primary/"
                "user.authentication_challenge.SendOtp/send-otp-000"
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(idempotency_keys, [expected, expected])

    def test_research_identity_login_uses_the_pre_runtime_subject_and_owner(self) -> None:
        instance_scope = hashlib.sha256(b"research-runtime-proof").hexdigest()
        responses = [
            {"challengeId": "challenge-research"},
            {
                "ownerId": "owner-research",
                "activePersona": {"personaId": "persona-research"},
                "accessToken": "access-research",
                "refreshToken": "refresh-research",
                "accountState": "active",
                "identityOrigin": "phone",
            },
        ]
        with (
            mock.patch.object(
                local_environment_auth,
                "load_local_research_identity_binding",
                return_value={
                    "phone": "+999300000001999",
                    "accountId": "owner-research",
                },
            ),
            mock.patch.object(local_environment_auth, "_clear_local_otp_send_throttle"),
            mock.patch.object(
                local_environment_auth,
                "request_local_environment_public_json",
                side_effect=responses,
            ) as public_request,
            mock.patch.object(
                local_environment_auth,
                "request_local_environment_json",
                return_value={"ownerId": "owner-research"},
            ),
            mock.patch(
                "quwoquan_ops.cli.lib.local_sms_provider_debug.read_latest_debug_otp",
                return_value=SimpleNamespace(code="123456"),
            ),
        ):
            actor = local_environment_auth.open_local_phone_acceptance_session(
                "https://api.alpha.quwoquan.com",
                environment="alpha",
                target_name="alpha-local",
                test_data_instance_id=instance_scope,
                identity_set_id="research-identity",
                actor_role="primary",
                actor_index=0,
            )

        self.assertEqual(actor.session.owner_id, "owner-research")
        self.assertEqual(
            public_request.call_args_list[0].kwargs["body"]["phone"],
            "+999300000001999",
        )

    def test_research_identity_login_rejects_owner_readback_drift(self) -> None:
        instance_scope = hashlib.sha256(b"research-runtime-proof").hexdigest()
        with (
            mock.patch.object(
                local_environment_auth,
                "load_local_research_identity_binding",
                return_value={
                    "phone": "+999300000001999",
                    "accountId": "expected-owner",
                },
            ),
            mock.patch.object(local_environment_auth, "_clear_local_otp_send_throttle"),
            mock.patch.object(
                local_environment_auth,
                "request_local_environment_public_json",
                side_effect=[
                    {"challengeId": "challenge-research"},
                    {
                        "ownerId": "other-owner",
                        "activePersona": {"personaId": "persona-research"},
                        "accessToken": "access-research",
                        "refreshToken": "refresh-research",
                    },
                ],
            ),
            mock.patch(
                "quwoquan_ops.cli.lib.local_sms_provider_debug.read_latest_debug_otp",
                return_value=SimpleNamespace(code="123456"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "managed acceptance identity"):
                local_environment_auth.open_local_phone_acceptance_session(
                    "https://api.alpha.quwoquan.com",
                    environment="alpha",
                    target_name="alpha-local",
                    test_data_instance_id=instance_scope,
                    identity_set_id="research-identity",
                    actor_role="primary",
                    actor_index=0,
                )

    def test_prod_is_rejected_before_identity_materialization(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden for Prod"):
            local_environment_auth.materialize_test_data_identity_set(
                environment="prod",
                target_name="prod-sim",
                identity_set_id="typed-prod",
                actor_count=1,
            )

    def test_runtime_preflight_cleanup_uses_public_close_account_operation(
        self,
    ) -> None:
        with mock.patch.object(
            local_environment_auth,
            "request_local_environment_json",
            return_value={"status": "closed"},
        ) as request:
            local_environment_auth.close_test_data_acceptance_actor(
                "https://api.gamma.quwoquan.com",
                actor=_actor(),
                test_data_instance_id="case-run-123",
            )

        kwargs = request.call_args.kwargs
        self.assertEqual(kwargs["session"].owner_id, "owner-1")
        self.assertEqual(kwargs["body"].keys(), {"clientRequestId"})
        self.assertEqual(
            kwargs["headers"],
            {"Idempotency-Key": kwargs["body"]["clientRequestId"]},
        )
        self.assertNotIn("access-secret", json.dumps(kwargs["body"]))
        self.assertNotIn("refresh-secret", json.dumps(kwargs["body"]))


if __name__ == "__main__":
    unittest.main()
