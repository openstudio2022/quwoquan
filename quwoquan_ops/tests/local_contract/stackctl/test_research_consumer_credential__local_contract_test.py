"""research consumer credential 必须独立回读刚签发的 attestation。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import research_consumer_credential as credential
from quwoquan_ops.cli.lib.local_environment_auth import (
    LocalAcceptanceActor,
    LocalAcceptanceSession,
    LocalEnvironmentHTTPError,
)

_SUBJECT_HASH = "sha256:" + "a" * 64
_ATTESTATION = "signed-attestation-secret"
_EXPIRES_AT = "2026-09-01T05:00:00Z"


def _issuance() -> dict[str, str]:
    return {
        "subjectHash": _SUBJECT_HASH,
        "attestationId": _ATTESTATION,
        "expiresAt": _EXPIRES_AT,
    }


def _actor() -> LocalAcceptanceActor:
    return LocalAcceptanceActor(
        role="research-consumer-verification",
        session=LocalAcceptanceSession(
            owner_id="credential-owner",
            persona_id="credential-persona",
            access_token="bearer-secret",
        ),
        challenge_id="challenge-1",
        account_state="active",
        identity_origin="phone",
    )


class ResearchConsumerCredentialContractTest(unittest.TestCase):
    def _call(
        self,
        request_side_effect: object,
    ) -> tuple[dict[str, object], mock.Mock]:
        with tempfile.TemporaryDirectory() as directory:
            ca_file = Path(directory) / "root-ca.crt"
            ca_file.write_text("test-ca", encoding="utf-8")
            request_json = mock.Mock(side_effect=request_side_effect)
            with (
                mock.patch.object(credential, "load_environment_topology", return_value={}),
                mock.patch.object(
                    credential,
                    "get_target",
                    return_value={
                        "publicBases": {
                            "api": "https://api.alpha.quwoquan.local"
                        }
                    },
                ),
                mock.patch.object(credential, "root_certificate_path", return_value=ca_file),
                mock.patch.object(
                    credential,
                    "open_local_phone_acceptance_session",
                    return_value=_actor(),
                ),
                mock.patch.object(
                    credential, "request_local_environment_json", request_json
                ),
            ):
                result = credential.issue_research_consumer_credential(
                    environment="alpha",
                    release_id="release-1",
                    verify_run_id="verify-1",
                )
        return result, request_json

    def test_issuance_is_independently_read_back_before_return(self) -> None:
        result, request_json = self._call([_issuance(), _issuance()])

        self.assertEqual(request_json.call_count, 2)
        issuance_call, readback_call = request_json.call_args_list
        self.assertEqual(issuance_call.kwargs["path"], "/auth/research/session")
        self.assertEqual(issuance_call.kwargs["method"], "POST")
        self.assertEqual(
            readback_call.kwargs["path"],
            "/auth/research/session/attestation",
        )
        self.assertEqual(readback_call.kwargs["method"], "GET")
        self.assertEqual(
            readback_call.kwargs["headers"],
            {"X-Research-Identity-Attestation": _ATTESTATION},
        )
        self.assertEqual(result["subjectHash"], _SUBJECT_HASH)
        self.assertEqual(result["attestationToken"], _ATTESTATION)
        self.assertEqual(result["expiresAt"], _EXPIRES_AT)

    def test_attestation_readback_http_403_is_typed_and_redacted(self) -> None:
        failure = LocalEnvironmentHTTPError(
            method="GET",
            path="/auth/research/session/attestation",
            status=403,
        )
        with self.assertRaises(credential.ResearchConsumerCredentialError) as raised:
            self._call([_issuance(), failure])

        self.assertIn("attestation readback returned HTTP 403", str(raised.exception))
        self.assertNotIn(_ATTESTATION, str(raised.exception))
        self.assertNotIn("bearer-secret", str(raised.exception))

    def test_attestation_readback_exact_fields_and_identity_must_match(self) -> None:
        cases = {
            "missing-field": {
                "subjectHash": _SUBJECT_HASH,
                "attestationId": _ATTESTATION,
            },
            "extra-field": {**_issuance(), "unexpected": "field"},
            "subjectHash": {**_issuance(), "subjectHash": "sha256:" + "b" * 64},
            "attestationId": {**_issuance(), "attestationId": "other-proof"},
            "expiresAt": {**_issuance(), "expiresAt": "2026-09-01T05:01:00Z"},
        }
        for label, readback in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(
                    credential.ResearchConsumerCredentialError
                ) as raised:
                    self._call([_issuance(), readback])
                self.assertNotIn(_ATTESTATION, str(raised.exception))
                self.assertNotIn("bearer-secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
