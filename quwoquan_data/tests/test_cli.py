"""Basic CLI smoke tests."""
import subprocess
import sys
from pathlib import Path

CLI_PATH = Path(__file__).resolve().parents[1] / "scripts" / "cli.py"


def test_cli_help():
    result = subprocess.run([sys.executable, str(CLI_PATH), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "explore" in result.stdout
    assert "build" in result.stdout
    assert "download" in result.stdout
    assert "produce" in result.stdout
    assert "publish" in result.stdout
    assert "reconcile" in result.stdout


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
