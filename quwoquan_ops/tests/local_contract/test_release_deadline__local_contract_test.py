from __future__ import annotations

import sys
import time
import unittest
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.common import run


class ReleaseDeadlineContractTest(unittest.TestCase):
    def test_remaining_deadline_rejects_an_expired_cutoff(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "deadline has been reached"):
            stackctl._remaining_deadline_seconds(int(time.time()) - 1, "release")

    def test_subprocess_is_terminated_at_its_absolute_budget(self) -> None:
        result = run(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            timeout_seconds=0.05,
        )
        self.assertEqual(result.returncode, 124)
        self.assertIn("deterministic deadline", result.stderr)

    def test_operator_interrupt_is_forwarded_to_managed_process_group(self) -> None:
        process = mock.Mock()
        process.pid = 43120
        process.wait.side_effect = [KeyboardInterrupt, 0]
        with (
            mock.patch(
                "quwoquan_ops.cli.lib.common.subprocess.Popen",
                return_value=process,
            ),
            mock.patch("quwoquan_ops.cli.lib.common.os.killpg") as killpg,
        ):
            result = run(
                [sys.executable, "-c", "pass"],
                timeout_seconds=30,
            )

        killpg.assert_called_once_with(process.pid, __import__("signal").SIGINT)
        self.assertEqual(result.returncode, 130)
        self.assertIn("managed child process was stopped", result.stderr)


if __name__ == "__main__":
    unittest.main()
