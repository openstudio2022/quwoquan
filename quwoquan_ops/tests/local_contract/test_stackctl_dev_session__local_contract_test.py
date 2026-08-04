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
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(stackctl, "command_package", return_value=_ok("package")),
            mock.patch.object(
                stackctl,
                "command_up",
                side_effect=AssertionError("hot session must not call up"),
            ),
            mock.patch.object(stackctl, "command_health", return_value=_ok("health")),
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value={
                    "attemptId": "full-1",
                    "status": "running",
                    "workload": "full",
                },
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
        self.assertEqual([phase["name"] for phase in result["phases"]], ["package", "up", "health"])

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

        def run_target(**kwargs: object) -> dict[str, object]:
            target = str(kwargs["target"])
            visited.append(target)
            if target == "beta-local":
                return {
                    "exitCode": 2,
                    "sessionKind": "cold",
                    "blockerKind": "runtime_health_failed",
                    "details": ["beta failed"],
                    "phases": [],
                }
            return {
                "exitCode": 0,
                "sessionKind": "cold",
                "blockerKind": "",
                "details": [],
                "phases": [],
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
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            mock.patch.object(stackctl, "_run_dev_session_target", side_effect=run_target),
            mock.patch.object(stackctl, "command_down", return_value=_ok("down")),
        ):
            result = stackctl.command_dev_session(args)

        self.assertEqual(visited, ["alpha-local", "beta-local"])
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_health_failed")

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
