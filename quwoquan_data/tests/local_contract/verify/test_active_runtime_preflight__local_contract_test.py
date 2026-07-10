"""Data full-gate preflight for active runtime processes."""
from __future__ import annotations

from verify.verify_no_active_data_runtime import active_runtime_processes


def test_active_runtime_preflight_blocks_long_running_recipe_process():
    lines = [
        (
            "12345 python3 quwoquan_data/scripts/cli.py task run-recipe "
            "content/travel/homepage/zhejiang_province --batch b1"
        ),
        "22222 python3 quwoquan_data/scripts/cli.py verify output-root-isolation",
    ]

    active = active_runtime_processes(lines)

    assert len(active) == 1
    assert "task run-recipe" in active[0]


def test_active_runtime_preflight_blocks_nested_workflow_process():
    lines = [
        (
            "12345 python3 /repo/quwoquan_data/scripts/cli.py data workflow run "
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
