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



class ManagedConsumerLeaseBindingTest(unittest.TestCase):
    def test_bind_updates_existing_identity_without_reacquire(self) -> None:
        from quwoquan_ops.cli.lib import local_runtime_consumer_lease as leases

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            with mock.patch.dict(
                "os.environ", {"QWQ_OUTPUT_ROOT": str(output_root)}, clear=False
            ):
                acquired = leases.acquire_consumer_lease(
                    target="alpha-local",
                    device="SIM-1",
                    consumer=_CONSUMER_ID,
                    package_name="com.quwoquan.alpha.debug",
                    ports=[],
                    platform="ios-simulator",
                )
                started_at = acquired["startedAt"]
                bound = leases.bind_consumer_lease(
                    target="alpha-local",
                    device="SIM-1",
                    consumer=_CONSUMER_ID,
                    lease_id=str(acquired["leaseId"]),
                    handoff_digest=_DIGEST,
                    release_id="alpha-slice-003",
                    manifest_digest=_DIGEST,
                )
        self.assertEqual(bound["leaseId"], acquired["leaseId"])
        self.assertEqual(bound["startedAt"], started_at)
        self.assertEqual(bound["handoffDigest"], _DIGEST)
        self.assertEqual(bound["releaseId"], "alpha-slice-003")

    def test_bind_rejects_a_different_lease_identity(self) -> None:
        from quwoquan_ops.cli.lib import local_runtime_consumer_lease as leases

        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            with mock.patch.dict(
                "os.environ", {"QWQ_OUTPUT_ROOT": str(output_root)}, clear=False
            ):
                leases.acquire_consumer_lease(
                    target="alpha-local",
                    device="SIM-1",
                    consumer=_CONSUMER_ID,
                    package_name="com.quwoquan.alpha.debug",
                    ports=[],
                    platform="ios-simulator",
                )
                with self.assertRaisesRegex(ValueError, "leaseId mismatch"):
                    leases.bind_consumer_lease(
                        target="alpha-local",
                        device="SIM-1",
                        consumer=_CONSUMER_ID,
                        lease_id="sha256:" + "f" * 64,
                        handoff_digest=_DIGEST,
                    )


