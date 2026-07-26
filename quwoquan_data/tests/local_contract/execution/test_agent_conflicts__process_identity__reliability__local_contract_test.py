"""Managed workspace conflict detection only blocks real Data CLI processes."""
from __future__ import annotations

import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
if str(DATA_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(DATA_ROOT / "scripts"))

from content.execution.agent import agent_conflicts
from content.execution.agent.agent_conflicts import _is_data_cli_process


def test_shell_text_containing_data_cli_is_not_a_data_cli_process() -> None:
    command = "/bin/zsh -c 'python3 quwoquan_data/scripts/cli.py task execute --execution-id sample'"

    assert _is_data_cli_process(command) is False


def test_python_data_cli_process_is_recognized() -> None:
    command = "/opt/homebrew/bin/python3 quwoquan_data/scripts/cli.py task execute --execution-id sample"

    assert _is_data_cli_process(command) is True


def test_execution_output_cleanup_shell_is_detected_before_new_execution() -> None:
    command = (
        "/bin/zsh -c 'find .qwq_output/data/tasks -mindepth 1 "
        "-maxdepth 1 -exec rm -rf {} +'")

    assert agent_conflicts._deletes_execution_output(command, Path.cwd()) is True


def test_unrelated_output_cleanup_does_not_block_execution() -> None:
    command = "/bin/zsh -c 'find .qwq_output/env/repo/runs -delete'"

    assert agent_conflicts._deletes_execution_output(command, Path.cwd()) is False


def test_workspace_admission_rejects_a_foreign_execution(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        agent_conflicts,
        "_managed_local_workspace_conflicts",
        lambda _workspace: [
            {
                "kind": "data_cli",
                "pid": 42,
                "command": (
                    "python3 quwoquan_data/scripts/cli.py task execute "
                    "--execution-id 20260723--travel-homepage-coverage--test-region-a--pilot-001"
                ),
            }
        ],
    )

    try:
        agent_conflicts.assert_managed_workspace_available(
            Path.cwd(),
            provider="cursor_sdk",
            execution_id="20260723--travel-homepage-coverage--test-region-b--pilot-001",
        )
    except agent_conflicts.ManagedWorkspaceConflictError as exc:
        assert "data_cli pid=42" in str(exc)
    else:
        raise AssertionError("foreign managed execution must block workspace admission")
