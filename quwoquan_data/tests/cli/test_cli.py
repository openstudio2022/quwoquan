"""Basic CLI smoke tests."""
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import subprocess
import sys
from pathlib import Path

CLI_PATH = SCRIPTS_ROOT / "cli.py"


def test_cli_help():
    result = subprocess.run([sys.executable, str(CLI_PATH), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "explore" in result.stdout
    assert "build" in result.stdout
    assert "download" in result.stdout
    assert "produce" in result.stdout
    assert "publish" in result.stdout


def test_explore_help():
    result = subprocess.run([sys.executable, str(CLI_PATH), "explore", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--task" in result.stdout
    assert "--regions" in result.stdout


def test_produce_help():
    result = subprocess.run([sys.executable, str(CLI_PATH), "produce", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--type" in result.stdout
    assert "article" in result.stdout
