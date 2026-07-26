"""Data full-gate preflight for active runtime processes."""
from __future__ import annotations

from verify.verify_no_active_data_runtime import active_runtime_processes


def test_active_runtime_preflight_blocks_long_running_recipe_process():
    lines = [
        (
            "12345 python3 quwoquan_data/scripts/cli.py task execute "
            "--execution-id 20260713--travel-homepage-coverage--test-region-a--pilot-001"
        ),
        "22222 python3 quwoquan_data/scripts/cli.py verify output-root-isolation",
    ]

    active = active_runtime_processes(lines)

    assert len(active) == 1
    assert "task execute" in active[0]


def test_active_runtime_preflight_blocks_nested_execution_process():
    lines = [
        (
            "12345 python3 /repo/quwoquan_data/scripts/cli.py task execute "
            "--task task-a --batch b1"
        )
    ]

    assert active_runtime_processes(lines) == lines


def test_active_runtime_preflight_ignores_verify_and_itself():
    lines = [
        "1 python3 quwoquan_data/scripts/cli.py verify output-root-isolation",
        "2 python3 quwoquan_data/scripts/verify/verify_no_active_data_runtime.py",
    ]

    assert active_runtime_processes(lines) == []


def test_active_runtime_preflight_ignores_parent_shell_with_cli_text():
    lines = [
        (
            "3 /bin/zsh -c 'python3 quwoquan_data/scripts/cli.py task execute "
            "--execution-id test-region-a'"
        )
    ]

    assert active_runtime_processes(lines) == []
