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


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002.t1
def test_state_root_rejects_symlink_components_and_secures_temp_repo_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = repo / "state"
    assert _state_root(state) == state.absolute()
    assert state.is_dir()
    assert state.stat().st_mode & 0o077 == 0

    target = repo / "target"
    target.mkdir()
    linked = repo / "linked"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(LocalReadinessError, match="symlink component"):
        _state_root(linked / "state")
    monkeypatch.setenv("QWQ_LOCAL_READINESS_ROOT", str(linked / "override"))
    with pytest.raises(LocalReadinessError, match="symlink component"):
        _state_root()


def test_empty_legacy_queue_is_safely_projected_to_current_schema(tmp_path: Path) -> None:
    from lib.local_readiness.queue import read_queue

    queue = tmp_path / "queue.json"
    queue.write_text('{"schema":"local-readiness-queue-v1","items":[]}\n', encoding="utf-8")
    assert read_queue(queue) == {"schema": "local-readiness-queue-v2", "items": []}
    queue.write_text('{"schema":"local-readiness-queue-v1","items":[{}]}\n', encoding="utf-8")
    with pytest.raises(LocalReadinessError, match="queue schema"):
        read_queue(queue)


def test_queue_corruption_symlink_and_extra_fields_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init(repo)
    monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
    state = repo / "state"
    queue = state / "process/deferred-queue.json"
    enqueue_paths(["source.txt"], state_root=state)

    corruptions = [
        {"schema": "local-readiness-queue-v2", "items": [], "extra": True},
        {"schema": "local-readiness-queue-v2", "items": [{**json.loads(queue.read_text())["items"][0], "extra": True}]},
        {"schema": "wrong", "items": []},
    ]
    for value in corruptions:
        queue.write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(LocalReadinessError, match="queue"):
            enqueue_paths(["source.txt"], state_root=state)

    external = repo / "external-queue.json"
    external.write_text('{"schema":"local-readiness-queue-v2","items":[]}', encoding="utf-8")
    queue.unlink()
    queue.symlink_to(external)
    with pytest.raises(LocalReadinessError, match="regular file|symlink"):
        enqueue_paths(["source.txt"], state_root=state)
    queue.unlink()
    queue.mkdir()
    with pytest.raises(LocalReadinessError, match="regular file"):
        enqueue_paths(["source.txt"], state_root=state)


def test_atomic_write_and_resource_lock_reject_destination_symlinks(tmp_path: Path) -> None:
    state = tmp_path / "state"
    external = tmp_path / "external.json"
    external.write_text("unchanged\n", encoding="utf-8")
    destination = state / "process/value.json"
    destination.parent.mkdir(parents=True)
    destination.symlink_to(external)
    with pytest.raises(LocalReadinessError, match="destination"):
        _atomic_json(destination, {"status": "PASS"})
    assert external.read_text(encoding="utf-8") == "unchanged\n"

    locks = state / "process/locks"
    locks.mkdir()
    locks.rmdir()
    lock_target = tmp_path / "external-locks"
    lock_target.mkdir()
    locks.symlink_to(lock_target, target_is_directory=True)
    with pytest.raises(LocalReadinessError, match="symlink"):
        with resource_lock("runner", state_root=state):
            pass

    locks.unlink()
    locks.mkdir()
    external_lock = tmp_path / "external.lock"
    external_lock.touch()
    (locks / "runner.lock").symlink_to(external_lock)
    with pytest.raises(LocalReadinessError, match="lock|regular file"):
        with resource_lock("runner", state_root=state):
            pass


def test_cache_read_rejects_symlink_before_reuse(tmp_path: Path) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace", state_root=state)
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        cache = state / "cache/exact-input" / f"{receipt['fingerprint']['digest'].removeprefix('sha256:')}.json"
        external = Path(tempfile.mkdtemp()) / "external-cache.json"
        external.write_bytes(cache.read_bytes())
        cache.unlink()
        cache.symlink_to(external)
        with pytest.raises(LocalReadinessError, match="cache.*regular file|cache.*symlink"):
            run_readiness(plan, repo_root=repo, state_root=state)
        cache.unlink()
        cache.mkdir()
        with pytest.raises(LocalReadinessError, match="cache.*regular file"):
            run_readiness(plan, repo_root=repo, state_root=state)


