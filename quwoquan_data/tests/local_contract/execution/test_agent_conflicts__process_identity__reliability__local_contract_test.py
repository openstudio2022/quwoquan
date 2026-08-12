"""Managed workspace conflict detection only blocks real Data CLI processes."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
if str(DATA_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(DATA_ROOT / "scripts"))

from content.execution.agent import agent_conflicts
from content.execution.agent.managed_workspace import managed_local_workspace_lock_path
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


def test_workspace_admission_allows_a_foreign_execution_root(
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

    agent_conflicts.assert_managed_workspace_available(
        Path.cwd(),
        provider="cursor_sdk",
        execution_id="20260723--travel-homepage-coverage--test-region-b--pilot-001",
    )


def test_workspace_admission_rejects_the_same_execution_root(monkeypatch) -> None:
    execution_id = "20260723--travel-homepage-coverage--test-region-a--pilot-001"
    monkeypatch.setattr(
        agent_conflicts,
        "_managed_local_workspace_conflicts",
        lambda _workspace: [
            {
                "kind": "data_cli",
                "pid": 42,
                "command": (
                    "python3 quwoquan_data/scripts/cli.py task execute "
                    f"--execution-id {execution_id}"
                ),
            }
        ],
    )

    with pytest.raises(
        agent_conflicts.ManagedWorkspaceConflictError,
        match=r"DATA\.EXECUTION\.RESOURCE_CONFLICT.*data_cli pid=42",
    ):
        agent_conflicts.assert_managed_workspace_available(
            Path.cwd(),
            provider="cursor_sdk",
            execution_id=execution_id,
        )


def test_resource_filter_allows_bridge_for_another_execution_root(
    tmp_path: Path,
) -> None:
    tasks_root = tmp_path / "data/tasks"
    current_root = tasks_root / "execution-a"
    foreign_root = tasks_root / "execution-b"
    conflicts = [
        {
            "kind": "cursor_sdk_bridge",
            "pid": 43,
            "command": f"cursor-sdk-bridge --workspace {foreign_root}",
        }
    ]

    assert agent_conflicts._managed_execution_resource_conflicts(
        conflicts,
        execution_id="execution-a",
        execution_root=current_root,
    ) == []


@pytest.mark.parametrize(
    ("kind", "command"),
    [
        ("cursor_sdk_bridge", "cursor-sdk-bridge --workspace {current}"),
        ("cursor_sdk_bridge", "cursor-sdk-bridge --workspace {repo}"),
        ("execution_output_cleanup", "rm -rf .qwq_output/data/tasks"),
    ],
)
def test_resource_filter_keeps_shared_mutable_resources(
    tmp_path: Path,
    kind: str,
    command: str,
) -> None:
    current_root = tmp_path / "data/tasks/execution-a"
    rendered = command.format(current=current_root, repo=tmp_path)
    conflict = {"kind": kind, "pid": 44, "command": rendered}

    assert agent_conflicts._managed_execution_resource_conflicts(
        [conflict],
        execution_id="execution-a",
        execution_root=current_root,
    ) == [conflict]


def test_managed_guard_lock_is_scoped_to_the_mutable_execution_root(
    tmp_path: Path,
) -> None:
    workspace = str(tmp_path / "source-capsule")
    first_root = tmp_path / "data/tasks/execution-a"
    second_root = tmp_path / "data/tasks/execution-b"

    first = managed_local_workspace_lock_path(
        workspace, execution_root=first_root
    )
    replay = managed_local_workspace_lock_path(
        workspace, execution_root=first_root
    )
    second = managed_local_workspace_lock_path(
        workspace, execution_root=second_root
    )

    assert replay == first
    assert second != first
