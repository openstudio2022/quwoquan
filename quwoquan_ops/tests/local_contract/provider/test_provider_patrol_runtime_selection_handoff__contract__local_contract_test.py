"""Provider Patrol consumes the runtime identity selected by stackctl.

spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#req-002
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from quwoquan_ops.ci.provider_conformance import run_provider_patrol_uat as subject


_IDENTITY_ENV = "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"
_BASELINE = "sha256:" + "1" * 64
_PROVIDER_DIGEST = "sha256:" + "2" * 64
_COMPOSE_DIGEST = "sha256:" + "3" * 64
_CONFIGURATION_DIGEST = "sha256:" + "4" * 64
_STATE_DIGEST = "sha256:" + "5" * 64
_WORKSPACE_DIGEST = "sha256:" + "6" * 64
_RESOLVER_DIGEST = "sha256:" + "7" * 64


def _immutable_handoff() -> dict[str, object]:
    return {
        "schema": "stackctl.provider_conformance_runtime_identity",
        "runtimeMode": "immutable_candidate",
        "environment": "alpha",
        "target": "alpha-local",
        "workload": "full",
        "startupAttemptId": "attempt-immutable-alpha",
        "providerRuntimeDigest": _PROVIDER_DIGEST,
        "failureFree": True,
        "nonPromotable": False,
        "candidateDigest": _BASELINE,
    }


def _mutable_handoff() -> dict[str, object]:
    return {
        "schema": "stackctl.provider_conformance_runtime_identity",
        "runtimeMode": "test_live",
        "environment": "alpha",
        "target": "alpha-local",
        "workload": "full",
        "startupAttemptId": "attempt-test-live-alpha",
        "providerRuntimeDigest": _PROVIDER_DIGEST,
        "failureFree": True,
        "nonPromotable": True,
        "mutableComposeDigest": _COMPOSE_DIGEST,
        "mutableConfigurationDigest": _CONFIGURATION_DIGEST,
        "mutableStateDigest": _STATE_DIGEST,
        "mutableWorkspaceStatusDigest": _WORKSPACE_DIGEST,
        "mutableResolverHandoffDigest": _RESOLVER_DIGEST,
        "mutableSourceRevision": "a" * 40,
    }


def _mutable_receipt() -> dict[str, object]:
    return {
        "status": "running",
        "environment": "alpha",
        "target": "alpha-local",
        "workload": "full",
        "attemptId": "attempt-test-live-alpha",
        "providerRuntimeDigest": _PROVIDER_DIGEST,
        "composeDigest": _COMPOSE_DIGEST,
        "configurationDigest": _CONFIGURATION_DIGEST,
        "mutableStateDigest": _STATE_DIGEST,
        "workspaceStatusDigest": _WORKSPACE_DIGEST,
        "resolverHandoffDigest": _RESOLVER_DIGEST,
        "sourceRevision": "a" * 40,
        "failure": None,
        "cleanupFailure": None,
    }


class ProviderPatrolRuntimeSelectionHandoffContractTest(unittest.TestCase):
    def _select_with(self, payload: dict[str, object]) -> object:
        with mock.patch.dict(
            os.environ,
            {_IDENTITY_ENV: json.dumps(payload, sort_keys=True)},
            clear=False,
        ):
            return subject._select_nonprod_runtime_identity(
                "alpha",
                "alpha-local",
            )

    def test_immutable_handoff_ignores_historical_test_live_and_active_pointer(
        self,
    ) -> None:
        immutable_identity = mock.sentinel.immutable_identity
        with (
            mock.patch.object(
                subject,
                "load_test_live_startup_attempt",
                side_effect=AssertionError("immutable rail must not scan test_live"),
            ),
            mock.patch.object(
                subject,
                "active_deployment_candidate",
                side_effect=AssertionError("runner must not scan the active pointer"),
                create=True,
            ),
            mock.patch.object(
                subject,
                "_load_nonprod_runtime_identity",
                return_value=immutable_identity,
            ) as load_immutable,
        ):
            selected = self._select_with(_immutable_handoff())

        self.assertIs(selected, immutable_identity)
        load_immutable.assert_called_once_with(
            "alpha",
            "alpha-local",
            candidate_digest=_BASELINE,
            startup_attempt_id="attempt-immutable-alpha",
            provider_runtime_digest=_PROVIDER_DIGEST,
        )

    def test_running_mutable_exact_handoff_selects_only_mutable(self) -> None:
        mutable_identity = mock.sentinel.mutable_identity
        receipt = _mutable_receipt()
        with (
            mock.patch.object(
                subject,
                "load_test_live_startup_attempt",
                return_value=receipt,
            ),
            mock.patch.object(
                subject,
                "_load_mutable_test_live_runtime_identity",
                return_value=mutable_identity,
            ) as load_mutable,
            mock.patch.object(
                subject,
                "_load_nonprod_runtime_identity",
                side_effect=AssertionError("mutable rail must not fallback"),
            ),
        ):
            selected = self._select_with(_mutable_handoff())

        self.assertIs(selected, mutable_identity)
        load_mutable.assert_called_once_with("alpha", "alpha-local", receipt)

    def test_running_mutable_handoff_drift_fails_without_fallback(self) -> None:
        receipt_fields = {
            "environment": "beta",
            "target": "beta-local",
            "workload": "content-commercial",
            "attemptId": "other-attempt",
            "providerRuntimeDigest": "sha256:" + "8" * 64,
            "composeDigest": "sha256:" + "8" * 64,
            "configurationDigest": "sha256:" + "8" * 64,
            "mutableStateDigest": "sha256:" + "8" * 64,
            "workspaceStatusDigest": "sha256:" + "8" * 64,
            "resolverHandoffDigest": "sha256:" + "8" * 64,
            "sourceRevision": "b" * 40,
            "status": "stopped",
            "failure": "provider failed",
            "cleanupFailure": "cleanup failed",
        }
        for field, value in receipt_fields.items():
            with self.subTest(field=field):
                receipt = _mutable_receipt()
                receipt[field] = value
                with (
                    mock.patch.object(
                        subject,
                        "load_test_live_startup_attempt",
                        return_value=receipt,
                    ),
                    mock.patch.object(
                        subject,
                        "_load_mutable_test_live_runtime_identity",
                        side_effect=AssertionError("drift must fail before load"),
                    ),
                    mock.patch.object(
                        subject,
                        "_load_nonprod_runtime_identity",
                        side_effect=AssertionError("drift must not fallback"),
                    ),
                    self.assertRaisesRegex(ValueError, "runtime identity handoff"),
                ):
                    self._select_with(_mutable_handoff())

    def test_missing_partial_foreign_or_extra_handoff_fails_before_selection(
        self,
    ) -> None:
        cases: list[tuple[str, str | None]] = []
        partial = _immutable_handoff()
        partial.pop("startupAttemptId")
        foreign = _immutable_handoff()
        foreign["environment"] = "beta"
        extra = _immutable_handoff()
        extra["secret"] = "must-not-be-accepted"
        cases.extend(
            (
                ("missing", None),
                ("partial", json.dumps(partial)),
                ("foreign", json.dumps(foreign)),
                ("extra", json.dumps(extra)),
            )
        )
        for label, raw in cases:
            with self.subTest(label=label):
                environment = dict(os.environ)
                if raw is None:
                    environment.pop(_IDENTITY_ENV, None)
                else:
                    environment[_IDENTITY_ENV] = raw
                with (
                    mock.patch.dict(os.environ, environment, clear=True),
                    mock.patch.object(
                        subject,
                        "_load_nonprod_runtime_identity",
                        side_effect=AssertionError("invalid handoff must not select"),
                    ),
                    mock.patch.object(
                        subject,
                        "_load_mutable_test_live_runtime_identity",
                        side_effect=AssertionError("invalid handoff must not select"),
                    ),
                    self.assertRaises(ValueError),
                ):
                    subject._select_nonprod_runtime_identity(
                        "alpha",
                        "alpha-local",
                    )


if __name__ == "__main__":
    unittest.main()
