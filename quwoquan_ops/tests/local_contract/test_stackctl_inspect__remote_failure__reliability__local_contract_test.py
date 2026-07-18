from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import stackctl


class StackctlInspectRemoteFailureTest(unittest.TestCase):
    def test_prod_runtime_failure_propagates_to_report_and_exit_code(self) -> None:
        runtime_failure = {
            "error": "inspect command failed",
            "exitCode": 255,
        }

        with TemporaryDirectory() as directory:
            report_dir = Path(directory)
            args = argparse.Namespace(
                command="inspect",
                target="prod-hosted",
                scope="config",
                report_dir=str(report_dir),
            )
            with mock.patch.object(
                stackctl,
                "_prod_plane_runtime_report",
                return_value=runtime_failure,
            ):
                result = stackctl.command_inspect(args)

            report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
            findings = json.loads(
                (report_dir / "findings.json").read_text(encoding="utf-8")
            )
            summary = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))

        expected_issue = "prod service plane rootless runtime inspect failed"
        self.assertEqual(result["exitCode"], 1)
        self.assertEqual(result["details"], [expected_issue])
        self.assertEqual(report["findings"], [expected_issue])
        self.assertEqual(findings["issues"], [expected_issue])
        self.assertEqual(summary["status"], "failed")


if __name__ == "__main__":
    unittest.main()
