# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t4
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
    IntegrationBranchActivation,
    PullRequestEdge,
    RequiredPromotionCheck,
    SystemBacksync,
    activation_readback,
    branch_policy_issues,
    current_repo_issues,
    evaluate_transition,
    load_policy,
    load_policy_bytes,
    local_commit_issues,
    pre_push_issues,
    pull_request_context_from_environment,
    repository_branch_context_from_environment,
    write_activation_transition_evidence,
)

LANE_BRANCHES = (
    "lane/product-mainline",
    "lane/data-engineering",
    "lane/engineering",
    "lane/ops",
    "lane/small-fix",
    "lane/refactor",
)
ALL_LONG_LIVED = ("dev1.0", "main", *LANE_BRANCHES)


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


def test_repository_policy_declares_dev_integration_main_release_and_six_lanes() -> None:
    policy = _repository_policy()

    assert policy.allowed_local == set(ALL_LONG_LIVED)
    assert policy.allowed_remote == set(ALL_LONG_LIVED)
    assert policy.pull_request_prefixes == {"lane/"}
    assert policy.integration_branch == "dev1.0"
    assert policy.release_branch == "main"
    assert policy.integration_branch_activation == IntegrationBranchActivation(
        state="active",
        transition_command=(
            "python3 -B quwoquan_ops/gate/verify_git_branch_policy.py "
            "--activation-transition --evidence-path "
            ".qwq_output/env/repo/runs/branch-policy/dev1.0-activation.json"
        ),
        evidence_kind="integration_branch_activation_v1",
        bootstrap_remote_before_oid="absent",
        bootstrap_remote_after_oid="exact_local_integration_head",
        bootstrap_source_branch="dev1.0",
        bootstrap_target_branch="dev1.0",
        bootstrap_release_eligibility=False,
        active_accepted_updates=(
            "lane_pull_request_merge",
            "system_fast_forward_backsync",
        ),
        active_direct_push="forbidden",
    )
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
        PullRequestEdge(base="dev1.0", head="lane/*"),
    )
    assert policy.system_backsync == SystemBacksync(
        head="main",
        base="dev1.0",
        mode="fast-forward-only",
    )
    assert policy.persistent_lane_admission is not None
    assert policy.persistent_lane_admission.isolation == "branch_per_writer"
    assert policy.persistent_lane_admission.promotion == "declared_pull_request_edge_only"
    assert policy.persistent_lane_admission.resync == "mandatory_fast_forward_after_integration_or_abort"
    assert policy.persistent_lane_admission.worktree_lifecycle == "retained"
    assert policy.persistent_lane_admission.concurrency_evidence == "required"
    assert dict(policy.failure_codes) == {
        "authority_unavailable": "OPS.BRANCH.AUTHORITY_UNAVAILABLE",
        "backsync_cas_conflict": "OPS.BRANCH.BACKSYNC_CAS_CONFLICT",
        "backsync_not_fast_forward": "OPS.BRANCH.BACKSYNC_NOT_FAST_FORWARD",
        "direct_push_not_allowed": "OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED",
        "integration_read_only": "OPS.BRANCH.INTEGRATION_READ_ONLY",
        "policy_invalid": "OPS.BRANCH.POLICY_INVALID",
        "ref_not_allowed": "OPS.BRANCH.REF_NOT_ALLOWED",
        "source_not_main_reachable": "OPS.BRANCH.SOURCE_NOT_MAIN_REACHABLE",
    }


@pytest.mark.parametrize("branch", ["dev1.0", "main"])
def test_local_commit_rejects_integration_and_release(branch: str) -> None:
    issues = local_commit_issues(policy=_repository_policy(), current_branch=branch)
    assert len(issues) == 1
    assert issues[0].startswith("OPS.BRANCH.INTEGRATION_READ_ONLY:")
    assert "terminal=blocked" in issues[0]
    assert "commit_from_a_lane_worktree_then_open_pull_request" in issues[0]


