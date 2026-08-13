from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import stackctl


class StackctlInspectRemoteFailureTest(unittest.TestCase):
    def test_alpha_logs_use_the_content_release_state_truth(self) -> None:
        with TemporaryDirectory() as directory:
            process_dir = Path(directory)
            observability_root = process_dir / "observability"
            (process_dir / "content-release.json").write_text(
                json.dumps(
                    {
                        "target": "alpha-local",
                        "workload": "content-release",
                        "runRoot": str(process_dir / "run"),
                        "observabilityRoot": str(observability_root),
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                stackctl,
                "target_process_dir",
                return_value=process_dir,
            ):
                result = stackctl._local_runtime_log_root("alpha-local")

        self.assertEqual(result, observability_root / "logs" / "service")

    def test_prod_runtime_failure_propagates_to_report_and_exit_code(self) -> None:
        def runtime_failure(
            plane: str,
            *_: object,
            **__: object,
        ) -> dict[str, object]:
            return {
                "plane": plane,
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
                side_effect=runtime_failure,
            ), mock.patch.object(
                stackctl,
                "_candidate_workspace_report",
                return_value={"status": "current", "drifted": False},
            ):
                result = stackctl.command_inspect(args)

            report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
            findings = json.loads(
                (report_dir / "findings.json").read_text(encoding="utf-8")
            )
            summary = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))

        expected_issues = [
            "prod service plane rootless runtime inspect failed",
            "prod edge plane rootless runtime inspect failed",
        ]
        self.assertEqual(result["exitCode"], 1)
        self.assertEqual(result["details"], expected_issues)
        self.assertEqual(report["findings"], expected_issues)
        self.assertEqual(findings["issues"], expected_issues)
        self.assertEqual(summary["status"], "failed")


if __name__ == "__main__":
    unittest.main()
