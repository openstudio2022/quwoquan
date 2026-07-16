"""Canonical CLI surface smoke tests."""
import subprocess
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

CLI_PATH = SCRIPTS_ROOT / "cli.py"


def test_cli_help():
    result = subprocess.run([sys.executable, str(CLI_PATH), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "data" in result.stdout
    assert "task" in result.stdout
    assert "verify" in result.stdout


def test_task_help():
    result = subprocess.run(
        [sys.executable, str(CLI_PATH), "task", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "geo-homepages" in result.stdout


@pytest.mark.parametrize("retired_command", ["explore", "produce"])
def test_retired_top_level_commands_are_rejected(retired_command: str):
    result = subprocess.run(
        [sys.executable, str(CLI_PATH), retired_command, "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
