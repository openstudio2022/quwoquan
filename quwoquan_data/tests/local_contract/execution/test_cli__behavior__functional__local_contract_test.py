"""Canonical CLI surface smoke tests."""
import os
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
    assert "execute" in result.stdout


def test_ship_help_does_not_import_content_production_toolchain(tmp_path: Path):
    sitecustomize = tmp_path / "sitecustomize.py"
    sitecustomize.write_text(
        """
import importlib.abc
import sys

class _BlockCanonicalRelease(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'content.release.canonical.handler':
            raise ImportError('canonical release toolchain must stay unloaded')
        return None

sys.meta_path.insert(0, _BlockCanonicalRelease())
""".strip()
        + "\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-B", str(CLI_PATH), "ship", "--help"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage: qwq-data ship" in result.stdout


def test_plan_images_help_has_side_effect_free_cold_start():
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(CLI_PATH),
            "task",
            "plan-images",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage: qwq-data task plan-images" in result.stdout


def test_campaign_parser_import_has_side_effect_free_cold_start():
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            (
                "import argparse; "
                "from content.execution.handler import register_parser; "
                "parser = argparse.ArgumentParser(); "
                "register_parser(parser.add_subparsers(dest='command'))"
            ),
        ],
        cwd=SCRIPTS_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "partially initialized module" not in result.stderr


@pytest.mark.parametrize("retired_command", ["explore", "produce"])
def test_retired_top_level_commands_are_rejected(retired_command: str):
    result = subprocess.run(
        [sys.executable, str(CLI_PATH), retired_command, "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
