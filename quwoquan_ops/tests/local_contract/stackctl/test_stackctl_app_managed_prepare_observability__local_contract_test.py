"""Managed strict preflight 的 mutable observability identity 与迁移恢复。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""
from __future__ import annotations

import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from quwoquan_ops.cli import stackctl

_DIGEST = "sha256:" + "a" * 64


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
        "schema": stackctl._DATA_READINESS_SCHEMA,
        "releaseId": "alpha-slice-003",
        "verifyRunId": "verify-20260830T1600Z",
        "manifestDigest": _DIGEST,
        "readinessPhase": "research",
        "passed": True,
    }


def _binding(readiness_path: Path) -> dict[str, Any]:
    import hashlib

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


class ManagedObservabilityRuntimeTest(unittest.TestCase):
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
        ]

    def test_prod_sim_uses_canonical_occupancy_without_receipt_loaders(self) -> None:
        topology = stackctl.load_environment_topology()
        real_startup = stackctl.load_startup_attempt
        real_workload = stackctl.load_workload_startup_attempt
        startup_targets: list[str] = []
        workload_targets: list[str] = []

        def load_startup(target: str) -> Any:
            if target == "prod-sim":
                raise AssertionError("prod-sim must not use immutable receipt loader")
            startup_targets.append(target)
            return real_startup(target)

        def load_workload(target: str, workload: str) -> Any:
            if target == "prod-sim":
                raise AssertionError("prod-sim must not use workload receipt loader")
            workload_targets.append(target)
            return real_workload(target, workload)

        with (
            mock.patch.object(stackctl, "load_startup_attempt", side_effect=load_startup),
            mock.patch.object(
                stackctl, "load_workload_startup_attempt", side_effect=load_workload
            ),
            mock.patch.object(stackctl, "load_test_live_startup_attempt", return_value=None),
            mock.patch.object(stackctl, "read_stale_test_live_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl, "active_conflicting_local_targets", return_value=()
            ),
        ):
            _requested, conflict = stackctl._dev_session_runtime_preflight(
                topology=topology,
                target="alpha-local",
            )

        self.assertIsNone(conflict)
        self.assertNotIn("prod-sim", startup_targets)
        self.assertNotIn("prod-sim", workload_targets)

        with (
            mock.patch.object(stackctl, "load_startup_attempt", side_effect=load_startup),
            mock.patch.object(
                stackctl, "load_workload_startup_attempt", side_effect=load_workload
            ),
            mock.patch.object(stackctl, "load_test_live_startup_attempt", return_value=None),
            mock.patch.object(stackctl, "read_stale_test_live_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl,
                "active_conflicting_local_targets",
                return_value=("prod-sim",),
            ),
        ):
            _requested, conflict = stackctl._dev_session_runtime_preflight(
                topology=topology,
                target="alpha-local",
            )

        self.assertEqual(conflict["target"], "prod-sim")
        self.assertEqual(conflict["receiptScope"], "canonical-occupancy")

    def test_fresh_start_writes_and_reuses_real_test_live_receipt(self) -> None:
        from quwoquan_ops.cli.lib import test_live_startup_attempt_receipt as receipt

        plan = {
            "schema": "stackctl.mutable_test_live_runtime",
            "environment": "alpha",
            "target": "alpha-local",
            "composeProject": "quwoquan_alpha_test_live",
            "composeDigest": "sha256:" + "1" * 64,
            "configurationDigest": "sha256:" + "2" * 64,
            "providerRuntimeDigest": "sha256:" + "3" * 64,
            "observabilityLogSinkDigest": "sha256:" + "9" * 64,
            "portProfile": "alpha-local",
            "portBlock": {"start": 17000, "end": 17999},
            "publishedPorts": [
                {"role": "api-edge", "hostPort": 17000, "protocol": "tcp"}
            ],
            "tlsProfile": "local-managed",
            "resolverHandoffDigest": "sha256:" + "4" * 64,
            "publicWebPackage": {
                "environment": "alpha",
                "packageVersion": "web-release-alpha",
                "manifestDigest": "sha256:" + "7" * 64,
                "contentDigest": "sha256:" + "8" * 64,
                "publicOrigin": "https://alpha.quwoquan.com:17000",
            },
            "workspaceIdentity": {
                "sourceRevision": "a" * 40,
                "workspaceStatusDigest": "sha256:" + "5" * 64,
                "mutableStateDigest": "sha256:" + "6" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_root = root / "runs" / "dev-session-alpha"
            with (
                mock.patch.object(receipt, "target_process_dir", return_value=root / "process"),
                mock.patch.object(receipt, "env_runs_root", return_value=root / "runs"),
                mock.patch.object(receipt, "load_environment_topology", wraps=receipt.load_environment_topology),
                mock.patch.object(receipt, "load_port_manifest", wraps=receipt.load_port_manifest),
            ):
                prepared = receipt.transition_test_live_startup_attempt(
                    environment="alpha",
                    target="alpha-local",
                    attempt_id="alpha-test-live-fresh-start",
                    status="prepared",
                    runtime_plan=plan,
                    run_root=run_root,
                )
                receipt.transition_test_live_startup_attempt(
                    environment="alpha",
                    target="alpha-local",
                    attempt_id=prepared["attemptId"],
                    status="partial",
                    runtime_plan=plan,
                    run_root=run_root,
                )
                running = receipt.transition_test_live_startup_attempt(
                    environment="alpha",
                    target="alpha-local",
                    attempt_id=prepared["attemptId"],
                    status="running",
                    runtime_plan=plan,
                    run_root=run_root,
                )
                with mock.patch.object(
                    stackctl,
                    "_dev_session_resume_running_mutable_runtime",
                    return_value=(
                        {"startupAttempt": running, "runtime": plan},
                        [],
                    ),
                ) as inspect_runtime:
                    reused = stackctl._managed_inspect_running_full_runtime(
                        environment="alpha",
                        target="alpha-local",
                        immutable_attempt=None,
                        workspace_snapshot=plan["workspaceIdentity"],
                    )

        self.assertEqual(reused["startupAttempt"]["attemptId"], prepared["attemptId"])
        self.assertTrue(reused["reused"])
        inspect_runtime.assert_called_once()

    def test_stale_receipt_replacement_requires_zero_runtime_residue(self) -> None:
        clean_patches = (
            mock.patch.object(stackctl, "active_consumer_leases", return_value=[]),
            mock.patch.object(
                stackctl, "_mutable_test_live_container_ids", return_value=[]
            ),
            mock.patch.object(
                stackctl, "_mutable_test_live_resource_names", return_value=[]
            ),
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "load_port_manifest", return_value={}),
            mock.patch.object(
                stackctl,
                "project_canonical_runtime_owned_ports",
                return_value=[
                    {"role": "api-edge", "hostPort": 17000, "protocol": "tcp"}
                ],
            ),
            mock.patch.object(
                stackctl,
                "_runtime_owned_port_occupancy_report",
                return_value={"publishedEndpoints": []},
            ),
            mock.patch.object(
                stackctl,
                "bounded_replace_stale_test_live_startup_attempt",
                return_value={"attemptId": "alpha-old-generation"},
            ),
        )
        with contextlib.ExitStack() as patches:
            mocks = [patches.enter_context(patch) for patch in clean_patches]
            replaced = stackctl._bounded_replace_stale_managed_receipt(
                target="alpha-local"
            )
        self.assertEqual(replaced["attemptId"], "alpha-old-generation")
        mocks[-1].assert_called_once_with("alpha-local")

        with (
            mock.patch.object(stackctl, "active_consumer_leases", return_value=[]),
            mock.patch.object(
                stackctl, "_mutable_test_live_container_ids", return_value=["c0ffee"]
            ),
            mock.patch.object(
                stackctl, "_mutable_test_live_resource_names", return_value=[]
            ),
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "load_port_manifest", return_value={}),
            mock.patch.object(
                stackctl,
                "project_canonical_runtime_owned_ports",
                return_value=[],
            ),
            mock.patch.object(
                stackctl,
                "_runtime_owned_port_occupancy_report",
                return_value={"publishedEndpoints": []},
            ),
            mock.patch.object(
                stackctl,
                "bounded_replace_stale_test_live_startup_attempt",
                side_effect=AssertionError("live residue must retain the receipt"),
            ),
            self.assertRaisesRegex(ValueError, "live runtime residue"),
        ):
            stackctl._bounded_replace_stale_managed_receipt(target="alpha-local")

    def test_stale_receipt_is_bounded_replaced_before_fresh_start(self) -> None:
        stale = {
            "attemptId": "alpha-old-generation",
            "composeProject": "quwoquan_alpha_test_live",
        }
        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            for patch in self._base_patches():
                patches.enter_context(patch)
            preflight_results: list[Any] = [
                stackctl.InadmissibleCurrentTestLiveReceipt(
                    "alpha-local", "fields mismatch"
                ),
                (None, None),
            ]

            def preflight(**_kwargs: Any) -> Any:
                result = preflight_results.pop(0)
                if isinstance(result, Exception):
                    raise result
                return result

            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_dev_session_runtime_preflight",
                    side_effect=preflight,
                )
            )
            replace = patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_bounded_replace_stale_managed_receipt",
                    return_value=stale,
                )
            )
            start = patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_start_mutable_test_live_runtime",
                    return_value={
                        "exitCode": 0,
                        "startupAttempt": {"attemptId": "alpha-attempt-new"},
                    },
                )
            )
            resume_results = iter(
                [
                    (None, []),
                    (_resume_payload("alpha-attempt-new"), []),
                ]
            )
            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_managed_inspect_running_full_runtime",
                    side_effect=lambda **_kwargs: (
                        None
                        if (result := next(resume_results))[0] is None
                        else {
                            **result[0],
                            "reused": True,
                            "replaced": False,
                            "warnings": list(result[1]),
                        }
                    ),
                )
            )

            payload = stackctl._managed_runtime_ready(
                environment="alpha",
                target="alpha-local",
                report_dir=Path(temporary),
            )

        replace.assert_called_once_with(target="alpha-local")
        start.assert_called_once()
        self.assertFalse(payload["reused"])
        self.assertTrue(payload["replaced"])
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(
            payload["startupAttempt"]["attemptId"], "alpha-attempt-new"
        )

    def test_inadmissible_receipt_with_live_residue_is_preserved(self) -> None:
        first_detail = (
            "alpha-local current test-live startup receipt is inadmissible: "
            "fields mismatch"
        )
        with (
            contextlib.ExitStack() as patches,
            tempfile.TemporaryDirectory() as temporary,
        ):
            for patch in self._base_patches():
                patches.enter_context(patch)
            patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_dev_session_runtime_preflight",
                    side_effect=stackctl.InadmissibleCurrentTestLiveReceipt(
                        "alpha-local", "fields mismatch"
                    ),
                )
            )
            replace = patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_bounded_replace_stale_managed_receipt",
                    side_effect=ValueError(
                        "stale mutable startup receipt still describes live runtime residue"
                    ),
                )
            )
            start = patches.enter_context(
                mock.patch.object(
                    stackctl,
                    "_start_mutable_test_live_runtime",
                    side_effect=AssertionError("live residue must block fresh start"),
                )
            )
            with self.assertRaises(stackctl.ManagedPreparationBlocked) as raised:
                stackctl._managed_runtime_ready(
                    environment="alpha",
                    target="alpha-local",
                    report_dir=Path(temporary),
                )

        self.assertEqual(raised.exception.details[0], first_detail)
        self.assertIn("live runtime residue", raised.exception.details[1])
        replace.assert_called_once_with(target="alpha-local")
        start.assert_not_called()


class ManagedObservabilityStrictPreflightTest(unittest.TestCase):
    def test_strict_preflight_accepts_canonical_observability_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            readiness_path = Path(temporary) / "release-readiness.json"
            readiness_path.write_text(
                json.dumps(_readiness_payload(), sort_keys=True) + "\n",
                encoding="utf-8",
            )
            binding = _binding(readiness_path)
            debug = {
                **_passed_debug_preflight(binding),
                "startupAttempt": {
                    "status": "running",
                    "observabilityLogSinkDigest": "sha256:" + "7" * 64,
                },
            }
            with (
                mock.patch.object(
                    stackctl,
                    "command_app_debug_preflight",
                    return_value=debug,
                ),
                mock.patch.object(
                    stackctl,
                    "command_app_content_preflight",
                    return_value=_passed_content_preflight(binding),
                ),
            ):
                payloads = stackctl._managed_strict_preflight(
                    environment="alpha",
                    target="alpha-local",
                    content_binding=binding,
                    report_dir=Path(temporary) / "strict",
                )

        self.assertEqual(payloads["debugPayload"]["status"], "passed")
        self.assertEqual(payloads["debugPayload"]["warnings"], [])
        self.assertRegex(
            payloads["debugPayload"]["startupAttempt"][
                "observabilityLogSinkDigest"
            ],
            r"^sha256:[0-9a-f]{64}$",
        )



if __name__ == "__main__":
    unittest.main()
