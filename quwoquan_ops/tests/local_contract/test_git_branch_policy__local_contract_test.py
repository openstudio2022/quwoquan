from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_git_branch_policy import (
    branch_policy_issues,
    pull_request_branch_from_environment,
)


def test_branch_policy_accepts_dev1_only_locally_and_main_remotely() -> None:
    issues = branch_policy_issues(
        allowed_local={"dev1.0"},
        allowed_remote={"dev1.0", "main"},
        local_branches=["dev1.0"],
        remote_branches=["dev1.0", "main"],
        current_branch="dev1.0",
    )

    assert issues == []


def test_branch_policy_rejects_extra_local_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"dev1.0"},
        allowed_remote={"dev1.0", "main"},
        local_branches=["dev1.0", "feature/demo"],
        remote_branches=["dev1.0", "main"],
        current_branch="feature/demo",
    )

    assert any("feature/demo" in issue for issue in issues)


def test_branch_policy_rejects_local_main_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"dev1.0"},
        allowed_remote={"dev1.0", "main"},
        local_branches=["dev1.0", "main"],
        remote_branches=["dev1.0", "main"],
        current_branch="main",
    )

    assert any("current branch 'main'" in issue for issue in issues)
    assert any("unexpected local branches: main" in issue for issue in issues)


def test_branch_policy_rejects_extra_remote_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"dev1.0"},
        allowed_remote={"dev1.0", "main"},
        local_branches=["dev1.0"],
        remote_branches=["cursor/demo", "dev1.0", "main"],
        current_branch="dev1.0",
    )

    assert any("cursor/demo" in issue for issue in issues)


def test_branch_policy_uses_reviewed_dev_branch_for_github_pr_merge_preview() -> None:
    current_branch = pull_request_branch_from_environment(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_HEAD_REF": "dev1.0",
        }
    )

    issues = branch_policy_issues(
        allowed_local={"dev1.0"},
        allowed_remote={"dev1.0", "main"},
        local_branches=[],
        remote_branches=[],
        current_branch=current_branch,
    )

    assert issues == []


def test_branch_policy_does_not_trust_detached_non_pr_environment() -> None:
    current_branch = pull_request_branch_from_environment(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_HEAD_REF": "dev1.0",
        }
    )

    issues = branch_policy_issues(
        allowed_local={"dev1.0"},
        allowed_remote={"dev1.0", "main"},
        local_branches=[],
        remote_branches=[],
        current_branch=current_branch,
    )

    assert any("detached HEAD" in issue for issue in issues)
