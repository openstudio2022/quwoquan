"""Process and Git facts used by the task recipe facade."""
from __future__ import annotations

import subprocess
from pathlib import Path


def current_git_commit(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def current_git_branch(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def runtime_preflight_argv(execution_root: Path) -> list[str]:
    evidence = execution_root / "evidence" / "runtime_preflight.json"
    return [
        "task",
        "preflight",
        "--cursor-startup",
        "--require-reliabletask-fleet",
        "--report-out",
        str(evidence),
    ]
