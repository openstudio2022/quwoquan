"""stackctl app-managed-prepare 严格 managed preparation 状态机契约。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from quwoquan_ops.cli import stackctl

_DIGEST = "sha256:" + "a" * 64
_LEASE_ID = "sha256:" + "b" * 64
_CONSUMER_ID = "flutter-run-test-1"


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(**overrides: str) -> dict[str, str]:
    identity = {
        "deviceId": "SIM-1",
        "deviceKind": "ios-simulator",
        "platform": "ios",
        "leasePlatform": "ios-simulator",
        "trustPlatform": "ios-simulator",
    }
    identity.update(overrides)
    return identity


def _resume_payload(attempt_id: str = "alpha-attempt-1") -> dict[str, Any]:
    return {
        "exitCode": 0,
        "startupAttempt": {
            "attemptId": attempt_id,
            "composeProject": "quwoquan_alpha_test_live",
            "composeDigest": "sha256:" + "1" * 64,
            "configurationDigest": "sha256:" + "2" * 64,
            "providerRuntimeDigest": "sha256:" + "3" * 64,
        },
        "runtime": {"environment": "alpha", "target": "alpha-local"},
    }


def _readiness_payload() -> dict[str, Any]:
    return {
        "schema": "quwoquan_data.release_readiness.v1",
        "releaseId": "alpha-slice-003",
        "verifyRunId": "verify-20260830T1600Z",
        "manifestDigest": _DIGEST,
        "readinessPhase": "research",
        "passed": True,
    }


def _binding(readiness_path: Path) -> dict[str, Any]:
    return {
        "releaseId": "alpha-slice-003",
        "verifyRunId": "verify-20260830T1600Z",
        "manifestDigest": _DIGEST,
        "readinessPhase": "research",
        "readinessReceiptRef": str(readiness_path.absolute()),
        "readinessReceiptDigest": "sha256:"
        + hashlib.sha256(readiness_path.read_bytes()).hexdigest(),
    }


def _passed_debug_preflight(binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "exitCode": 0,
        "schema": "quwoquan_ops.app_debug_preflight",
        "purpose": "content_live",
        "target": "alpha-local",
        "status": "passed",
        "firstBlocker": "",
        "details": [],
        "warnings": [],
        "nonPromotable": True,
        "releaseId": binding["releaseId"],
        "manifestDigest": binding["manifestDigest"],
        "readinessReceiptRef": binding["readinessReceiptRef"],
        "readinessReceiptDigest": binding["readinessReceiptDigest"],
        "contentBinding": dict(binding),
    }


def _passed_content_preflight(binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "exitCode": 0,
        "schema": "quwoquan_ops.app_content_preflight",
        "target": "alpha-local",
        "status": "passed",
        "details": [],
        "releaseId": binding["releaseId"],
        "manifestDigest": binding["manifestDigest"],
        "readinessReceiptRef": binding["readinessReceiptRef"],
        "readinessReceiptDigest": binding["readinessReceiptDigest"],
        "releaseProbe": {
            "exitCode": 0,
            "executedSampleCount": 100,
            "mediaChecks": {"automatic": True},
        },
    }


def _passed_strict_preflight(binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "debugPayload": _passed_debug_preflight(binding),
        "contentPayload": _passed_content_preflight(binding),
    }


class ManagedRuntimeReadyTest(unittest.TestCase):
    """runtime 复用与有界替换语义（identity：Provider/config/Compose）。"""

    def _base_patches(self) -> list[Any]:
        return [
            mock.patch.object(
                stackctl,
                "_local_stack_operation_lock",
                lambda _target: contextlib.nullcontext(),
            ),
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(
                stackctl,
                "_dev_session_runtime_preflight",
                return_value=(None, None),
            ),
            mock.patch.object(
                stackctl, "_mutable_workspace_snapshot", return_value={}
            ),
            mock.patch.object(
                stackctl,
                "_managed_inspect_running_full_runtime",
                side_effect=lambda **_kwargs: _resume_payload(),
            ),
        ]

    def test_exact_running_runtime_is_reused_without_restart(self) -> None:
        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            for patch in self._base_patches():
                patches.enter_context(patch)
            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_managed_inspect_running_full_runtime",
                    return_value={
                        **_resume_payload(),
                        "reused": True,
                        "replaced": False,
                        "warnings": ["digest changed warning"],
                    },
                )
            )
            start = patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_start_mutable_test_live_runtime",
                    side_effect=AssertionError("exact reuse must not restart"),
                )
            )
            down = patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_command_down_unlocked",
                    side_effect=AssertionError("exact reuse must not tear down"),
                )
            )
            payload = stackctl._managed_runtime_ready(
                environment="alpha",
                target="alpha-local",
                report_dir=Path(temporary),
            )

        self.assertTrue(payload["reused"])
        self.assertFalse(payload["replaced"])
        self.assertEqual(
            payload["startupAttempt"]["attemptId"], "alpha-attempt-1"
        )
        self.assertIn("digest changed warning", payload["warnings"])
        start.assert_not_called()
        down.assert_not_called()


    def _immutable_runtime_readback(
        self,
        *,
        actual_image: str = "sha256:" + "5" * 64,
        project_label: str = "quwoquan_alpha_release",
    ) -> tuple[dict[str, Any], list[list[str]], mock.Mock, mock.Mock, mock.Mock]:
        immutable = {
            "attemptId": "immutable-full-1",
            "status": "running",
            "workload": "full",
            "composeProject": "quwoquan_alpha_release",
            "candidateDigest": "sha256:" + "1" * 64,
            "configurationDigest": "sha256:" + "2" * 64,
            "providerRuntimeDigest": "sha256:" + "3" * 64,
            "observabilityLogSinkDigest": "sha256:" + "4" * 64,
            "imageComposition": {
                "images": {"service-core": {"ref": "sha256:" + "5" * 64}}
            },
        }
        expected = {
            key: immutable[key]
            for key in (
                "candidateDigest",
                "configurationDigest",
                "providerRuntimeDigest",
                "observabilityLogSinkDigest",
                "imageComposition",
            )
        }
        commands: list[list[str]] = []

        def docker_run(command: list[str], **_kwargs: Any) -> Any:
            commands.append(command)
            if command[:2] == ["docker", "ps"]:
                return __import__("subprocess").CompletedProcess(
                    command, 0, "container-1\n", ""
                )
            if command[:2] == ["docker", "inspect"]:
                return __import__("subprocess").CompletedProcess(
                    command,
                    0,
                    json.dumps(
                        [
                            {
                                "Id": "container-1-full-id",
                                "Config": {
                                    "Labels": {
                                        "com.docker.compose.project": project_label,
                                        "com.docker.compose.service": "service-core",
                                    }
                                },
                                "Image": actual_image,
                            }
                        ]
                    ),
                    "",
                )
            raise AssertionError(f"unexpected Docker command: {command}")

        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    lambda _target: contextlib.nullcontext(),
                )
            )
            patches.enter_context(
                mock.patch.object(stackctl, "load_environment_topology", return_value={})
            )
            patches.enter_context(
                mock.patch.object(stackctl, "_mutable_workspace_snapshot", return_value={})
            )
            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_dev_session_runtime_preflight",
                    return_value=(immutable, None),
                )
            )
            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_managed_inspect_running_full_runtime",
                    wraps=stackctl._managed_inspect_running_full_runtime,
                )
            )
            patches.enter_context(
                mock.patch.object(stackctl, "load_test_live_startup_attempt", return_value=None)
            )
            snapshot = {"target": "alpha-local"}
            patches.enter_context(
                mock.patch.object(
                    stackctl, "active_deployment_candidate_snapshot", return_value=snapshot
                )
            )
            patches.enter_context(
                mock.patch.object(
                    stackctl, "_fixed_candidate_runtime_identity", return_value=expected
                )
            )
            patches.enter_context(
                mock.patch.object(stackctl, "_runtime_identity_mismatches", return_value=[])
            )
            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "runtime_image_owner_names",
                    return_value=("service-core",),
                )
            )
            assert_snapshot = patches.enter_context(
                mock.patch.object(stackctl, "assert_active_deployment_candidate_snapshot")
            )
            inspect_runtime = patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_inspect_gamma_release_runtime",
                    side_effect=AssertionError(
                        "local immutable reuse must not require formal registry RepoDigest"
                    ),
                )
            )
            patches.enter_context(mock.patch.object(stackctl, "run", side_effect=docker_run))
            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "command_health",
                    return_value={"exitCode": 0, "details": []},
                )
            )
            start_runtime = patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_start_mutable_test_live_runtime",
                    side_effect=AssertionError("healthy immutable full must be reused"),
                )
            )
            payload = stackctl._managed_runtime_ready(
                environment="alpha",
                target="alpha-local",
                report_dir=Path(temporary),
            )
        return payload, commands, assert_snapshot, inspect_runtime, start_runtime

    def test_immutable_running_full_is_reused_after_exact_docker_readback(self) -> None:
        payload, commands, assert_snapshot, inspect_runtime, start_runtime = (
            self._immutable_runtime_readback()
        )

        self.assertTrue(payload["reused"])
        self.assertFalse(payload["replaced"])
        self.assertEqual(payload["startupAttempt"]["attemptId"], "immutable-full-1")
        assert_snapshot.assert_called_once_with({"target": "alpha-local"})
        inspect_runtime.assert_not_called()
        self.assertEqual(
            payload["runtime"]["images"]["service-core"]["runtimeImageId"],
            "sha256:" + "5" * 64,
        )
        self.assertEqual(
            commands[0],
            [
                "docker",
                "ps",
                "--filter",
                "label=com.docker.compose.project=quwoquan_alpha_release",
                "--filter",
                "status=running",
                "--format",
                "{{.ID}}",
            ],
        )
        self.assertEqual(commands[1], ["docker", "inspect", "container-1"])
        start_runtime.assert_not_called()

    def test_immutable_running_full_actual_image_drift_blocks_reuse(self) -> None:
        with self.assertRaises(stackctl.ManagedPreparationBlocked) as raised:
            self._immutable_runtime_readback(actual_image="sha256:" + "6" * 64)
        self.assertTrue(
            any("image drifted: service-core" in detail for detail in raised.exception.details)
        )

    def test_immutable_running_full_project_label_drift_blocks_reuse(self) -> None:
        with self.assertRaises(stackctl.ManagedPreparationBlocked) as raised:
            self._immutable_runtime_readback(project_label="quwoquan_other_release")
        self.assertTrue(
            any("project label drifted" in detail for detail in raised.exception.details)
        )


if __name__ == "__main__":
    unittest.main()
