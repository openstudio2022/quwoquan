# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002.t2
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_git_branch_policy import (
    ZERO_SHA,
    BranchDecision,
    BranchPolicy,
    BranchTransition,
    PullRequestEdge,
    RequiredPromotionCheck,
    SystemBacksync,
    branch_policy_issues,
    evaluate_transition,
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
    assert policy.production_workflow == ".github/workflows/deploy-prod-auto.yml"
    assert policy.required_promotion_checks == (
        RequiredPromotionCheck(
            name="03. Delivery Gate",
            workflow=".github/workflows/delivery-gate.yml",
        ),
        RequiredPromotionCheck(
            name="04. Pre-Release Gate",
            workflow=".github/workflows/pre-release-gate.yml",
        ),
        RequiredPromotionCheck(
            name="05. App Env Device Matrix",
            workflow=".github/workflows/app-env-device-matrix-self-hosted.yml",
        ),
    )
    assert policy.allowed_pull_request_edges == (
        PullRequestEdge(base="dev1.0", head="codex/*"),
        PullRequestEdge(base="main", head="dev1.0"),
    )
    assert policy.system_backsync == SystemBacksync(
        head="main",
        base="dev1.0",
        mode="fast-forward-only",
    )
    assert dict(policy.failure_codes) == {
        "authority_unavailable": "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
        "backsync_cas_conflict": "OPS.BRANCH.BACKSYNC_CAS_CONFLICT",
        "backsync_not_fast_forward": "OPS.BRANCH.BACKSYNC_NOT_FAST_FORWARD",
        "direct_push_not_allowed": "OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED",
        "policy_invalid": "OPS.BRANCH.POLICY_INVALID",
        "ref_not_allowed": "OPS.BRANCH.REF_NOT_ALLOWED",
        "source_not_main_reachable": "OPS.BRANCH.SOURCE_NOT_MAIN_REACHABLE",
    }


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
    assert all(issue.startswith("OPS.BRANCH.REF_NOT_ALLOWED:") for issue in issues)


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
    payload = yaml.safe_load(
        (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text(
            encoding="utf-8"
        )
    )
    payload["allowed_local_branches"] = ["main"]
    payload["allowed_remote_branches"] = ["main"]
    payload["integration_branch"] = "main"
    payload["allowed_pull_request_edges"] = [{"head": "codex/*", "base": "main"}]
    payload.pop("system_backsync")
    fixture_policy.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
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


def test_policy_loader_rejects_missing_canonical_failure_code(tmp_path: Path) -> None:
    payload = yaml.safe_load(
        (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text(
            encoding="utf-8"
        )
    )
    payload["failure_codes"].pop("backsync_cas_conflict")
    fixture_policy = tmp_path / "branch_policy.yaml"
    fixture_policy.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="exact canonical keys"):
        load_policy(fixture_policy)


def test_transition_evaluator_has_single_typed_result_semantics() -> None:
    policy = _repository_policy()

    accepted = evaluate_transition(
        policy=policy,
        transition=BranchTransition(
            event="pull_request",
            actor_kind="github",
            repository="owner/repo",
            head="codex/branch-policy",
            base="dev1.0",
        ),
    )
    blocked = evaluate_transition(
        policy=policy,
        transition=BranchTransition(
            event="direct_push",
            actor_kind="human",
            repository="owner/repo",
            head="dev1.0",
            base="dev1.0",
        ),
    )

    assert accepted == BranchDecision(
        status="allowed",
        string_context=(
            ("actorKind", "github"),
            ("base", "dev1.0"),
            ("event", "pull_request"),
            ("head", "codex/branch-policy"),
            ("repository", "owner/repo"),
        ),
    )
    assert blocked.status == "blocked"
    assert blocked.reason_code == "OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED"
    assert blocked.allowed is False


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
    assert all(
        issue.startswith("OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED:") for issue in issues
    )


def test_pre_push_rejects_self_reported_system_backsync_identity() -> None:
    update = _update(local_branch="main", remote_branch="dev1.0")
    system_environment = {
        "GITHUB_ACTIONS": "true",
        "QWQ_SYSTEM_BRANCH_BACKSYNC": "true",
    }

    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch="main",
        update_lines=[update],
        environment=system_environment,
    )
    assert any(
        issue.startswith("OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED:")
        for issue in issues
    )


def test_transition_evaluator_fails_closed_when_ancestry_query_is_unavailable() -> None:
    decision = evaluate_transition(
        policy=_repository_policy(),
        transition=BranchTransition(
            event="system_backsync",
            actor_kind="system",
            repository="owner/repo",
            head="main",
            base="dev1.0",
            before_oid="b" * 40,
            after_oid="a" * 40,
        ),
        is_ancestor=lambda _ancestor, _descendant: (_ for _ in ()).throw(
            RuntimeError("authority unavailable")
        ),
    )

    assert decision.allowed is False
    assert decision.reason_code == "OPS.BRANCH.AUTHORITY_UNAVAILABLE"


@pytest.mark.parametrize(
    ("before_oid", "after_oid", "is_ancestor", "allowed", "reason_code"),
    [
        ("a" * 40, "a" * 40, None, True, None),
        ("b" * 40, "a" * 40, lambda _before, _after: True, True, None),
        (
            "b" * 40,
            "a" * 40,
            lambda _before, _after: False,
            False,
            "OPS.BRANCH.BACKSYNC_NOT_FAST_FORWARD",
        ),
    ],
)
def test_system_backsync_decision_table_is_pure_and_fail_closed(
    before_oid: str,
    after_oid: str,
    is_ancestor,
    allowed: bool,
    reason_code: str | None,
) -> None:
    decision = evaluate_transition(
        policy=_repository_policy(),
        transition=BranchTransition(
            event="system_backsync",
            actor_kind="system",
            repository="owner/repo",
            head="main",
            base="dev1.0",
            before_oid=before_oid,
            after_oid=after_oid,
        ),
        is_ancestor=is_ancestor,
    )

    assert decision.allowed is allowed
    assert decision.reason_code == reason_code


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


@pytest.mark.parametrize("remote_branch", ["dev1.0", "main", "release/other"])
def test_pre_push_blocks_long_lived_or_undeclared_branch_deletion(
    remote_branch: str,
) -> None:
    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch="dev1.0",
        update_lines=[
            _update(
                local_branch="dev1.0",
                remote_branch=remote_branch,
                local_sha=ZERO_SHA,
            )
        ],
        environment={},
    )

    assert issues == [
        "OPS.BRANCH.REF_NOT_ALLOWED: deletion of protected or undeclared branch "
        f"'{remote_branch}' is blocked"
    ]
