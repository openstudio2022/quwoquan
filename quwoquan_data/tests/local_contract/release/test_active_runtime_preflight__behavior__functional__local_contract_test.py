"""Data full-gate preflight for active runtime processes."""
from __future__ import annotations

from verify import verify_no_active_data_runtime
from verify.verify_no_active_data_runtime import active_runtime_processes, retired_launch_agents


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


def test_active_runtime_preflight_ignores_other_git_worktree(monkeypatch, tmp_path):
    lines = [
        "12345 python3 quwoquan_data/scripts/cli.py task execute --execution-id other"
    ]
    monkeypatch.setattr(
        verify_no_active_data_runtime,
        "_process_lines",
        lambda: lines,
    )
    monkeypatch.setattr(
        verify_no_active_data_runtime,
        "_process_worktree_root",
        lambda _pid: tmp_path.resolve(),
    )

    assert verify_no_active_data_runtime.active_runtime_processes() == []


def test_active_runtime_preflight_blocks_retired_supervisor_and_fleet() -> None:
    lines = [
        (
            "12345 python3 /repo/quwoquan_data/.qwq_output/data/video/"
            "run_video_m100_supervisor.py"
        ),
        (
            "12346 /opt/homebrew/bin/mongod --dbpath "
            "/repo/quwoquan_data/.qwq_output/data/video/fleet-native/mongo"
        ),
        "12347 /bin/zsh -c 'run_video_m100_supervisor.py is only diagnostic text'",
    ]

    active = active_runtime_processes(lines)

    assert active == lines[:2]


def test_active_runtime_preflight_blocks_launch_agent_that_can_revive_retired_root(
    tmp_path,
) -> None:
    launch_agents = tmp_path / "Library/LaunchAgents"
    launch_agents.mkdir(parents=True)
    retired = launch_agents / "custom-data-guard.plist"
    retired.write_text(
        "<string>/repo/quwoquan_data/.qwq_output/data/supervisor.py</string>",
        encoding="utf-8",
    )
    unrelated = launch_agents / "unrelated.plist"
    unrelated.write_text("<string>/tmp/healthy.py</string>", encoding="utf-8")

    assert retired_launch_agents(tmp_path) == [str(retired)]
