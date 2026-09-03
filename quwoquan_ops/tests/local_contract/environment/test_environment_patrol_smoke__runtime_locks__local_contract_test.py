"""environment patrol smoke：执行锁与本地 runtime 使用锁契约。"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke.environment_patrol_smoke import runtime_locks


class EnvironmentPatrolSmokeRuntimeLocksTest(unittest.TestCase):
    def test_local_target_acquires_and_registers_both_locks(self) -> None:
        execution_lock = mock.Mock()
        runtime_use_lock = mock.Mock()
        with (
            mock.patch.object(
                runtime_locks,
                "_acquire_patrol_execution_lock",
                return_value=execution_lock,
            ) as acquire_execution,
            mock.patch.object(
                runtime_locks, "_is_local_target", return_value=True
            ),
            mock.patch.object(
                runtime_locks,
                "_local_target_for_environment_alias",
                return_value="gamma-local",
            ) as resolve_target,
            mock.patch.object(
                runtime_locks,
                "acquire_local_runtime_use_lock",
                return_value=runtime_use_lock,
            ) as acquire_runtime,
            mock.patch.object(runtime_locks.atexit, "register") as register,
        ):
            acquired = runtime_locks.acquire_patrol_runtime_locks(
                env_name="local-gamma",
                target="test/user_acceptance/example_test.dart",
            )

        self.assertTrue(acquired)
        acquire_execution.assert_called_once_with(
            env_name="local-gamma",
            target="test/user_acceptance/example_test.dart",
        )
        resolve_target.assert_called_once_with("local-gamma")
        acquire_runtime.assert_called_once_with(
            target="gamma-local",
            purpose="environment-patrol-smoke",
        )
        self.assertEqual(
            [call.args[0] for call in register.call_args_list],
            [execution_lock.close, runtime_use_lock.close],
        )

    def test_nonlocal_target_acquires_only_the_execution_lock(self) -> None:
        execution_lock = mock.Mock()
        with (
            mock.patch.object(
                runtime_locks,
                "_acquire_patrol_execution_lock",
                return_value=execution_lock,
            ),
            mock.patch.object(
                runtime_locks, "_is_local_target", return_value=False
            ),
            mock.patch.object(
                runtime_locks, "acquire_local_runtime_use_lock"
            ) as acquire_runtime,
            mock.patch.object(runtime_locks.atexit, "register") as register,
        ):
            acquired = runtime_locks.acquire_patrol_runtime_locks(
                env_name="prod",
                target="test/user_acceptance/example_test.dart",
            )

        self.assertTrue(acquired)
        acquire_runtime.assert_not_called()
        register.assert_called_once_with(execution_lock.close)

    def test_runtime_lock_failure_closes_execution_lock_and_gate_blocks(self) -> None:
        execution_lock = mock.Mock()
        stderr = io.StringIO()
        with (
            mock.patch.object(
                runtime_locks,
                "_acquire_patrol_execution_lock",
                return_value=execution_lock,
            ),
            mock.patch.object(
                runtime_locks, "_is_local_target", return_value=True
            ),
            mock.patch.object(
                runtime_locks,
                "_local_target_for_environment_alias",
                return_value="gamma-local",
            ),
            mock.patch.object(
                runtime_locks,
                "acquire_local_runtime_use_lock",
                side_effect=RuntimeError("runtime is busy"),
            ),
            mock.patch.object(runtime_locks.atexit, "register"),
            mock.patch.object(runtime_locks.sys, "stderr", stderr),
        ):
            acquired = runtime_locks.acquire_patrol_runtime_locks(
                env_name="local-gamma",
                target="test/user_acceptance/example_test.dart",
            )

        self.assertFalse(acquired)
        execution_lock.close.assert_called_once_with()
        self.assertEqual(stderr.getvalue(), "GATE_BLOCK: runtime is busy\n")


if __name__ == "__main__":
    unittest.main()
