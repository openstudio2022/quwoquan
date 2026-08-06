"""Dev sessions are the only package/up/health developer orchestration.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""
from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl


def _ok(summary: str) -> dict[str, object]:
    return {"exitCode": 0, "summary": summary, "details": [], "reportDir": summary}


class StackctlDevSessionTest(unittest.TestCase):
    def test_cold_session_runs_package_up_health_in_order(self) -> None:
        events: list[str] = []

        def invoke(name: str):
            def command(_args: argparse.Namespace) -> dict[str, object]:
                events.append(name)
                return _ok(name)

            return command

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(stackctl, "command_package", side_effect=invoke("package")),
            mock.patch.object(stackctl, "command_up", side_effect=invoke("up")),
            mock.patch.object(stackctl, "command_health", side_effect=invoke("health")),
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                return_value=None,
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="alpha",
                target="alpha-local",
                release_attestation="candidate.json",
                rollback_release_attestation="rollback.json",
                device_id="emulator-5554",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(events, ["package", "up", "health"])
        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["sessionKind"], "cold")
        self.assertIn("./run.sh --env alpha -d emulator-5554", result["details"][0])

    def test_hot_session_never_repeats_compose_up(self) -> None:
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
                side_effect=lambda _args: events.append("package") or _ok("package"),
            ),
            mock.patch.object(
                stackctl,
                "command_up",
                side_effect=AssertionError("hot session must not call up"),
            ),
            mock.patch.object(
                stackctl,
                "command_health",
                side_effect=lambda _args: events.append("health") or _ok("health"),
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
                release_attestation="candidate.json",
                rollback_release_attestation="rollback.json",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["sessionKind"], "hot")
        self.assertEqual(events, ["package", "health"])
        self.assertEqual([phase["name"] for phase in result["phases"]], ["package", "up", "health"])

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
                        release_attestation="candidate.json",
                        rollback_release_attestation="rollback.json",
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

    def test_stopped_bounded_receipt_allows_cold_session(self) -> None:
        events: list[str] = []
        stopped = {
            "attemptId": "content-release-old",
            "status": "stopped",
            "workload": "content-release",
        }

        def invoke(name: str):
            def command(_args: argparse.Namespace) -> dict[str, object]:
                events.append(name)
                return _ok(name)

            return command

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(stackctl, "command_package", side_effect=invoke("package")),
            mock.patch.object(stackctl, "command_up", side_effect=invoke("up")),
            mock.patch.object(stackctl, "command_health", side_effect=invoke("health")),
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
                release_attestation="candidate.json",
                rollback_release_attestation="rollback.json",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["sessionKind"], "cold")
        self.assertEqual(events, ["package", "up", "health"])

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
                release_attestation="candidate.json",
                rollback_release_attestation="rollback.json",
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

    def test_package_failure_stops_before_runtime(self) -> None:
        package_failure = {
            "exitCode": 2,
            "summary": "package blocked",
            "details": ["release attestation invalid"],
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(stackctl, "command_package", return_value=package_failure),
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
                release_attestation="candidate.json",
                rollback_release_attestation="rollback.json",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "package_failed")

    def test_all_nonprod_is_serial_and_failure_stops_later_targets(self) -> None:
        visited: list[str] = []
        down_targets: list[str] = []

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

        def down_target(args: argparse.Namespace) -> dict[str, object]:
            down_targets.append(str(args.target))
            return _ok("down")

        args = argparse.Namespace(
            command="dev-session",
            all_nonprod=True,
            env="",
            target="",
            release_attestation="candidate.json",
            rollback_release_attestation="rollback.json",
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
            mock.patch.object(stackctl, "_run_dev_session_target", side_effect=run_target),
            mock.patch.object(stackctl, "command_down", side_effect=down_target),
        ):
            result = stackctl.command_dev_session(args)

        self.assertEqual(visited, ["alpha-local", "beta-local"])
        self.assertEqual(down_targets, ["alpha-local"])
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
            release_attestation="candidate.json",
            rollback_release_attestation="rollback.json",
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
        full_attempt = {
            "attemptId": "full-1",
            "status": "running",
            "workload": "full",
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
                "load_startup_attempt",
                return_value=full_attempt,
            ),
        ):
            reused = stackctl._reuse_running_full_for_bounded_workload(
                argparse.Namespace(workload="content-release"),
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


if __name__ == "__main__":
    unittest.main()