class ManagedPreparationStateMachineTest(unittest.TestCase):
    """固定顺序状态机 + blocked receipt 语义。"""

    def _prepare(
        self,
        report_dir: Path,
        patches: contextlib.ExitStack,
        **overrides: Any,
    ) -> dict[str, Any]:
        readiness_path = report_dir / "release-readiness.json"
        readiness_path.parent.mkdir(parents=True, exist_ok=True)
        if not readiness_path.exists():
            readiness_path.write_text(
                json.dumps(_readiness_payload(), sort_keys=True) + "\n",
                encoding="utf-8",
            )
        binding = _binding(readiness_path)
        defaults: dict[str, Any] = {
            "load_environment_topology": mock.patch.object(
                stackctl, "load_environment_topology", return_value={}
            ),
            "get_target": mock.patch.object(
                stackctl, "get_target", return_value={"env": "alpha"}
            ),
            "_managed_device_identity": mock.patch.object(
                stackctl, "_managed_device_identity", return_value=_identity()
            ),
            "_managed_runtime_ready": mock.patch.object(
                stackctl,
                "_managed_runtime_ready",
                return_value={
                    "reused": True,
                    "replaced": False,
                    "warnings": [],
                    "startupAttempt": _resume_payload()["startupAttempt"],
                    "runtime": {},
                },
            ),
            "application_id_for": mock.patch.object(
                stackctl,
                "application_id_for",
                return_value="com.quwoquan.alpha.debug",
            ),
            "acquire_consumer_lease": mock.patch.object(
                stackctl,
                "acquire_consumer_lease",
                return_value={"leaseId": _LEASE_ID},
            ),
            "release_consumer_lease": mock.patch.object(
                stackctl, "release_consumer_lease", return_value=True
            ),
            "_managed_device_trust": mock.patch.object(
                stackctl,
                "_managed_device_trust",
                return_value={
                    "deviceTrustReceiptRef": "",
                    "deviceTrustReceiptDigest": "",
                },
            ),
            "_managed_content_binding": mock.patch.object(
                stackctl, "_managed_content_binding", return_value=binding
            ),
            "_managed_strict_preflight": mock.patch.object(
                stackctl,
                "_managed_strict_preflight",
                return_value=_passed_strict_preflight(binding),
            ),
        }
        defaults.update(overrides)
        mocks = {name: patches.enter_context(patch) for name, patch in defaults.items()}
        result = stackctl.run_managed_preparation(
            target="alpha-local",
            device_id="SIM-1",
            platform="ios",
            consumer_id=_CONSUMER_ID,
            report_dir=report_dir,
        )
        result["_mocks"] = mocks
        return result

    def test_prepared_receipt_schema_digest_and_lease_release(self) -> None:
        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            result = self._prepare(Path(temporary), patches)
            mocks = result.pop("_mocks")

            self.assertEqual(result["exitCode"], 0)
            self.assertEqual(result["status"], "prepared")
            receipt_path = Path(result["receiptPath"])
            raw = receipt_path.read_bytes()
            self.assertEqual(
                result["receiptDigest"],
                "sha256:" + hashlib.sha256(raw).hexdigest(),
            )
            receipt = json.loads(raw)
            self.assertEqual(
                set(receipt),
                {
                    "schema",
                    "target",
                    "environment",
                    "platform",
                    "deviceId",
                    "runtimeIdentity",
                    "consumerId",
                    "consumerLeaseId",
                    "androidReversePorts",
                    "androidReverseOwnedPorts",
                    "deviceTrustReceiptRef",
                    "deviceTrustReceiptDigest",
                    "contentBinding",
                    "strictPreflightReceiptRef",
                    "strictPreflightReceiptDigest",
                    "strictContentPreflightReceiptRef",
                    "strictContentPreflightReceiptDigest",
                    "createdAt",
                    "status",
                    "firstBlocker",
                },
            )
            self.assertEqual(
                receipt["schema"], "quwoquan_ops.app_managed_preparation.v1"
            )
            self.assertEqual(receipt["target"], "alpha-local")
            self.assertEqual(receipt["environment"], "alpha")
            self.assertEqual(receipt["platform"], "ios")
            self.assertEqual(receipt["deviceId"], "SIM-1")
            self.assertEqual(receipt["status"], "prepared")
            self.assertEqual(receipt["firstBlocker"], "")
            self.assertEqual(receipt["consumerId"], _CONSUMER_ID)
            self.assertEqual(receipt["consumerLeaseId"], _LEASE_ID)
            self.assertEqual(
                receipt["contentBinding"]["readinessReceiptDigest"],
                _sha256_file(Path(receipt["contentBinding"]["readinessReceiptRef"])),
            )
            self.assertEqual(receipt["contentBinding"]["readinessPhase"], "research")
            self.assertEqual(
                receipt["runtimeIdentity"]["startupAttemptId"], "alpha-attempt-1"
            )
            self.assertTrue(receipt["runtimeIdentity"]["reused"])
            # 严格 preflight receipt 单独落盘且 digest 与文件字节一致。
            strict_ref = Path(receipt["strictPreflightReceiptRef"])
            self.assertTrue(strict_ref.is_file())
            self.assertEqual(
                receipt["strictPreflightReceiptDigest"],
                "sha256:" + hashlib.sha256(strict_ref.read_bytes()).hexdigest(),
            )
            envelope = json.loads(strict_ref.read_text(encoding="utf-8"))
            self.assertEqual(envelope["schema"], "quwoquan_ops.app_debug_preflight")
            self.assertEqual(envelope["purpose"], "content_live")
            content_ref = Path(receipt["strictContentPreflightReceiptRef"])
            self.assertTrue(content_ref.is_file())
            self.assertNotEqual(content_ref, strict_ref)
            self.assertEqual(
                receipt["strictContentPreflightReceiptDigest"],
                _sha256_file(content_ref),
            )
            content_envelope = json.loads(content_ref.read_text(encoding="utf-8"))
            self.assertEqual(
                content_envelope["schema"],
                "quwoquan_ops.app_content_preflight_exact.v1",
            )
            self.assertEqual(content_envelope["releaseProbe"]["exitCode"], 0)
            self.assertGreater(
                content_envelope["releaseProbe"]["executedSampleCount"], 0
            )
            self.assertTrue(
                content_envelope["releaseProbe"]["mediaChecks"]["automatic"]
            )
            self.assertEqual(content_ref.stat().st_mode & 0o777, 0o600)
            # trust 安装与前台 run.sh 将接管的稳定 consumer lease 使用同一身份。
            mocks["_managed_device_trust"].assert_called_once_with(
                target="alpha-local",
                trust_platform="ios-simulator",
                device_id="SIM-1",
                lease_id=_LEASE_ID,
            )
            mocks["release_consumer_lease"].assert_not_called()

    def test_idempotent_rerun_reuses_without_reinstall(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipts = []
            for round_index in range(2):
                with contextlib.ExitStack() as patches:
                    result = self._prepare(
                        Path(temporary) / f"round-{round_index}", patches
                    )
                    mocks = result.pop("_mocks")
                    self.assertEqual(result["status"], "prepared")
                    # 健康 runtime 复用（reused=True 由 runtime mock 表达），
                    # trust 步骤每轮只走 verify-first 复用路径。
                    mocks["_managed_runtime_ready"].assert_called_once()
                    receipts.append(
                        json.loads(Path(result["receiptPath"]).read_bytes())
                    )
            for field in (
                "releaseId",
                "verifyRunId",
                "manifestDigest",
                "readinessPhase",
                "readinessReceiptDigest",
            ):
                self.assertEqual(
                    receipts[0]["contentBinding"][field],
                    receipts[1]["contentBinding"][field],
                )
            self.assertEqual(
                receipts[0]["runtimeIdentity"], receipts[1]["runtimeIdentity"]
            )

    def test_readiness_exact_byte_drift_blocks_prepared_receipt(self) -> None:
        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            report_dir = Path(temporary)
            readiness_path = report_dir / "release-readiness.json"
            readiness_path.write_text(
                json.dumps(_readiness_payload(), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            stale_binding = _binding(readiness_path)
            readiness_path.write_text(
                readiness_path.read_text(encoding="utf-8") + " ",
                encoding="utf-8",
            )
            result = self._prepare(
                report_dir,
                patches,
                _managed_content_binding=mock.patch.object(
                    stackctl,
                    "_managed_content_binding",
                    return_value=stale_binding,
                ),
                _managed_strict_preflight=mock.patch.object(
                    stackctl,
                    "_managed_strict_preflight",
                    side_effect=AssertionError(
                        "readiness byte drift must block before strict preflight"
                    ),
                ),
            )
            result.pop("_mocks")

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            result["firstBlocker"],
            "APP.PREPARATION.content_binding_unavailable",
        )
        self.assertTrue(
            any("exact-byte digest drifted" in detail for detail in result["details"])
        )

    def test_readback_failure_and_ambiguous_readiness_block_before_build(self) -> None:
        for candidates in (None, [], [{"verifyRunId": "run-a"}, {"verifyRunId": "run-b"}]):
            with self.subTest(
                candidates="readback-failed" if candidates is None else len(candidates)
            ), contextlib.ExitStack() as patches, tempfile.TemporaryDirectory() as temporary:
                binding_patches: dict[str, Any] = {
                    "_managed_content_binding": mock.patch.object(
                        stackctl, "_managed_content_binding", wraps=stackctl._managed_content_binding
                    ),
                    "_managed_active_release_readback": mock.patch.object(
                        stackctl,
                        "_managed_active_release_readback",
                        return_value={
                            "releaseId": "alpha-slice-003",
                            "manifestDigest": _DIGEST,
                        },
                        side_effect=(
                            ValueError("fresh readback contract drift")
                            if candidates is None
                            else None
                        ),
                    ),
                    "_managed_research_readiness_candidates": mock.patch.object(
                        stackctl, "_managed_research_readiness_candidates", return_value=candidates or [],
                        side_effect=(
                            AssertionError("failed readback must stop candidate discovery")
                            if candidates is None
                            else None
                        ),
                    ),
                    "create_test_live_content_binding": mock.patch.object(
                        stackctl, "create_test_live_content_binding",
                        side_effect=AssertionError("ambiguous readiness must not bind"),
                    ),
                    "_managed_strict_preflight": mock.patch.object(
                        stackctl, "_managed_strict_preflight",
                        side_effect=AssertionError("binding block must precede preflight"),
                    ),
                }
                result = self._prepare(
                    Path(temporary), patches, **binding_patches
                )
                result.pop("_mocks")

                self.assertEqual(result["exitCode"], 2)
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(
                    result["firstBlocker"],
                    "APP.PREPARATION.content_binding_unavailable",
                )
                receipt = json.loads(Path(result["receiptPath"]).read_bytes())
                self.assertEqual(receipt["status"], "blocked")
                self.assertEqual(
                    receipt["firstBlocker"],
                    "APP.PREPARATION.content_binding_unavailable",
                )

    def test_runtime_drift_block_writes_blocked_receipt(self) -> None:
        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            result = self._prepare(
                Path(temporary),
                patches,
                _managed_runtime_ready=mock.patch.object(
                    stackctl,
                    "_managed_runtime_ready",
                    side_effect=stackctl.ManagedPreparationBlocked(
                        "APP.PREPARATION.runtime_unavailable",
                        ["identity drift while another lease is live"],
                    ),
                ),
                acquire_consumer_lease=mock.patch.object(
                    stackctl,
                    "acquire_consumer_lease",
                    side_effect=AssertionError(
                        "runtime block must precede lease acquisition"
                    ),
                ),
            )
            result.pop("_mocks")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(
                result["firstBlocker"], "APP.PREPARATION.runtime_unavailable"
            )
            receipt = json.loads(Path(result["receiptPath"]).read_bytes())
            self.assertEqual(receipt["status"], "blocked")
            self.assertNotEqual(receipt["firstBlocker"], "")

    def test_trust_install_binds_the_real_consumer_lease(self) -> None:
        installed: dict[str, Any] = {}

        def install(**kwargs: Any) -> dict[str, Any]:
            installed.update(kwargs)
            return {"systemTrustStore": True, "receipt": kwargs["lease_id"]}

        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            trust_receipt = Path(temporary) / "device-trust.json"
            trust_receipt.write_text("{}\n", encoding="utf-8")
            verify_results: list[Any] = [
                stackctl.LocalDeviceTrustError("no receipt yet"),
                {"receipt": str(trust_receipt), "leases": [_LEASE_ID]},
            ]

            def verify(**_kwargs: Any) -> dict[str, Any]:
                result = verify_results.pop(0)
                if isinstance(result, Exception):
                    raise result
                trust_receipt.write_text(
                    json.dumps(
                        {
                            "target": "alpha-local",
                            "platform": "ios-simulator",
                            "device": "SIM-1",
                            "status": "installed",
                            "systemTrustStore": True,
                            "leases": [_LEASE_ID],
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return result

            result = self._prepare(
                Path(temporary),
                patches,
                _managed_device_trust=mock.patch.object(
                    stackctl,
                    "_managed_device_trust",
                    wraps=stackctl._managed_device_trust,
                ),
                verify_device_trust=mock.patch.object(
                    stackctl, "verify_device_trust", side_effect=verify
                ),
                install_device_trust=mock.patch.object(
                    stackctl, "install_device_trust", side_effect=install
                ),
            )
            result.pop("_mocks")

            self.assertEqual(result["status"], "prepared", result)
            self.assertEqual(installed["lease_id"], _LEASE_ID)
            receipt = json.loads(Path(result["receiptPath"]).read_bytes())
            self.assertEqual(receipt["consumerLeaseId"], _LEASE_ID)
            self.assertEqual(
                receipt["deviceTrustReceiptRef"], str(trust_receipt)
            )
            self.assertEqual(
                receipt["deviceTrustReceiptDigest"],
                "sha256:"
                + hashlib.sha256(trust_receipt.read_bytes()).hexdigest(),
            )

    def test_block_after_lease_releases_same_consumer_and_trust(self) -> None:
        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            release_trust = patches.enter_context(
                mock.patch.object(stackctl, "release_device_trust", return_value={})
            )
            result = self._prepare(
                Path(temporary),
                patches,
                _managed_device_trust=mock.patch.object(
                    stackctl,
                    "_managed_device_trust",
                    side_effect=stackctl.ManagedPreparationBlocked(
                        "APP.PREPARATION.strict_preflight_failed",
                        ["trust receipt lease mismatch"],
                    ),
                ),
            )
            mocks = result.pop("_mocks")

            self.assertEqual(result["status"], "blocked")
            mocks["release_consumer_lease"].assert_called_once_with(
                target="alpha-local",
                device="SIM-1",
                consumer=_CONSUMER_ID,
            )
            release_trust.assert_called_once_with(
                target="alpha-local",
                platform_name="ios-simulator",
                device="SIM-1",
                lease_id=_LEASE_ID,
            )

    def test_prepared_receipt_write_failure_releases_unhanded_lease(self) -> None:
        calls = 0
        real_writer = stackctl._write_managed_preparation_receipt

        def fail_prepared_write(path: Path, payload: dict[str, Any]) -> str:
            nonlocal calls
            calls += 1
            if payload.get("status") == "prepared":
                raise OSError("receipt fsync failed")
            return real_writer(path, payload)

        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            result = self._prepare(
                Path(temporary),
                patches,
                _write_managed_preparation_receipt=mock.patch.object(
                    stackctl,
                    "_write_managed_preparation_receipt",
                    side_effect=fail_prepared_write,
                ),
            )
            mocks = result.pop("_mocks")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["firstBlocker"], "APP.PREPARATION.receipt_invalid")
            self.assertGreaterEqual(calls, 2)
            mocks["release_consumer_lease"].assert_called_once_with(
                target="alpha-local",
                device="SIM-1",
                consumer=_CONSUMER_ID,
            )

    def test_otp_journey_failure_blocks_with_blocked_receipt(self) -> None:
        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            result = self._prepare(
                Path(temporary),
                patches,
                _managed_strict_preflight=mock.patch.object(
                    stackctl,
                    "_managed_strict_preflight",
                    wraps=stackctl._managed_strict_preflight,
                ),
                command_app_debug_preflight=mock.patch.object(
                    stackctl,
                    "command_app_debug_preflight",
                    return_value={
                        "exitCode": 2,
                        "status": "gate_block",
                        "firstBlocker": "APP.LAUNCH.runtime_dependency_unavailable",
                        "details": ["login journey failed: OTP was not accepted"],
                        "warnings": [],
                    },
                ),
                command_app_content_preflight=mock.patch.object(
                    stackctl,
                    "command_app_content_preflight",
                    side_effect=AssertionError(
                        "debug preflight failure must stop the chain"
                    ),
                ),
            )
            result.pop("_mocks")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(
                result["firstBlocker"], "APP.PREPARATION.strict_preflight_failed"
            )
            self.assertTrue(
                any("OTP was not accepted" in item for item in result["details"])
            )
            receipt = json.loads(Path(result["receiptPath"]).read_bytes())
            self.assertEqual(receipt["status"], "blocked")
            self.assertEqual(
                receipt["firstBlocker"], "APP.PREPARATION.strict_preflight_failed"
            )

    def test_media_probe_failure_blocks_with_blocked_receipt(self) -> None:
        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            readiness_path = Path(temporary) / "release-readiness.json"
            readiness_path.write_text(
                json.dumps(_readiness_payload(), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = self._prepare(
                Path(temporary),
                patches,
                _managed_strict_preflight=mock.patch.object(
                    stackctl,
                    "_managed_strict_preflight",
                    wraps=stackctl._managed_strict_preflight,
                ),
                command_app_debug_preflight=mock.patch.object(
                    stackctl,
                    "command_app_debug_preflight",
                    return_value=_passed_debug_preflight(_binding(readiness_path)),
                ),
                command_app_content_preflight=mock.patch.object(
                    stackctl,
                    "command_app_content_preflight",
                    return_value={
                        "exitCode": 2,
                        "status": "gate_block",
                        "details": [
                            "release probe media bytes are unavailable: typed_video"
                        ],
                    },
                ),
            )
            result.pop("_mocks")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(
                result["firstBlocker"], "APP.PREPARATION.strict_preflight_failed"
            )
            self.assertTrue(
                any("typed_video" in item for item in result["details"])
            )
            receipt = json.loads(Path(result["receiptPath"]).read_bytes())
            self.assertEqual(receipt["status"], "blocked")

    def test_strict_preflight_warning_status_is_upgraded_to_typed_block(self) -> None:
        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            readiness_path = Path(temporary) / "release-readiness.json"
            readiness_path.write_text(
                json.dumps(_readiness_payload(), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            binding = _binding(readiness_path)
            warning_payload = {
                **_passed_debug_preflight(binding),
                "status": "warning",
                "warnings": [
                    "readiness.content: content-live components are GATE_BLOCK"
                ],
            }
            result = self._prepare(
                Path(temporary),
                patches,
                _managed_strict_preflight=mock.patch.object(
                    stackctl,
                    "_managed_strict_preflight",
                    wraps=stackctl._managed_strict_preflight,
                ),
                command_app_debug_preflight=mock.patch.object(
                    stackctl,
                    "command_app_debug_preflight",
                    return_value=warning_payload,
                ),
                command_app_content_preflight=mock.patch.object(
                    stackctl,
                    "command_app_content_preflight",
                    side_effect=AssertionError(
                        "warning upgrade must stop before content preflight"
                    ),
                ),
            )
            result.pop("_mocks")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(
                result["firstBlocker"], "APP.PREPARATION.strict_preflight_failed"
            )
            self.assertTrue(
                any("readiness.content" in item for item in result["details"])
            )


if __name__ == "__main__":
    unittest.main()
