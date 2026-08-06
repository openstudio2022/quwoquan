"""Canonical nonprod phone authentication contract.

spec_ref: specs/feature-tree/spec.md#uat-009
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import local_environment_auth


def _test_auth(
    environment: str,
    *,
    secret: str | None = None,
    issuer: str | None = None,
    audience: str = "quwoquan-app",
) -> SimpleNamespace:
    return SimpleNamespace(
        environment={
            "AUTH_JWT_SECRET": secret or f"{environment}-jwt-secret",
            "AUTH_JWT_ISSUER": issuer or f"quwoquan.{environment}.local",
            "AUTH_JWT_AUDIENCE": audience,
            "AUTH_JWT_TOKEN_VERSION": "1",
        }
    )


def _test_access_token(
    *,
    environment: str = "gamma",
    target_name: str = "gamma-local",
    owner_id: str = "owner-token",
    persona_id: str = "persona-token",
    secret: str | None = None,
    issuer: str | None = None,
    audience: str = "quwoquan-app",
) -> str:
    with mock.patch.object(
        local_environment_auth,
        "prepare_local_environment_auth",
        return_value=_test_auth(
            environment,
            secret=secret,
            issuer=issuer,
            audience=audience,
        ),
    ):
        return local_environment_auth._mint_local_access_token(
            environment=environment,
            target_name=target_name,
            owner_id=owner_id,
            persona_id=persona_id,
        )


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
                mock.patch(
                    "quwoquan_ops.cli.lib.local_sms_provider_debug.read_latest_debug_otp",
                    return_value=SimpleNamespace(code="654321"),
                ) as capture_read,
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
        capture_read.assert_called_once_with(
            environment="alpha",
            target_name="alpha-local",
            recipient="+8613800000001",
            timeout_seconds=30.0,
        )
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

    def test_reference_session_reuses_cache_without_otp(self) -> None:
        epoch = "c" * 64
        baseline = "sha256:91e4ec0346e6856159480135150a31020240f414ef940064f3da96de718a39dd"
        package = "sha256:b7e8e5147c91f8a823198dfe83b3096677ff4c8ef5dd4f21e2d4634787f2bf29"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret_root = root / "gamma-local/secrets"
            secret_root.mkdir(parents=True)
            runs = root / "runs/nonprod-data" / epoch
            runs.mkdir(parents=True)
            (runs / "nonprod_reference_identity.json").write_text(
                json.dumps(
                    {
                        "schema": "qwq.nonprod_acceptance_dataset_receipt",
                        "target": "gamma-local",
                        "baselineId": baseline,
                        "packageDigest": package,
                        "datasetId": "nonprod_reference_identity",
                        "datasetEpoch": epoch,
                        "status": "passed",
                        "cleanupState": "retained",
                        "expiresAt": "2099-01-01T00:00:00+00:00",
                        "actorReceiptRefs": [
                            {
                                "role": "primary",
                                "ownerId": "owner-cache",
                                "accountState": "active",
                                "identityOrigin": "phone",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            cache = secret_root / "nonprod-reference-session.cache.json"
            cached_token = _test_access_token(
                owner_id="owner-cache",
                persona_id="persona-cache",
            )
            cache.write_text(
                json.dumps(
                    {
                        "schema": "qwq.nonprod_reference_session_cache",
                        "target": "gamma-local",
                        "baselineId": baseline,
                        "packageDigest": package,
                        "datasetEpoch": epoch,
                        "actorIndex": 0,
                        "ownerId": "owner-cache",
                        "personaId": "persona-cache",
                        "accessToken": cached_token,
                        "expiresAt": "2099-01-01T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            cache.chmod(0o600)
            candidate_dir = root / "candidate"
            candidate_dir.mkdir()
            (candidate_dir / "manifest.json").write_text(
                json.dumps(
                    {"baselineId": baseline, "packageDigest": package},
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    local_environment_auth,
                    "active_deployment_candidate",
                    return_value={
                        "baselineId": baseline,
                        "candidateDir": str(candidate_dir),
                    },
                ),
                mock.patch.object(
                    local_environment_auth,
                    "env_runs_root",
                    return_value=root / "runs",
                ),
                mock.patch.object(
                    local_environment_auth,
                    "deployment_target_path",
                    return_value=secret_root,
                ),
                mock.patch.object(
                    local_environment_auth,
                    "prepare_local_environment_auth",
                    return_value=_test_auth("gamma"),
                ),
                mock.patch.object(
                    local_environment_auth,
                    "request_local_environment_json",
                    return_value={"ownerId": "owner-cache"},
                ) as me_request,
                mock.patch.object(
                    local_environment_auth,
                    "open_local_phone_acceptance_session",
                    side_effect=AssertionError("cache hit must not resend OTP"),
                ),
            ):
                session = local_environment_auth.open_reference_acceptance_session(
                    "https://api.gamma.quwoquan.com:19000",
                    environment="gamma",
                    target_name="gamma-local",
                )

        self.assertEqual(session.owner_id, "owner-cache")
        self.assertEqual(session.persona_id, "persona-cache")
        self.assertEqual(session.access_token, cached_token)
        me_request.assert_called_once()

    def test_cached_reference_session_rejects_jwt_identity_and_environment_drift(
        self,
    ) -> None:
        baseline = "sha256:" + "1" * 64
        package = "sha256:" + "2" * 64
        epoch = "3" * 64
        expected_owner = "owner-token"
        expected_persona = "persona-token"
        invalid_tokens = {
            "owner": _test_access_token(
                owner_id="other-owner",
                persona_id=expected_persona,
            ),
            "persona": _test_access_token(
                owner_id=expected_owner,
                persona_id="other-persona",
            ),
            "environment": _test_access_token(
                environment="beta",
                target_name="beta-local",
                owner_id=expected_owner,
                persona_id=expected_persona,
            ),
            "audience": _test_access_token(
                owner_id=expected_owner,
                persona_id=expected_persona,
                audience="other-audience",
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            secret_root = Path(directory) / "gamma-local/secrets"
            secret_root.mkdir(parents=True)
            cache = secret_root / "nonprod-reference-session.cache.json"
            for mismatch, token in invalid_tokens.items():
                with self.subTest(mismatch=mismatch):
                    cache.write_text(
                        json.dumps(
                            {
                                "schema": "qwq.nonprod_reference_session_cache",
                                "target": "gamma-local",
                                "baselineId": baseline,
                                "packageDigest": package,
                                "datasetEpoch": epoch,
                                "actorIndex": 0,
                                "ownerId": expected_owner,
                                "personaId": expected_persona,
                                "accessToken": token,
                                "expiresAt": "2099-01-01T00:00:00+00:00",
                            }
                        ),
                        encoding="utf-8",
                    )
                    cache.chmod(0o600)
                    with (
                        mock.patch.object(
                            local_environment_auth,
                            "deployment_target_path",
                            return_value=secret_root,
                        ),
                        mock.patch.object(
                            local_environment_auth,
                            "prepare_local_environment_auth",
                            return_value=_test_auth("gamma"),
                        ),
                        mock.patch.object(
                            local_environment_auth,
                            "request_local_environment_json",
                            side_effect=AssertionError(
                                "mismatched JWT must fail before /me"
                            ),
                        ),
                    ):
                        session = (
                            local_environment_auth._try_cached_reference_session(
                                "https://api.gamma.quwoquan.com:19000",
                                environment="gamma",
                                target_name="gamma-local",
                                baseline_id=baseline,
                                package_digest=package,
                                dataset_epoch=epoch,
                                actor_index=0,
                                owner_id=expected_owner,
                                timeout_seconds=1.0,
                            )
                        )

                    self.assertIsNone(session)
                    self.assertFalse(cache.exists())

    def test_retained_session_rejects_minted_jwt_identity_and_environment_drift(
        self,
    ) -> None:
        expected_owner = "owner-retained"
        expected_persona = "persona-retained"
        invalid_tokens = {
            "owner": _test_access_token(
                owner_id="other-owner",
                persona_id=expected_persona,
            ),
            "persona": _test_access_token(
                owner_id=expected_owner,
                persona_id="other-persona",
            ),
            "environment": _test_access_token(
                environment="beta",
                target_name="beta-local",
                owner_id=expected_owner,
                persona_id=expected_persona,
            ),
            "audience": _test_access_token(
                owner_id=expected_owner,
                persona_id=expected_persona,
                audience="other-audience",
            ),
        }
        for mismatch, token in invalid_tokens.items():
            with self.subTest(mismatch=mismatch):
                with (
                    mock.patch.object(
                        local_environment_auth,
                        "_mint_local_access_token",
                        return_value=token,
                    ),
                    mock.patch.object(
                        local_environment_auth,
                        "prepare_local_environment_auth",
                        return_value=_test_auth("gamma"),
                    ),
                    mock.patch.object(
                        local_environment_auth,
                        "request_local_environment_json",
                        side_effect=AssertionError(
                            "mismatched minted JWT must fail before /me"
                        ),
                    ),
                ):
                    session = (
                        local_environment_auth._restore_retained_reference_session(
                            "https://api.gamma.quwoquan.com:19000",
                            environment="gamma",
                            target_name="gamma-local",
                            owner_id=expected_owner,
                            persona_id=expected_persona,
                            timeout_seconds=1.0,
                        )
                    )

                self.assertIsNone(session)

    def test_reference_session_rechecks_cache_under_lock_without_otp(self) -> None:
        epoch = "d" * 64
        baseline = "sha256:91e4ec0346e6856159480135150a31020240f414ef940064f3da96de718a39dd"
        package = "sha256:b7e8e5147c91f8a823198dfe83b3096677ff4c8ef5dd4f21e2d4634787f2bf29"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret_root = root / "gamma-local/secrets"
            secret_root.mkdir(parents=True)
            runs = root / "runs/nonprod-data" / epoch
            runs.mkdir(parents=True)
            (runs / "nonprod_reference_identity.json").write_text(
                json.dumps(
                    {
                        "schema": "qwq.nonprod_acceptance_dataset_receipt",
                        "target": "gamma-local",
                        "baselineId": baseline,
                        "packageDigest": package,
                        "datasetId": "nonprod_reference_identity",
                        "datasetEpoch": epoch,
                        "status": "passed",
                        "cleanupState": "retained",
                        "expiresAt": "2099-01-01T00:00:00+00:00",
                        "actorReceiptRefs": [
                            {
                                "role": "primary",
                                "ownerId": "owner-lock",
                                "accountState": "active",
                                "identityOrigin": "phone",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            candidate_dir = root / "candidate"
            candidate_dir.mkdir()
            (candidate_dir / "manifest.json").write_text(
                json.dumps(
                    {"baselineId": baseline, "packageDigest": package},
                ),
                encoding="utf-8",
            )
            peer_session = local_environment_auth.LocalAcceptanceSession(
                owner_id="owner-lock",
                persona_id="persona-lock",
                access_token="peer-token",
            )
            with (
                mock.patch.object(
                    local_environment_auth,
                    "active_deployment_candidate",
                    return_value={
                        "baselineId": baseline,
                        "candidateDir": str(candidate_dir),
                    },
                ),
                mock.patch.object(
                    local_environment_auth,
                    "env_runs_root",
                    return_value=root / "runs",
                ),
                mock.patch.object(
                    local_environment_auth,
                    "deployment_target_path",
                    return_value=secret_root,
                ),
                mock.patch.object(
                    local_environment_auth,
                    "_try_cached_reference_session",
                    side_effect=[None, peer_session],
                ),
                mock.patch.object(
                    local_environment_auth,
                    "_clear_local_otp_send_throttle",
                    side_effect=AssertionError("peer cache hit must not clear OTP"),
                ),
                mock.patch.object(
                    local_environment_auth,
                    "open_local_phone_acceptance_session",
                    side_effect=AssertionError("peer cache hit must not resend OTP"),
                ),
            ):
                session = local_environment_auth.open_reference_acceptance_session(
                    "https://api.gamma.quwoquan.com:19000",
                    environment="gamma",
                    target_name="gamma-local",
                )

        self.assertEqual(session.access_token, "peer-token")

    def test_retained_receipt_clears_otp_throttle_before_single_provision(
        self,
    ) -> None:
        epoch = "e" * 64
        baseline = "sha256:91e4ec0346e6856159480135150a31020240f414ef940064f3da96de718a39dd"
        package = "sha256:b7e8e5147c91f8a823198dfe83b3096677ff4c8ef5dd4f21e2d4634787f2bf29"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret_root = root / "gamma-local/secrets"
            secret_root.mkdir(parents=True)
            runs = root / "runs/nonprod-data" / epoch
            runs.mkdir(parents=True)
            (runs / "nonprod_reference_identity.json").write_text(
                json.dumps(
                    {
                        "schema": "qwq.nonprod_acceptance_dataset_receipt",
                        "target": "gamma-local",
                        "baselineId": baseline,
                        "packageDigest": package,
                        "datasetId": "nonprod_reference_identity",
                        "datasetEpoch": epoch,
                        "status": "passed",
                        "cleanupState": "retained",
                        "expiresAt": "2099-01-01T00:00:00+00:00",
                        "actorReceiptRefs": [
                            {
                                "role": "primary",
                                "ownerId": "owner-provision",
                                "accountState": "active",
                                "identityOrigin": "phone",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            candidate_dir = root / "candidate"
            candidate_dir.mkdir()
            (candidate_dir / "manifest.json").write_text(
                json.dumps(
                    {"baselineId": baseline, "packageDigest": package},
                ),
                encoding="utf-8",
            )
            actor = local_environment_auth.LocalAcceptanceActor(
                role="primary",
                session=local_environment_auth.LocalAcceptanceSession(
                    owner_id="owner-provision",
                    persona_id="persona-provision",
                    access_token="fresh-token",
                ),
                challenge_id="challenge-provision",
                account_state="active",
                identity_origin="phone",
            )
            with (
                mock.patch.object(
                    local_environment_auth,
                    "active_deployment_candidate",
                    return_value={
                        "baselineId": baseline,
                        "candidateDir": str(candidate_dir),
                    },
                ),
                mock.patch.object(
                    local_environment_auth,
                    "env_runs_root",
                    return_value=root / "runs",
                ),
                mock.patch.object(
                    local_environment_auth,
                    "deployment_target_path",
                    return_value=secret_root,
                ),
                mock.patch.object(
                    local_environment_auth,
                    "_try_cached_reference_session",
                    return_value=None,
                ),
                mock.patch.object(
                    local_environment_auth,
                    "_restore_retained_reference_session",
                    return_value=None,
                ),
                mock.patch.object(
                    local_environment_auth,
                    "_nonprod_acceptance_phone",
                    return_value="+8613900001001",
                ),
                mock.patch.object(
                    local_environment_auth,
                    "_clear_local_otp_send_throttle",
                ) as clear_throttle,
                mock.patch.object(
                    local_environment_auth,
                    "open_local_phone_acceptance_session",
                    return_value=actor,
                ) as open_phone,
            ):
                session = local_environment_auth.open_reference_acceptance_session(
                    "https://api.gamma.quwoquan.com:19000",
                    environment="gamma",
                    target_name="gamma-local",
                )
                self.assertEqual(session.access_token, "fresh-token")
                clear_throttle.assert_called_once_with(
                    target_name="gamma-local",
                    phone="+8613900001001",
                )
                open_phone.assert_called_once()
                cache = secret_root / "nonprod-reference-session.cache.json"
                self.assertTrue(cache.is_file())

    def test_retained_receipt_restores_session_without_otp(self) -> None:
        epoch = "f" * 64
        baseline = "sha256:91e4ec0346e6856159480135150a31020240f414ef940064f3da96de718a39dd"
        package = "sha256:b7e8e5147c91f8a823198dfe83b3096677ff4c8ef5dd4f21e2d4634787f2bf29"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secret_root = root / "gamma-local/secrets"
            secret_root.mkdir(parents=True)
            runs = root / "runs/nonprod-data" / epoch
            runs.mkdir(parents=True)
            (runs / "nonprod_reference_identity.json").write_text(
                json.dumps(
                    {
                        "schema": "qwq.nonprod_acceptance_dataset_receipt",
                        "target": "gamma-local",
                        "baselineId": baseline,
                        "packageDigest": package,
                        "datasetId": "nonprod_reference_identity",
                        "datasetEpoch": epoch,
                        "status": "passed",
                        "cleanupState": "retained",
                        "expiresAt": "2099-01-01T00:00:00+00:00",
                        "actorReceiptRefs": [
                            {
                                "role": "primary",
                                "ownerId": "owner-restore",
                                "personaIds": ["persona-restore"],
                                "accountState": "active",
                                "identityOrigin": "phone",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            candidate_dir = root / "candidate"
            candidate_dir.mkdir()
            (candidate_dir / "manifest.json").write_text(
                json.dumps(
                    {"baselineId": baseline, "packageDigest": package},
                ),
                encoding="utf-8",
            )
            restored = local_environment_auth.LocalAcceptanceSession(
                owner_id="owner-restore",
                persona_id="persona-restore",
                access_token="restored-token",
            )
            with (
                mock.patch.object(
                    local_environment_auth,
                    "active_deployment_candidate",
                    return_value={
                        "baselineId": baseline,
                        "candidateDir": str(candidate_dir),
                    },
                ),
                mock.patch.object(
                    local_environment_auth,
                    "env_runs_root",
                    return_value=root / "runs",
                ),
                mock.patch.object(
                    local_environment_auth,
                    "deployment_target_path",
                    return_value=secret_root,
                ),
                mock.patch.object(
                    local_environment_auth,
                    "_try_cached_reference_session",
                    return_value=None,
                ),
                mock.patch.object(
                    local_environment_auth,
                    "_restore_retained_reference_session",
                    return_value=restored,
                ) as restore,
                mock.patch.object(
                    local_environment_auth,
                    "open_local_phone_acceptance_session",
                    side_effect=AssertionError("retained restore must not resend OTP"),
                ),
            ):
                session = local_environment_auth.open_reference_acceptance_session(
                    "https://api.gamma.quwoquan.com:19000",
                    environment="gamma",
                    target_name="gamma-local",
                )
                self.assertEqual(session.access_token, "restored-token")
                restore.assert_called_once()
                self.assertTrue(
                    (secret_root / "nonprod-reference-session.cache.json").is_file()
                )

    def test_mint_local_access_token_reuses_auth_jwt_without_otp(self) -> None:
        auth = SimpleNamespace(
            environment={
                "AUTH_JWT_SECRET": "unit-test-auth-jwt-secret",
                "AUTH_JWT_ISSUER": "gamma-local-issuer",
                "AUTH_JWT_AUDIENCE": "gamma-local-audience",
                "AUTH_JWT_TOKEN_VERSION": "1",
            }
        )
        with mock.patch.object(
            local_environment_auth,
            "prepare_local_environment_auth",
            return_value=auth,
        ) as prepare:
            token = local_environment_auth._mint_local_access_token(
                environment="gamma",
                target_name="gamma-local",
                owner_id="owner-mint",
                persona_id="persona-mint",
            )

        prepare.assert_called_once_with("gamma", "gamma-local")
        parts = token.split(".")
        self.assertEqual(len(parts), 3)

        def _pad(segment: str) -> bytes:
            return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))

        claims = json.loads(_pad(parts[1]).decode("utf-8"))
        self.assertEqual(claims["sub"], "owner-mint")
        self.assertEqual(claims["psn"], "persona-mint")
        self.assertEqual(claims["tkn"], "access")
        self.assertEqual(claims["iss"], "gamma-local-issuer")
        self.assertEqual(claims["aud"], "gamma-local-audience")
        digest = hmac.new(
            b"unit-test-auth-jwt-secret",
            f"{parts[0]}.{parts[1]}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        self.assertEqual(
            base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
            parts[2],
        )


if __name__ == "__main__":
    unittest.main()
