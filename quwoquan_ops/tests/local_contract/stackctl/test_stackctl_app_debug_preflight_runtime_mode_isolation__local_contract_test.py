"""App debug preflight runtime-mode isolation contracts.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003
spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
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
from quwoquan_ops.cli.commands import app_preflight_debug as preflight_debug

_CONFIGURATION_DIGEST = "sha256:" + "1" * 64
_BASELINE_ID = "sha256:" + "2" * 64
_PROVIDER_DIGEST = "sha256:" + "3" * 64
_LOGIN_RECEIPT_DIGEST = "sha256:" + "4" * 64
_OBSERVABILITY_DIGEST = "sha256:" + "5" * 64
_MANIFEST_DIGEST = "sha256:" + "6" * 64
_READINESS_DIGEST = "sha256:" + "7" * 64
_RELEASE_UAT_SAMPLE_PLAN_DIGEST = "sha256:" + "8" * 64
_APP_UAT_PLAN_DIGEST = "sha256:" + "9" * 64


def _provider_runtime(*, candidate_bound: bool) -> dict[str, object]:
    return {
        "baselineId": _BASELINE_ID if candidate_bound else "",
        "composition": {
            "runtimeCompositionDigest": _PROVIDER_DIGEST,
            "workloads": [
                {
                    "role": "sms-provider-substitute",
                    "adapterIds": ["ext.sms.local_capture"],
                    "capabilityIds": ["identity.sms.otp"],
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
        "observabilityLogSinkDigest": _OBSERVABILITY_DIGEST,
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
    if url.endswith("/auth/otp/readiness"):
        body = '{"availability":"ready","retryAfterSeconds":0}'
    elif "17330" in url:
        body = json.dumps(
            {
                "status": "ready",
                "adapterId": "ext.sms.local_capture",
                "environment": "alpha",
                "configurationDigest": _CONFIGURATION_DIGEST,
                "profile": "success",
                "nonPromotable": True,
            }
        )
    else:
        body = '{"status":"ok"}'
    return True, 200, body, "application/json"


def _content_identity() -> dict[str, object]:
    return {
        "releaseId": "release-alpha-a",
        "manifestDigest": _MANIFEST_DIGEST,
        "readinessReceiptRef": (
            "env/alpha/runs/data-release/release-alpha-a/verify-a/"
            "release-readiness.json"
        ),
        "readinessReceiptDigest": _READINESS_DIGEST,
        "dataSourceIdentity": {
            "sourceRevision": "data-revision-a",
            "sourceDigest": "sha256:" + "a" * 64,
            "entityCatalogDigest": "sha256:" + "b" * 64,
        },
        "activationEnvelope": {"activationId": "activation-alpha-a"},
        "activationEnvelopeDigest": "sha256:" + "c" * 64,
        "lifecycleExitRef": (
            "env/alpha/runs/release-lifecycle-exit/release-alpha-a/exit-a/"
            "lifecycle-exit.json"
        ),
        "releaseHeaderRef": "data/releases/release-alpha-a/payload/release.json",
        "releaseHeaderDigest": _APP_UAT_PLAN_DIGEST,
        "releaseUatSamplePlanRef": "uat/sample_plan.json",
        "releaseUatSamplePlanDigest": _RELEASE_UAT_SAMPLE_PLAN_DIGEST,
        "appUatPlan": {
            "releaseIdentity": {
                "releaseId": "release-alpha-a",
                "payloadSha256": _MANIFEST_DIGEST,
            },
            "releaseUatSamplePlanRef": "uat/sample_plan.json",
            "releaseUatSamplePlanDigest": _RELEASE_UAT_SAMPLE_PLAN_DIGEST,
            "carrierIdentities": {"video": "video-alpha-a"},
            "orderedSamples": [],
            "requiredCasePlan": [],
            "videoPagination": {"expectedWorkIds": ["video-alpha-a"]},
        },
        "appUatPlanDigest": _APP_UAT_PLAN_DIGEST,
    }


def _immutable_content_preflight() -> dict[str, object]:
    return {
        "exitCode": 0,
        "status": "passed",
        "packageBaseline": _BASELINE_ID,
        "sourceRevision": "a" * 40,
        **_content_identity(),
        "releaseUatSamplePlan": {
            "schema": "quwoquan_data.release_uat_sample_plan",
            "releaseId": "release-alpha-a",
        },
        "contentReadback": {
            "postIds": ["article-alpha-a", "video-alpha-a"],
            "feedQueries": [
                {
                    "name": "typed_video",
                    "matchedPostIds": ["video-alpha-a"],
                },
                {
                    "name": "homepage_recommend",
                    "matchedPostIds": ["article-alpha-a"],
                },
            ],
        },
        "contentReadinessReportRef": (
            "env/alpha/runs/app-content-preflight/content-readiness/report.json"
        ),
        "releaseProbe": {
            "exitCode": 0,
            "mediaChecks": {"automatic": True},
            "searchCanaries": [
                {"id": "homepage"},
                {"id": "article"},
                {"id": "image"},
                {"id": "video"},
            ],
        },
        "details": [],
    }


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
        purpose: str = "runtime",
        content_binding: dict[str, object] | None = None,
        content_preflight: dict[str, object] | None = None,
        content_binding_error: Exception | None = None,
        startup_status: str = "running",
        provider_runtime_error: Exception | None = None,
        tls_error: Exception | None = None,
        network_unavailable: bool = False,
        otp_readiness_available: bool = True,
        container_issues: list[str] | None = None,
        capacity_issues: list[str] | None = None,
        api_base_url: str = "https://api.alpha.quwoquan.com:17000",
        observability_digest: str = _OBSERVABILITY_DIGEST,
    ) -> tuple[dict[str, object], mock.Mock, mock.Mock]:
        provider_runtime = _provider_runtime(
            candidate_bound=runtime_mode == "immutable_candidate"
        )
        content_loader = mock.Mock(
            side_effect=content_binding_error,
            return_value=content_binding,
        )
        content_preflight_command = mock.Mock(return_value=content_preflight or {})
        container_issues = list(container_issues or [])
        capacity_issues = list(capacity_issues or [])

        def fetch(url: str, **kwargs: object) -> tuple[bool, int, str, str]:
            if url.endswith("/auth/otp/readiness") and not otp_readiness_available:
                return (
                    True,
                    200,
                    '{"availability":"temporarily_unavailable",'
                    '"retryAfterSeconds":5}',
                    "application/json",
                )
            return _fetch(url, **kwargs)

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(
                stackctl,
                "get_target",
                return_value={
                    "env": "alpha",
                    "portProfile": "alpha",
                    "publicBases": {"api": api_base_url},
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
                    "observabilityLogSinkDigest": observability_digest,
                },
            ) as immutable_startup,
            mock.patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value={
                    **_startup(runtime_mode="test_live"),
                    "status": startup_status,
                    "observabilityLogSinkDigest": observability_digest,
                },
            ) as mutable_startup,
            mock.patch.object(
                stackctl,
                "load_test_live_content_binding",
                content_loader,
            ),
            mock.patch.object(
                preflight_debug,
                "_runtime_container_liveness_evidence",
                return_value={
                    "status": "unavailable" if container_issues else "ready",
                    "composeProject": "quwoquan_alpha_test_live",
                    "blocker": "APP.LAUNCH.runtime_dependency_unavailable"
                    if container_issues
                    else "",
                    "containers": [],
                    "issues": container_issues,
                    "warnings": [],
                },
            ),
            mock.patch.object(
                stackctl,
                "local_runtime_capacity_evidence",
                return_value={
                    "issues": capacity_issues,
                    "warnings": [],
                    "blocker": "LOCAL.RUNTIME.capacity_unavailable"
                    if capacity_issues
                    else "",
                    "evidence": {
                        "status": "gate_block" if capacity_issues else "ready"
                    },
                },
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
                    else fetch
                ),
            ),
            mock.patch.object(
                stackctl,
                "_execute_otp_login_journey",
                return_value=_login_receipt(runtime_mode=runtime_mode),
            ),
            mock.patch.object(
                stackctl,
                "command_app_content_preflight",
                content_preflight_command,
            ),
        ):
            result = stackctl.command_app_debug_preflight(
                argparse.Namespace(
                    target="alpha-local",
                    runtime_mode=runtime_mode,
                    purpose=purpose,
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
        return result, content_loader, content_preflight_command

    def test_test_live_content_live_does_not_delegate_commercial_content_uat(
        self,
    ) -> None:
        result, _content_loader, content_preflight_command = self._invoke(
            runtime_mode="test_live",
            purpose="content_live",
        )

        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["contentLive"], "warning")
        self.assertIs(result["nonPromotable"], True)
        self.assertIs(result["contentLiveChecks"]["nonPromotable"], True)
        self.assertEqual(result["firstBlocker"], "")
        self.assertFalse(result["details"])
        self.assertIn("readiness.content:", " ".join(result["warnings"]))
        content_preflight_command.assert_not_called()

    def test_immutable_otp_pass_ignores_stopped_test_live_binding(self) -> None:
        result, content_loader, _content_preflight_command = self._invoke(
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
        result, content_loader, _content_preflight_command = self._invoke(
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
                result, _content_loader, _content_preflight_command = self._invoke(
                    runtime_mode=runtime_mode,
                    provider_runtime_error=ValueError(
                        "Provider composition unavailable"
                    ),
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
                    self.assertIs(result["nonPromotable"], True)
                    self.assertEqual(result["firstBlocker"], "")
                else:
                    self.assertFalse(result["warnings"])
                    self.assertEqual(
                        result["firstBlocker"],
                        "APP.LAUNCH.runtime_dependency_unavailable",
                    )

    def test_test_live_content_live_projects_service_capacity_and_content_to_warnings(
        self,
    ) -> None:
        result, _content_loader, content_preflight_command = self._invoke(
            runtime_mode="test_live",
            purpose="content_live",
            provider_runtime_error=ValueError("Provider composition unavailable"),
            tls_error=ValueError("TLS trust unavailable"),
            network_unavailable=True,
            container_issues=["required service container exited"],
            capacity_issues=["container storage below threshold"],
            observability_digest="drifted",
        )

        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["contentLive"], "warning")
        self.assertEqual(result["firstBlocker"], "")
        self.assertFalse(result["details"])
        combined = " ".join(result["warnings"])
        for category in (
            "readiness.service:",
            "readiness.provider:",
            "readiness.tls:",
            "readiness.transport:",
            "readiness.content:",
            "readiness.observability:",
            "readiness.capacity:",
            "readiness.drift:",
        ):
            self.assertIn(category, combined)
        content_preflight_command.assert_not_called()

    def test_sms_provider_ready_but_relay_unavailable_warns_and_managed_blocks(
        self,
    ) -> None:
        result, _content_loader, _content_preflight_command = self._invoke(
            runtime_mode="test_live",
            purpose="content_live",
            content_binding={"releaseId": "release-alpha-a"},
            otp_readiness_available=False,
        )

        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(result["status"], "warning")
        self.assertTrue(result["provider"]["ready"])
        self.assertEqual(
            result["smsOtpReadiness"],
            {
                "operationId": (
                    "user.authentication_challenge.GetOtpDeliveryReadiness"
                ),
                "path": "/auth/otp/readiness",
                "statusCode": 200,
                "availability": "temporarily_unavailable",
                "retryAfterSeconds": 5,
                "ready": False,
            },
        )
        self.assertIn(
            "readiness.provider: SMS Provider/relay readiness is unavailable",
            " ".join(result["warnings"]),
        )
        with (
            mock.patch.object(
                stackctl,
                "command_app_debug_preflight",
                return_value=result,
            ),
            mock.patch.object(
                stackctl,
                "command_app_content_preflight",
                side_effect=AssertionError(
                    "strict debug finding must stop before content preflight"
                ),
            ),
            self.assertRaises(stackctl.ManagedPreparationBlocked) as raised,
        ):
            stackctl._managed_strict_preflight(
                environment="alpha",
                target="alpha-local",
                content_binding={"releaseId": "release-alpha-a"},
                report_dir=Path("unused"),
            )
        self.assertEqual(
            raised.exception.blocker,
            "APP.PREPARATION.strict_preflight_failed",
        )

    def test_canonical_sms_relay_readiness_ready_passes_strict_candidate(
        self,
    ) -> None:
        result, _content_loader, _content_preflight_command = self._invoke(
            runtime_mode="immutable_candidate",
        )

        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["smsOtpReadiness"]["availability"], "ready")
        self.assertEqual(result["smsOtpReadiness"]["retryAfterSeconds"], 0)
        self.assertTrue(result["smsOtpReadiness"]["ready"])

    def test_immutable_candidate_keeps_liveness_and_capacity_strict(self) -> None:
        result, _content_loader, _content_preflight_command = self._invoke(
            runtime_mode="immutable_candidate",
            container_issues=["required service container exited"],
            capacity_issues=["container storage below threshold"],
        )

        self.assertEqual(result["exitCode"], 2, result)
        self.assertEqual(result["status"], "gate_block")
        self.assertFalse(result["warnings"])
        self.assertIn("required service container exited", " ".join(result["details"]))
        self.assertIn("container storage below threshold", " ".join(result["details"]))
        self.assertEqual(
            result["firstBlocker"],
            "APP.LAUNCH.runtime_dependency_unavailable",
        )

    def test_immutable_content_live_keeps_commercial_readiness_strict(self) -> None:
        result, _content_loader, content_preflight_command = self._invoke(
            runtime_mode="immutable_candidate",
            purpose="content_live",
            content_preflight={
                "exitCode": 2,
                "status": "gate_block",
                "packageBaseline": _BASELINE_ID,
                "details": ["commercial content readiness unavailable"],
            },
        )

        self.assertEqual(result["exitCode"], 2, result)
        self.assertEqual(result["status"], "gate_block")
        self.assertEqual(result["contentLive"], "gate_block")
        self.assertFalse(result["warnings"])
        self.assertIn(
            "commercial content readiness unavailable", " ".join(result["details"])
        )
        self.assertEqual(
            result["firstBlocker"],
            "APP.LAUNCH.runtime_dependency_unavailable",
        )
        content_preflight_command.assert_called_once()

    def test_immutable_content_live_projects_verified_content_identity(self) -> None:
        verified = _immutable_content_preflight()
        result, content_loader, content_preflight_command = self._invoke(
            runtime_mode="immutable_candidate",
            purpose="content_live",
            content_preflight=verified,
        )

        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["contentLive"], "passed")
        self.assertEqual(result["purpose"], "content_live")
        self.assertIs(result["nonPromotable"], False)
        self.assertEqual(result["contentBindingState"], "bound")
        self.assertEqual(result["contentAvailability"]["state"], "bound")
        self.assertEqual(result["packageBaseline"], _BASELINE_ID)
        self.assertEqual(result["sourceRevision"], "a" * 40)
        for field, expected in _content_identity().items():
            self.assertEqual(result[field], expected, field)
        self.assertEqual(result["contentReadback"], verified["contentReadback"])
        self.assertEqual(
            result["releaseUatSamplePlan"],
            verified["releaseUatSamplePlan"],
        )
        self.assertEqual(
            result["contentReadinessReportRef"],
            verified["contentReadinessReportRef"],
        )
        self.assertEqual(result["contentBinding"], {})
        self.assertFalse(result["details"])
        self.assertFalse(result["warnings"])
        content_loader.assert_not_called()
        content_preflight_command.assert_called_once()

    def test_immutable_content_live_fails_closed_on_package_baseline_drift(
        self,
    ) -> None:
        drifted = {
            **_immutable_content_preflight(),
            "packageBaseline": "sha256:" + "f" * 64,
        }
        result, _content_loader, content_preflight_command = self._invoke(
            runtime_mode="immutable_candidate",
            purpose="content_live",
            content_preflight=drifted,
        )

        self.assertEqual(result["exitCode"], 2, result)
        self.assertEqual(result["status"], "gate_block")
        self.assertEqual(result["packageBaseline"], _BASELINE_ID)
        self.assertIn("binding", result["contentLiveChecks"]["blockedComponents"])
        self.assertIn(
            "content-live components are GATE_BLOCK",
            " ".join(result["details"]),
        )
        content_preflight_command.assert_called_once()

    def test_immutable_content_live_fails_closed_on_source_revision_drift(
        self,
    ) -> None:
        drifted = {
            **_immutable_content_preflight(),
            "sourceRevision": "b" * 40,
        }
        result, _content_loader, _content_preflight_command = self._invoke(
            runtime_mode="immutable_candidate",
            purpose="content_live",
            content_preflight=drifted,
        )

        self.assertEqual(result["exitCode"], 2, result)
        self.assertEqual(result["status"], "gate_block")
        self.assertEqual(result["sourceRevision"], "a" * 40)
        self.assertIn("binding", result["contentLiveChecks"]["blockedComponents"])

    def test_test_live_bound_payload_still_projects_only_mutable_binding(self) -> None:
        binding = {
            **_content_identity(),
            "readinessPhase": "consumer",
            "startupIdentity": {"sourceRevision": "a" * 40},
        }
        result, content_loader, content_preflight_command = self._invoke(
            runtime_mode="test_live",
            content_binding=binding,
        )

        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(result["packageBaseline"], "")
        self.assertEqual(result["sourceRevision"], "a" * 40)
        for field, expected in _content_identity().items():
            self.assertEqual(result[field], expected, field)
        self.assertEqual(result["contentBinding"], binding)
        content_loader.assert_called_once_with("alpha-local")
        content_preflight_command.assert_not_called()

    def test_valid_alpha_namespace_keeps_namespace_check_open(self) -> None:
        result, _content_loader, _content_preflight_command = self._invoke(
            runtime_mode="test_live",
            api_base_url="https://api.alpha.quwoquan.com:17000",
        )

        self.assertEqual(result["exitCode"], 0, result)
        self.assertNotEqual(result["status"], "gate_block")
        self.assertEqual(result["firstBlocker"], "")

    def test_illegal_namespace_remains_a_canonical_launch_blocker(self) -> None:
        for api_base_url in (
            "https://api.prod.quwoquan.com",
            "https://api.alpha.quwoquan.com:17000/../prod",
            "https://api.alpha.quwoquan.com:17000/%2e%2e/prod",
            "https://api.alpha.quwoquan.com:17000//foreign",
        ):
            with self.subTest(api_base_url=api_base_url):
                result, _content_loader, _content_preflight_command = self._invoke(
                    runtime_mode="test_live",
                    api_base_url=api_base_url,
                )

                self.assertEqual(result["exitCode"], 2, result)
                self.assertEqual(result["status"], "gate_block")
                self.assertIn(
                    "escapes the selected alpha namespace",
                    " ".join(result["details"]),
                )
                self.assertEqual(
                    result["firstBlocker"],
                    "APP.LAUNCH.runtime_config_activation_failed",
                )

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
        result, content_loader, _content_preflight_command = self._invoke(
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