@pytest.mark.parametrize("branch", list(LANE_BRANCHES))
def test_local_commit_accepts_fixed_lanes(branch: str) -> None:
    assert local_commit_issues(policy=_repository_policy(), current_branch=branch) == []


@pytest.mark.parametrize("current_branch", list(ALL_LONG_LIVED))
def test_branch_policy_accepts_every_declared_long_lived_branch(
    current_branch: str,
) -> None:
    assert _issues(current_branch=current_branch) == []


def test_branch_policy_accepts_six_persistent_lane_refs_locally_and_remotely() -> None:
    assert (
        _issues(
            current_branch="dev1.0",
            local_branches=list(ALL_LONG_LIVED),
            remote_branches=list(ALL_LONG_LIVED),
        )
        == []
    )


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


def test_local_commit_accepts_current_lane_despite_stale_undeclared_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    calls: list[tuple[str, ...]] = []

    def fake_run_git(*args: str) -> list[str]:
        calls.append(args)
        if args == ("symbolic-ref", "--quiet", "--short", "HEAD"):
            return ["lane/small-fix"]
        raise AssertionError(f"local-commit enumerated refs: {args!r}")

    monkeypatch.setattr(module, "_run_git", fake_run_git)

    assert module.main(["--local-commit"]) == 0
    assert calls == [("symbolic-ref", "--quiet", "--short", "HEAD")]


def test_local_commit_rejects_undeclared_current_branch() -> None:
    issues = local_commit_issues(_repository_policy(), "release/other")

    assert len(issues) == 1
    assert "current branch 'release/other' is not allowed" in issues[0]
    assert issues[0].startswith("OPS.BRANCH.REF_NOT_ALLOWED:")


def test_local_commit_rejects_detached_head() -> None:
    issues = local_commit_issues(_repository_policy(), None)

    assert len(issues) == 1
    assert "detached HEAD is forbidden" in issues[0]
    assert issues[0].startswith("OPS.BRANCH.REF_NOT_ALLOWED:")


def test_default_mode_still_rejects_stale_undeclared_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    def fake_run_git(*args: str) -> list[str]:
        if args == ("for-each-ref", "--format=%(refname:short)", "refs/heads"):
            return ["dev1.0", "lane/small-fix", "stale/local"]
        if args == (
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/remotes/origin",
        ):
            return ["origin/dev1.0", "origin/lane/small-fix", "origin/stale/remote"]
        if args == ("symbolic-ref", "--quiet", "--short", "HEAD"):
            return ["lane/small-fix"]
        raise AssertionError(args)

    monkeypatch.setattr(module, "_run_git", fake_run_git)

    issues = module.current_repo_issues(_repository_policy())

    assert any("unexpected local branches: stale/local" in issue for issue in issues)
    assert any("unexpected remote branches: stale/remote" in issue for issue in issues)


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


