"""app-managed-prepare CLI report-dir canonicalization contract.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from quwoquan_ops.cli import stackctl

_CONSUMER_ID = "flutter-run-test-1"
_DIGEST = "sha256:" + "a" * 64


class ManagedPreparationCommandReportDirTest(unittest.TestCase):
    @staticmethod
    def _args(report_dir: str | None = None) -> Any:
        arguments = [
            "app-managed-prepare",
            "--target",
            "alpha-local",
            "--device",
            "SIM-1",
            "--consumer-id",
            _CONSUMER_ID,
        ]
        if report_dir is not None:
            arguments.extend(("--report-dir", report_dir))
        return stackctl.build_parser().parse_args(arguments)

    @staticmethod
    def _prepared_result(report_dir: Path) -> dict[str, Any]:
        return {
            "exitCode": 0,
            "status": "prepared",
            "firstBlocker": "",
            "receiptPath": str(report_dir / "managed-preparation.json"),
            "receiptDigest": _DIGEST,
            "details": [],
            "warnings": [],
        }

    def test_default_run_dir_is_absolute_before_state_machine(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "output"
            with (
                mock.patch.dict(
                    "os.environ", {"QWQ_OUTPUT_ROOT": str(output_root)}, clear=False
                ),
                mock.patch.object(
                    stackctl, "load_environment_topology", return_value={}
                ),
                mock.patch.object(
                    stackctl, "get_target", return_value={"env": "alpha"}
                ),
                mock.patch.object(
                    stackctl,
                    "run_managed_preparation",
                    side_effect=lambda **kwargs: self._prepared_result(
                        kwargs["report_dir"]
                    ),
                ) as preparation,
                mock.patch.object(stackctl, "write_json"),
            ):
                result = stackctl.app_managed_prepare_commands.command_app_managed_prepare(
                    self._args()
                )

        report_dir = preparation.call_args.kwargs["report_dir"]
        self.assertTrue(report_dir.is_absolute())
        self.assertTrue(
            report_dir.is_relative_to(
                (output_root / "env" / "alpha" / "runs").resolve()
            )
        )
        self.assertEqual(result["reportDir"], str(report_dir))

    def test_relative_env_run_dir_is_absolute_before_state_machine(self) -> None:
        relative_report_dir = Path(
            ".qwq_output/env/alpha/runs/relative-managed-prepare"
        )
        expected_report_dir = (stackctl.ROOT / relative_report_dir).resolve()
        with (
            mock.patch.dict(
                "os.environ",
                {"QWQ_OUTPUT_ROOT": str(stackctl.ROOT / ".qwq_output")},
                clear=False,
            ),
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(
                stackctl, "get_target", return_value={"env": "alpha"}
            ),
            mock.patch.object(
                stackctl,
                "run_managed_preparation",
                return_value=self._prepared_result(expected_report_dir),
            ) as preparation,
            mock.patch.object(stackctl, "write_json") as write_json,
        ):
            result = stackctl.app_managed_prepare_commands.command_app_managed_prepare(
                self._args(str(relative_report_dir))
            )

        preparation.assert_called_once_with(
            target="alpha-local",
            device_id="SIM-1",
            platform="",
            consumer_id=_CONSUMER_ID,
            report_dir=expected_report_dir,
        )
        self.assertEqual(result["reportDir"], str(expected_report_dir))
        report_path, report = write_json.call_args.args
        self.assertEqual(report_path, expected_report_dir / "report.json")
        self.assertEqual(report["reportDir"], str(expected_report_dir))

    def test_traversal_and_env_external_paths_block_before_state_machine(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "output"
            invalid_paths = (
                "../escape",
                str(output_root / "env" / "beta" / "runs" / "wrong-env"),
            )
            with mock.patch.dict(
                "os.environ", {"QWQ_OUTPUT_ROOT": str(output_root)}, clear=False
            ):
                for invalid_path in invalid_paths:
                    with self.subTest(report_dir=invalid_path):
                        with (
                            mock.patch.object(
                                stackctl,
                                "load_environment_topology",
                                return_value={},
                            ),
                            mock.patch.object(
                                stackctl,
                                "get_target",
                                return_value={"env": "alpha"},
                            ),
                            mock.patch.object(
                                stackctl, "run_managed_preparation"
                            ) as preparation,
                            mock.patch.object(stackctl, "write_json") as write_json,
                        ):
                            result = stackctl.app_managed_prepare_commands.command_app_managed_prepare(
                                self._args(invalid_path)
                            )

                        self.assertEqual(result["exitCode"], 2)
                        self.assertEqual(result["status"], "blocked")
                        self.assertEqual(
                            result["firstBlocker"],
                            "APP.PREPARATION.receipt_invalid",
                        )
                        self.assertTrue(
                            result["details"][0].startswith(
                                "unsafe app-managed-prepare report directory:"
                            )
                        )
                        preparation.assert_not_called()
                        write_json.assert_not_called()

    def test_symlink_path_blocks_before_state_machine(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "output"
            runs_root = output_root / "env" / "alpha" / "runs"
            canonical_target = runs_root / "canonical-target"
            canonical_target.mkdir(parents=True)
            linked = runs_root / "linked"
            linked.symlink_to(canonical_target, target_is_directory=True)
            with (
                mock.patch.dict(
                    "os.environ", {"QWQ_OUTPUT_ROOT": str(output_root)}, clear=False
                ),
                mock.patch.object(
                    stackctl, "load_environment_topology", return_value={}
                ),
                mock.patch.object(
                    stackctl, "get_target", return_value={"env": "alpha"}
                ),
                mock.patch.object(
                    stackctl, "run_managed_preparation"
                ) as preparation,
                mock.patch.object(stackctl, "write_json") as write_json,
            ):
                result = stackctl.app_managed_prepare_commands.command_app_managed_prepare(
                    self._args(str(linked / "attempt"))
                )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            result["firstBlocker"], "APP.PREPARATION.receipt_invalid"
        )
        preparation.assert_not_called()
        write_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
