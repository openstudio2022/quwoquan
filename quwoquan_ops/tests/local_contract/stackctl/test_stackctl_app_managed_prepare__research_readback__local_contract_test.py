"""managed preparation Research active release readback 合约。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""
from __future__ import annotations

import copy
import hashlib
import unittest
from collections.abc import Callable
from typing import Any
from unittest import mock

from quwoquan_ops.cli import stackctl

_DIGEST = "sha256:" + "a" * 64
_SUBJECT_HASH = "sha256:" + "b" * 64
_ATTESTATION_TOKEN = "managed-attestation-token"
_ATTESTATION_ID_HASH = "sha256:" + hashlib.sha256(
    _ATTESTATION_TOKEN.encode("utf-8")
).hexdigest()


def _credential() -> dict[str, str]:
    return {
        "apiBaseUrl": "https://api.alpha.quwoquan.local",
        "bearerToken": "bearer-secret",
        "attestationToken": _ATTESTATION_TOKEN,
        "subjectHash": _SUBJECT_HASH,
    }


def _readback() -> dict[str, Any]:
    return {
        "releaseId": "alpha-slice-003",
        "manifestDigest": _DIGEST,
        "subjectHash": _SUBJECT_HASH,
        "attestationIdHash": _ATTESTATION_ID_HASH,
        "signatureVerified": True,
        "researchBadgeVisible": True,
        "postIds": ["post-1", "post-2"],
        "entityRefs": ["entity-1", "entity-2"],
        "mediaAssetIds": ["media-1"],
        "publicCdnDetected": False,
        "anonymousMediaUrlDetected": False,
    }


def _readiness() -> dict[str, Any]:
    return {
        "internalSubjectHash": _SUBJECT_HASH,
        "postIds": ["post-2", "post-1"],
        "researchReadbackEntityRefs": ["entity-2", "entity-1"],
        "researchReadbackMediaAssetIds": ["media-1"],
    }


class ManagedResearchReadbackContractTest(unittest.TestCase):
    def _call_readback(self, payload: dict[str, Any]) -> dict[str, Any]:
        with (
            mock.patch.object(
                stackctl, "issue_research_consumer_credential", return_value=_credential()
            ),
            mock.patch.object(
                stackctl, "request_local_environment_json", return_value=payload
            ),
        ):
            return stackctl._managed_active_release_readback(
                environment="alpha", startup_attempt_id="attempt-1"
            )

    def test_exact_contract_projects_identity_and_all_closures(self) -> None:
        projection = self._call_readback(_readback())

        self.assertEqual(projection, _readback())
        self.assertEqual(projection["releaseId"], "alpha-slice-003")
        self.assertEqual(projection["manifestDigest"], _DIGEST)
        self.assertEqual(projection["subjectHash"], _SUBJECT_HASH)
        self.assertEqual(projection["attestationIdHash"], _ATTESTATION_ID_HASH)
        self.assertEqual(projection["postIds"], ["post-1", "post-2"])
        self.assertEqual(projection["entityRefs"], ["entity-1", "entity-2"])
        self.assertEqual(projection["mediaAssetIds"], ["media-1"])

    def test_every_contract_drift_is_rejected(self) -> None:
        def set_field(field: str, value: Any) -> Callable[[dict[str, Any]], None]:
            return lambda payload: payload.__setitem__(field, value)

        cases: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
            ("missing-field", lambda payload: payload.pop("postIds")),
            ("extra-field", lambda payload: payload.__setitem__("envelope", {})),
            ("releaseId-whitespace", set_field("releaseId", " alpha-slice-003 ")),
            ("releaseId-segment", set_field("releaseId", "alpha/release")),
            ("manifestDigest", set_field("manifestDigest", "sha256:INVALID")),
            ("subjectHash", set_field("subjectHash", "sha256:" + "c" * 64)),
            ("attestationIdHash", set_field("attestationIdHash", "sha256:" + "d" * 64)),
            ("signatureVerified", set_field("signatureVerified", False)),
            ("researchBadgeVisible", set_field("researchBadgeVisible", False)),
            ("publicCdnDetected", set_field("publicCdnDetected", True)),
            ("anonymousMediaUrlDetected", set_field("anonymousMediaUrlDetected", True)),
        ]
        for field in ("postIds", "entityRefs", "mediaAssetIds"):
            cases.extend(
                (
                    (f"{field}-empty", set_field(field, [])),
                    (f"{field}-duplicate", set_field(field, ["same", "same"])),
                    (f"{field}-non-string", set_field(field, [1])),
                )
            )
        for label, mutate in cases:
            with self.subTest(label=label):
                payload = _readback()
                mutate(payload)
                with self.assertRaises(ValueError):
                    self._call_readback(payload)

    def test_unique_readiness_matches_fresh_identity_and_closures(self) -> None:
        created = {"readinessPhase": "research", "binding": "created"}
        create = mock.Mock(return_value=created)
        with (
            mock.patch.object(
                stackctl, "_managed_active_release_readback", return_value=_readback()
            ),
            mock.patch.object(
                stackctl,
                "_managed_research_readiness_candidates",
                return_value=[
                    {
                        "verifyRunId": "verify-1",
                        "readiness": _readiness(),
                        "receiptPath": "/receipt.json",
                    }
                ],
            ),
            mock.patch.object(
                stackctl, "create_test_live_content_binding", create
            ),
        ):
            binding = stackctl._managed_content_binding(
                environment="alpha",
                target="alpha-local",
                startup_attempt_id="attempt-1",
            )

        self.assertEqual(binding, created)
        create.assert_called_once_with(
            environment="alpha",
            target="alpha-local",
            startup_attempt_id="attempt-1",
            release_id="alpha-slice-003",
            verify_run_id="verify-1",
            manifest_digest=_DIGEST,
        )

    def test_each_readiness_identity_or_closure_drift_blocks_before_binding(self) -> None:
        for field, value in (
            ("internalSubjectHash", "sha256:" + "e" * 64),
            ("postIds", ["post-drift"]),
            ("researchReadbackEntityRefs", ["entity-drift"]),
            ("researchReadbackMediaAssetIds", ["media-drift"]),
        ):
            with self.subTest(field=field):
                readiness = copy.deepcopy(_readiness())
                readiness[field] = value
                create = mock.Mock(
                    side_effect=AssertionError("readiness drift must not bind")
                )
                with (
                    mock.patch.object(
                        stackctl,
                        "_managed_active_release_readback",
                        return_value=_readback(),
                    ),
                    mock.patch.object(
                        stackctl,
                        "_managed_research_readiness_candidates",
                        return_value=[
                            {"verifyRunId": "verify-1", "readiness": readiness}
                        ],
                    ),
                    mock.patch.object(
                        stackctl, "create_test_live_content_binding", create
                    ),
                    self.assertRaises(stackctl.ManagedPreparationBlocked) as raised,
                ):
                    stackctl._managed_content_binding(
                        environment="alpha",
                        target="alpha-local",
                        startup_attempt_id="attempt-1",
                    )
                self.assertEqual(
                    raised.exception.blocker,
                    "APP.PREPARATION.content_binding_unavailable",
                )
                self.assertTrue(any(field in item for item in raised.exception.details))
                create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
