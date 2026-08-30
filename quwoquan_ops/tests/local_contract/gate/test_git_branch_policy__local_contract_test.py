# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002.t2
from __future__ import annotations

import subprocess
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
    current_repo_issues,
    evaluate_transition,
    load_policy,
    load_policy_bytes,
    pre_push_issues,
    pull_request_context_from_environment,
    repository_branch_context_from_environment,
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
    assert policy.pull_request_prefixes == set()
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


def test_branch_policy_rejects_codex_branch_even_when_it_targets_dev() -> None:
    issues = _issues(
        current_branch=None,
        local_branches=[],
        remote_branches=["dev1.0", "main", "codex/nullability"],
        ci_head_branch="codex/nullability",
        ci_base_branch="dev1.0",
    )

    assert any("codex/nullability -> dev1.0" in issue for issue in issues)
    assert any("unexpected remote branches: codex/nullability" in issue for issue in issues)


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
        ("codex/nullability", "dev1.0"),
        ("main", "dev1.0"),
        ("dev1.0", "dev1.0"),
        ("main", "main"),
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
            "GITHUB_HEAD_REF": "dev1.0",
            "GITHUB_BASE_REF": "main",
        }
    ) == ("dev1.0", "main")
    assert pull_request_context_from_environment(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_HEAD_REF": "dev1.0",
            "GITHUB_BASE_REF": "main",
        }
    ) == (None, None)


@pytest.mark.parametrize("event_name", ["push", "workflow_dispatch"])
def test_hosted_direct_run_uses_exact_branch_context(event_name: str) -> None:
    assert repository_branch_context_from_environment(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": event_name,
            "GITHUB_REF_TYPE": "branch",
            "GITHUB_REF_NAME": "dev1.0",
        }
    ) == "dev1.0"
    assert repository_branch_context_from_environment(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": event_name,
            "GITHUB_REF_TYPE": "tag",
            "GITHUB_REF_NAME": "v1.0.0",
        }
    ) is None


