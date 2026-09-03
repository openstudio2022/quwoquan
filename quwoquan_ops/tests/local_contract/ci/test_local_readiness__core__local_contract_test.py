"""Local readiness exact-input, deferred, runner, staged, and hook contracts.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-003.t3
"""
from __future__ import annotations

import json
import os
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
    _state_root,
    _staged_identity,
    capture_fingerprint,
    enqueue_paths,
    parse_push_updates,
    plan_readiness,
    push_paths,
    resource_lock,
    run_readiness,
    verify_receipt,
    worker_once,
    source_execution_root,
    staged_paths,
)
from quwoquan_ops.ci.detect_ci_impacted_scopes import classify as classify_hosted  # noqa: E402
from quwoquan_ops.ci.impact_planner_core import (  # noqa: E402
    ImpactPlannerError,
    SCOPE_NAMES,
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
    base["checks"] = [{"id": "focused:test", "scope": "spec_contract", "phase": "focused", "command": ["bash", "-c", command], "cwd": ".", "resources": ["fixture"]}]
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
    assert plan["impact_planner"] == planner_identity()
    assert plan["impact_planner"]["source"] == "quwoquan-impact-planner"
    assert plan["impact_planner"]["version"] == "impact-planner-v1"
    assert plan["impact_planner"]["digest"].startswith("sha256:")


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


def test_after_edit_hook_failure_is_visible_and_never_passes(tmp_path: Path) -> None:
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


def test_queue_scope_outstanding_blocks_scope_and_worker_consumes_exact_item(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        enqueue_paths(["source.txt"], state_root=state)
        result = worker_once(state_root=state, debounce_seconds=0)
        assert result["status"] == "PASS"
        assert json.loads((state / "process/deferred-queue.json").read_text())["items"] == []
        (repo / "other.txt").write_text("other\n", encoding="utf-8")
        enqueue_paths(["other.txt"], state_root=state)
        plan = {**build_impact_plan(["source.txt"], level="scope", repo_root=repo), "mode": "workspace"}
        plan["fingerprint"] = capture_fingerprint(plan, repo_root=repo, mode="workspace", allow_missing_admission=True)
        with pytest.raises(LocalReadinessError, match="outstanding|owner manifest"):
            run_readiness(plan, repo_root=repo, state_root=state)


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
        with pytest.raises(LocalReadinessError, match="current owner manifest"):
            run_readiness(plan, repo_root=repo, state_root=state)
        assert not (state / "process/receipts/current").exists()
        assert not (state / "cache/exact-input").exists()


def test_staged_boundary_rejects_generated_only_and_production_without_related_test(tmp_path: Path) -> None:
    from quwoquan_ops.cli.local_readiness import _staged_governance

    with pytest.raises(LocalReadinessError, match="generated-only"):
        _staged_governance(["quwoquan_app/lib/generated/value.g.dart"])
    _staged_governance(["quwoquan_app/lib/runtime/value.dart"])


def test_data_scope_without_affected_tests_fails_closed_instead_of_verify_only() -> None:
    with pytest.raises(ValueError, match="affected tests"):
        build_impact_plan(["quwoquan_data/schema/unknown.schema.json"], level="scope")


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
            lambda check, log_path, *, repo_root, execution_env=None: (
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
            lambda check, log_path, *, repo_root, execution_env=None: {
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
        def drift(check, log_path, *, repo_root, execution_env=None):
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


def test_data_required_release_plan_cannot_be_skip_or_verify_only() -> None:
    plan = build_impact_plan(["quwoquan_data/tests/local_contract/execution/test_stage_receipt__handoff_chain__contract__local_contract_test.py"], level="release")
    assert plan["deferred"] == []
    assert any(check["id"] == "release:data" and check["command"] == ["bash", "quwoquan_ops/gate/gate_repo.sh", "--scope", "data"] for check in plan["checks"])
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    assert "expect_typed_pending_or_skipped \"quwoquan_data\"" in workflow
    assert "expect_typed_pending_or_skipped \"quwoquan_data_tests\"" in workflow


def test_failed_queue_item_backs_off_does_not_starve_and_dead_letters(monkeypatch: pytest.MonkeyPatch) -> None:
    with _repo() as directory:
        repo = Path(directory)
        _init(repo)
        (repo / "ready.txt").write_text("ready\n", encoding="utf-8")
        state = repo / "state"
        monkeypatch.setattr("lib.local_readiness.core.ROOT", repo)
        enqueue_paths(["source.txt", "ready.txt"], state_root=state)
        original_run = __import__("lib.local_readiness.core", fromlist=["run_readiness"]).run_readiness

        def selective(plan, **kwargs):
            if plan["paths"] == ["source.txt"]:
                raise LocalReadinessError("deterministic failure")
            return original_run(plan, **kwargs)

        monkeypatch.setattr("lib.local_readiness.core.run_readiness", selective)
        first = worker_once(state_root=state, debounce_seconds=0)
        assert first["status"] == "PENDING"
        assert first["processed"] == ["ready.txt", "source.txt"]
        items = json.loads((state / "process/deferred-queue.json").read_text(encoding="utf-8"))["items"]
        assert [item["path"] for item in items] == ["source.txt"]
        failed = items[0]
        assert failed["attempt_count"] == 1
        assert failed["next_eligible_at"] is not None
        assert failed["last_error_digest"].startswith("sha256:")
        assert failed["evidence_fingerprint_ref"].startswith("evidence-fingerprint-v1:")
        identity = (failed["evidence_fingerprint_ref"], failed["check_identity_digest"])
        backing_off = worker_once(state_root=state, debounce_seconds=0)
        assert backing_off["status"] == "BACKING_OFF"
        for _attempt in range(failed["max_attempts"] - 1):
            payload = json.loads((state / "process/deferred-queue.json").read_text(encoding="utf-8"))
            payload["items"][0]["next_eligible_at"] = "2000-01-01T00:00:00+00:00"
            (state / "process/deferred-queue.json").write_text(json.dumps(payload), encoding="utf-8")
            terminal = worker_once(state_root=state, debounce_seconds=0)
        assert terminal["status"] == "GATE_BLOCK"
        inspected = __import__("lib.local_readiness.core", fromlist=["inspect_state"]).inspect_state(state_root=state)
        assert inspected["readiness"] == "GATE_BLOCK"
        assert inspected["dead_letter"][0]["terminal"]["code"] == "LOCAL_READINESS.RETRY_EXHAUSTED"
        assert (inspected["dead_letter"][0]["evidence_fingerprint_ref"], inspected["dead_letter"][0]["check_identity_digest"]) == identity
        pointer_root = state / "process/receipts/current"
        failed_receipts = [] if not pointer_root.exists() else [
            json.loads(Path(json.loads(pointer.read_text(encoding="utf-8"))["receipt"]).read_text(encoding="utf-8"))
            for pointer in pointer_root.glob("*.json")
        ]
        assert all(receipt.get("paths") != ["source.txt"] for receipt in failed_receipts)