def test_pointer_receipt_path_is_confined_and_reads_reject_symlinks(tmp_path: Path) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace", state_root=state)
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        pointer = next((state / "process/receipts/current").glob("*.json"))
        immutable = state / "process/receipts/by-fingerprint" / f"{receipt['fingerprint']['digest'].removeprefix('sha256:')}.json"
        external = repo / "external-receipt.json"
        external.write_text(immutable.read_text(encoding="utf-8"), encoding="utf-8")

        for raw in (str(external), "../../../../external-receipt.json"):
            value = json.loads(pointer.read_text(encoding="utf-8"))
            value["receipt"] = raw
            pointer.write_text(json.dumps(value), encoding="utf-8")
            with pytest.raises(LocalReadinessError, match="canonical|receipt"):
                verify_receipt(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace", state_root=state)

        value = {"schema": "local-readiness-current-pointer-v1", "receipt": str(immutable), "fingerprint": receipt["fingerprint"]["ref"]}
        pointer.write_text(json.dumps(value), encoding="utf-8")
        pointer_target = repo / "pointer-target.json"
        pointer.replace(pointer_target)
        pointer.symlink_to(pointer_target)
        with pytest.raises(LocalReadinessError, match="pointer.*regular file|pointer.*symlink"):
            verify_receipt(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace", state_root=state)

        pointer.unlink()
        pointer.mkdir()
        with pytest.raises(LocalReadinessError, match="pointer.*regular file"):
            verify_receipt(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace", state_root=state)
        pointer.rmdir()
        pointer_target.replace(pointer)
        receipt_target = repo / "receipt-target.json"
        immutable.replace(receipt_target)
        immutable.symlink_to(receipt_target)
        with pytest.raises(LocalReadinessError, match="receipt.*regular file|receipt.*symlink"):
            verify_receipt(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace", state_root=state)
        immutable.unlink()
        immutable.mkdir()
        with pytest.raises(LocalReadinessError, match="receipt.*regular file"):
            verify_receipt(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace", state_root=state)


def _commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", message],
        cwd=repo,
        check=True,
    )
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def test_dirty_unstaged_byte_cannot_affect_staged_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        source = repo / "source.txt"
        source.write_text("index-byte\n", encoding="utf-8")
        subprocess.run(["git", "add", "source.txt"], cwd=repo, check=True)
        source.write_text("dirty-byte\n", encoding="utf-8")
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="staged")

        observed: list[str] = []
        monkeypatch.setattr(
            "lib.local_readiness.core._run_check",
            lambda check, log_path, *, repo_root, execution_env=None, timeout_seconds=None: (
                observed.append((repo_root / "source.txt").read_text(encoding="utf-8"))
                or {"id": check["id"], "status": "PASS", "exit_code": 0, "elapsed_ms": 0, "log": str(log_path)}
            ),
        )
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        assert receipt["status"] == "PASS"
        assert receipt["source_execution"] == "immutable_capsule"
        assert observed == ["index-byte\n"]
        assert source.read_text(encoding="utf-8") == "dirty-byte\n"


def test_staged_capsule_materializes_exact_add_delete_rename_mode_and_symlink() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        (repo / "delete.txt").write_text("delete\n", encoding="utf-8")
        (repo / "rename.txt").write_text("rename\n", encoding="utf-8")
        (repo / "target.txt").write_text("target\n", encoding="utf-8")
        os.symlink("target.txt", repo / "link.txt")
        _commit_all(repo, "fixture")
        (repo / "added.txt").write_text("added\n", encoding="utf-8")
        (repo / "delete.txt").unlink()
        subprocess.run(["git", "mv", "rename.txt", "renamed.txt"], cwd=repo, check=True)
        subprocess.run(["chmod", "+x", "source.txt"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        (repo / "added.txt").write_text("dirty-after-index\n", encoding="utf-8")
        plan = plan_readiness(level="fast", paths=staged_paths(repo), repo_root=repo, mode="staged")
        state = repo / "state"
        with source_execution_root(repo_root=repo, mode="staged", state_root=_state_root(state), fingerprint=plan["fingerprint"]) as (capsule, env, entries):
            assert (capsule / "added.txt").read_text(encoding="utf-8") == "added\n"
            assert not (capsule / "delete.txt").exists()
            assert not (capsule / "rename.txt").exists()
            assert (capsule / "renamed.txt").read_text(encoding="utf-8") == "rename\n"
            assert os.access(capsule / "source.txt", os.X_OK)
            assert (capsule / "link.txt").is_symlink()
            assert os.readlink(capsule / "link.txt") == "target.txt"
            assert Path(env["GIT_DIR"]).parent.parent == _state_root(state) / "process/materializations"
            assert Path(env["GIT_DIR"]).is_dir()
            assert any(entry["path"] == "added.txt" for entry in entries)
        assert not list((state / "process/materializations").glob("*-*"))


def test_commit_and_push_capsules_execute_exact_commit_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        source = repo / "source.txt"
        source.write_text("commit-byte\n", encoding="utf-8")
        previous = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        head = _commit_all(repo, "candidate")
        source.write_text("dirty-byte\n", encoding="utf-8")
        monkeypatch.setattr(
            "lib.local_readiness.core._run_check",
            lambda check, log_path, *, repo_root, execution_env=None, timeout_seconds=None: {
                "id": check["id"],
                "status": "PASS" if (repo_root / "source.txt").read_text(encoding="utf-8") == "commit-byte\n" else "FAIL",
                "exit_code": 0 if (repo_root / "source.txt").read_text(encoding="utf-8") == "commit-byte\n" else 1,
                "elapsed_ms": 0,
                "log": str(log_path),
            },
        )
        commit_plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="commit")
        assert run_readiness(commit_plan, repo_root=repo, state_root=repo / "commit-state")["status"] == "PASS"
        updates = parse_push_updates(f"refs/heads/dev1.0 {head} refs/heads/dev1.0 {previous}\n")
        push_plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="push", push_updates=updates)
        assert run_readiness(push_plan, repo_root=repo, push_updates=updates, state_root=repo / "push-state")["status"] == "PASS"


def test_source_drift_during_worktree_run_stales_receipt_without_green(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        plan = plan_readiness(level="fast", paths=["source.txt"], repo_root=repo, mode="workspace")
        def drift(check, log_path, *, repo_root, execution_env=None, timeout_seconds=None):
            (repo_root / "source.txt").write_text("drift\n", encoding="utf-8")
            return {"id": check["id"], "status": "PASS", "exit_code": 0, "elapsed_ms": 0, "log": str(log_path)}

        monkeypatch.setattr("lib.local_readiness.core._run_check", drift)
        receipt = run_readiness(plan, repo_root=repo, state_root=state)
        assert receipt["status"] == "FAIL"
        assert receipt["input_stable"] is False
        assert not (state / "process/receipts/current").exists()


def test_capsule_rejects_symlink_escape_and_cleans_process_root() -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        os.symlink("../../outside", repo / "escape")
        subprocess.run(["git", "add", "escape"], cwd=repo, check=True)
        plan = plan_readiness(level="fast", paths=["escape"], repo_root=repo, mode="staged")
        state = repo / "state"
        with pytest.raises(LocalReadinessError, match="symlink target 越出"):
            with source_execution_root(repo_root=repo, mode="staged", state_root=_state_root(state), fingerprint=plan["fingerprint"]):
                pass
        materializations = state / "process/materializations"
        assert not list(materializations.iterdir())


def test_data_required_release_plan_and_delivery_closure_require_full_gates() -> None:
    import yaml

    from quwoquan_ops.gate.local_dependency_purity.shell_commands import (
        reachable_shell_array_tokens,
        reachable_shell_command_tokens,
    )

    plan = build_impact_plan(
        [
            "quwoquan_data/tests/local_contract/execution/"
            "test_stage_receipt__handoff_chain__contract__local_contract_test.py"
        ],
        level="release",
    )
    assert plan["deferred"] == []
    assert any(
        check["id"] == "release:data"
        and check["command"]
        == ["bash", "quwoquan_ops/gate/gate_repo.sh", "--scope", "data"]
        for check in plan["checks"]
    )

    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]
    for job_name in ("quwoquan_data", "quwoquan_data_tests"):
        assert jobs[job_name].get("if") is None

    summary = jobs["delivery_gate_summary"]
    assert summary.get("if") == "always()"
    summary_step = next(
        step
        for step in summary["steps"]
        if {"DATA", "DATA_TESTS"} <= set(step.get("env", {}))
    )
    assert summary_step.get("if") == "always()"
    assert summary_step.get("continue-on-error") in (None, False)
    assert summary_step["env"]["DATA"] == "${{ needs.quwoquan_data.result }}"
    assert (
        summary_step["env"]["DATA_TESTS"]
        == "${{ needs.quwoquan_data_tests.result }}"
    )
    summary_run = summary_step["run"]
    for job_name, result_variable in (
        ("quwoquan_data", "${DATA}"),
        ("quwoquan_data_tests", "${DATA_TESTS}"),
    ):
        assert len(
            reachable_shell_command_tokens(
                summary_run,
                command_prefix=("expect_success", job_name, result_variable),
            )
        ) == 1
        assert not reachable_shell_command_tokens(
            summary_run,
            command_prefix=(
                "expect_typed_pending_or_skipped",
                job_name,
                result_variable,
            ),
        )

    release_evidence = jobs["release_evidence"]
    aggregate = next(
        step
        for step in release_evidence["steps"]
        if step.get("name") == "Aggregate exact three-layer test results"
    )
    evidence_arguments = reachable_shell_array_tokens(
        aggregate["run"],
        array_name="ARGS",
        consumer_prefix=(
            "python3",
            "quwoquan_ops/ci/render_delivery_release_evidence.py",
        ),
    )
    for requirement in ("data", "data_tests"):
        assert any(
            evidence_arguments[index : index + 2]
            == ("--local-required", requirement)
            for index in range(len(evidence_arguments) - 1)
        )


def test_failed_queue_item_backs_off_does_not_starve_and_dead_letters(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        (repo / "z-ready.txt").write_text("ready\n", encoding="utf-8")
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        enqueue_paths(["source.txt", "z-ready.txt"], state_root=state)
        original_run = __import__("lib.local_readiness.core", fromlist=["run_readiness"]).run_readiness

        def selective(plan, **kwargs):
            if plan["paths"] == ["source.txt"]:
                raise LocalReadinessError("deterministic failure")
            return original_run(plan, **kwargs)

        monkeypatch.setattr("lib.local_readiness.core.run_readiness", selective)
        first = worker_once(state_root=state, debounce_seconds=0)
        assert first["status"] == "PENDING"
        assert first["processed"] == ["source.txt", "z-ready.txt"]
        items = json.loads((state / "process/deferred-queue.json").read_text(encoding="utf-8"))["items"]
        assert [item["path"] for item in items] == ["source.txt"]
        failed = items[0]
        assert failed["attempt_count"] == 1
        assert failed["next_eligible_at"] is not None
        assert failed["last_error_digest"].startswith("sha256:")
        assert failed["evidence_fingerprint_ref"].startswith("evidence-fingerprint-v1:")
        identity = (failed["evidence_fingerprint_ref"], failed["check_identity_digest"])
        payload = json.loads((state / "process/deferred-queue.json").read_text(encoding="utf-8"))
        payload["items"][0]["next_eligible_at"] = "2999-01-01T00:00:00+00:00"
        (state / "process/deferred-queue.json").write_text(json.dumps(payload), encoding="utf-8")
        backing_off = worker_once(state_root=state, debounce_seconds=0)
        assert backing_off["status"] == "BACKING_OFF"
        for _attempt in range(failed["max_attempts"] - 1):
            payload = json.loads((state / "process/deferred-queue.json").read_text(encoding="utf-8"))
            payload["items"][0]["next_eligible_at"] = "2000-01-01T00:00:00+00:00"
            (state / "process/deferred-queue.json").write_text(json.dumps(payload), encoding="utf-8")
            terminal = worker_once(state_root=state, debounce_seconds=0)
        assert terminal["status"] == "GATE_BLOCK"
        inspected = __import__("lib.local_readiness.core", fromlist=["inspect_state"]).inspect_state(state_root=state)
        assert inspected["readiness"] == "ADVISORY"
        assert inspected["queue_closure"]["blocking"] == []
        assert inspected["dead_letter"][0]["terminal"]["code"] == "LOCAL_READINESS.RETRY_EXHAUSTED"
        assert (inspected["dead_letter"][0]["evidence_fingerprint_ref"], inspected["dead_letter"][0]["check_identity_digest"]) == identity
        pointer_root = state / "process/receipts/current"
        failed_receipts = [] if not pointer_root.exists() else [
            json.loads(Path(json.loads(pointer.read_text(encoding="utf-8"))["receipt"]).read_text(encoding="utf-8"))
            for pointer in pointer_root.glob("*.json")
        ]
        assert all(receipt.get("paths") != ["source.txt"] for receipt in failed_receipts)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _forking_sleep_command(child_pid_path: Path) -> list[str]:
    fixture = (
        "import pathlib,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )
    return [sys.executable, "-c", fixture]


def test_readiness_check_timeout_kills_forked_process_group(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    check = {
        "id": "focused:hanging-fixture", "scope": "spec_contract",
        "phase": "focused", "command": _forking_sleep_command(child_pid_path),
        "cwd": ".", "resources": ["fixture"], "timeout_seconds": 1,
    }

    result = _run_check(check, tmp_path / "timeout.log", repo_root=ROOT)

    assert result["status"] == "FAIL"
    assert result["exit_code"] == 124
    assert result["timed_out"] is True
    assert result["termination_signal"] in {"SIGTERM", "SIGKILL"}
    assert result["outcome"] == "timeout"
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    for _ in range(50):
        if not _pid_exists(child_pid):
            break
        import time as _time
        _time.sleep(0.02)
    assert not _pid_exists(child_pid)


def test_worker_budget_terminates_current_check_process_group(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        child_pid_path = tmp_path / "worker-child.pid"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        contract = __import__("lib.local_readiness.core", fromlist=["_load_contract"])._load_contract()
        contract["worker"]["wall_clock_budget_seconds"] = 2.0
        monkeypatch.setattr("lib.local_readiness.core._load_contract", lambda: contract)
        enqueue_paths(["source.txt"], state_root=state)
        check = {
            "id": "focused:worker-hang", "scope": "spec_contract",
            "phase": "focused", "command": _forking_sleep_command(child_pid_path),
            "cwd": ".", "resources": ["fixture"], "timeout_seconds": 30,
        }
        canonical = build_impact_plan(["source.txt"], level="fast", repo_root=repo)
        canonical["checks"] = [check]
        monkeypatch.setattr(
            "lib.local_readiness.core.build_impact_plan",
            lambda paths, *, level, repo_root: {
                **canonical, "paths": list(paths), "level": level,
            },
        )
        started = __import__("time").monotonic()
        result = worker_once(state_root=state, debounce_seconds=0)
        elapsed = __import__("time").monotonic() - started

        assert elapsed < 6
        assert result["status"] == "PENDING"
        assert result["budget_exhausted"] is True
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        for _ in range(50):
            if not _pid_exists(child_pid):
                break
            __import__("time").sleep(0.02)
        assert not _pid_exists(child_pid)


def test_worker_once_honors_contract_item_cap_and_stable_order(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        for name in ("a.txt", "b.txt", "c.txt"):
            (repo / name).write_text(name + "\n", encoding="utf-8")
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        contract = __import__("lib.local_readiness.core", fromlist=["_load_contract"])._load_contract()
        contract["worker"]["max_items_per_run"] = 2
        monkeypatch.setattr("lib.local_readiness.core._load_contract", lambda: contract)
        enqueue_paths(["c.txt", "a.txt", "b.txt"], state_root=state)
        queue_path = state / "process/deferred-queue.json"
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
        for item in payload["items"]:
            item["enqueued_at"] = "2026-01-01T00:00:00+00:00"
            item["next_eligible_at"] = "2026-01-01T00:00:00+00:00"
        queue_path.write_text(json.dumps(payload), encoding="utf-8")

        result = worker_once(state_root=state, debounce_seconds=0)
        assert result["processed"] == ["a.txt", "b.txt"]
        assert result["status"] == "PENDING"
        assert result["budget_exhausted"] is True
        assert [item["path"] for item in json.loads(queue_path.read_text())["items"]] == ["c.txt"]


def test_worker_wall_clock_budget_is_checked_before_next_item(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        (repo / "later.txt").write_text("later\n", encoding="utf-8")
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        contract = __import__("lib.local_readiness.core", fromlist=["_load_contract"])._load_contract()
        contract["worker"]["max_items_per_run"] = 2
        contract["worker"]["wall_clock_budget_seconds"] = 1
        monkeypatch.setattr("lib.local_readiness.core._load_contract", lambda: contract)
        enqueue_paths(["source.txt", "later.txt"], state_root=state)
        ticks = iter((0.0, 0.0, 0.0, 2.0))
        last_tick = [2.0]

        def monotonic() -> float:
            last_tick[0] = next(ticks, last_tick[0])
            return last_tick[0]

        monkeypatch.setattr("lib.local_readiness.worker.time.monotonic", monotonic)
        processed_by_runner: list[str] = []

        def consume(plan, **kwargs):
            assert 0 < kwargs["wall_clock_budget_seconds"] <= 1
            processed_by_runner.extend(plan["paths"])
            clear_queue_exact(plan["paths"], state_root=kwargs["state_root"])
            return {"status": "PASS"}

        monkeypatch.setattr("lib.local_readiness.core.run_readiness", consume)
        result = worker_once(state_root=state, debounce_seconds=0)
        assert result["processed"] == processed_by_runner
        assert len(result["processed"]) == 1
        assert result["budget_exhausted"] is True
        assert result["status"] == "PENDING"


def test_inspect_exposes_backlog_oldest_and_failure_summaries(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        (repo / "failed.txt").write_text("failed\n", encoding="utf-8")
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        enqueue_paths(["source.txt", "failed.txt"], state_root=state)
        queue_path = state / "process/deferred-queue.json"
        payload = json.loads(queue_path.read_text(encoding="utf-8"))
        payload["items"][0]["enqueued_at"] = "2026-01-01T00:00:00+00:00"
        payload["items"][0]["next_eligible_at"] = "2026-01-01T00:00:00+00:00"
        payload["items"][0]["attempt_count"] = 1
        payload["items"][0]["last_error_digest"] = "sha256:" + "1" * 64
        queue_path.write_text(json.dumps(payload), encoding="utf-8")
        (repo / "source.txt").write_text("stale\n", encoding="utf-8")

        inspected = inspect_state(state_root=state)
        assert inspected["backlog_count"] == 2
        assert inspected["summary"]["pending_count"] == 2
        assert inspected["oldest_enqueued_at"] == "2026-01-01T00:00:00+00:00"
        assert inspected["oldest_age_seconds"] > 0
        assert inspected["failed_count"] == 1
        assert inspected["stale_count"] == 1
        assert inspected["running_count"] == 0
        assert len(inspected["queue"]["items"]) == 2
        assert inspected["queue_closure"]["enforcement"] == (
            "advisory_until_verified_consumer"
        )
        assert inspected["queue_closure"]["blocking"] == []
        assert {
            (item["classification"], item["path"])
            for item in inspected["queue_closure"]["advisories"]
        } == {
            ("exact-pending", "failed.txt"),
            ("foreign-pending", "source.txt"),
        }
