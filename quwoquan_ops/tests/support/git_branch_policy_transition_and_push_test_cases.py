# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t4
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002.t2
"""分支政策 activation、转换判定与 pre-push 本地契约。

由 1000 行硬顶按运行时判定职责拆分自
``test_git_branch_policy__local_contract_test.py``；由原 companion 导入并收集，测试断言逐字保留。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_git_branch_policy import (
    ZERO_SHA,
    BranchDecision,
    BranchPolicy,
    BranchTransition,
    evaluate_transition,
    load_policy,
    load_policy_bytes,
    pre_push_issues,
)


def _repository_policy() -> BranchPolicy:
    return load_policy()


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


def test_transition_evaluator_allows_integration_worktree_fast_forward() -> None:
    before = "b" * 40
    after = "a" * 40
    calls: list[tuple[str, str]] = []

    decision = evaluate_transition(
        policy=_repository_policy(),
        transition=BranchTransition(
            event="direct_push",
            actor_kind="integration_worktree",
            repository="owner/repo",
            head="dev1.0",
            base="dev1.0",
            before_oid=before,
            after_oid=after,
        ),
        is_ancestor=lambda ancestor, descendant: (
            calls.append((ancestor, descendant)) or True
        ),
    )

    assert decision.allowed is True
    assert calls == [(before, after)]


def test_transition_evaluator_allows_idempotent_integration_worktree_update() -> None:
    oid = "a" * 40
    decision = evaluate_transition(
        policy=_repository_policy(),
        transition=BranchTransition(
            event="direct_push",
            actor_kind="integration_worktree",
            repository="owner/repo",
            head="dev1.0",
            base="dev1.0",
            before_oid=oid,
            after_oid=oid,
        ),
    )

    assert decision.allowed is True


@pytest.mark.parametrize(
    ("missing_field", "missing_value"),
    [
        ("before_oid", None),
        ("after_oid", None),
        ("before_oid", ZERO_SHA),
        ("after_oid", ZERO_SHA),
    ],
)
def test_transition_evaluator_rejects_integration_update_without_oids(
    missing_field: str, missing_value: str | None,
) -> None:
    values: dict[str, str | None] = {
        "before_oid": "b" * 40,
        "after_oid": "a" * 40,
    }
    values[missing_field] = missing_value

    decision = evaluate_transition(
        policy=_repository_policy(),
        transition=BranchTransition(
            event="direct_push",
            actor_kind="integration_worktree",
            repository="owner/repo",
            head="dev1.0",
            base="dev1.0",
            before_oid=values["before_oid"],
            after_oid=values["after_oid"],
        ),
        is_ancestor=lambda _ancestor, _descendant: True,
    )

    assert decision.allowed is False
    assert decision.reason_code == "OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED"


def test_transition_evaluator_rejects_integration_update_without_ancestry_authority() -> None:
    decision = evaluate_transition(
        policy=_repository_policy(),
        transition=BranchTransition(
            event="direct_push",
            actor_kind="integration_worktree",
            repository="owner/repo",
            head="dev1.0",
            base="dev1.0",
            before_oid="b" * 40,
            after_oid="a" * 40,
        ),
    )

    assert decision.allowed is False
    assert decision.reason_code == "OPS.BRANCH.AUTHORITY_UNAVAILABLE"


def test_transition_evaluator_rejects_integration_non_fast_forward() -> None:
    decision = evaluate_transition(
        policy=_repository_policy(),
        transition=BranchTransition(
            event="direct_push",
            actor_kind="integration_worktree",
            repository="owner/repo",
            head="dev1.0",
            base="dev1.0",
            before_oid="b" * 40,
            after_oid="a" * 40,
        ),
        is_ancestor=lambda _ancestor, _descendant: False,
    )

    assert decision.allowed is False
    assert decision.reason_code == "OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED"


def test_transition_evaluator_rejects_non_integration_actor_dev_direct_push() -> None:
    decision = evaluate_transition(
        policy=_repository_policy(),
        transition=BranchTransition(
            event="direct_push",
            actor_kind="human",
            repository="owner/repo",
            head="dev1.0",
            base="dev1.0",
            before_oid="b" * 40,
            after_oid="a" * 40,
        ),
        is_ancestor=lambda _ancestor, _descendant: True,
    )

    assert decision.allowed is False
    assert decision.reason_code == "OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED"


def test_transition_evaluator_has_single_typed_result_semantics() -> None:
    policy = _repository_policy()

    accepted = evaluate_transition(
        policy=policy,
        transition=BranchTransition(
            event="direct_push",
            actor_kind="human",
            repository="owner/repo",
            head="lane/ops",
            base="lane/ops",
        ),
    )
    blocked = evaluate_transition(
        policy=policy,
        transition=BranchTransition(
            event="direct_push",
            actor_kind="human",
            repository="owner/repo",
            head="main",
            base="main",
        ),
    )

    assert accepted == BranchDecision(
        status="allowed",
        string_context=(
            ("actorKind", "human"),
            ("base", "lane/ops"),
            ("event", "direct_push"),
            ("head", "lane/ops"),
            ("repository", "owner/repo"),
        ),
    )
    assert blocked.status == "blocked"
    assert blocked.reason_code == "OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED"
    assert blocked.allowed is False


@pytest.mark.parametrize(
    ("head", "base", "allowed"),
    [
        ("lane/ops", "lane/ops", True),
        ("lane/refactor", "lane/refactor", True),
        ("lane/ops", "dev1.0", False),
        ("lane/undeclared", "lane/undeclared", False),
    ],
)
def test_transition_evaluator_direct_push_decision_covers_lane_branches(
    head: str, base: str, allowed: bool,
) -> None:
    decision = evaluate_transition(
        policy=_repository_policy(),
        transition=BranchTransition(
            event="direct_push",
            actor_kind="human",
            repository="owner/repo",
            head=head,
            base=base,
        ),
    )

    assert decision.allowed is allowed
    if not allowed:
        assert decision.reason_code == "OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED"
        assert decision.recovery_action == "use_canonical_publisher_or_allowed_pull_request_then_retry"


def test_pre_push_allows_matching_integration_worktree_fast_forward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    before = "b" * 40
    after = "a" * 40
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module,
        "_git_is_ancestor",
        lambda ancestor, descendant: calls.append((ancestor, descendant)) or True,
    )

    assert pre_push_issues(
        policy=_repository_policy(),
        current_branch="dev1.0",
        update_lines=[
            _update(
                local_branch="dev1.0",
                remote_branch="dev1.0",
                local_sha=after,
                remote_sha=before,
            )
        ],
        environment={},
    ) == []
    assert calls == [(before, after)]


def test_pre_push_rejects_matching_integration_worktree_non_fast_forward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    monkeypatch.setattr(module, "_git_is_ancestor", lambda _before, _after: False)
    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch="dev1.0",
        update_lines=[_update(local_branch="dev1.0", remote_branch="dev1.0")],
        environment={},
    )

    assert len(issues) == 1
    assert issues[0].startswith("OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED:")
    assert "integration worktree fast-forward update" in issues[0]


def test_pre_push_rejects_integration_update_without_remote_before_oid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    monkeypatch.setattr(
        module,
        "_git_is_ancestor",
        lambda _before, _after: (_ for _ in ()).throw(
            AssertionError("missing before OID queried ancestry")
        ),
    )
    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch="dev1.0",
        update_lines=[
            _update(
                local_branch="dev1.0",
                remote_branch="dev1.0",
                remote_sha=ZERO_SHA,
            )
        ],
        environment={},
    )

    assert len(issues) == 1
    assert issues[0].startswith("OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED:")


def test_pre_push_rejects_matching_integration_worktree_without_git_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    monkeypatch.setattr(
        module,
        "_git_is_ancestor",
        lambda _before, _after: (_ for _ in ()).throw(OSError("unavailable")),
    )
    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch="dev1.0",
        update_lines=[_update(local_branch="dev1.0", remote_branch="dev1.0")],
        environment={},
    )

    assert len(issues) == 1
    assert issues[0].startswith("OPS.BRANCH.AUTHORITY_UNAVAILABLE:")


def test_pre_push_one_ordinary_lane_does_not_require_all_lanes() -> None:
    update = _update(
        local_branch="lane/data-engineering",
        remote_branch="lane/data-engineering",
    )

    assert pre_push_issues(
        policy=_repository_policy(),
        current_branch="lane/data-engineering",
        update_lines=[update],
        environment={},
    ) == []


def test_pre_push_accepts_only_matching_lane_remote_branch() -> None:
    policy = _repository_policy()

    assert (
        pre_push_issues(
            policy=policy,
            current_branch="lane/small-fix",
            update_lines=[
                _update(
                    local_branch="lane/small-fix",
                    remote_branch="lane/small-fix",
                )
            ],
            environment={},
        )
        == []
    )
    foreign_source = pre_push_issues(
        policy=policy,
        current_branch="dev1.0",
        update_lines=[
            _update(local_branch="dev1.0", remote_branch="lane/small-fix")
        ],
        environment={},
    )
    assert any(
        "persistent lane push must update its matching remote ref" in issue
        for issue in foreign_source
    )
    lane_to_dev = pre_push_issues(
        policy=policy,
        current_branch="lane/small-fix",
        update_lines=[
            _update(local_branch="lane/small-fix", remote_branch="dev1.0")
        ],
        environment={},
    )
    assert any("active integration branch 'dev1.0'" in issue for issue in lane_to_dev)
    lane_to_main = pre_push_issues(
        policy=policy,
        current_branch="lane/small-fix",
        update_lines=[
            _update(local_branch="lane/small-fix", remote_branch="main")
        ],
        environment={},
    )
    assert any("dev1.0 -> main promotion PR" in issue for issue in lane_to_main)


@pytest.mark.parametrize(
    ("operation", "local_sha", "remote_sha"),
    [
        ("create", "a" * 40, ZERO_SHA),
        ("update", "a" * 40, "b" * 40),
        ("delete", ZERO_SHA, "b" * 40),
    ],
)
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t3
def test_pre_push_rejects_undeclared_lane_create_update_and_delete(
    operation: str, local_sha: str, remote_sha: str,
) -> None:
    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch="lane/undeclared",
        update_lines=[
            _update(
                local_branch="lane/undeclared",
                remote_branch="lane/undeclared",
                local_sha=local_sha,
                remote_sha=remote_sha,
            )
        ],
        environment={},
    )
    assert issues, operation
    assert all(issue.startswith("OPS.BRANCH.REF_NOT_ALLOWED:") for issue in issues)
    assert all("terminal=blocked" in issue for issue in issues)
    assert all("recovery=use_declared_branch_and_allowed_pr_edge_then_retry" in issue for issue in issues)


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t3
def test_pre_push_blocks_direct_main_update() -> None:
    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch="dev1.0",
        update_lines=[
            _update(local_branch="dev1.0", remote_branch="main")
        ],
        environment={},
    )

    assert any("dev1.0 -> main promotion PR" in issue for issue in issues)
    assert all(
        issue.startswith("OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED:") for issue in issues
    )
    assert all("terminal=blocked" in issue for issue in issues)
    assert all("recovery=use_canonical_publisher_or_allowed_pull_request_then_retry" in issue for issue in issues)


def test_pre_push_rejects_self_reported_system_backsync_identity() -> None:
    update = _update(local_branch="main", remote_branch="dev1.0")
    system_environment = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF_TYPE": "branch",
        "GITHUB_REF_NAME": "main",
        "GITHUB_ACTOR": "human",
        "GITHUB_WORKFLOW_REF": (
            "openstudio2022/quwoquan/.github/workflows/"
            "system-backsync.yml@refs/heads/main"
        ),
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


def test_pre_push_accepts_provable_managed_system_fast_forward_backsync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    before = "b" * 40
    after = "a" * 40
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        module,
        "_git_is_ancestor",
        lambda ancestor, descendant: calls.append((ancestor, descendant)) or True,
    )
    environment = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF_TYPE": "branch",
        "GITHUB_REF_NAME": "main",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": after,
        "GITHUB_ACTOR": "github-actions[bot]",
        "GITHUB_WORKFLOW_REF": (
            "openstudio2022/quwoquan/.github/workflows/"
            "delivery-gate.yml@refs/heads/main"
        ),
        "QWQ_SYSTEM_BACKSYNC_WORKFLOW_REF": (
            "openstudio2022/quwoquan/.github/workflows/"
            "system-backsync.yml@refs/heads/main"
        ),
        "QWQ_MANAGED_SYSTEM_BACKSYNC": "system-fast-forward-cas-v1",
        "GITHUB_REPOSITORY": "openstudio2022/quwoquan",
    }

    assert pre_push_issues(
        policy=_repository_policy(),
        current_branch="main",
        update_lines=[
            _update(
                local_branch="main",
                remote_branch="dev1.0",
                local_sha=after,
                remote_sha=before,
            )
        ],
        environment=environment,
    ) == []
    assert calls == [(before, after)]


def test_pre_push_system_identity_does_not_replace_matching_integration_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF_TYPE": "branch",
        "GITHUB_REF_NAME": "main",
        "GITHUB_ACTOR": "github-actions[bot]",
        "GITHUB_WORKFLOW_REF": (
            "openstudio2022/quwoquan/.github/workflows/"
            "system-backsync.yml@refs/heads/main"
        ),
    }

    monkeypatch.setattr(
        "quwoquan_ops.gate.verify_git_branch_policy._git_is_ancestor",
        lambda _before, _after: True,
    )

    assert pre_push_issues(
        policy=_repository_policy(),
        current_branch="dev1.0",
        update_lines=[_update(local_branch="dev1.0", remote_branch="dev1.0")],
        environment=environment,
    ) == []


@pytest.mark.parametrize(
    "transition",
    [
        BranchTransition(
            event="system_backsync", actor_kind="human", repository="owner/repo",
            head="main", base="dev1.0", before_oid="b" * 40, after_oid="a" * 40,
        ),
        BranchTransition(
            event="system_backsync", actor_kind="system", repository="owner/repo",
            head="lane/small-fix", base="dev1.0", before_oid="b" * 40, after_oid="a" * 40,
        ),
        BranchTransition(
            event="system_backsync", actor_kind="system", repository="owner/repo",
            head="main", base="dev1.0", before_oid=None, after_oid="a" * 40,
        ),
    ],
)
def test_invalid_system_backsync_identity_has_stable_recovery(
    transition: BranchTransition,
) -> None:
    decision = evaluate_transition(policy=_repository_policy(), transition=transition)
    assert decision.allowed is False
    assert decision.reason_code == "OPS.BRANCH.REF_NOT_ALLOWED"
    assert decision.recovery_action == "use_declared_branch_and_allowed_pr_edge_then_retry"


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
    assert decision.recovery_action == "restore_git_authority_then_retry"


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
    if reason_code is not None:
        assert decision.recovery_action is not None


def test_pre_push_blocks_unknown_remote_ref() -> None:
    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch="dev1.0",
        update_lines=[
            f"refs/heads/dev1.0 {'a' * 40} refs/tags/v1.0.0 {'b' * 40}\n"
        ],
        environment={},
    )

    assert len(issues) == 1
    assert issues[0].startswith("OPS.BRANCH.REF_NOT_ALLOWED:")
    assert "undeclared remote ref 'refs/tags/v1.0.0'" in issues[0]


@pytest.mark.parametrize(
    "remote_branch",
    ["dev1.0", "main", "lane/small-fix", "lane/data-engineering", "codex/merged", "release/other"],
)
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
        (
            "OPS.BRANCH.REF_NOT_ALLOWED: terminal=blocked; deletion of protected or undeclared "
            f"branch '{remote_branch}' is blocked; "
            "recovery=use_declared_branch_and_allowed_pr_edge_then_retry"
        )
    ]
