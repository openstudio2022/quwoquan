from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_git_branch_policy import (
    branch_policy_issues,
    load_policy,
    pull_request_branch_from_environment,
)


def test_repository_policy_declares_main_only_and_codex_pr_prefix() -> None:
    allowed_local, allowed_remote, pull_request_prefixes = load_policy()

    assert allowed_local == {"main"}
    assert allowed_remote == {"main"}
    assert pull_request_prefixes == {"codex/"}


def test_branch_policy_accepts_main_as_the_only_long_lived_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"main"},
        allowed_remote={"main"},
        pull_request_prefixes={"codex/"},
        local_branches=["main"],
        remote_branches=["main"],
        current_branch="main",
    )

    assert issues == []


def test_branch_policy_rejects_extra_local_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"main"},
        allowed_remote={"main"},
        pull_request_prefixes={"codex/"},
        local_branches=["main", "feature/demo"],
        remote_branches=["main"],
        current_branch="feature/demo",
    )

    assert any("feature/demo" in issue for issue in issues)


def test_branch_policy_rejects_retired_dev_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"main"},
        allowed_remote={"main"},
        pull_request_prefixes={"codex/"},
        local_branches=["dev1.0", "main"],
        remote_branches=["dev1.0", "main"],
        current_branch="dev1.0",
    )

    assert any("current branch 'dev1.0'" in issue for issue in issues)
    assert any("unexpected local branches: dev1.0" in issue for issue in issues)
    assert any("unexpected remote branches: dev1.0" in issue for issue in issues)


def test_branch_policy_rejects_extra_remote_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"main"},
        allowed_remote={"main"},
        pull_request_prefixes={"codex/"},
        local_branches=["main"],
        remote_branches=["cursor/demo", "main"],
        current_branch="main",
    )

    assert any("cursor/demo" in issue for issue in issues)


def test_branch_policy_accepts_only_the_reviewed_codex_pr_branch_as_ephemeral() -> None:
    current_branch = pull_request_branch_from_environment(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_HEAD_REF": "codex/graphql-read-plane",
        }
    )

    issues = branch_policy_issues(
        allowed_local={"main"},
        allowed_remote={"main"},
        pull_request_prefixes={"codex/"},
        local_branches=["codex/graphql-read-plane"],
        remote_branches=["codex/graphql-read-plane", "main"],
        current_branch=current_branch,
        ci_head_branch=current_branch,
    )

    assert issues == []


def test_branch_policy_does_not_trust_detached_non_pr_environment() -> None:
    current_branch = pull_request_branch_from_environment(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_HEAD_REF": "codex/graphql-read-plane",
        }
    )

    issues = branch_policy_issues(
        allowed_local={"main"},
        allowed_remote={"main"},
        pull_request_prefixes={"codex/"},
        local_branches=[],
        remote_branches=[],
        current_branch=current_branch,
    )

    assert any("detached HEAD" in issue for issue in issues)
