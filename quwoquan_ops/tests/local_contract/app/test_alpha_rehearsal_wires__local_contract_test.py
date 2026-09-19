"""Alpha 演练默认 response wire 必须可由 generated fromWire 派生。"""

from __future__ import annotations

import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.generate_alpha_rehearsal_wires import generate, output_path

ROOT = Path(__file__).resolve().parents[4]


class AlphaRehearsalWiresTest(unittest.TestCase):
    def test_generated_wires_match_current_contracts(self) -> None:
        expected = generate(ROOT)
        actual = output_path(ROOT).read_text(encoding="utf-8")
        self.assertEqual(actual, expected)
        self.assertIn("AuthSessionGrant", expected)
        self.assertIn("FollowCommandResult", expected)
        self.assertIn("CommentPageSlice", expected)


if __name__ == "__main__":
    unittest.main()
