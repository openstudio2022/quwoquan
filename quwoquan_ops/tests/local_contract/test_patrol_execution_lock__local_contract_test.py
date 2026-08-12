import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.patrol_execution_lock import (
    acquire_patrol_execution_lock,
)


class PatrolExecutionLockContractTest(unittest.TestCase):
    def test_direct_flutter_and_patrol_share_one_workspace_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "patrol.lock"
            first = acquire_patrol_execution_lock(
                env_name="alpha-local",
                target="direct-flutter-run:SIMULATOR",
                lock_path=lock_path,
            )
            self.addCleanup(first.close)

            with self.assertRaisesRegex(
                RuntimeError,
                "Patrol build workspace is already in use",
            ):
                acquire_patrol_execution_lock(
                    env_name="alpha-local",
                    target="homepage-feed",
                    lock_path=lock_path,
                )

            first.close()
            second = acquire_patrol_execution_lock(
                env_name="alpha-local",
                target="homepage-feed",
                lock_path=lock_path,
            )
            second.close()


if __name__ == "__main__":
    unittest.main()
