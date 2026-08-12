"""Local contract for bounded, actionable stackctl command summaries."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import stackctl  # noqa: E402


def test_stackctl_command_details__preserves_distinct_failure_lines__observability__local_contract() -> None:
    result = subprocess.CompletedProcess(
        args=["child"],
        returncode=1,
        stdout="first prerequisite failed\nsecond prerequisite failed\n",
        stderr="second prerequisite failed\nthird prerequisite failed\n",
    )

    assert stackctl._command_details(result) == [
        "first prerequisite failed",
        "second prerequisite failed",
        "third prerequisite failed",
    ]


def test_stackctl_command_details__bounds_output_and_keeps_terminal_blocker__observability__local_contract() -> None:
    result = subprocess.CompletedProcess(
        args=["child"],
        returncode=1,
        stdout="\n".join(f"failure-{index}" for index in range(stackctl.COMMAND_SUMMARY_DETAIL_LIMIT + 1)),
        stderr="",
    )

    details = stackctl._command_details(result)

    split = stackctl.COMMAND_SUMMARY_DETAIL_LIMIT // 2
    assert details[:split] == [f"failure-{index}" for index in range(split)]
    assert details[split] == "... 1 command output line(s) omitted ..."
    assert details[split + 1 :] == [
        f"failure-{index}"
        for index in range(
            split + 1,
            stackctl.COMMAND_SUMMARY_DETAIL_LIMIT + 1,
        )
    ]
