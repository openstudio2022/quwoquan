"""Local readiness exact-input, deferred, runner, staged, and hook contracts.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t3
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002.t3
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002.t4
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t4
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t5
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t6
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t7
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.local_readiness.core import (  # noqa: E402
    LocalReadinessError,
    _atomic_json,
    _run_check,
    _staged_identity,
    _state_root,
    capture_fingerprint,
    enqueue_paths,
    inspect_state,
    parse_push_updates,
    plan_readiness,
    push_paths,
    resource_lock,
    run_readiness,
    source_execution_root,
    staged_paths,
    verify_receipt,
    worker_once,
)
from lib.local_readiness.queue import (  # noqa: E402
    assert_scope_queue_closed,
    clear_queue_exact,
    path_queue_digest,
)

from quwoquan_ops.ci.detect_ci_impacted_scopes import (  # noqa: E402
    classify as classify_hosted,
)
from quwoquan_ops.ci.impact_planner_core import (  # noqa: E402
    SCOPE_NAMES,
    ImpactPlannerError,
    classify_impacts,
    planner_identity,
)
from quwoquan_ops.ci.local_readiness_planner import (  # noqa: E402
    build_impact_plan,
    classify_scopes,
)

HOOK = ROOT / "quwoquan_ops/hooks/local_readiness_after_edit.py"
PRE_COMMIT = ROOT / "quwoquan_ops/hooks/pre-commit"
PRE_PUSH = ROOT / "quwoquan_ops/hooks/pre-push"
COMMIT_GATE = ROOT / "quwoquan_ops/gate/commit_gate.sh"


def _repo() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory()


def _init(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "checkout", "-qb", "dev1.0"], cwd=path, check=True)
    (path / "source.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.txt"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "base"],
        cwd=path,
        check=True,
    )


def _commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.invalid",
            "commit", "-qm", message,
        ],
        cwd=repo,
        check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _minimal_plan(repo: Path, command: str, *, level: str = "fast", deferred: list | None = None) -> dict:
    base = {**build_impact_plan(["source.txt"], level=level, repo_root=repo), "mode": "workspace"}
    # Temporary-repository tests intentionally prove runner behavior with one
    # deterministic command; production run_readiness rejects this tampering.
    base["checks"] = [{"id": "focused:test", "scope": "spec_contract", "phase": "focused", "command": ["bash", "-c", command], "cwd": ".", "resources": ["fixture"], "timeout_seconds": 60}]
    base["deferred"] = deferred or []
    base["fingerprint"] = capture_fingerprint(base, repo_root=repo, mode="workspace", allow_missing_admission=True)
    return base


def test_canonical_property_table_keeps_local_and_hosted_common_scope_parity() -> None:
    table = (
        ("app", ["quwoquan_app/lib/runtime/bootstrap.dart"], {"app"}),
        ("service", ["quwoquan_service/services/chat-service/internal/chat.go"], {"service"}),
        ("data", ["quwoquan_data/schema/release/release_header.schema.json"], {"data"}),
        ("portal", ["quwoquan_ops/portal/src/app/App.tsx"], {"portal", "data"}),
        ("topology", ["quwoquan_ops/environments/prod/runtime.yaml"], set(SCOPE_NAMES)),
        ("workflow", [".github/workflows/delivery-gate.yml"], set(SCOPE_NAMES)),
        ("ops", ["quwoquan_ops/ci/impact_planner_core.py"], set(SCOPE_NAMES)),
        ("data-script", ["quwoquan_data/scripts/content/release/publish.py"], set(SCOPE_NAMES)),
        (
            "metadata",
            ["quwoquan_service/contracts/metadata/_schemas/common.yaml"],
            {"service", "app", "portal"},
        ),
        (
            "service-contract",
            ["quwoquan_service/services/user-service/contracts/account/storage.yaml"],
            {"service", "app", "portal"},
        ),
        ("doc", ["docs/ci/delivery-gate.md"], set()),
        (
            "mixed",
            [
                "quwoquan_app/lib/runtime/bootstrap.dart",
                "quwoquan_data/schema/release/release_header.schema.json",
            ],
            {"app", "data"},
        ),
    )
    for label, paths, expected in table:
        hosted = classify_hosted(paths)
        local = set(classify_scopes(paths))
        common_local = {scope for scope in SCOPE_NAMES if scope in local}
        actual = {scope for scope, required in hosted.items() if required}
        assert actual == expected, label
        assert common_local == actual, label


def test_spec_contract_is_only_a_local_projection() -> None:
    path = "specs/feature-tree/runtime/runtime-client-foundation/spec.md"
    canonical = classify_impacts([path])
    assert canonical["local_scopes"]["spec_contract"] is True
    assert "spec_contract" in classify_scopes([path])
    assert "spec_contract" not in classify_hosted([path])


def test_local_readiness_contract_declares_five_independent_fact_dimensions() -> None:
    contract = __import__("yaml").safe_load((ROOT / "quwoquan_ops/policies/local_readiness_contract.yaml").read_text(encoding="utf-8"))
    assert contract["schema_version"] == 2
    assert list(contract["fact_dimensions"]) == [
        "sourceReadiness", "environmentReadiness", "deviceReadiness",
        "integrationEligibility", "promotionEligibility",
    ]
    assert contract["independence"] == {
        "source_pass_implies": [],
        "cross_dimension_inference": "denied",
        "local_readiness_writes": ["sourceReadiness"],
        "non_source_default": "not_evaluated",
    }


def test_source_pass_keeps_all_other_readiness_dimensions_unevaluated() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace")
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        assert receipt["schema"] == "local-readiness-receipt-v2"
        assert "readiness" not in receipt
        assert receipt["facts"] == {
            "sourceReadiness": {"status": "fast_green", "producer": "local_readiness"},
            "environmentReadiness": {"status": "not_evaluated", "producer": "environment_ops"},
            "deviceReadiness": {"status": "not_evaluated", "producer": "package_acceptance"},
            "integrationEligibility": {"status": "not_evaluated", "producer": "trusted_integration_publisher"},
            "promotionEligibility": {"status": "not_evaluated", "producer": "integration_qualification"},
        }
        verify_receipt(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace", state_root=state)


def test_impact_plan_exposes_canonical_source_identity_and_version() -> None:
    plan = build_impact_plan(["quwoquan_app/lib/runtime/bootstrap.dart"], level="scope")
    canonical_identity = planner_identity()
    assert plan["impact_planner"] == canonical_identity
    assert plan["impact_planner"]["source"] == canonical_identity["source"]
    assert plan["impact_planner"]["version"] == canonical_identity["version"]
    assert plan["impact_planner"]["digest"].startswith("sha256:")


def test_plan_checks_have_canonical_bounded_timeout_identity() -> None:
    fast = build_impact_plan(["README.md"], level="fast")
    scope = build_impact_plan(["README.md"], level="scope")

    assert fast["schema"] == "local-readiness-plan-v2"
    assert fast["timeout_policy"] == scope["timeout_policy"]
    assert fast["timeout_policy"]["schema"] == "local-readiness-timeouts-v1"
    assert fast["timeout_policy"]["digest"].startswith("sha256:")
    assert fast["checks"]
    assert all(
        type(check["timeout_seconds"]) is int
        and 0 < check["timeout_seconds"] <= 300
        for check in fast["checks"]
    )
    assert all(type(check["timeout_seconds"]) is int for check in scope["checks"])


def test_candidate_impact_identity_closes_timeout_policy() -> None:
    from lib.candidate_evidence import _impact_plan

    projection, identity = _impact_plan(["README.md"], repo_root=ROOT)
    assert "timeout_policy" in projection
    assert set(identity) == {
        "schema", "digest", "projection_ref",
        "timeout_policy_ref", "timeout_policy_digest",
    }
    assert identity["timeout_policy_ref"] == projection["timeout_policy"]["source"]
    assert identity["timeout_policy_digest"] == projection["timeout_policy"]["digest"]


def test_ordinary_branch_policy_ignores_unrelated_local_ref(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init(repo)
    subprocess.run(["git", "checkout", "-qb", "lane/data-engineering"], cwd=repo, check=True)
    subprocess.run(["git", "branch", "lane/data-engineering-hard-cut"], cwd=repo, check=True)
    assert "lane/data-engineering-hard-cut" in subprocess.run(
        ["git", "branch", "--format=%(refname:short)"], cwd=repo,
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()

    (repo / "quwoquan_ops/gate").mkdir(parents=True)
    (repo / "quwoquan_ops/policies").mkdir(parents=True)
    shutil.copy2(
        ROOT / "quwoquan_ops/gate/verify_git_branch_policy.py",
        repo / "quwoquan_ops/gate/verify_git_branch_policy.py",
    )
    shutil.copytree(
        ROOT / "quwoquan_ops/gate/git_branch_policy",
        repo / "quwoquan_ops/gate/git_branch_policy",
    )
    shutil.copy2(
        ROOT / "quwoquan_ops/policies/branch_policy.yaml",
        repo / "quwoquan_ops/policies/branch_policy.yaml",
    )
    plan = build_impact_plan(["README.md"], level="fast")
    check = next(item for item in plan["checks"] if item["id"] == "static:branch_policy")
    assert check["command"][-1] == "--local-commit"

    result = _run_check(check, tmp_path / "branch-policy.log", repo_root=repo)
    assert result["status"] == "PASS"
    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    assert result["outcome"] == "exited"


def test_local_planner_rejects_malformed_or_outside_paths() -> None:
    for path in (
        "../outside.py",
        "quwoquan_app/../quwoquan_data/file.py",
        "/tmp/outside.py",
        "C:/repo/file.py",
        "quwoquan_app//lib/main.dart",
        "quwoquan_app/lib/main.dart\x00ignored",
        "quwoquan_app/lib/main.dart\nignored",
    ):
        with pytest.raises(ImpactPlannerError):
            build_impact_plan([path], level="scope")


def test_app_only_has_no_data_and_empty_hosted_classification_fails_closed() -> None:
    assert classify_hosted(["quwoquan_app/lib/runtime/bootstrap.dart"])["data"] is False
    failed_closed = classify_impacts([], fail_closed_empty=True)
    assert all(failed_closed["scopes"].values())

def test_same_git_status_with_changed_content_invalidates_fingerprint() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        source = repo / "source.txt"
        source.write_text("two\n", encoding="utf-8")
        status_before = subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True).stdout
        first = _minimal_plan(repo, "true")["fingerprint"]["digest"]
        source.write_text("three\n", encoding="utf-8")
        status_after = subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True).stdout
        second = _minimal_plan(repo, "true")["fingerprint"]["digest"]
        assert status_before == status_after == " M source.txt\n"
        assert first != second
    assert "git status --porcelain | shasum" not in COMMIT_GATE.read_text(encoding="utf-8")
    assert "local_readiness.py plan --level fast --staged" in COMMIT_GATE.read_text(encoding="utf-8")


def test_workspace_fingerprint_ignores_unrelated_tracked_worktree_bytes() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        unrelated = repo / "unrelated.txt"
        unrelated.write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "add", "unrelated.txt"], cwd=repo, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                "unrelated fixture",
            ],
            cwd=repo,
            check=True,
        )
        plan = _minimal_plan(repo, "true")
        first = plan["fingerprint"]["digest"]

        unrelated.write_text("two\n", encoding="utf-8")
        assert (
            capture_fingerprint(plan, repo_root=repo, mode="workspace")["digest"]
            == first
        )

        (repo / "source.txt").write_text("related change\n", encoding="utf-8")
        assert (
            capture_fingerprint(plan, repo_root=repo, mode="workspace")["digest"]
            != first
        )


def test_workspace_fingerprint_excludes_qwq_output_and_state_root() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = _minimal_plan(repo, "true")
        plan["paths"] = [".qwq_output/runtime.txt", "source.txt", "state/runtime.txt"]
        first = capture_fingerprint(
            plan, repo_root=repo, mode="workspace", state_root=state
        )["digest"]

        for relative in (".qwq_output/runtime.txt", "state/runtime.txt"):
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("managed mutation\n", encoding="utf-8")
        assert (
            capture_fingerprint(
                plan, repo_root=repo, mode="workspace", state_root=state
            )["digest"]
            == first
        )


def test_empty_input_scope_cannot_produce_readiness() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        empty = {**build_impact_plan([], level="scope", repo_root=repo), "mode": "workspace"}
        with pytest.raises(LocalReadinessError, match="空输入范围"):
            capture_fingerprint(empty, repo_root=repo, mode="workspace", allow_missing_admission=True)

def test_scope_deferred_is_a_hard_blocker() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        plan = _minimal_plan(repo, "true", level="scope", deferred=[{"scope": "data", "work": "remaining"}])
        with pytest.raises(LocalReadinessError, match="deferred"):
            run_readiness(plan, repo_root=repo, state_root=repo / "state")


def test_exact_input_pass_cache_hits_then_command_and_toolchain_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = Path(tempfile.mkdtemp()) / "state"
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace")
        first = run_readiness(plan, repo_root=repo, state_root=state)
        second = run_readiness(plan, repo_root=repo, state_root=state)
        assert first["status"] == "PASS" and not first["cache_hit"]
        assert second["status"] == "PASS" and second["cache_hit"]
        changed = {**plan, "checks": [{**plan["checks"][0], "command": ["bash", "-c", "printf changed >/dev/null"]}]}
        changed["fingerprint"] = capture_fingerprint(changed, repo_root=repo, mode="workspace")
        assert changed["fingerprint"]["digest"] != plan["fingerprint"]["digest"]
        with pytest.raises(LocalReadinessError, match="canonical planner exact plan"):
            run_readiness(changed, repo_root=repo, state_root=state)
        monkeypatch.setattr("lib.local_readiness.core._versions", lambda _commands: {"python": "changed"})
        toolchain_changed = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace")
        assert toolchain_changed["fingerprint"]["digest"] != plan["fingerprint"]["digest"]



def test_source_lockfile_owner_manifest_and_command_all_change_exact_input() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        (repo / "lock.txt").write_text("lock-one\n", encoding="utf-8")
        (repo / "owner.json").write_text('{"owner":"one"}\n', encoding="utf-8")
        base = _minimal_plan(repo, "true")
        base["lockfiles"] = ["lock.txt"]
        with pytest.raises(LocalReadinessError, match="current canonical manifest"):
            capture_fingerprint(base, repo_root=repo, mode="workspace", owner_manifest=repo / "owner.json")
        first = capture_fingerprint(base, repo_root=repo, mode="workspace")["digest"]

        (repo / "source.txt").write_text("source-two\n", encoding="utf-8")
        source_changed = capture_fingerprint(base, repo_root=repo, mode="workspace")["digest"]
        assert source_changed != first
        (repo / "source.txt").write_text("one\n", encoding="utf-8")

        (repo / "lock.txt").write_text("lock-two\n", encoding="utf-8")
        lock_changed = capture_fingerprint(base, repo_root=repo, mode="workspace")["digest"]
        assert lock_changed != first
        (repo / "lock.txt").write_text("lock-one\n", encoding="utf-8")

        (repo / "owner.json").write_text('{"owner":"two"}\n', encoding="utf-8")
        with pytest.raises(LocalReadinessError, match="current canonical manifest"):
            capture_fingerprint(base, repo_root=repo, mode="workspace", owner_manifest=repo / "owner.json")

        command_changed_plan = {**base, "checks": [{**base["checks"][0], "command": ["bash", "-c", "printf changed >/dev/null"]}]}
        command_changed = capture_fingerprint(command_changed_plan, repo_root=repo, mode="workspace")["digest"]
        assert command_changed != first

# spec_ref:
# - specs/feature-tree/runtime/runtime-control-plane-foundation/human-authority-role-cards/spec.md#gwt-001.t1
# - specs/feature-tree/runtime/runtime-control-plane-foundation/human-authority-role-cards/spec.md#gwt-001.t2
# - specs/feature-tree/runtime/runtime-control-plane-foundation/human-authority-role-cards/spec.md#gwt-001.t3
# - specs/feature-tree/runtime/runtime-control-plane-foundation/human-authority-role-cards/spec.md#gwt-001.t4
# - specs/feature-tree/runtime/runtime-control-plane-foundation/human-authority-role-cards/spec.md#gwt-001.t5
# - specs/feature-tree/runtime/runtime-control-plane-foundation/human-authority-role-cards/spec.md#gwt-001.t6
# - specs/feature-tree/runtime/runtime-control-plane-foundation/human-authority-role-cards/spec.md#gwt-002.t1
# - specs/feature-tree/runtime/runtime-control-plane-foundation/human-authority-role-cards/spec.md#gwt-002.t2
# - specs/feature-tree/runtime/runtime-control-plane-foundation/human-authority-role-cards/spec.md#gwt-002.t3
# - specs/feature-tree/runtime/runtime-control-plane-foundation/human-authority-role-cards/spec.md#gwt-003.t3
def test_portal_runner_executes_test_and_build() -> None:
    plan = build_impact_plan(["quwoquan_ops/portal/src/app/App.tsx"], level="scope")
    commands = [check["command"] for check in plan["checks"]]
    assert ["python3", "-B", "quwoquan_ops/cli/local_readiness.py", "managed-portal-test"] in commands
    assert ["python3", "-B", "quwoquan_ops/cli/local_readiness.py", "managed-portal-build"] in commands


def test_git_hooks_only_check_boundaries_and_never_consume_receipts() -> None:
    """硬门只在准出：本地 hooks 只做 staged boundary 与 branch policy，不消费 readiness 回执。"""
    source = PRE_COMMIT.read_text(encoding="utf-8")
    assert "commit_gate.sh" not in source
    assert "local_readiness.py staged-boundary" in source
    assert "--local-commit" in (ROOT / "quwoquan_ops/cli/local_readiness.py").read_text(encoding="utf-8")
    assert "verify --level" not in source
    assert "scope --staged" not in source
    assert "scope_ready" not in source
    assert "release_ready" not in source
    assert "readiness PASS" not in source
    pre_push = PRE_PUSH.read_text(encoding="utf-8")
    assert "verify_git_branch_policy.py --pre-push" in pre_push
    assert "verify --level release" not in pre_push
    assert "scope_ready" not in pre_push
    assert "release_ready" not in pre_push
    assert "readiness PASS" not in pre_push
    assert "local_readiness.py" not in pre_push


def test_staged_receipt_freshness_is_exact() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = Path(tempfile.mkdtemp()) / "state"
        source_file = repo / "source.txt"
        source_file.write_text("staged-one\n", encoding="utf-8")
        subprocess.run(["git", "add", "source.txt"], cwd=repo, check=True)
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="staged")
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        assert receipt["status"] == "PASS"
        verify_receipt(level="fast", paths=["source.txt"], repo_root=repo, mode="staged", state_root=state)
        source_file.write_text("worktree-after-receipt\n", encoding="utf-8")
        # Staged identity is index-only; an unstaged worktree edit must not invalidate it.
        verify_receipt(level="fast", paths=["source.txt"], repo_root=repo, mode="staged", state_root=state)
        source_file.write_text("staged-two\n", encoding="utf-8")
        subprocess.run(["git", "add", "source.txt"], cwd=repo, check=True)
        with pytest.raises(LocalReadinessError, match="stale"):
            verify_receipt(level="fast", paths=["source.txt"], repo_root=repo, mode="staged", state_root=state)


def test_host_hook_configs_do_not_wire_automatic_edit_readiness() -> None:
    codex = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
    cursor = json.loads((ROOT / ".cursor/hooks.json").read_text(encoding="utf-8"))

    assert "PostToolUse" not in codex["hooks"]
    assert "自动 edit readiness" in codex["description"]
    assert all(
        "local_readiness_after_edit.py" not in json.dumps(entry)
        for entries in codex["hooks"].values()
        for entry in entries
    )
    assert set(cursor["hooks"]) == {"beforeShellExecution", "sessionStart"}
    assert "local_readiness_after_edit.py" not in json.dumps(cursor)


def test_explicit_enqueue_cli_remains_available(tmp_path: Path) -> None:
    state = tmp_path / "state"
    completed = subprocess.run(
        [
            sys.executable, "-B", "quwoquan_ops/cli/local_readiness.py",
            "enqueue", "--path", "README.md", "--reason", "test_explicit",
        ],
        cwd=ROOT,
        env={**os.environ, "QWQ_LOCAL_READINESS_ROOT": str(state)},
        capture_output=True, text=True, check=False,
    )

    assert completed.returncode == 0, completed.stderr
    queued = json.loads(completed.stdout)
    assert queued["items"][0]["path"] == "README.md"
    assert queued["items"][0]["reason"] == "test_explicit"


def test_after_edit_script_failure_is_fail_open_and_never_passes(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["QWQ_LOCAL_READINESS_ROOT"] = str(tmp_path / "blocked" / "state")
    # Make the parent a file so queue creation fails deterministically.
    (tmp_path / "blocked").write_text("not a directory", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        cwd=ROOT,
        input=json.dumps({"file_path": str(ROOT / "README.md")}),
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert "入队失败" in payload["additional_context"]
    assert "未生成 readiness PASS" in payload["additional_context"]
    assert "fast_green" not in payload["additional_context"]


def test_runner_input_drift_does_not_write_pass_receipt() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = Path(tempfile.mkdtemp()) / "state"
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace")
        plan["checks"] = [{**plan["checks"][0], "command": ["bash", "-c", "printf drift >> source.txt"]}]
        plan["fingerprint"] = capture_fingerprint(plan, repo_root=repo, mode="workspace")
        with pytest.raises(LocalReadinessError, match="canonical planner exact plan"):
            run_readiness(plan, repo_root=repo, state_root=state)
        pointer_root = state / "process/receipts/current"
        failed_path_receipts = [] if not pointer_root.exists() else [
            json.loads(path.read_text(encoding="utf-8"))
            for path in pointer_root.glob("*.json")
            if "source.txt" in json.loads(Path(json.loads(path.read_text(encoding="utf-8"))["receipt"]).read_text(encoding="utf-8")).get("paths", [])
        ]
        assert failed_path_receipts == []


def test_staged_identity_covers_mode_blob_delete_rename_symlink_and_keeps_untracked_assets() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        (repo / "delete.txt").write_text("delete\n", encoding="utf-8")
        (repo / "rename.txt").write_text("rename\n", encoding="utf-8")
        (repo / "target-one.txt").write_text("one\n", encoding="utf-8")
        os.symlink("target-one.txt", repo / "link.txt")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
            cwd=repo,
            check=True,
        )
        (repo / "source.txt").write_text("mode-one\n", encoding="utf-8")
        subprocess.run(["chmod", "+x", "source.txt"], cwd=repo, check=True)
        (repo / "delete.txt").unlink()
        subprocess.run(["git", "mv", "rename.txt", "renamed.txt"], cwd=repo, check=True)
        (repo / "link.txt").unlink()
        os.symlink("delete.txt", repo / "link.txt")
        (repo / "untracked.txt").write_text("u1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        paths = ["source.txt", "delete.txt", "rename.txt", "renamed.txt", "link.txt", "untracked.txt"]
        identity = _staged_identity(repo, paths)
        assert all(identity[key] != "sha256:" + "0" * 64 for key in identity)
        assert identity["deleted_digest"] != identity["renamed_digest"]
        assert identity["symlink_digest"] != identity["tracked_digest"]
        first = {**build_impact_plan(paths, level="fast", repo_root=repo), "mode": "staged"}
        first_fp = capture_fingerprint(first, repo_root=repo, mode="staged")["digest"]
        (repo / "untracked-extra.txt").write_text("u2\n", encoding="utf-8")
        # An unrelated untracked file is outside exact staged scope and must not poison it.
        assert capture_fingerprint(first, repo_root=repo, mode="staged")["digest"] == first_fp
        (repo / "untracked.txt").write_text("u2\n", encoding="utf-8")
        # Index blob, not worktree bytes, owns the staged identity.
        assert capture_fingerprint(first, repo_root=repo, mode="staged")["digest"] == first_fp
        subprocess.run(["git", "add", "untracked.txt"], cwd=repo, check=True)
        assert capture_fingerprint(first, repo_root=repo, mode="staged")["digest"] != first_fp


def test_plan_tamper_fields_commands_level_and_empty_checks_fail_closed() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace")
        mutations = []
        mutations.append({**plan, "paths": ["source.txt", "other.txt"]})
        mutations.append({**plan, "level": "scope"})
        mutations.append({**plan, "checks": []})
        mutations.append({**plan, "checks": [{**plan["checks"][0], "id": "tampered"}]})
        mutations.append({**plan, "checks": [{**plan["checks"][0], "command": ["bash", "-c", "true"]}]})
        mutations.append({**plan, "checks": [{**plan["checks"][0], "timeout_seconds": plan["checks"][0]["timeout_seconds"] + 1}]})
        mutations.append({**plan, "timeout_policy": {**plan["timeout_policy"], "digest": "sha256:" + "0" * 64}})
        mutations.append({**plan, "unknown": True})
        for tampered in mutations:
            with pytest.raises(LocalReadinessError):
                run_readiness(tampered, repo_root=repo, state_root=state)


def test_cache_hit_recomputes_current_input_and_rejects_stale_plan() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace")
        first = run_readiness(plan, repo_root=repo, state_root=state)
        assert first["status"] == "PASS"
        (repo / "source.txt").write_text("changed\n", encoding="utf-8")
        with pytest.raises(LocalReadinessError, match="stale|changed"):
            run_readiness(plan, repo_root=repo, state_root=state)


@pytest.mark.parametrize("level", ["scope", "release"])
def test_scope_and_release_queue_pending_is_contract_advisory(
    monkeypatch: pytest.MonkeyPatch, level: str,
) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        (repo / "other.txt").write_text("other\n", encoding="utf-8")
        enqueue_paths(["source.txt", "other.txt"], state_root=state)
        plan = {
            **build_impact_plan(["source.txt"], level=level, repo_root=repo),
            "mode": "workspace",
        }
        plan["fingerprint"] = capture_fingerprint(
            plan, repo_root=repo, mode="workspace",
            allow_missing_admission=True, state_root=state,
        )

        closure = assert_scope_queue_closed(plan, state_root=state)
        assert closure["enforcement"] == "advisory_until_verified_consumer"
        assert closure["blocking"] == []
        assert [(item["classification"], item["path"]) for item in closure["advisories"]] == [
            ("foreign-pending", "other.txt"),
            ("exact-pending", "source.txt"),
        ]

        original_capture = capture_fingerprint

        def capture_without_admission(*args, **kwargs):
            kwargs["allow_missing_admission"] = True
            return original_capture(*args, **kwargs)

        monkeypatch.setattr(
            "lib.local_readiness.core.capture_fingerprint", capture_without_admission
        )
        monkeypatch.setattr(
            "lib.local_readiness.core._load_review_inputs",
            lambda *_args, **_kwargs: ([], {"required": True, "consolidation": None, "evidence": []}),
        )
        monkeypatch.setattr(
            "lib.local_readiness.core._run_check",
            lambda check, log_path, **_kwargs: {
                "id": check["id"], "status": "PASS", "exit_code": 0,
                "elapsed_ms": 0, "log": str(log_path), "timed_out": False,
                "termination_signal": None, "outcome": "exited",
            },
        )

        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        assert receipt["status"] == "PASS"
        assert receipt["queue_closure"] == closure
        remaining = json.loads(
            (state / "process/deferred-queue.json").read_text(encoding="utf-8")
        )["items"]
        assert [item["path"] for item in remaining] == ["other.txt"]


def test_queue_closure_enforcement_is_contract_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        enqueue_paths(["source.txt"], state_root=state)
        plan = {
            **build_impact_plan(["source.txt"], level="scope", repo_root=repo),
            "mode": "workspace",
        }
        contract = __import__(
            "lib.local_readiness.core", fromlist=["_load_contract"]
        )._load_contract()
        contract["queue_closure"]["enforcement"] = "block_exact_candidate_pending"
        monkeypatch.setattr("lib.local_readiness.core._load_contract", lambda: contract)

        with pytest.raises(LocalReadinessError, match="exact candidate.*pending"):
            assert_scope_queue_closed(plan, state_root=state)


def test_worker_consumes_exact_item(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        enqueue_paths(["source.txt"], state_root=state)
        result = worker_once(state_root=state, debounce_seconds=0)
        assert result["status"] == "PASS"
        assert json.loads((state / "process/deferred-queue.json").read_text())["items"] == []

def test_worker_typed_failure_keeps_queue_and_never_projects_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        enqueue_paths(["source.txt"], state_root=state)
        monkeypatch.setattr("lib.local_readiness.core.plan_readiness", lambda **_kwargs: (_ for _ in ()).throw(LocalReadinessError("typed")))
        result = worker_once(state_root=state, debounce_seconds=0)
        assert result["status"] == "PENDING"
        assert json.loads((state / "process/deferred-queue.json").read_text())["items"]
        assert not (state / "process/receipts/current").exists()


def test_push_updates_reject_fake_local_sha_and_non_fast_forward_base() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        fake = "1" * 40
        updates = parse_push_updates(f"refs/heads/dev1.0 {fake} refs/heads/dev1.0 {head}\n")
        with pytest.raises(LocalReadinessError, match="不存在|mismatch"):
            push_paths(repo, updates)
        subprocess.run(["git", "checkout", "-qb", "side"], cwd=repo, check=True)
        (repo / "side.txt").write_text("side\n", encoding="utf-8")
        subprocess.run(["git", "add", "side.txt"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "side"], cwd=repo, check=True)
        side = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "checkout", "-q", "dev1.0"], cwd=repo, check=True)
        updates = parse_push_updates(f"refs/heads/dev1.0 {head} refs/heads/dev1.0 {side}\n")
        with pytest.raises(LocalReadinessError, match="fast-forward"):
            push_paths(repo, updates)


def test_hook_contract_contains_single_recovery_and_no_full_gate_or_sensitive_prompt_fields() -> None:
    pre_commit = PRE_COMMIT.read_text(encoding="utf-8")
    assert pre_commit.count("[pre-commit] RECOVER:") == 1
    assert "commit_gate.sh" not in pre_commit
    assert "gate_repo.sh" not in pre_commit
    contract = (ROOT / "quwoquan_ops/policies/local_readiness_contract.yaml").read_text(encoding="utf-8")
    assert "prompt" not in contract.lower()
    assert ".qwq_output" in contract
    assert "logs:" not in contract


def test_scope_producer_requires_current_owner_review_and_required_evidence_before_any_pass() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="scope", paths=["source.txt"], repo_root=repo, mode="workspace")
        with pytest.raises(
            LocalReadinessError,
            match=r"scope/release readiness 要求 owner identity \+ candidate evidence",
        ):
            run_readiness(plan, repo_root=repo, state_root=state)
        assert not (state / "process/receipts/current").exists()
        assert not (state / "cache/exact-input").exists()


def test_staged_boundary_rejects_generated_only_and_production_without_related_test(tmp_path: Path) -> None:
    from quwoquan_ops.cli.local_readiness import _staged_governance

    with pytest.raises(LocalReadinessError, match="generated-only"):
        _staged_governance(["quwoquan_app/lib/generated/value.g.dart"])
    _staged_governance(["quwoquan_app/lib/runtime/value.dart"])


def test_staged_boundary_blocks_staged_unstaged_same_path_overlap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import quwoquan_ops.cli.local_readiness as cli

    repo = tmp_path / "repo"
    repo.mkdir()
    _init(repo)
    source = repo / "source.txt"
    source.write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.txt"], cwd=repo, check=True)
    source.write_text("unstaged\n", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", repo)

    with pytest.raises(
        LocalReadinessError, match="LOCAL_READINESS.STAGED_UNSTAGED_OVERLAP"
    ):
        cli.command_staged_boundary(None)


def test_staged_boundary_allows_unrelated_unstaged_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import quwoquan_ops.cli.local_readiness as cli

    repo = tmp_path / "repo"
    repo.mkdir()
    _init(repo)
    (repo / "other.txt").write_text("one\n", encoding="utf-8")
    _commit_all(repo, "add other")
    (repo / "source.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.txt"], cwd=repo, check=True)
    (repo / "other.txt").write_text("unstaged\n", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", repo)
    monkeypatch.setattr(cli, "_staged_governance", lambda _paths: None)
    real_run = subprocess.run

    def branch_pass(command, **kwargs):
        if any("verify_git_branch_policy.py" in str(item) for item in command):
            return subprocess.CompletedProcess(command, 0, "", "")
        return real_run(command, **kwargs)

    monkeypatch.setattr(cli.subprocess, "run", branch_pass)
    assert cli.command_staged_boundary(None) == 0


def test_staged_boundary_blocks_delete_then_untracked_recreation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import quwoquan_ops.cli.local_readiness as cli

    repo = tmp_path / "repo"
    repo.mkdir()
    _init(repo)
    source = repo / "source.txt"
    source.unlink()
    subprocess.run(["git", "add", "-A", "source.txt"], cwd=repo, check=True)
    source.write_text("untracked replacement\n", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", repo)

    with pytest.raises(
        LocalReadinessError, match="LOCAL_READINESS.STAGED_UNSTAGED_OVERLAP"
    ):
        cli.command_staged_boundary(None)


def test_staged_boundary_uses_local_commit_branch_policy() -> None:
    source = (ROOT / "quwoquan_ops/cli/local_readiness.py").read_text(
        encoding="utf-8"
    )
    command_start = source.index("def command_staged_boundary")
    command_end = source.index("\ndef _common", command_start)
    boundary_source = source[command_start:command_end]

    assert '"quwoquan_ops/gate/verify_git_branch_policy.py",' in boundary_source
    assert '"--local-commit",' in boundary_source
    assert "--pre-push" not in boundary_source


def test_staged_pii_phone_pattern_ignores_digits_inside_hex_digests() -> None:
    from quwoquan_ops.cli.local_readiness import _PII_PATTERNS

    phone_pattern = _PII_PATTERNS[0]
    digest = b'"sha256": "18916601719eac77353c72e05249c70eb08b547c61f87c78c4f760d94c1f00"'
    assert phone_pattern.search(digest) is None
    # 号码字面量在源码里拆开拼接，避免本测试文件自己被 staged-boundary 判为直接 PII。
    phone = b"189" + b"16601719"
    assert phone_pattern.search(b"contact " + phone + b" now").group(0) == phone
    assert phone_pattern.search(b"phone=" + phone + b",") is not None


def test_staged_pii_email_pattern_ignores_image_density_suffixes() -> None:
    from quwoquan_ops.cli.local_readiness import _PII_PATTERNS

    email_pattern = _PII_PATTERNS[1]
    assert email_pattern.search(b"LaunchBrandCluster@2x.png") is None
    email = b"owner" + b"@" + b"quwoquan.example"
    assert email_pattern.search(email) is not None


def test_data_scope_without_affected_tests_fails_closed_instead_of_verify_only() -> None:
    with pytest.raises(ValueError, match="affected tests"):
        build_impact_plan(["quwoquan_data/schema/unknown.schema.json"], level="scope")


def test_selector_deferred_directories_stay_explicit_and_out_of_managed_pytest() -> None:
    source = "quwoquan_data/scripts/content/execution/handler.py"
    target = "quwoquan_data/tests/local_contract/execution"

    fast = build_impact_plan([source], level="fast")
    scope = build_impact_plan([source], level="scope")
    release = build_impact_plan([source], level="release")

    assert {"scope": "data", "work": target} in fast["deferred"]
    assert scope["deferred"] == []
    assert release["deferred"] == []
    for plan in (fast, scope, release):
        python_checks = [
            check for check in plan["checks"] if check["id"] == "focused:python"
        ]
        assert all(target not in check["command"] for check in python_checks)
    assert any(check["id"] == "static:data_verify" for check in scope["checks"])
    assert any(
        check["id"] == "scope_build:data-local-contract"
        and check["command"] == [
            "env",
            "GATE_DATA_PHASE=local_contract",
            "bash",
            "quwoquan_ops/gate/gate_repo.sh",
            "--scope",
            "data",
        ]
        for check in scope["checks"]
    )
    assert any(
        check["id"] == "release:data"
        and check["command"] == [
            "bash", "quwoquan_ops/gate/gate_repo.sh", "--scope", "data"
        ]
        for check in release["checks"]
    )


def test_selector_plan_is_stable_for_equivalent_input_order() -> None:
    paths = [
        "quwoquan_ops/gate/verify_ci_cd_evidence_contracts.py",
        "quwoquan_ops/ci/github_actions_timing.py",
    ]

    first = build_impact_plan(paths, level="fast")
    second = build_impact_plan(list(reversed(paths)), level="fast")

    assert first == second


def test_source_scope_routes_fast_and_full_code_health_with_bounded_timeouts() -> None:
    path = "quwoquan_ops/ci/value.py"
    fast = build_impact_plan([path], level="fast")
    scope = build_impact_plan([path], level="scope")
    fast_check = next(check for check in fast["checks"] if check["id"] == "static:code_health_delta_fast")
    full_check = next(check for check in scope["checks"] if check["id"] == "static:code-health-delta")
    assert fast_check["timeout_seconds"] == 30
    assert "--mode" in fast_check["command"] and "fast" in fast_check["command"]
    assert full_check["timeout_seconds"] == 300
    assert "full" in full_check["command"] and path in full_check["command"]
    assert not any(check["id"] == "static:code_health_delta_fast" for check in scope["checks"])


def test_unknown_root_path_stays_focused_locally_but_fans_out_in_delivery() -> None:
    """未知根级路径的 scope 事实为零；Delivery 层才把它升到 R3 并全 scope。

    本地 L-1/L0 复用 classify_impacts 做秒级反馈，若在此扇出，任何陌生根文件都会
    让 fast 反馈跑遍全部 scope，直接违反 REQ-001 的短时完成要求。
    """
    from quwoquan_ops.ci.impact_planner_core import build_delivery_impact_plan, classify_impacts

    local = classify_impacts(["source.txt"])
    assert not any(local["scopes"].values())
    # 零运行时 scope 时本地 planner 回落到 spec_contract，不为陌生根文件调度任何
    # portal/service/app/data 的 focused 或 scope_build 检查。
    fast = build_impact_plan(["source.txt"], level="fast")
    assert fast["scopes"] == ["spec_contract"]
    assert not any(
        check["id"].startswith(("focused:portal", "focused:go", "focused:dart", "focused:data", "scope_build:"))
        for check in fast["checks"]
    )

    delivery = build_delivery_impact_plan(
        ["source.txt"], source_sha="b" * 40, base_sha="a" * 40,
        source_tree_digest="sha1:" + "c" * 40,
    )
    assert delivery["risk"]["level"] == "R3"
    assert all(delivery["scopes"][name] for name in ("service", "app", "portal", "topology", "data"))