@pytest.mark.parametrize("lane", list(LANE_BRANCHES))
def test_branch_policy_accepts_every_lane_to_dev_pull_request_edge(lane: str) -> None:
    assert (
        _issues(
            current_branch=None,
            local_branches=[],
            remote_branches=["dev1.0", "main", lane],
            ci_head_branch=lane,
            ci_base_branch="dev1.0",
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
        ("lane/small-fix", "main"),
        ("lane/small-fix", "lane/refactor"),
        ("lane/undeclared", "dev1.0"),
        ("dev1.0", "lane/small-fix"),
        ("main", "lane/small-fix"),
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


def test_hosted_pull_request_uses_only_remote_event_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_HEAD_REF", "lane/ops")
    monkeypatch.setenv("GITHUB_BASE_REF", "dev1.0")
    monkeypatch.setattr(
        module,
        "_run_git",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("hosted PR inspected local checkout refs")
        ),
    )

    assert current_repo_issues() == []


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
    payload["integration_branch_activation"]["bootstrap"]["source_branch"] = "main"
    payload["integration_branch_activation"]["bootstrap"]["target_branch"] = "main"
    payload["allowed_pull_request_edges"] = [{"head": "main", "base": "main"}]
    payload["pull_request_branch_prefixes"] = []
    payload.pop("persistent_lane_admission")
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


def test_local_commit_classifies_git_authority_failure_as_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    monkeypatch.setattr(
        module,
        "_run_git",
        lambda *_args: (_ for _ in ()).throw(
            subprocess.CalledProcessError(128, ["git", "symbolic-ref"])
        ),
    )

    assert module.main(["--local-commit"]) == 1
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "OPS.BRANCH.AUTHORITY_UNAVAILABLE" in output
    assert "recovery=restore_git_authority_then_retry" in output
    assert "Traceback" not in output


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


def test_cli_local_commit_mode_rejects_integration_branch(monkeypatch, capsys) -> None:
    import quwoquan_ops.gate.verify_git_branch_policy as module

    monkeypatch.setattr(module, "_current_branch", lambda: "dev1.0")
    assert module.main(["--local-commit"]) == 1
    output = capsys.readouterr().out
    assert "OPS.BRANCH.INTEGRATION_READ_ONLY" in output
    assert "terminal=blocked" in output
    assert "commit_from_a_lane_worktree_then_open_pull_request" in output


def test_policy_byte_loader_rejects_unknown_or_missing_root_fields() -> None:
    raw = (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_bytes()
    with pytest.raises(ValueError, match="root fields drifted"):
        load_policy_bytes(raw + b"unexpected_policy_field: true\n")
    with pytest.raises(ValueError, match="root fields drifted"):
        load_policy_bytes(raw.replace(b"production_workflow:", b"removed_workflow:", 1))


def test_persistent_lane_admission_schema_is_exact_and_closed() -> None:
    payload = yaml.safe_load(
        (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text(encoding="utf-8")
    )
    assert payload["persistent_lane_admission"] == {
        "isolation": "branch_per_writer",
        "promotion": "declared_pull_request_edge_only",
        "resync": "mandatory_fast_forward_after_integration_or_abort",
        "worktree_lifecycle": "retained",
        "concurrency_evidence": "required",
    }
    for mutate in (
        lambda value: value.update(unexpected=True),
        lambda value: value.update(resync="optional"),
        lambda value: value.update(worktree_lifecycle="deleted"),
        lambda value: value.pop("concurrency_evidence"),
    ):
        broken = yaml.safe_load(
            (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text(
                encoding="utf-8"
            )
        )
        mutate(broken["persistent_lane_admission"])
        with pytest.raises(ValueError, match="exact isolation/promotion/resync/worktree_lifecycle|must be"):
            load_policy_bytes(
                yaml.safe_dump(broken, allow_unicode=True, sort_keys=False).encode(
                    "utf-8"
                )
            )


def test_persistent_lane_admission_requires_exact_six_lane_closed_set() -> None:
    canonical = yaml.safe_load(
        (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_text(
            encoding="utf-8"
        )
    )
    for mutate in (
        lambda value: value["allowed_local_branches"].remove("lane/refactor"),
        lambda value: value["allowed_remote_branches"].append("lane/other"),
        lambda value: value["allowed_pull_request_edges"].append(
            {"head": "lane/ops", "base": "main"}
        ),
        lambda value: value.update(pull_request_branch_prefixes=["feature/"]),
    ):
        broken = yaml.safe_load(yaml.safe_dump(canonical, sort_keys=False))
        mutate(broken)
        with pytest.raises(
            ValueError, match="persistent lane admission|declared pull-request prefix"
        ):
            load_policy_bytes(
                yaml.safe_dump(broken, allow_unicode=True, sort_keys=False).encode(
                    "utf-8"
                )
            )


def test_legacy_temporary_execution_admission_key_is_rejected() -> None:
    raw = (ROOT / "quwoquan_ops/policies/branch_policy.yaml").read_bytes()
    legacy = raw.replace(
        b"persistent_lane_admission:", b"temporary_execution_admission:", 1
    )
    with pytest.raises(ValueError, match="root fields drifted"):
        load_policy_bytes(legacy)


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
