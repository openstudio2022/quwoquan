"""App debug preflight runtime-mode isolation contracts.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from quwoquan_ops.cli import stackctl


_CONFIGURATION_DIGEST = "sha256:" + "1" * 64
_BASELINE_ID = "sha256:" + "2" * 64
_PROVIDER_DIGEST = "sha256:" + "3" * 64
_LOGIN_RECEIPT_DIGEST = "sha256:" + "4" * 64


def _provider_runtime(*, candidate_bound: bool) -> dict[str, object]:
    return {
        "baselineId": _BASELINE_ID if candidate_bound else "",
        "composition": {
            "runtimeCompositionDigest": _PROVIDER_DIGEST,
            "workloads": [
                {
                    "role": "sms-provider-substitute",
                    "adapterIds": ["ext.sms.local_capture"],
                }
            ],
        },
    }


def _startup(*, runtime_mode: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "running",
        "target": "alpha-local",
        "workload": "full",
        "attemptId": "attempt-alpha-runtime-mode",
        "configurationDigest": _CONFIGURATION_DIGEST,
        "providerRuntimeDigest": _PROVIDER_DIGEST,
    }
    if runtime_mode == "immutable_candidate":
        payload.update({"env": "alpha", "candidateDigest": _BASELINE_ID})
    else:
        payload["environment"] = "alpha"
    return payload


def _login_receipt(*, runtime_mode: str) -> dict[str, object]:
    return {
        "schema": "otp-local-capture-live-journey",
        "status": "passed",
        "target": "alpha-local",
        "launchPolicy": runtime_mode,
        "baselineId": _BASELINE_ID if runtime_mode == "immutable_candidate" else "",
        "sourceRevision": "a" * 40,
        "configurationDigest": _CONFIGURATION_DIGEST,
        "providerRuntimeDigest": _PROVIDER_DIGEST,
        "startupAttemptId": "attempt-alpha-runtime-mode",
        "challengePresent": True,
        "sessionPresent": True,
        "nonPromotable": True,
        "receiptRef": "receipt:otp-login:attempt-alpha-runtime-mode",
        "receiptDigest": _LOGIN_RECEIPT_DIGEST,
    }


def _fetch(url: str, **_kwargs: object) -> tuple[bool, int, str, str]:
    body = (
        json.dumps(
            {
                "status": "ready",
                "adapterId": "ext.sms.local_capture",
                "environment": "alpha",
                "configurationDigest": _CONFIGURATION_DIGEST,
                "profile": "success",
                "nonPromotable": True,
            }
        )
        if "17330" in url
        else '{"status":"ok"}'
    )
    return True, 200, body, "application/json"


class StackctlAppDebugPreflightRuntimeModeIsolationTest(unittest.TestCase):
    def test_test_live_otp_actor_is_unique_per_append_only_preflight_run(
        self,
    ) -> None:
        startup = _startup(runtime_mode="test_live")
        actor = SimpleNamespace(
            challenge_id="challenge-a",
            session=SimpleNamespace(owner_id="owner-a"),
        )
        opened_instances: list[str] = []

        def open_actor(
            _api_base_url: str,
            **kwargs: object,
        ) -> SimpleNamespace:
            opened_instances.append(str(kwargs["test_data_instance_id"]))
            return actor

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "open_test_data_acceptance_session",
                side_effect=open_actor,
            ),
            mock.patch.object(
                stackctl,
                "close_test_data_acceptance_actor",
            ) as close_actor,
            mock.patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value=startup,
            ),
        ):
            root = Path(temporary)
            first = stackctl._execute_otp_login_journey(
                environment="alpha",
                target_name="alpha-local",
                runtime_mode="test_live",
                startup=startup,
                provider_runtime=_provider_runtime(candidate_bound=False),
                api_base_url="https://api.alpha.quwoquan.com:17000",
                report_dir=root / "preflight-a",
            )
            second = stackctl._execute_otp_login_journey(
                environment="alpha",
                target_name="alpha-local",
                runtime_mode="test_live",
                startup=startup,
                provider_runtime=_provider_runtime(candidate_bound=False),
                api_base_url="https://api.alpha.quwoquan.com:17000",
                report_dir=root / "preflight-b",
            )

        self.assertNotEqual(opened_instances[0], opened_instances[1])
        self.assertTrue(all(value.startswith("otp-") for value in opened_instances))
        self.assertEqual(first["startupAttemptId"], startup["attemptId"])
        self.assertEqual(second["startupAttemptId"], startup["attemptId"])
        self.assertEqual(first["status"], "passed")
        self.assertEqual(second["status"], "passed")
        self.assertEqual(close_actor.call_count, 2)

    def _invoke(
        self,
        *,
        runtime_mode: str,
        content_binding_error: Exception | None = None,
        startup_status: str = "running",
        provider_runtime_error: Exception | None = None,
        tls_error: Exception | None = None,
        network_unavailable: bool = False,
    ) -> tuple[dict[str, object], mock.Mock]:
        provider_runtime = _provider_runtime(
            candidate_bound=runtime_mode == "immutable_candidate"
        )
        content_loader = mock.Mock(
            side_effect=content_binding_error,
            return_value=None,
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(
                stackctl,
                "get_target",
                return_value={
                    "env": "alpha",
                    "portProfile": "alpha",
                    "publicBases": {
                        "api": "https://api.alpha.quwoquan.com:17000"
                    },
                },
            ),
            mock.patch.object(
                stackctl,
                "_active_provider_runtime",
                return_value=provider_runtime,
                side_effect=provider_runtime_error,
            ) as active_provider,
            mock.patch.object(
                stackctl,
                "compile_provider_runtime_composition",
                return_value=provider_runtime["composition"],
                side_effect=provider_runtime_error,
            ) as mutable_provider,
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value={
                    **_startup(runtime_mode="immutable_candidate"),
                    "status": startup_status,
                },
            ) as immutable_startup,
            mock.patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value={
                    **_startup(runtime_mode="test_live"),
                    "status": startup_status,
                },
            ) as mutable_startup,
            mock.patch.object(
                stackctl,
                "load_test_live_content_binding",
                content_loader,
            ),
            mock.patch.object(
                stackctl,
                "verify_certificate",
                return_value={"profile": "local-managed", "status": "ready"},
                side_effect=tls_error,
            ),
            mock.patch.object(stackctl, "load_port_manifest", return_value={}),
            mock.patch.object(
                stackctl,
                "profile_ports",
                return_value={
                    "user-service": 17001,
                    "integration-service": 17002,
                    "sms-provider-substitute": 17330,
                },
            ),
            mock.patch.object(
                stackctl,
                "root_certificate_path",
                return_value=Path(temporary) / "root.crt",
            ),
            mock.patch.object(
                stackctl,
                "fetch_url",
                side_effect=(
                    (lambda *_args, **_kwargs: (False, None, "", ""))
                    if network_unavailable
                    else _fetch
                ),
            ),
            mock.patch.object(
                stackctl,
                "_execute_otp_login_journey",
                return_value=_login_receipt(runtime_mode=runtime_mode),
            ),
        ):
            result = stackctl.command_app_debug_preflight(
                argparse.Namespace(
                    target="alpha-local",
                    runtime_mode=runtime_mode,
                    report_dir=str(Path(temporary) / "preflight"),
                )
            )

        if runtime_mode == "immutable_candidate":
            active_provider.assert_called_once()
            mutable_provider.assert_not_called()
            immutable_startup.assert_called_once_with("alpha-local")
            mutable_startup.assert_not_called()
        else:
            active_provider.assert_not_called()
            mutable_provider.assert_called_once()
            immutable_startup.assert_not_called()
            mutable_startup.assert_called_once_with("alpha-local")
        return result, content_loader

    def test_immutable_otp_pass_ignores_stopped_test_live_binding(self) -> None:
        result, content_loader = self._invoke(
            runtime_mode="immutable_candidate",
            content_binding_error=ValueError(
                "test-live content binding requires the exact running startup attempt"
            ),
        )

        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["packageBaseline"], _BASELINE_ID)
        self.assertEqual(result["loginJourneyReceiptDigest"], _LOGIN_RECEIPT_DIGEST)
        self.assertTrue(result["loginJourney"]["sessionPresent"])
        self.assertFalse(result["warnings"])
        self.assertEqual(
            result["contentAvailability"],
            {"state": "not_evaluated", "packageBaseline": _BASELINE_ID},
        )
        content_loader.assert_not_called()

    def test_immutable_candidate_keeps_stopped_runtime_strict(self) -> None:
        result, content_loader = self._invoke(
            runtime_mode="immutable_candidate",
            startup_status="stopped",
        )

        self.assertEqual(result["exitCode"], 2, result)
        self.assertEqual(result["status"], "gate_block")
        self.assertIn("not running", " ".join(result["details"]))
        self.assertFalse(result["warnings"])
        content_loader.assert_not_called()

    def test_same_provider_tls_and_network_failures_follow_selected_policy(
        self,
    ) -> None:
        for runtime_mode, expected_status, expected_exit in (
            ("test_live", "warning", 0),
            ("immutable_candidate", "gate_block", 2),
        ):
            with self.subTest(runtime_mode=runtime_mode):
                result, _content_loader = self._invoke(
                    runtime_mode=runtime_mode,
                    provider_runtime_error=ValueError("Provider composition unavailable"),
                    tls_error=ValueError("TLS trust unavailable"),
                    network_unavailable=True,
                )

                self.assertEqual(result["exitCode"], expected_exit, result)
                self.assertEqual(result["status"], expected_status)
                findings = (
                    result["warnings"]
                    if runtime_mode == "test_live"
                    else result["details"]
                )
                combined = " ".join(findings)
                self.assertIn("Provider composition unavailable", combined)
                self.assertIn("TLS trust unavailable", combined)
                self.assertIn("api-edge is not ready: network_error", combined)
                if runtime_mode == "test_live":
                    self.assertFalse(result["details"])
                else:
                    self.assertFalse(result["warnings"])

    def test_cli_requires_an_explicit_runtime_mode(self) -> None:
        parser = stackctl.build_parser()
        command_action = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        preflight_parser = command_action.choices["app-debug-preflight"]
        runtime_mode_action = next(
            action
            for action in preflight_parser._actions
            if action.dest == "runtime_mode"
        )

        self.assertTrue(runtime_mode_action.required)
        self.assertIsNone(runtime_mode_action.default)

    def test_test_live_invalid_stored_binding_warns_and_launches_unbound(self) -> None:
        result, content_loader = self._invoke(
            runtime_mode="test_live",
            content_binding_error=ValueError(
                "test-live content binding requires the exact running startup attempt"
            ),
        )

        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(result["status"], "warning")
        self.assertFalse(result["details"])
        self.assertIn("exact running startup attempt", " ".join(result["warnings"]))
        self.assertEqual(result["contentBindingState"], "unbound")
        self.assertEqual(
            result["contentAvailability"],
            {"state": "unbound", "emptyReason": "no_active_release"},
        )
        self.assertEqual(result["packageBaseline"], "")
        content_loader.assert_called_once_with("alpha-local")


if __name__ == "__main__":
    unittest.main()
