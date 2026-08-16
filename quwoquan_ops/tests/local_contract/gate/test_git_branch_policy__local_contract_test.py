# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t2
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_git_branch_policy import (
    ZERO_SHA,
    BranchPolicy,
    PullRequestEdge,
    SystemBacksync,
    branch_policy_issues,
    load_policy,
    pre_push_issues,
    pull_request_context_from_environment,
)


def _repository_policy() -> BranchPolicy:
    return load_policy()


def _issues(
    *,
    current_branch: str | None,
    local_branches: list[str] | None = None,
    remote_branches: list[str] | None = None,
    ci_head_branch: str | None = None,
    ci_base_branch: str | None = None,
    policy: BranchPolicy | None = None,
) -> list[str]:
    return branch_policy_issues(
        policy=policy or _repository_policy(),
        local_branches=local_branches or ["dev1.0", "main"],
        remote_branches=remote_branches or ["dev1.0", "main"],
        current_branch=current_branch,
        ci_head_branch=ci_head_branch,
        ci_base_branch=ci_base_branch,
    )


def _update(
    *,
    local_branch: str,
    remote_branch: str,
    local_sha: str = "a" * 40,
    remote_sha: str = "b" * 40,
) -> str:
    return (
        f"refs/heads/{local_branch} {local_sha} "
        f"refs/heads/{remote_branch} {remote_sha}\n"
    )


def test_repository_policy_declares_dev_integration_and_main_release() -> None:
    policy = _repository_policy()

    assert policy.allowed_local == {"dev1.0", "main"}
    assert policy.allowed_remote == {"dev1.0", "main"}
    assert policy.pull_request_prefixes == {"codex/"}
    assert policy.integration_branch == "dev1.0"
    assert policy.release_branch == "main"
    assert policy.production_source_branch == "main"
    assert policy.allowed_pull_request_edges == (
        PullRequestEdge(base="dev1.0", head_prefix="codex/"),
        PullRequestEdge(base="main", head="dev1.0"),
    )
    assert policy.system_backsync == SystemBacksync(
        head="main",
        base="dev1.0",
        mode="fast_forward_only",
    )


@pytest.mark.parametrize("current_branch", ["dev1.0", "main"])
def test_branch_policy_accepts_both_declared_long_lived_branches(
    current_branch: str,
) -> None:
    assert _issues(current_branch=current_branch) == []


def test_branch_policy_rejects_a_third_long_lived_branch() -> None:
    issues = _issues(
        current_branch="release/other",
        local_branches=["dev1.0", "main", "release/other"],
        remote_branches=["dev1.0", "main", "release/other"],
    )

    assert any(
        "current branch 'release/other' is not allowed" in issue for issue in issues
    )
    assert any("unexpected local branches: release/other" in issue for issue in issues)
    assert any("unexpected remote branches: release/other" in issue for issue in issues)


def test_branch_policy_accepts_codex_to_dev_pull_request() -> None:
    assert (
        _issues(
            current_branch=None,
            local_branches=[],
            remote_branches=["dev1.0", "main"],
            ci_head_branch="codex/nullability",
            ci_base_branch="dev1.0",
        )
        == []
    )


def test_branch_policy_accepts_dev_to_main_promotion() -> None:
    assert (
        _issues(
            current_branch=None,
            local_branches=[],
            remote_branches=["dev1.0", "main"],
            ci_head_branch="dev1.0",
            ci_base_branch="main",
        )
        == []
    )


@pytest.mark.parametrize(
    ("head", "base"),
    [
        ("codex/nullability", "main"),
        ("main", "dev1.0"),
        ("release/other", "main"),
    ],
)
def test_branch_policy_rejects_every_undeclared_pull_request_edge(
    head: str,
    base: str,
) -> None:
    issues = _issues(
        current_branch=None,
        local_branches=[],
        remote_branches=["dev1.0", "main"],
        ci_head_branch=head,
        ci_base_branch=base,
    )

    assert any(
        f"pull-request edge '{head} -> {base}' is not allowed" in issue
        for issue in issues
    )


