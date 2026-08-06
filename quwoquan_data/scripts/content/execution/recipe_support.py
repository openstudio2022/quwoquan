"""Process and Git facts used by the task recipe facade."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def current_git_commit(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    if str(os.environ.get("QWQ_CAMPAIGN_ROOT_EXECUTION_ID") or "").strip():
        return str(os.environ.get("QWQ_FROZEN_MAIN_COMMIT") or "").strip()
    raise subprocess.CalledProcessError(
        result.returncode,
        result.args,
        output=result.stdout,
        stderr=result.stderr,
    )


def current_git_branch(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    if str(os.environ.get("QWQ_CAMPAIGN_ROOT_EXECUTION_ID") or "").strip():
        return str(os.environ.get("QWQ_FROZEN_MAIN_BRANCH") or "").strip()
    raise subprocess.CalledProcessError(
        result.returncode,
        result.args,
        output=result.stdout,
        stderr=result.stderr,
    )


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
