"""Bounded stackctl verify waves and resource isolation contracts.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t3
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path
from threading import Event, Lock
from unittest import mock

from quwoquan_ops.cli import stackctl


class _OverlapProbe:
    def __init__(self) -> None:
        self.lock = Lock()
        self.overlap = Event()
        self.active = 0
        self.peak = 0

    def enter(self) -> None:
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active >= 2:
                self.overlap.set()
        if not self.overlap.wait(timeout=1):
            raise RuntimeError("independent verify nodes did not overlap")

    def exit(self) -> None:
        with self.lock:
            self.active -= 1


def _passed(argv: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, 0, "passed", "")


class StackctlVerifyParallelSchedulerContractTest(unittest.TestCase):
    def test_static_gates_and_readiness_overlap_but_evidence_order_is_stable(
        self,
    ) -> None:
        probe = _OverlapProbe()

        def run(command, **_kwargs):
            probe.enter()
            try:
                return _passed(command)
            finally:
                probe.exit()

        commands = [["gate", str(index)] for index in range(4)]
        with mock.patch.object(stackctl, "run", side_effect=run):
            results, readiness, _wall_ms = stackctl._run_static_verify_wave(
                commands,
                target_name="gamma-local",
                readiness_call=lambda: {"exitCode": 0},
                max_concurrency=4,
            )

        self.assertGreaterEqual(probe.peak, 2)
        self.assertLessEqual(probe.peak, 4)
        self.assertEqual([item[0] for item in results], commands)
        self.assertEqual(readiness, {"exitCode": 0})

    def test_full_profiles_require_explicit_exit_without_a_content_track(self) -> None:
        # spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004
        for profile in ("baseline", "smoke", "integration", "release"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temporary:
                args = argparse.Namespace(
                    kind="topology", profile=profile, service="",
                    env="" if profile == "baseline" else "alpha",
                    target="" if profile == "baseline" else "alpha-local",
                    report_dir=temporary, test_data_request="",
                    data_release_id="release-1", data_verify_run_id="verify-1",
                    data_manifest_digest="sha256:" + "a" * 64,
                    data_lifecycle_exit_ref="exact-exit-ref",
                )

                def static_wave(_commands, *, target_name, readiness_call):
                    del target_name
                    if profile in {"integration", "release"}:
                        self.assertIsNotNone(readiness_call)
                        readiness_call()
                    else:
                        self.assertIsNone(readiness_call)
                    # 只截取真实编排传入的调用边界，不启动环境或下游 wave。
                    raise StopIteration("readiness boundary observed")

                with (
                    mock.patch.object(stackctl, "resolve_report_dir", return_value=Path(temporary)),
                    mock.patch.object(stackctl, "active_deployment_candidate_snapshot", return_value=None),
                    mock.patch.object(stackctl, "read_startup_attempt", return_value=None),
                    mock.patch.object(stackctl, "can_reuse_package", return_value=(True, "exact package")),
                    mock.patch.object(stackctl, "_selected_verify_commands", return_value=[]),
                    mock.patch.object(stackctl, "_run_static_verify_wave", side_effect=static_wave),
                    mock.patch.object(stackctl, "command_content_readiness", return_value={}) as readiness,
                    self.assertRaisesRegex(StopIteration, "readiness boundary observed"),
                ):
                    stackctl.command_verify(args)
                if profile in {"integration", "release"}:
                    readiness.assert_called_once()
                    request = readiness.call_args.args[0]
                    self.assertNotIn("phase", vars(request))
                    self.assertTrue(request.require_lifecycle_exit)
                    self.assertEqual(request.lifecycle_exit_ref, "exact-exit-ref")
                    self.assertEqual(request.verify_run_id, "verify-1")
                else:
                    readiness.assert_not_called()

    def test_profile_health_is_a_barrier_and_patrol_stays_serial(self) -> None:
        probe = _OverlapProbe()
        observed: list[str] = []
        active_patrol = 0
        patrol_lock = Lock()

        def execute(command, **_kwargs):
            nonlocal active_patrol
            name = command["name"]
            if name == "gamma-health":
                observed.append(name)
                return _passed(command["argv"])
            if name in {"api-a", "api-b"}:
                self.assertIn("gamma-health", observed)
                probe.enter()
                try:
                    observed.append(name)
                    return _passed(command["argv"])
                finally:
                    probe.exit()
            with patrol_lock:
                active_patrol += 1
                self.assertEqual(active_patrol, 1)
            try:
                self.assertIn("api-a", observed)
                self.assertIn("api-b", observed)
                observed.append(name)
                return _passed(command["argv"])
            finally:
                with patrol_lock:
                    active_patrol -= 1

        commands = [
            {"name": "gamma-health", "argv": ["health"]},
            {"name": "api-a", "argv": ["api-a"]},
            {"name": "api-b", "argv": ["api-b"]},
            {
                "name": "page-patrol",
                "argv": ["python3", "run_environment_patrol_smoke.py"],
            },
            {
                "name": "search-patrol",
                "argv": ["python3", "run_environment_patrol_smoke.py"],
            },
        ]
        with mock.patch.object(
            stackctl,
            "_run_profile_command",
            side_effect=execute,
        ):
            results = stackctl._run_profile_commands_parallel(
                commands,
                target_name="gamma-local",
                actor_context=None,
                max_concurrency=4,
            )

        self.assertGreaterEqual(probe.peak, 2)
        self.assertEqual([item[0]["name"] for item in results], [
            "gamma-health",
            "api-a",
            "api-b",
            "page-patrol",
            "search-patrol",
        ])
        self.assertLess(
            observed.index("page-patrol"),
            observed.index("search-patrol"),
        )
        self.assertTrue(all(not item[3] for item in results))

    def test_failed_health_skips_all_dependent_profile_nodes(self) -> None:
        commands = [
            {"name": "gamma-health", "argv": ["health"]},
            {"name": "api", "argv": ["api"]},
            {
                "name": "page-patrol",
                "argv": ["python3", "run_environment_patrol_smoke.py"],
            },
        ]
        with mock.patch.object(
            stackctl,
            "_run_profile_command",
            return_value=subprocess.CompletedProcess(["health"], 2, "", "down"),
        ) as execute:
            results = stackctl._run_profile_commands_parallel(
                commands,
                target_name="gamma-local",
                actor_context=None,
            )

        self.assertEqual(execute.call_count, 1)
        self.assertFalse(results[0][3])
        self.assertTrue(results[1][3])
        self.assertTrue(results[2][3])


if __name__ == "__main__":
    unittest.main()