@pytest.mark.parametrize("branch", ["dev1.0", "main"])
def test_hosted_push_does_not_infer_direct_push_without_explicit_update_source(
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF_TYPE", "branch")
    monkeypatch.setenv("GITHUB_REF_NAME", branch)
    monkeypatch.setenv("GITHUB_REPOSITORY", "openstudio2022/quwoquan")

    assert current_repo_issues() == []


def test_main_push_after_pr_merge_is_not_misreported_as_direct_push(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF_TYPE", "branch")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setenv("GITHUB_REPOSITORY", "openstudio2022/quwoquan")
    monkeypatch.setenv("GITHUB_EVENT_PATH", "/tmp/push-after-pr-merge.json")

    issues = current_repo_issues()

    assert not any("DIRECT_PUSH_NOT_ALLOWED" in issue for issue in issues)
    assert issues == []


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
    payload["allowed_pull_request_edges"] = [{"head": "main", "base": "main"}]
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


def test_policy_byte_loader_matches_path_loader_and_reads_once(tmp_path: Path) -> None:
    raw = (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_bytes()
    fixture_policy = tmp_path / "branch_policy.yaml"
    fixture_policy.write_bytes(raw)

    assert load_policy_bytes(raw) == load_policy(fixture_policy)

    class ReadOncePath:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload
            self.read_count = 0

        def read_bytes(self) -> bytes:
            self.read_count += 1
            if self.read_count > 1:
                raise AssertionError("branch policy path was read more than once")
            return self.payload

    read_once = ReadOncePath(raw)
    assert load_policy(read_once) == load_policy_bytes(raw)  # type: ignore[arg-type]
    assert read_once.read_count == 1


def test_policy_byte_loader_rejects_invalid_utf8() -> None:
    with pytest.raises(UnicodeDecodeError):
        load_policy_bytes(b"\xff\xfe")


@pytest.mark.parametrize(
    "raw",
    [
        b"allowed_local_branches: []\nallowed_local_branches: []\n",
        b"failure_codes:\n  policy_invalid: OPS.BRANCH.POLICY_INVALID\n  policy_invalid: OPS.BRANCH.OTHER\n",
    ],
)
def test_policy_byte_loader_rejects_top_level_and_nested_duplicate_keys(raw: bytes) -> None:
    with pytest.raises(yaml.YAMLError, match="duplicate key"):
        load_policy_bytes(raw)


@pytest.mark.parametrize(
    ("needle", "replacement"),
    [
        (b"integration_branch: dev1.0", b"integration_branch: true"),
        (b"release_branch: main", b"release_branch: 7"),
        (b"production_source_branch: main", b"production_source_branch: null"),
        (b"  - dev1.0\n  - main", b"  - true\n  - main"),
        (b"  policy_invalid: OPS.BRANCH.POLICY_INVALID", b"  true: OPS.BRANCH.POLICY_INVALID"),
        (b"  policy_invalid: OPS.BRANCH.POLICY_INVALID", b"  policy_invalid: 1"),
        (b"  policy_invalid: OPS.BRANCH.POLICY_INVALID", b"  policy_invalid: null"),
    ],
)
def test_policy_byte_loader_rejects_non_string_declared_values(
    needle: bytes, replacement: bytes,
) -> None:
    raw = (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_bytes()
    assert needle in raw
    with pytest.raises((TypeError, ValueError)):
        load_policy_bytes(raw.replace(needle, replacement, 1))


def _run_branch_policy_cli() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "quwoquan_ops/gate/verify_git_branch_policy.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_cli_separates_policy_and_git_authority_failures_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    malformed = tmp_path / "branch-policy.yaml"
    malformed.write_text("allowed_local_branches: [", encoding="utf-8")
    actual_load_policy = module.load_policy
    monkeypatch.setattr(module, "load_policy", lambda: actual_load_policy(malformed))
    assert module.main([]) == 1
    policy_output = capsys.readouterr()
    assert "OPS.BRANCH.POLICY_INVALID" in policy_output.out
    assert "recovery=repair_canonical_branch_policy" in policy_output.out
    assert "AUTHORITY_UNAVAILABLE" not in policy_output.out
    assert policy_output.out.count("recovery=") == 1
    assert "Traceback" not in policy_output.out + policy_output.err

    canonical = ROOT / "quwoquan_ops/policies/branch_policy.yaml"
    monkeypatch.setattr(module, "load_policy", lambda: actual_load_policy(canonical))
    monkeypatch.setattr(
        module,
        "_run_git",
        lambda *_args: (_ for _ in ()).throw(
            subprocess.CalledProcessError(128, ["git", "for-each-ref"])
        ),
    )
    assert module.main([]) == 1
    authority_output = capsys.readouterr()
    assert "OPS.BRANCH.AUTHORITY_UNAVAILABLE" in authority_output.out
    assert "recovery=restore_git_authority_then_retry" in authority_output.out
    assert "POLICY_INVALID" not in authority_output.out
    assert authority_output.out.count("recovery=") == 1
    assert "Traceback" not in authority_output.out + authority_output.err


def test_cli_classifies_git_unicode_decode_failure_as_authority_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    decode_error = UnicodeDecodeError(
        "utf-8", b"\xff", 0, 1, "invalid start byte",
    )
    monkeypatch.setattr(
        module,
        "_run_git",
        lambda *_args: (_ for _ in ()).throw(decode_error),
    )

    assert module.main([]) != 0
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "OPS.BRANCH.AUTHORITY_UNAVAILABLE" in output
    assert "terminal=blocked" in output
    assert "recovery=restore_git_authority_then_retry" in output
    assert "OPS.BRANCH.POLICY_INVALID" not in output
    assert output.count("recovery=") == 1
    assert "Traceback" not in output


def test_real_cli_passes_without_traceback() -> None:
    completed = _run_branch_policy_cli()
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "[verify_git_branch_policy] OK" in completed.stdout
    assert "Traceback" not in completed.stdout + completed.stderr


def test_policy_byte_loader_rejects_unknown_or_missing_root_fields() -> None:
    raw = (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_bytes()
    with pytest.raises(ValueError, match="root fields drifted"):
        load_policy_bytes(raw + b"unexpected_policy_field: true\n")
    with pytest.raises(ValueError, match="root fields drifted"):
        load_policy_bytes(raw.replace(b"production_workflow:", b"removed_workflow:", 1))


def test_temporary_execution_admission_schema_is_exact_and_closed() -> None:
    raw = (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_bytes()
    lifecycle = b"""temporary_execution_admission:
  isolation: branch_per_writer
  promotion: declared_pull_request_edge_only
  cleanup: mandatory_after_promotion_or_abort
  concurrency_evidence: required
  unexpected: true
"""
    with pytest.raises(ValueError, match="exact isolation/promotion/cleanup"):
        load_policy_bytes(raw + lifecycle)


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
            event="direct_push",
            actor_kind="human",
            repository="owner/repo",
            head="dev1.0",
            base="dev1.0",
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
            ("base", "dev1.0"),
            ("event", "direct_push"),
            ("head", "dev1.0"),
            ("repository", "owner/repo"),
        ),
    )
    assert blocked.status == "blocked"
    assert blocked.reason_code == "OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED"
    assert blocked.allowed is False


def test_pre_push_accepts_only_matching_dev_remote_branch() -> None:
    policy = _repository_policy()

    assert (
        pre_push_issues(
            policy=policy,
            current_branch="dev1.0",
            update_lines=[
                _update(
                    local_branch="dev1.0",
                    remote_branch="dev1.0",
                )
            ],
            environment={},
        )
        == []
    )
    issues = pre_push_issues(
        policy=policy,
        current_branch="main",
        update_lines=[
            _update(local_branch="main", remote_branch="dev1.0")
        ],
        environment={},
    )
    assert any("matching local dev1.0 branch" in issue for issue in issues)


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


@pytest.mark.parametrize(
    "remote_branch", ["dev1.0", "main", "codex/merged", "release/other"]
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
        "OPS.BRANCH.REF_NOT_ALLOWED: deletion of protected or undeclared branch "
        f"'{remote_branch}' is blocked"
    ]