def test_pull_request_context_requires_github_pull_request_event() -> None:
    assert pull_request_context_from_environment(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_HEAD_REF": "codex/nullability",
            "GITHUB_BASE_REF": "dev1.0",
        }
    ) == ("codex/nullability", "dev1.0")
    assert pull_request_context_from_environment(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_HEAD_REF": "codex/nullability",
            "GITHUB_BASE_REF": "dev1.0",
        }
    ) == (None, None)


def test_branch_policy_does_not_trust_detached_non_pr_environment() -> None:
    issues = _issues(current_branch=None, local_branches=[], remote_branches=[])

    assert any("detached HEAD" in issue for issue in issues)


def test_main_only_fixture_still_fails_closed_for_dev_branch(tmp_path: Path) -> None:
    fixture_policy = tmp_path / "branch_policy.yaml"
    fixture_policy.write_text(
        """allowed_local_branches:
  - main
allowed_remote_branches:
  - main
pull_request_branch_prefixes:
  - codex/
integration_branch: main
release_branch: main
production_source_branch: main
allowed_pull_request_edges:
  - head_prefix: codex/
    base: main
""",
        encoding="utf-8",
    )
    policy = load_policy(fixture_policy)

    issues = _issues(
        policy=policy,
        current_branch="dev1.0",
        local_branches=["dev1.0", "main"],
        remote_branches=["dev1.0", "main"],
    )

    assert any("current branch 'dev1.0' is not allowed" in issue for issue in issues)
    assert any("unexpected local branches: dev1.0" in issue for issue in issues)
    assert any("unexpected remote branches: dev1.0" in issue for issue in issues)


def test_pre_push_accepts_only_matching_codex_remote_branch() -> None:
    policy = _repository_policy()

    assert (
        pre_push_issues(
            policy=policy,
            current_branch="codex/nullability",
            update_lines=[
                _update(
                    local_branch="codex/nullability",
                    remote_branch="codex/nullability",
                )
            ],
            environment={},
        )
        == []
    )
    issues = pre_push_issues(
        policy=policy,
        current_branch="codex/nullability",
        update_lines=[
            _update(local_branch="codex/nullability", remote_branch="codex/other")
        ],
        environment={},
    )
    assert any("matching remote ref" in issue for issue in issues)


@pytest.mark.parametrize(
    ("current_branch", "remote_branch", "expected"),
    [
        ("dev1.0", "dev1.0", "codex/* -> dev1.0 PR"),
        ("dev1.0", "main", "dev1.0 -> main promotion PR"),
    ],
)
def test_pre_push_blocks_direct_long_lived_updates(
    current_branch: str,
    remote_branch: str,
    expected: str,
) -> None:
    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch=current_branch,
        update_lines=[
            _update(local_branch=current_branch, remote_branch=remote_branch)
        ],
        environment={},
    )

    assert any(expected in issue for issue in issues)


def test_pre_push_allows_only_system_fast_forward_main_to_dev_backsync() -> None:
    update = _update(local_branch="main", remote_branch="dev1.0")
    system_environment = {
        "GITHUB_ACTIONS": "true",
        "QWQ_SYSTEM_BRANCH_BACKSYNC": "true",
    }

    assert (
        pre_push_issues(
            policy=_repository_policy(),
            current_branch="main",
            update_lines=[update],
            environment=system_environment,
            is_ancestor=lambda ancestor, descendant: (
                (ancestor, descendant) == ("b" * 40, "a" * 40)
            ),
        )
        == []
    )
    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch="main",
        update_lines=[update],
        environment=system_environment,
        is_ancestor=lambda _ancestor, _descendant: False,
    )
    assert any("system fast-forward backsync" in issue for issue in issues)


def test_pre_push_allows_remote_branch_deletion_for_cleanup() -> None:
    assert (
        pre_push_issues(
            policy=_repository_policy(),
            current_branch="dev1.0",
            update_lines=[
                _update(
                    local_branch="dev1.0",
                    remote_branch="codex/merged",
                    local_sha=ZERO_SHA,
                )
            ],
            environment={},
        )
        == []
    )
