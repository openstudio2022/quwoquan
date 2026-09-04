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
    activation_readback,
    evaluate_transition,
    load_policy,
    load_policy_bytes,
    pre_push_issues,
    write_activation_transition_evidence,
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


def _policy_with_activation_state(state: object) -> BranchPolicy:
    payload = yaml.safe_load(
        (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text(
            encoding="utf-8"
        )
    )
    payload["integration_branch_activation"]["state"] = state
    return load_policy_bytes(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).encode("utf-8")
    )


def test_activation_contract_closes_readme_and_specs() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    release_spec = (
        ROOT
        / "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/"
        "daily-merge-release-strategy/spec.md"
    ).read_text(encoding="utf-8")
    local_ci_spec = (
        ROOT
        / "specs/feature-tree/runtime/development-workflow-governance/"
        "local-continuous-integration/spec.md"
    ).read_text(encoding="utf-8")

    assert "integration_branch_activation.state=active" in readme
    assert "`bootstrap|active` 闭集" in release_spec
    assert "当前成熟仓库为 `active`" in release_spec
    assert "bootstrap 仅允许远端 integration ref 不存在" in release_spec
    assert "`--pre-push` 必须消费 canonical activation state" in local_ci_spec
    for stale_claim in (
        "bootstrap direct-push 通道",
        "activation PR 合入后才关闭",
        "`--pre-push` 语义不变",
        "`--pre-push` 行为保持不变",
    ):
        assert stale_claim not in readme
        assert stale_claim not in release_spec
        assert stale_claim not in local_ci_spec


def test_activation_state_is_strictly_typed_and_closed() -> None:
    for malformed in (True, 1, None, "pending", " active"):
        with pytest.raises((TypeError, ValueError), match="integration_branch_activation.state"):
            _policy_with_activation_state(malformed)


def test_active_activation_readback_is_explicit_and_non_mutating() -> None:
    readback = activation_readback(_repository_policy())

    assert readback["state"] == "active"
    assert readback["integration_branch"] == "dev1.0"
    assert readback["kind"] == "integration_branch_activation_v1"
    assert readback["tracked_policy_mutated"] is False
    assert "--activation-transition" in str(readback["transition_command"])


def test_activation_transition_requires_bootstrap_and_writes_create_once_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    policy_path = tmp_path / "branch_policy.yaml"
    payload = yaml.safe_load(
        (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text(
            encoding="utf-8"
        )
    )
    payload["integration_branch_activation"]["state"] = "bootstrap"
    policy_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    policy = load_policy(policy_path)
    evidence_path = tmp_path / ".qwq_output/evidence/activation.json"
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "POLICY_PATH", policy_path)

    before = policy_path.read_bytes()
    first = write_activation_transition_evidence(
        policy=policy, evidence_path=str(evidence_path)
    )

    assert first["from_state"] == "bootstrap"
    assert first["proposed_state"] == "active"
    assert first["tracked_policy_mutated"] is False
    assert first["proposal"]["path"] == "branch_policy.yaml"
    assert policy_path.read_bytes() == before
    assert yaml.safe_load(evidence_path.read_text(encoding="utf-8")) == first
    with pytest.raises(ValueError, match="create-once"):
        write_activation_transition_evidence(
            policy=policy, evidence_path=str(evidence_path)
        )


def test_activation_transition_rejects_current_active_state(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires current state 'bootstrap'"):
        write_activation_transition_evidence(
            policy=_repository_policy(),
            evidence_path=str(tmp_path / ".qwq_output/evidence/activation.json"),
        )


def test_activation_cli_malformed_state_is_typed_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    payload = yaml.safe_load(
        (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text(
            encoding="utf-8"
        )
    )
    payload["integration_branch_activation"]["state"] = {"malformed": True}
    malformed = tmp_path / "branch_policy.yaml"
    malformed.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    actual_load_policy = module.load_policy
    monkeypatch.setattr(module, "load_policy", lambda: actual_load_policy(malformed))

    assert module.main(["--activation-readback"]) == 1
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "OPS.BRANCH.POLICY_INVALID" in output
    assert "integration_branch_activation.state" in output
    assert "Traceback" not in output


def test_transition_evaluator_applies_activation_state_to_dev_direct_push() -> None:
    active = evaluate_transition(
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
    )
    bootstrap_create = evaluate_transition(
        policy=_policy_with_activation_state("bootstrap"),
        transition=BranchTransition(
            event="direct_push",
            actor_kind="human",
            repository="owner/repo",
            head="dev1.0",
            base="dev1.0",
            before_oid=ZERO_SHA,
            after_oid="a" * 40,
        ),
    )
    bootstrap_update = evaluate_transition(
        policy=_policy_with_activation_state("bootstrap"),
        transition=BranchTransition(
            event="direct_push",
            actor_kind="human",
            repository="owner/repo",
            head="dev1.0",
            base="dev1.0",
            before_oid="b" * 40,
            after_oid="a" * 40,
        ),
    )

    assert active.allowed is False
    assert active.reason_code == "OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED"
    assert bootstrap_create.allowed is True
    assert bootstrap_update.allowed is False


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
        assert decision.recovery_action == "open_allowed_pull_request_then_retry"


def test_pre_push_bootstrap_exception_is_strictly_create_only() -> None:
    policy = _policy_with_activation_state("bootstrap")

    assert pre_push_issues(
        policy=policy,
        current_branch="dev1.0",
        update_lines=[
            _update(
                local_branch="dev1.0",
                remote_branch="dev1.0",
                remote_sha=ZERO_SHA,
            )
        ],
        environment={},
    ) == []
    for current_branch, remote_sha in (
        ("dev1.0", "b" * 40),
        ("main", ZERO_SHA),
        ("lane/ops", ZERO_SHA),
    ):
        issues = pre_push_issues(
            policy=policy,
            current_branch=current_branch,
            update_lines=[
                _update(
                    local_branch=current_branch,
                    remote_branch="dev1.0",
                    remote_sha=remote_sha,
                )
            ],
            environment={},
        )
        assert issues
        assert all(
            issue.startswith("OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED:")
            for issue in issues
        )


def test_pre_push_active_rejects_direct_dev_update() -> None:
    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch="dev1.0",
        update_lines=[_update(local_branch="dev1.0", remote_branch="dev1.0")],
        environment={},
    )

    assert len(issues) == 1
    assert "active integration branch 'dev1.0'" in issues[0]
    assert issues[0].startswith("OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED:")


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
    assert all("recovery=open_allowed_pull_request_then_retry" in issue for issue in issues)


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
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF_TYPE": "branch",
        "GITHUB_REF_NAME": "main",
        "GITHUB_ACTOR": "github-actions[bot]",
        "GITHUB_WORKFLOW_REF": (
            "openstudio2022/quwoquan/.github/workflows/"
            "system-backsync.yml@refs/heads/main"
        ),
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


def test_pre_push_system_identity_still_requires_matching_main_source() -> None:
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

    issues = pre_push_issues(
        policy=_repository_policy(),
        current_branch="dev1.0",
        update_lines=[_update(local_branch="dev1.0", remote_branch="dev1.0")],
        environment=environment,
    )

    assert len(issues) == 1
    assert issues[0].startswith("OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED:")


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
