"""Canonical task-facade binding for governed capacity calibration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest


DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
CLI = SCRIPTS_ROOT / "cli.py"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution.handler import register_parser  # noqa: E402
from content.execution.planning.capacity_calibration_cli import (  # noqa: E402
    handle_calibrate_capacity,
)
from content.execution.planning.capacity_calibration_writer import (  # noqa: E402
    CapacityCalibrationRunError,
)
from core.paths import CONTROL_PLANE_SHARED_ROOT, REPO_ROOT  # noqa: E402


def test_task_help_exposes_capacity_calibration_without_running_probes() -> None:
    task_help = subprocess.run(
        [sys.executable, "-B", str(CLI), "task", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert task_help.returncode == 0, task_help.stderr
    assert "calibrate-capacity" in task_help.stdout

    command_help = subprocess.run(
        [
            sys.executable,
            "-B",
            str(CLI),
            "task",
            "calibrate-capacity",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert command_help.returncode == 0, command_help.stderr
    assert "usage: qwq-data task calibrate-capacity" in command_help.stdout
    for option in (
        "--calibration-id",
        "--semantic-selection-id",
        "--fleet-report",
        "--execution-state",
        "--supersedes-calibration-id",
        "--provider-evidence-calibration-id",
    ):
        assert option in command_help.stdout


def test_capacity_calibration_parser_binds_canonical_handler() -> None:
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers(dest="command"))

    args = parser.parse_args(
        [
            "task",
            "calibrate-capacity",
            "--calibration-id",
            "capacity-calibration-001",
            "--semantic-selection-id",
            "cursor_grok",
            "--fleet-report",
            "fleet-report.json",
            "--execution-state",
            "execution-state.json",
        ]
    )

    assert args.handler is handle_calibrate_capacity


def test_capacity_calibration_facade_forwards_governed_inputs_and_prints_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    receipt_path = (
        REPO_ROOT
        / ".qwq_output/data/local/workspace/capacity-calibration/test/receipt.json"
    )

    def fake_run_capacity_calibration(**kwargs: object) -> tuple[dict[str, object], Path]:
        captured.update(kwargs)
        return (
            {
                "schema": "quwoquan_data.governed_capacity_calibration_receipt",
                "calibrationId": "capacity-calibration-002",
                "receiptDigest": "sha256:" + "1" * 64,
            },
            receipt_path,
        )

    monkeypatch.setattr(
        "content.execution.planning.capacity_calibration_cli.run_capacity_calibration",
        fake_run_capacity_calibration,
    )
    args = argparse.Namespace(
        calibration_id="capacity-calibration-002",
        semantic_selection_id="cursor_grok",
        fleet_report=[str(tmp_path / "fleet-001.json")],
        execution_state=[str(tmp_path / "execution-state-001.json")],
        supersedes_calibration_id="capacity-calibration-001",
        provider_evidence_calibration_id="provider-probes-001",
    )

    handle_calibrate_capacity(args)

    assert captured == {
        "calibration_id": "capacity-calibration-002",
        "semantic_selection_id": "cursor_grok",
        "fleet_report_paths": ((tmp_path / "fleet-001.json").resolve(),),
        "execution_state_paths": (
            (tmp_path / "execution-state-001.json").resolve(),
        ),
        "output_dir": (
            CONTROL_PLANE_SHARED_ROOT
            / "capacity_calibration/capacity-calibration-002"
        ),
        "supersedes_calibration_id": "capacity-calibration-001",
        "provider_evidence_dir": (
            CONTROL_PLANE_SHARED_ROOT / "capacity_calibration/provider-probes-001"
        ),
        "provider_evidence_calibration_id": "provider-probes-001",
    }
    output = json.loads(capsys.readouterr().out)
    assert output["calibrationId"] == "capacity-calibration-002"
    assert output["receiptRef"] == receipt_path.relative_to(REPO_ROOT).as_posix()


def test_capacity_calibration_facade_fails_with_typed_blocker_and_no_success_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_capacity_calibration(**_kwargs: object) -> tuple[dict[str, object], Path]:
        raise CapacityCalibrationRunError("fresh M100 fleet report is missing")

    monkeypatch.setattr(
        "content.execution.planning.capacity_calibration_cli.run_capacity_calibration",
        fail_capacity_calibration,
    )
    args = argparse.Namespace(
        calibration_id="capacity-calibration-002",
        semantic_selection_id="cursor_grok",
        fleet_report=[str(tmp_path / "fleet-001.json")],
        execution_state=[str(tmp_path / "execution-state-001.json")],
        supersedes_calibration_id=None,
        provider_evidence_calibration_id=None,
    )

    with pytest.raises(
        SystemExit,
        match=(
            r"GATE_BLOCK DATA\.CAPACITY\.CALIBRATION_FAILED: "
            r"fresh M100 fleet report is missing"
        ),
    ):
        handle_calibrate_capacity(args)

    assert capsys.readouterr().out == ""
