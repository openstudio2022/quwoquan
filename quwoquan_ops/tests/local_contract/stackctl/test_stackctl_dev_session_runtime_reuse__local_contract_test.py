"""dev-session 运行时观察复用、受限工作负载与固定运行时身份语义。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""
from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl

from quwoquan_ops.tests.support.stackctl_dev_session_test_support import (
    _ok,
    _handoff_completed,
    _runtime_started,
    _runtime_started_with_identity,
    StackctlDevSessionTestBase,
)


class StackctlDevSessionRuntimeReuseTest(StackctlDevSessionTestBase):
    def test_running_full_runtime_is_observed_but_never_repackaged(self) -> None:
        events: list[str] = []
        full_attempt = {
            "attemptId": "full-1",
            "status": "running",
            "workload": "full",
        }

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "command_package",
                side_effect=AssertionError("test_live must not package"),
            ),
            mock.patch.object(
                stackctl,
                "command_up",
                side_effect=AssertionError("hot session must not call up"),
            ),
            mock.patch.object(
                stackctl,
                "command_app_debug_preflight",
                side_effect=lambda _args: events.append("preflight")
                or {**_ok("preflight"), "status": "passed", "warnings": []},
            ),
            mock.patch.object(
                stackctl,
                "command_health",
                side_effect=lambda _args: events.append("health") or _ok("health"),
            ),
            mock.patch.object(stackctl.subprocess, "run", return_value=_handoff_completed()),
            mock.patch.object(
                stackctl,
                "_start_mutable_test_live_runtime",
                return_value=_runtime_started("beta", "beta-local"),
            ),
            mock.patch.object(
                stackctl,
                "_mutable_workspace_snapshot",
                return_value={"sourceRevision": "a", "workspaceStatusDigest": "same"},
            ),
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                side_effect=lambda target: (
                    full_attempt if target == "beta-local" else None
                ),
            ),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                side_effect=lambda target, workload: (
                    full_attempt
                    if target == "beta-local" and workload == "full"
                    else None
                ),
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="beta",
                target="beta-local",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["sessionKind"], "mutable")
        self.assertTrue(result["fullRuntimeSelected"])
        self.assertEqual(events, ["preflight", "health"])
        self.assertEqual(
            [phase["name"] for phase in result["phases"]],
            [
                "mutable-materialize",
                "compose-render",
                "compose-up",
                "preflight",
                "launcher-handoff",
                "health",
            ],
        )

    def test_running_bounded_workload_blocks_before_package(self) -> None:
        for workload in ("content-release", "content-commercial"):
            with self.subTest(workload=workload):
                attempt = {
                    "attemptId": f"{workload}-1",
                    "status": "running",
                    "workload": workload,
                }
                with (
                    tempfile.TemporaryDirectory() as temporary,
                    mock.patch.object(
                        stackctl,
                        "command_package",
                        side_effect=AssertionError("package must be skipped"),
                    ),
                    mock.patch.object(
                        stackctl,
                        "command_up",
                        side_effect=AssertionError("up must be skipped"),
                    ),
                    mock.patch.object(
                        stackctl,
                        "command_health",
                        side_effect=AssertionError("health must be skipped"),
                    ),
                    mock.patch.object(
                        stackctl,
                        "load_startup_attempt",
                        side_effect=lambda target: (
                            attempt if target == "alpha-local" else None
                        ),
                    ),
                    mock.patch.object(
                        stackctl,
                        "load_workload_startup_attempt",
                        side_effect=lambda target, scoped_workload: (
                            attempt
                            if target == "alpha-local"
                            and scoped_workload == workload
                            else None
                        ),
                    ),
                ):
                    result = stackctl._run_dev_session_target(
                        environment="alpha",
                        target="alpha-local",
                        device_id="",
                        launch_app_requested=False,
                        report_dir=Path(temporary),
                    )

                self.assertEqual(result["exitCode"], 2)
                self.assertEqual(
                    result["blockerKind"],
                    "runtime_workload_conflict",
                )
                self.assertEqual(result["activeRuntime"]["workload"], workload)
                self.assertEqual(
                    result["activeRuntime"]["attemptId"],
                    f"{workload}-1",
                )
                self.assertIn(
                    f"down --target alpha-local --workload {workload}",
                    result["details"][-1],
                )
                self.assertEqual(result["phases"], [])

    def test_stale_startup_receipt_is_warning_for_test_live(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "_dev_session_runtime_preflight",
                side_effect=ValueError("startup attempt target identity mismatch"),
            ),
            mock.patch.object(stackctl.subprocess, "run", return_value=_handoff_completed()),
            mock.patch.object(
                stackctl,
                "_start_mutable_test_live_runtime",
                return_value=_runtime_started(),
            ),
            mock.patch.object(
                stackctl,
                "command_app_debug_preflight",
                return_value={**_ok("preflight"), "status": "passed", "warnings": []},
            ),
            mock.patch.object(stackctl, "command_health", return_value=_ok("health")),
            mock.patch.object(
                stackctl,
                "_mutable_workspace_snapshot",
                return_value={"sourceRevision": "a", "workspaceStatusDigest": "same"},
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="alpha",
                target="alpha-local",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["status"], "warning")
        self.assertIn("stale runtime receipt ignored", result["warnings"][0])

    def test_stopped_bounded_receipt_allows_mutable_session(self) -> None:
        events: list[str] = []
        stopped = {
            "attemptId": "content-release-old",
            "status": "stopped",
            "workload": "content-release",
        }

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "command_package",
                side_effect=AssertionError("test_live must not package"),
            ),
            mock.patch.object(
                stackctl,
                "command_up",
                side_effect=AssertionError("test_live must not use immutable up"),
            ),
            mock.patch.object(
                stackctl,
                "command_app_debug_preflight",
                side_effect=lambda _args: events.append("preflight")
                or {**_ok("preflight"), "status": "passed", "warnings": []},
            ),
            mock.patch.object(
                stackctl,
                "command_health",
                side_effect=lambda _args: events.append("health") or _ok("health"),
            ),
            mock.patch.object(stackctl.subprocess, "run", return_value=_handoff_completed()),
            mock.patch.object(
                stackctl,
                "_start_mutable_test_live_runtime",
                return_value=_runtime_started("gamma", "gamma-local"),
            ),
            mock.patch.object(
                stackctl,
                "_mutable_workspace_snapshot",
                return_value={"sourceRevision": "a", "workspaceStatusDigest": "same"},
            ),
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                side_effect=lambda target, workload: (
                    stopped
                    if target == "gamma-local" and workload == "content-release"
                    else None
                ),
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="gamma",
                target="gamma-local",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["sessionKind"], "mutable")
        self.assertEqual(events, ["preflight", "health"])

    def test_active_workload_receipt_blocks_when_target_receipt_is_stale(self) -> None:
        scoped_attempt = {
            "attemptId": "content-release-scoped-1",
            "status": "running",
            "workload": "content-release",
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "command_package",
                side_effect=AssertionError("package must be skipped"),
            ),
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                side_effect=lambda target, workload: (
                    scoped_attempt
                    if target == "alpha-local" and workload == "content-release"
                    else None
                ),
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="alpha",
                target="alpha-local",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_workload_conflict")
        self.assertEqual(
            result["activeRuntime"]["receiptScope"],
            "workload:content-release",
        )

    def test_invalid_mutable_handoff_stops_after_running_before_health(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    args=["build_launcher_handoff.py"],
                    returncode=2,
                    stdout="",
                    stderr="unsafe production endpoint",
                ),
            ),
            mock.patch.object(stackctl, "_mutable_workspace_snapshot", return_value={}),
            mock.patch.object(
                stackctl,
                "_dev_session_runtime_preflight",
                return_value=(None, None),
            ),
            mock.patch.object(
                stackctl,
                "_start_mutable_test_live_runtime",
                return_value=_runtime_started(),
            ),
            mock.patch.object(
                stackctl,
                "command_app_debug_preflight",
                return_value={**_ok("preflight"), "status": "passed", "warnings": []},
            ),
            mock.patch.object(
                stackctl,
                "command_health",
                side_effect=AssertionError("health must be skipped"),
            ),
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                return_value=None,
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="gamma",
                target="gamma-local",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "launcher_handoff_invalid")
        self.assertIn("unsafe production endpoint", result["details"][0])

    def test_all_nonprod_is_serial_and_failure_stops_later_targets(self) -> None:
        visited: list[str] = []
        def run_target(**kwargs: object) -> dict[str, object]:
            target = str(kwargs["target"])
            visited.append(target)
            if target == "beta-local":
                return {
                    "exitCode": 2,
                    "sessionKind": "cold",
                    "blockerKind": "runtime_health_failed",
                    "details": ["beta failed"],
                    "fullRuntimeSelected": False,
                    "phases": [],
                }
            return {
                "exitCode": 0,
                "sessionKind": "cold",
                "blockerKind": "",
                "details": [],
                "fullRuntimeSelected": True,
                "phases": [],
            }

        args = argparse.Namespace(
            command="dev-session",
            all_nonprod=True,
            env="",
            target="",
            device_id="",
            launch_app=False,
            report_dir="",
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary),
            ),
            mock.patch.object(
                stackctl,
                "_local_stack_operation_lock",
                return_value=contextlib.nullcontext(),
            ),
            mock.patch.object(stackctl, "_run_dev_session_target", side_effect=run_target),
            mock.patch.object(
                stackctl,
                "command_down",
                side_effect=AssertionError("mutable dev-session must not auto-down"),
            ),
        ):
            result = stackctl.command_dev_session(args)

        self.assertEqual(visited, ["alpha-local", "beta-local"])
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_health_failed")

    def test_all_nonprod_cross_target_bounded_conflict_preserves_runtime(self) -> None:
        bounded_attempt = {
            "attemptId": "commercial-beta-1",
            "status": "running",
            "workload": "content-commercial",
        }
        args = argparse.Namespace(
            command="dev-session",
            all_nonprod=True,
            env="",
            target="",
            device_id="",
            launch_app=False,
            report_dir="",
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary),
            ),
            mock.patch.object(
                stackctl,
                "_local_stack_operation_lock",
                return_value=contextlib.nullcontext(),
            ),
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                side_effect=lambda target: (
                    bounded_attempt if target == "beta-local" else None
                ),
            ),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                side_effect=lambda target, workload: (
                    bounded_attempt
                    if target == "beta-local"
                    and workload == "content-commercial"
                    else None
                ),
            ),
            mock.patch.object(
                stackctl,
                "command_package",
                side_effect=AssertionError("package must be skipped"),
            ),
            mock.patch.object(
                stackctl,
                "command_down",
                side_effect=AssertionError("active bounded runtime must not be downed"),
            ),
        ):
            result = stackctl.command_dev_session(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_workload_conflict")
        self.assertEqual(len(result["sessions"]), 1)
        self.assertEqual(result["sessions"][0]["target"], "alpha-local")
        self.assertEqual(
            result["sessions"][0]["activeRuntime"],
            {
                "target": "beta-local",
                "workload": "content-commercial",
                "attemptId": "commercial-beta-1",
                "status": "running",
                "receiptScope": "target",
            },
        )

    def test_bounded_workload_reuses_full_and_targeted_down_is_noop(self) -> None:
        fixed_identity = {
            "candidateDigest": "sha256:" + "1" * 64,
            "configurationDigest": "sha256:" + "2" * 64,
            "providerRuntimeDigest": "sha256:" + "3" * 64,
            "observabilityLogSinkDigest": "sha256:" + "4" * 64,
            "imageComposition": {"identity": "full-oci"},
        }
        full_attempt = {
            "attemptId": "full-1",
            "status": "running",
            "workload": "full",
            **fixed_identity,
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary),
            ),
            mock.patch.object(
                stackctl,
                "command_health",
                return_value={"exitCode": 0, "details": ["full health ok"]},
            ),
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value=full_attempt,
            ),
            mock.patch.object(
                stackctl,
                "_fixed_candidate_runtime_identity",
                return_value=fixed_identity,
            ),
            mock.patch.object(
                stackctl,
                "assert_active_deployment_candidate_snapshot",
            ),
        ):
            reused = stackctl._reuse_running_full_for_bounded_workload(
                argparse.Namespace(workload="content-release"),
                candidate_snapshot={"baselineId": fixed_identity["candidateDigest"]},
                target_name="alpha-local",
                env_name="alpha",
                report_target="alpha-local",
                report_dir=Path(temporary) / "up",
                started_monotonic=0.0,
                started_at="2026-01-01T00:00:00Z",
            )
            down = stackctl._bounded_workload_down_decision(
                argparse.Namespace(
                    target="alpha-local",
                    workload="content-release",
                    report_dir=str(Path(temporary) / "down"),
                )
            )

        self.assertIsNotNone(reused)
        self.assertTrue(reused["runtimeReused"])
        self.assertIsNotNone(down)
        self.assertTrue(down["runtimeReused"])
        self.assertEqual(full_attempt["status"], "running")

    def test_fixed_runtime_identity_uses_one_snapshot_for_every_component(
        self,
    ) -> None:
        baseline_id = "sha256:" + "1" * 64
        candidate_root = Path("/candidate/alpha")
        snapshot = {"baselineId": baseline_id, "manifest": {}}
        startup_images = {
            "environment": "alpha",
            "target": "alpha-local",
            "imageVersion": "sha256:" + "5" * 64,
            "images": {"api": "sha256:" + "6" * 64},
        }
        provider = {
            "composition": {"runtimeCompositionDigest": "sha256:" + "3" * 64}
        }
        observability = {
            "composition": {"composeDigest": "sha256:" + "4" * 64}
        }
        with (
            mock.patch.object(
                stackctl,
                "_fixed_candidate_identity",
                return_value=(baseline_id, candidate_root, {}),
            ) as fixed_identity,
            mock.patch.object(
                stackctl,
                "_candidate_bindings_from_snapshot",
                return_value=(provider, observability),
            ) as candidate_bindings,
            mock.patch.object(
                stackctl,
                "_load_package_bound_local_image_composition",
                return_value={
                    "configurationDigest": "sha256:" + "2" * 64,
                    "startupImageComposition": startup_images,
                },
            ) as image_composition,
        ):
            actual = stackctl._fixed_candidate_runtime_identity(
                snapshot,
                environment_name="alpha",
                target_name="alpha-local",
            )

        self.assertEqual(
            actual,
            {
                "candidateDigest": baseline_id,
                "configurationDigest": "sha256:" + "2" * 64,
                "providerRuntimeDigest": "sha256:" + "3" * 64,
                "observabilityLogSinkDigest": "sha256:" + "4" * 64,
                "imageComposition": startup_images,
            },
        )
        fixed_identity.assert_called_once_with(
            snapshot,
            environment_name="alpha",
            target_name="alpha-local",
        )
        candidate_bindings.assert_called_once_with(
            snapshot,
            environment_name="alpha",
            target_name="alpha-local",
        )
        image_composition.assert_called_once_with(
            "alpha",
            "alpha-local",
            candidate_snapshot=snapshot,
        )

    def test_bounded_workload_rejects_receipt_identity_drift_and_pointer_switch(
        self,
    ) -> None:
        expected = {
            "candidateDigest": "sha256:" + "1" * 64,
            "configurationDigest": "sha256:" + "2" * 64,
            "providerRuntimeDigest": "sha256:" + "3" * 64,
            "observabilityLogSinkDigest": "sha256:" + "4" * 64,
            "imageComposition": {"identity": "full-oci"},
        }
        snapshot = {"baselineId": expected["candidateDigest"]}
        for field in expected:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                receipt = {
                    "attemptId": "full-1",
                    "status": "running",
                    "workload": "full",
                    **expected,
                }
                receipt[field] = None
                with (
                    mock.patch.object(
                        stackctl,
                        "load_startup_attempt",
                        return_value=receipt,
                    ),
                    mock.patch.object(
                        stackctl,
                        "_fixed_candidate_runtime_identity",
                        return_value=expected,
                    ),
                    mock.patch.object(
                        stackctl,
                        "assert_active_deployment_candidate_snapshot",
                    ) as snapshot_check,
                    mock.patch.object(stackctl, "_write_summary_bundle"),
                ):
                    result = stackctl._reuse_running_full_for_bounded_workload(
                        argparse.Namespace(workload="content-release"),
                        candidate_snapshot=snapshot,
                        target_name="alpha-local",
                        env_name="alpha",
                        report_target="alpha-local",
                        report_dir=Path(temporary),
                        started_monotonic=0.0,
                        started_at="2026-01-01T00:00:00Z",
                    )

                self.assertEqual(result["exitCode"], 2)
                self.assertEqual(
                    result["blockerKind"],
                    "candidate_identity_mismatch",
                )
                snapshot_check.assert_not_called()

        with tempfile.TemporaryDirectory() as temporary, (
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value={
                    "attemptId": "full-1",
                    "status": "running",
                    "workload": "full",
                    **expected,
                },
            )
        ), mock.patch.object(
            stackctl,
            "_fixed_candidate_runtime_identity",
            return_value=expected,
        ), mock.patch.object(
            stackctl,
            "assert_active_deployment_candidate_snapshot",
            side_effect=ValueError("pointer switched"),
        ), mock.patch.object(stackctl, "_write_summary_bundle"):
            result = stackctl._reuse_running_full_for_bounded_workload(
                argparse.Namespace(workload="content-release"),
                candidate_snapshot=snapshot,
                target_name="alpha-local",
                env_name="alpha",
                report_target="alpha-local",
                report_dir=Path(temporary),
                started_monotonic=0.0,
                started_at="2026-01-01T00:00:00Z",
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "candidate_pointer_changed")

    def test_bounded_workload_rejects_unhealthy_full_runtime(self) -> None:
        expected = {
            "candidateDigest": "sha256:" + "1" * 64,
            "configurationDigest": "sha256:" + "2" * 64,
            "providerRuntimeDigest": "sha256:" + "3" * 64,
            "observabilityLogSinkDigest": "sha256:" + "4" * 64,
            "imageComposition": {"identity": "full-oci"},
        }
        with tempfile.TemporaryDirectory() as temporary, (
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value={
                    "attemptId": "full-1",
                    "status": "running",
                    "workload": "full",
                    **expected,
                },
            )
        ), mock.patch.object(
            stackctl,
            "_fixed_candidate_runtime_identity",
            return_value=expected,
        ), mock.patch.object(
            stackctl,
            "assert_active_deployment_candidate_snapshot",
        ), mock.patch.object(
            stackctl,
            "command_health",
            return_value={
                "exitCode": 2,
                "details": ["api-edge healthz failed"],
            },
        ), mock.patch.object(stackctl, "_write_summary_bundle"):
            result = stackctl._reuse_running_full_for_bounded_workload(
                argparse.Namespace(workload="content-release"),
                candidate_snapshot={"baselineId": expected["candidateDigest"]},
                target_name="alpha-local",
                env_name="alpha",
                report_target="alpha-local",
                report_dir=Path(temporary),
                started_monotonic=0.0,
                started_at="2026-01-01T00:00:00Z",
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_health_failed")

