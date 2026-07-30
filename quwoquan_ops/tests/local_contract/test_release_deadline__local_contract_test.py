from __future__ import annotations

import sys
import time
import unittest

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


if __name__ == "__main__":
    unittest.main()
