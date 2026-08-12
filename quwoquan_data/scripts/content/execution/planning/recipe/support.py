"""Process and Git facts used by the task recipe facade."""
from __future__ import annotations

import subprocess
from pathlib import Path


def current_git_commit(repo_root: Path) -> str:
    from core.execution_branch import current_git_commit as captured_git_commit

    commit = captured_git_commit(cwd=repo_root)
    if commit:
        return commit
    raise subprocess.CalledProcessError(1, ["git", "rev-parse", "HEAD"])


def current_git_branch(repo_root: Path) -> str:
    from core.execution_branch import current_git_branch as captured_git_branch

    branch = captured_git_branch(cwd=repo_root)
    if branch:
        return branch
    raise subprocess.CalledProcessError(1, ["git", "branch", "--show-current"])


def runtime_preflight_argv(
    execution_root: Path,
    semantic_selection_id: str = "default",
) -> list[str]:
    evidence = execution_root / "evidence" / "runtime_preflight.json"
    return [
        "task",
        "preflight",
        "--semantic-agent-startup",
        "--semantic-selection-id",
        semantic_selection_id,
        "--report-out",
        str(evidence),
    ]
