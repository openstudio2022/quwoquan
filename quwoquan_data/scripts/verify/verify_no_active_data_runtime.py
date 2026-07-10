"""Preflight guard for data verification.

Full data gates must run against a quiet workspace. Long-running data workflow
processes can legitimately write runtime/publish evidence while tests are
running, which would make isolation gates report misleading leaks. This guard
blocks early and asks the operator to rerun after the active runtime exits.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_CLI_MARKERS = (
    "quwoquan_data/scripts/cli.py",
    str(REPO_ROOT / "quwoquan_data" / "scripts" / "cli.py"),
)
ACTIVE_COMMAND_MARKERS = (
    " task run-recipe ",
    " task scaled-e2e run ",
    " data workflow run ",
)


def _process_lines() -> list[str]:
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def active_runtime_processes(process_lines: list[str] | None = None) -> list[str]:
    lines = process_lines if process_lines is not None else _process_lines()
    active: list[str] = []
    for line in lines:
        if "verify_no_active_data_runtime.py" in line:
            continue
        if not any(marker in line for marker in ACTIVE_CLI_MARKERS):
            continue
        if not any(marker in line for marker in ACTIVE_COMMAND_MARKERS):
            continue
        active.append(line)
    return active


def main() -> int:
    active = active_runtime_processes()
    if active:
        print("GATE_BLOCK verify_no_active_data_runtime:")
        for line in active[:10]:
            print(f"  - {line}")
        if len(active) > 10:
            print(f"  - ... {len(active) - 10} more")
        print("Rerun data/repo gate after active data runtime processes exit.")
        return 1
    print("[verify_no_active_data_runtime] OK")
    return 0
