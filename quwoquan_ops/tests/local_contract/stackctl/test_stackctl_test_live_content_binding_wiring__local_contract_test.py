"""Stackctl wiring for explicit, run-bound test-live content evidence.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-001
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64


def _binding() -> dict[str, object]:
    return {
        "schema": "stackctl.mutable_test_live_content_binding",
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "bound",
        "retentionClass": "run_bound",
        "environment": "alpha",
        "target": "alpha-local",
        "startupAttemptId": "attempt-alpha-0001",
        "startupIdentity": {
            "sourceRevision": "1" * 40,
            "workspaceStatusDigest": _DIGEST_B,
            "mutableStateDigest": _DIGEST_C,
            "composeDigest": _DIGEST_A,
            "configurationDigest": _DIGEST_B,
            "providerRuntimeDigest": _DIGEST_C,
            "resolverHandoffDigest": _DIGEST_A,
        },
        "releaseId": "release-panda-001",
        "verifyRunId": "verify-alpha-001",
        "manifestDigest": _DIGEST_A,
        "readinessPhase": "consumer",
        "releaseAttestationRef": (
            "data/releases/release-panda-001/attestations/release.json"
        ),
        "releaseAttestationDigest": _DIGEST_B,
        "readinessReceiptRef": (
            "env/alpha/runs/data-release/release-panda-001/"
            "verify-alpha-001/release-readiness.json"
        ),
        "readinessReceiptDigest": _DIGEST_C,
        "releaseHeaderRef": "data/releases/release-panda-001/payload/release.json",
        "releaseHeaderDigest": _DIGEST_B,
        "releaseUatSamplePlanRef": "uat/sample_plan.json",
        "releaseUatSamplePlanDigest": _DIGEST_C,
        "appUatPlan": {
            "releaseIdentity": {
                "releaseId": "release-panda-001",
                "payloadSha256": _DIGEST_A,
            },
            "releaseUatSamplePlanRef": "uat/sample_plan.json",
            "releaseUatSamplePlanDigest": _DIGEST_C,
            "carrierIdentities": {
                "homepage": "homepage-harbour",
                "article": "article-a",
                "image": "image-a",
                "video": "video-a",
            },
            "orderedSamples": [],
            "requiredCasePlan": [],
        },
        "appUatPlanDigest": _DIGEST_A,
        "lifecycleExitRef": "",
        "lifecycleExitDigest": "",
        "boundAt": "2026-08-09T00:00:00Z",
    }


def _startup() -> dict[str, object]:
    return {
        "status": "running",
        "environment": "alpha",
        "target": "alpha-local",
        "workload": "full",
        "configurationDigest": _DIGEST_B,
        "providerRuntimeDigest": _DIGEST_C,
        "attemptId": "attempt-alpha-0001",
    }


def _content_ready_preflight() -> dict[str, object]:
    return {
        "exitCode": 0,
        "status": "passed",
        "warnings": [],
        "mutableWorkspaceWarnings": [],
        "runtimeChecks": [
            {"name": "api-edge", "ready": True},
            {"name": "user-service", "ready": True},
            {"name": "integration-service", "ready": True},
            {"name": "provider-protocol-substitute", "ready": True},
            {"name": "sms-provider-substitute", "ready": True},
        ],
        "tls": {"profile": "local-managed", "status": "ready"},
        "provider": {
            "adapterId": "ext.sms.local_capture",
            "environment": "alpha",
            "configurationDigest": _DIGEST_B,
            "nonPromotable": True,
            "ready": True,
        },
    }


class StackctlTestLiveContentBindingWiringContract(unittest.TestCase):
    def test_receipt_bound_bind_content_parser_requires_complete_identity(self) -> None:
        parser = stackctl.build_parser()
        args = parser.parse_args(
            [
                "dev-session",
                "bind-content",
                "--target",
                "alpha-local",
                "--startup-attempt-id",
                "attempt-alpha-0001",
                "--release-id",
                "release-panda-001",
                "--verify-run-id",
                "verify-alpha-001",
                "--manifest-digest",
                _DIGEST_A,
                "--readiness-digest",
                _DIGEST_C,
            ]
        )

        self.assertEqual(args.dev_session_action, "bind-content")
        self.assertEqual(args.startup_attempt_id, "attempt-alpha-0001")
        self.assertEqual(args.readiness_digest, _DIGEST_C)

    def test_parser_accepts_only_an_explicit_complete_identity(self) -> None:
        parser = stackctl.build_parser()
        disabled = parser.parse_args(["dev-session", "--env", "alpha"])
        enabled = parser.parse_args(
            [
                "dev-session",
                "--env",
                "alpha",
                "--release-id",
                "release-panda-001",
                "--verify-run-id",
                "verify-alpha-001",
                "--manifest-digest",
                _DIGEST_A,
            ]
        )
        self.assertEqual(stackctl._dev_session_content_binding_request(disabled), {})
        self.assertEqual(
            stackctl._dev_session_content_binding_request(enabled),
            {
                "releaseId": "release-panda-001",
                "verifyRunId": "verify-alpha-001",
                "manifestDigest": _DIGEST_A,
                "lifecycleExitRef": "",
            },
        )
        partial = argparse.Namespace(
            release_id="release-panda-001",
            verify_run_id="",
            manifest_digest=_DIGEST_A,
            lifecycle_exit_ref="",
        )
        with self.assertRaisesRegex(ValueError, "partial; missing verifyRunId"):
            stackctl._dev_session_content_binding_request(partial)
        implicit_lifecycle = argparse.Namespace(
            release_id="",
            verify_run_id="",
            manifest_digest="",
            lifecycle_exit_ref=(
                "env/alpha/runs/release-lifecycle-exit/release-panda-001/"
                "exit-alpha/lifecycle-exit.json"
            ),
        )
        with self.assertRaisesRegex(ValueError, "partial; missing"):
            stackctl._dev_session_content_binding_request(implicit_lifecycle)

        invalid = parser.parse_args(
            [
                "dev-session",
                "--env",
                "alpha",
                "--release-id",
                "release-panda-001",
                "--manifest-digest",
                _DIGEST_A,
            ]
        )
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(
                stackctl,
                "_run_dev_session_target",
                side_effect=AssertionError("partial identity must stop before runtime"),
            ),
        ):
            result = stackctl.command_dev_session(invalid)
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "invalid_content_binding_selection")

    def test_preflight_consumes_exact_binding_or_warns_unbound(self) -> None:
        topology_target = {
            "env": "alpha",
            "portProfile": "alpha-local",
            "publicBases": {"api": "https://api.alpha.quwoquan.com:17000"},
        }
        composition = {
            "runtimeCompositionDigest": _DIGEST_C,
            "workloads": [],
        }
        def enter_common(stack: contextlib.ExitStack) -> None:
            stack.enter_context(
                mock.patch.object(stackctl, "load_environment_topology", return_value={})
            )
            stack.enter_context(
                mock.patch.object(stackctl, "get_target", return_value=topology_target)
            )
            stack.enter_context(
                mock.patch.object(
                    stackctl,
                    "compile_provider_runtime_composition",
                    return_value=composition,
                )
            )
            stack.enter_context(
                mock.patch.object(stackctl, "_active_provider_runtime", return_value={})
            )
            stack.enter_context(
                mock.patch.object(
                    stackctl,
                    "load_test_live_startup_attempt",
                    return_value=_startup(),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    stackctl,
                    "verify_certificate",
                    return_value={"profile": "local-managed", "status": "ready"},
                )
            )
            stack.enter_context(
                mock.patch.object(stackctl, "load_port_manifest", return_value={})
            )
            stack.enter_context(
                mock.patch.object(
                    stackctl,
                    "profile_ports",
                    return_value={
                        "user-service": 17001,
                        "integration-service": 17002,
                    },
                )
            )
            stack.enter_context(
                mock.patch.object(
                    stackctl,
                    "fetch_url",
                    return_value=(True, 200, "{}", {}),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    stackctl,
                    "_execute_otp_login_journey",
                    return_value={
                        "status": "passed",
                        "sourceRevision": "a" * 40,
                        "challengePresent": True,
                        "sessionPresent": True,
                        "receiptRef": "receipt:otp-login:attempt-alpha-0001",
                        "receiptDigest": _DIGEST_A,
                    },
                )
            )

        with tempfile.TemporaryDirectory() as temporary:
            with contextlib.ExitStack() as stack:
                enter_common(stack)
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "load_test_live_content_binding",
                        return_value=_binding(),
                    )
                )
                bound = stackctl.command_app_debug_preflight(
                    argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(Path(temporary) / "bound"),
                        runtime_mode="test_live",
                    )
                )
            with contextlib.ExitStack() as stack:
                enter_common(stack)
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "load_test_live_content_binding",
                        return_value=None,
                    )
                )
                unbound = stackctl.command_app_debug_preflight(
                    argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(Path(temporary) / "unbound"),
                        runtime_mode="test_live",
                    )
                )

        self.assertEqual(bound["exitCode"], 0)
        self.assertEqual(bound["contentBindingState"], "bound")
        self.assertEqual(bound["releaseId"], "release-panda-001")
        self.assertEqual(bound["readinessReceiptDigest"], _DIGEST_C)
        self.assertEqual(bound["contentBinding"]["startupAttemptId"], "attempt-alpha-0001")
        self.assertEqual(unbound["exitCode"], 0)
        self.assertEqual(unbound["status"], "warning")
        self.assertEqual(unbound["contentBindingState"], "unbound")
        self.assertTrue(any("content is unbound" in row for row in unbound["warnings"]))

    def test_exact_running_attempt_is_reused_then_bound_before_preflight_and_handoff(
        self,
    ) -> None:
        order: list[str] = []
        binding = _binding()
        runtime_payload = {
            "exitCode": 0,
            "runtime": {"environment": "alpha", "target": "alpha-local"},
            "startupAttempt": _startup(),
            "phases": [{"name": "mutable-startup-running", "exitCode": 0}],
        }

        def resume(**_kwargs: object) -> tuple[dict[str, object], list[str]]:
            order.append("resume")
            return runtime_payload, [
                "running mutable workspace digest changed; reusing the exact "
                "verified deployed runtime for the run-bound operation"
            ]

        def bind(**kwargs: object) -> dict[str, object]:
            order.append("binding")
            self.assertEqual(kwargs["startup_attempt_id"], "attempt-alpha-0001")
            self.assertEqual(kwargs["release_id"], "release-panda-001")
            return binding

        def preflight(_args: argparse.Namespace) -> dict[str, object]:
            order.append("preflight")
            return {
                **_content_ready_preflight(),
                "contentBindingState": "bound",
            }

        def handoff(**kwargs: object) -> dict[str, object]:
            order.append("handoff")
            self.assertEqual(kwargs["content_binding"], binding)
            return {
                "launchPolicy": "test_live",
                "contentBindingState": "bound",
                "contentReleaseId": "release-panda-001",
                "contentManifestDigest": _DIGEST_A,
                "contentReadinessReceiptDigest": _DIGEST_C,
            }

        with tempfile.TemporaryDirectory() as temporary:
            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "_dev_session_runtime_preflight",
                        return_value=(None, None),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "_mutable_workspace_snapshot",
                        return_value={},
                    )
                )
                start = stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "_start_mutable_test_live_runtime",
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "_dev_session_resume_running_mutable_runtime",
                        side_effect=resume,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "create_test_live_content_binding",
                        side_effect=bind,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "command_app_debug_preflight",
                        side_effect=preflight,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "_dev_session_launcher_handoff",
                        side_effect=handoff,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "command_health",
                        return_value={
                            "exitCode": 0,
                            "summary": "healthy",
                            "details": [],
                        },
                    )
                )
                result = stackctl._run_dev_session_target(
                    environment="alpha",
                    target="alpha-local",
                    device_id="",
                    launch_app_requested=False,
                    report_dir=Path(temporary),
                    content_binding_request={
                        "releaseId": "release-panda-001",
                        "verifyRunId": "verify-alpha-001",
                        "manifestDigest": _DIGEST_A,
                        "lifecycleExitRef": "",
                    },
                )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(order[:4], ["resume", "binding", "preflight", "handoff"])
        start.assert_not_called()
        self.assertTrue(result["mutableWorkspaceWarnings"])
        self.assertEqual(result["contentBindingState"], "bound")
        self.assertEqual(result["contentBinding"], binding)

    def test_content_binding_refreshes_only_after_runtime_identity_drift(self) -> None:
        runtime_payload = {
            "exitCode": 0,
            "runtime": {"environment": "alpha", "target": "alpha-local"},
            "startupAttempt": _startup(),
            "phases": [{"name": "mutable-startup-running", "exitCode": 0}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "_dev_session_runtime_preflight",
                        return_value=(None, None),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "_mutable_workspace_snapshot",
                        return_value={},
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "_dev_session_resume_running_mutable_runtime",
                        side_effect=[
                            ValueError(
                                "running mutable receipt/plan drift: composeDigest"
                            ),
                            (runtime_payload, []),
                        ],
                    )
                )
                start = stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "_start_mutable_test_live_runtime",
                        return_value=runtime_payload,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "create_test_live_content_binding",
                        return_value=_binding(),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "command_app_debug_preflight",
                        return_value=_content_ready_preflight(),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "_dev_session_launcher_handoff",
                        return_value={
                            "launchPolicy": "test_live",
                            "contentBindingState": "bound",
                        },
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        stackctl,
                        "command_health",
                        return_value={"exitCode": 0, "summary": "healthy"},
                    )
                )
                result = stackctl._run_dev_session_target(
                    environment="alpha",
                    target="alpha-local",
                    device_id="",
                    launch_app_requested=False,
                    report_dir=Path(temporary),
                    content_binding_request={
                        "releaseId": "release-panda-001",
                        "verifyRunId": "verify-alpha-001",
                        "manifestDigest": _DIGEST_A,
                        "lifecycleExitRef": "",
                    },
                )

        self.assertEqual(result["exitCode"], 0)
        start.assert_called_once()
        self.assertTrue(
            any("cannot be reused" in warning for warning in result["warnings"])
        )

    def test_launcher_handoff_never_carries_content_identity(self) -> None:
        # 内容激活是服务端运行时事实：即使 dev-session 提供 content binding，
        # launcher handoff 也不得把 content identity 传给 builder 或返回体。
        binding = _binding()
        completed = subprocess.CompletedProcess(
            ["build_launcher_handoff.py"],
            0,
            json.dumps({"launchPolicy": "test_live"}),
            "",
        )
        with mock.patch.object(stackctl.subprocess, "run", return_value=completed) as execute:
            result = stackctl._dev_session_launcher_handoff(
                environment="alpha",
                target="alpha-local",
                content_binding=binding,
            )
        command = execute.call_args.args[0]
        self.assertEqual(result["launchPolicy"], "test_live")
        self.assertNotIn("contentBindingState", result)
        self.assertNotIn("--content-release-id", command)
        self.assertNotIn("--content-manifest-digest", command)
        self.assertNotIn("--content-readiness-receipt-digest", command)
        self.assertNotIn("latest", command)
        self.assertNotIn("candidate", " ".join(command))

    def test_receipt_bound_bind_content_never_materializes_runtime(self) -> None:
        startup = _startup()
        runtime = {"startupAttempt": startup, "runtime": {"target": "alpha-local"}}
        args = argparse.Namespace(
            command="dev-session",
            dev_session_action="bind-content",
            target="alpha-local",
            env="",
            all_nonprod=False,
            launch_app=False,
            device_id="",
            startup_attempt_id="attempt-alpha-0001",
            release_id="release-panda-001",
            verify_run_id="verify-alpha-001",
            manifest_digest=_DIGEST_A,
            readiness_digest=_DIGEST_C,
            lifecycle_exit_ref="",
        )
        with tempfile.TemporaryDirectory() as temporary:
            args.report_dir = temporary
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={"targets": {"alpha-local": {"env": "alpha"}}},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "alpha"},
                ),
                mock.patch.object(stackctl, "_local_stack_operation_lock"),
                mock.patch.object(
                    stackctl,
                    "_mutable_workspace_snapshot",
                    return_value={"mutableStateDigest": _DIGEST_A},
                ),
                mock.patch.object(
                    stackctl,
                    "_dev_session_resume_running_mutable_runtime",
                    side_effect=[(runtime, []), (runtime, [])],
                ) as validate_runtime,
                mock.patch.object(
                    stackctl,
                    "create_test_live_content_binding",
                    return_value=_binding(),
                ) as create_binding,
                mock.patch.object(
                    stackctl,
                    "_dev_session_launcher_handoff",
                    return_value={
                        "launchPolicy": "test_live",
                        "contentBindingState": "bound",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_start_mutable_test_live_runtime",
                ) as start_runtime,
            ):
                result = stackctl.command_dev_session(args)

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["contentBinding"]["startupAttemptId"], "attempt-alpha-0001")
        self.assertEqual(validate_runtime.call_count, 2)
        create_binding.assert_called_once_with(
            environment="alpha",
            target="alpha-local",
            startup_attempt_id="attempt-alpha-0001",
            release_id="release-panda-001",
            verify_run_id="verify-alpha-001",
            manifest_digest=_DIGEST_A,
            expected_readiness_receipt_digest=_DIGEST_C,
            lifecycle_exit_ref="",
        )
        start_runtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
