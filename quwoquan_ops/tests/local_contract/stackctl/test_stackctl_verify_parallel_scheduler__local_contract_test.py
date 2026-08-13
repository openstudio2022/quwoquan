"""Bounded stackctl verify waves and resource isolation contracts.

spec_ref: specs/feature-tree/runtime/runtime-testinfra/spec.md#sit-002.t3
"""

from __future__ import annotations

import subprocess
import unittest
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
