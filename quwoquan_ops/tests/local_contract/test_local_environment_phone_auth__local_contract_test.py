"""Canonical nonprod phone authentication contract.

spec_ref: specs/feature-tree/spec.md#uat-009
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import local_environment_auth


class LocalEnvironmentPhoneAuthContractTest(unittest.TestCase):
    def test_phone_actor_uses_public_otp_login_and_me(self) -> None:
        responses = [
            {"challengeId": "challenge-1"},
            {
                "ownerId": "owner-1",
                "activePersona": {"personaId": "persona-1"},
                "accessToken": "secret-token",
                "accountState": "active",
                "identityOrigin": "phone",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            secret_root = Path(directory) / "alpha-local/secrets"
            secret_root.mkdir(parents=True)
            pool = secret_root / "identity-pool.json"
            pool.write_text(
                json.dumps(
                    {
                        "schema": "qwq.nonprod_acceptance_identity_pool",
                        "target": "alpha-local",
                        "datasetPhones": {
                            "nonprod_reference_identity": ["+8613800000001"]
                        },
                    }
                ),
                encoding="utf-8",
            )
            pool.chmod(0o600)
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "QWQ_NONPROD_ACCEPTANCE_IDENTITY_POOL": str(pool),
                        "QWQ_NONPROD_ACCEPTANCE_OTP_CODE": "654321",
                    },
                    clear=False,
                ),
                mock.patch.object(
                    local_environment_auth,
                    "deployment_target_path",
                    return_value=secret_root,
                ),
                mock.patch.object(
                    local_environment_auth,
                    "request_local_environment_public_json",
                    side_effect=responses,
                ) as public_request,
                mock.patch.object(
                    local_environment_auth,
                    "request_local_environment_json",
                    return_value={"ownerId": "owner-1"},
                ) as authenticated_request,
            ):
                actor = local_environment_auth.open_local_phone_acceptance_session(
                    "https://api.alpha.quwoquan.local:17000",
                    environment="alpha",
                    target_name="alpha-local",
                    dataset_epoch="a" * 64,
                    dataset_id="nonprod_reference_identity",
                    actor_role="primary",
                    actor_index=0,
                )

        self.assertEqual(actor.session.owner_id, "owner-1")
        self.assertEqual(actor.session.persona_id, "persona-1")
        self.assertEqual(actor.challenge_id, "challenge-1")
        self.assertEqual(public_request.call_count, 2)
        otp_body = public_request.call_args_list[0].kwargs["body"]
        login_body = public_request.call_args_list[1].kwargs["body"]
        self.assertEqual(otp_body["sourceOperation"], "NonprodAcceptanceProvision")
        self.assertEqual(login_body["otpCode"], "654321")
        self.assertEqual(login_body["agreementVersion"], "2026-06")
        self.assertNotIn(otp_body["phone"], repr(actor))
        self.assertNotIn("secret-token", repr(actor))
        authenticated_request.assert_called_once()

    def test_prod_is_fail_closed_before_transport(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden for Prod"):
            local_environment_auth.open_local_phone_acceptance_session(
                "https://api.quwoquan.com",
                environment="prod",
                target_name="prod-sim",
                dataset_epoch="b" * 64,
                dataset_id="nonprod_reference_identity",
                actor_role="primary",
                actor_index=0,
            )

    def test_public_request_rejects_identity_headers(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot inject identity"):
            local_environment_auth.request_local_environment_public_json(
                "https://api.alpha.quwoquan.local:17000",
                path="/auth/otp/send",
                headers={"X-Client-User-Id": "forged"},
            )


if __name__ == "__main__":
    unittest.main()
