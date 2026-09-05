"""Canonical incremental code-health delta contracts.

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t1
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t2
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t3
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t4
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-002.t1
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-002.t2
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-002.t3
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-003.t1
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-003.t2
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-003.t3
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-007.t1
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-007.t2
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-007.t3
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-007.t4
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-007.t5
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.gate import verify_incremental_code_health
from quwoquan_ops.gate.code_health_delta.classification import classify_path
from quwoquan_ops.gate.code_health_delta.engine import REPORT_SCHEMA, analyze_delta
from quwoquan_ops.gate.code_health_delta import git_delta
from quwoquan_ops.gate.code_health_delta.metrics import reuse_scope_key
from quwoquan_ops.gate.code_health_delta.policy import PolicyError, load_policy

ROOT = Path(__file__).resolve().parents[4]
POLICY = ROOT / "quwoquan_ops/policies/code_health_policy.yaml"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def init_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "Fixture")
    (repo / "quwoquan_ops/policies").mkdir(parents=True)
    (repo / "quwoquan_ops/policies/code_health_policy.yaml").write_bytes(
        POLICY.read_bytes()
    )
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    return repo, git(repo, "rev-parse", "HEAD")


def commit(repo: Path, message: str = "candidate") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def write(repo: Path, relative: str, body: str) -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_seven_categories_are_mutually_exclusive() -> None:
    policy = load_policy(POLICY)
    cases = {
        "quwoquan_app/lib/service/post.dart": "handwritten-production",
        "quwoquan_app/test/local_contract/post_test.dart": "test",
        "quwoquan_service/generated/content/post.g.go": "generated",
        "quwoquan_service/runtime/observability/operation_privacy_generated.go": "generated",
        "quwoquan_app/vendor/sdk/lib.dart": "vendor",
        "quwoquan_service/services/content/contracts/post/fields.yaml": "contract-metadata",
        "quwoquan_ops/environments/prod/runtime.yaml": "config-data",
        "specs/feature-tree/runtime/spec.md": "docs",
    }
    assert {classify_path(path, policy) for path in cases} == set(cases.values())
    for path, expected in cases.items():
        assert classify_path(path, policy) == expected


def test_reuse_scope_is_bounded_without_a_second_owner_registry() -> None:
    assert reuse_scope_key("quwoquan_service/services/chat-service/internal/usecase.go") == "quwoquan_service/services/chat-service"
    assert reuse_scope_key("quwoquan_app/lib/service/chat_service/feed/page.dart") == "quwoquan_app/lib/service/chat_service"
    assert reuse_scope_key("quwoquan_ops/ci/delivery.py") == "quwoquan_ops/ci"
    assert reuse_scope_key("quwoquan_data/scripts/content/publish.py") == "quwoquan_data/scripts/content"


def test_policy_is_closed_and_rejects_automatic_promotion(tmp_path: Path) -> None:
    raw = POLICY.read_text(encoding="utf-8")
    invalid = tmp_path / "policy.yaml"
    invalid.write_text(raw.replace("automatic_promotion: false", "automatic_promotion: true"), encoding="utf-8")
    with pytest.raises(PolicyError, match="automatic_promotion"):
        load_policy(invalid)


def test_policy_rejects_unknown_nested_field_and_false_active_tool(tmp_path: Path) -> None:
    raw = POLICY.read_text(encoding="utf-8")
    invalid = tmp_path / "policy.yaml"
    invalid.write_text(
        raw.replace("    block: 1000", "    block: 1000\n    bypass: true"),
        encoding="utf-8",
    )
    with pytest.raises(PolicyError, match="thresholds.file_lines 字段不闭合"):
        load_policy(invalid)

    invalid.write_text(
        raw.replace(
            "python: {provider: ruff, rules: [C901, PLR0912, PLR0915], version: unavailable, status: advisory-unavailable}",
            "python: {provider: ruff, rules: [C901, PLR0912, PLR0915], version: unavailable, status: active}",
        ),
        encoding="utf-8",
    )
    with pytest.raises(PolicyError, match="active 时必须声明 exact version"):
        load_policy(invalid)


def test_suffixless_tracked_executable_blocks_before_source_classification(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    binary = repo / "quwoquan_service/codegen_storage"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    head = commit(repo)

    report = analyze_delta(repo, base=base, head=head, policy_path=POLICY)

    assert classify_path("quwoquan_service/codegen_storage", load_policy(POLICY)) == "config-data"
    assert any(
        finding["code"] == "CODE_HEALTH.TRACKED_SOURCE_EXECUTABLE"
        and finding["path"] == "quwoquan_service/codegen_storage"
        and finding["terminal"] == "GATE_BLOCK"
        for finding in report["findings"]
    )


def test_invalid_python_and_candidate_blob_read_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, base = init_repo(tmp_path)
    invalid = write(repo, "quwoquan_ops/ci/invalid.py", "def broken(:\n")
    head = commit(repo)
    with pytest.raises(ValueError, match="syntax unavailable"):
        analyze_delta(repo, base=base, head=head, policy_path=POLICY, mode="full")

    invalid.write_text("VALUE = 1\n", encoding="utf-8")
    original = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: (_ for _ in ()).throw(OSError("denied"))
        if path == invalid else original(path),
    )
    with pytest.raises(ValueError, match="candidate bytes unavailable"):
        git_delta.working_tree_blob(repo, "quwoquan_ops/ci/invalid.py")


def test_tracked_index_blob_read_failure_is_not_treated_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _ = init_repo(tmp_path)
    path = "quwoquan_ops/ci/tracked.py"
    write(repo, path, "VALUE = 1\n")
    subprocess.run(["git", "add", path], cwd=repo, check=True)
    original_run = subprocess.run

    def fail_show(command, *args, **kwargs):
        if command[:2] == ["git", "show"]:
            return subprocess.CompletedProcess(command, 128, b"", b"index read denied")
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(git_delta.subprocess, "run", fail_show)
    with pytest.raises(ValueError, match="index read denied"):
        git_delta.index_blob(repo, path)


def test_new_oversized_file_blocks_but_generated_and_test_do_not(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    body = "value = 1\n" * 1001
    write(repo, "quwoquan_ops/ci/new_module.py", body)
    write(repo, "quwoquan_service/generated/new_module.py", body)
    write(repo, "quwoquan_ops/tests/local_contract/ci/test_big.py", body)
    head = commit(repo)
    report = analyze_delta(repo, base=base, head=head, policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="fast")
    assert report["terminal"] == "GATE_BLOCK"
    blockers = [item for item in report["findings"] if item["terminal"] == "GATE_BLOCK"]
    assert [(item["code"], item["path"]) for item in blockers] == [
        ("CODE_HEALTH.NEW_FILE_OVER_BLOCK", "quwoquan_ops/ci/new_module.py")
    ]


def test_existing_oversized_growth_blocks_and_shrink_passes(tmp_path: Path) -> None:
    repo, _ = init_repo(tmp_path)
    target = write(repo, "quwoquan_ops/ci/large.py", "value = 1\n" * 1001)
    base = commit(repo, "oversized baseline")
    target.write_text("value = 1\n" * 1002, encoding="utf-8")
    grown = commit(repo, "grow")
    report = analyze_delta(repo, base=base, head=grown, policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="fast")
    assert any(item["code"] == "CODE_HEALTH.OVERSIZED_FILE_GROWTH" for item in report["findings"])
    target.write_text("value = 1\n" * 900, encoding="utf-8")
    shrunk = commit(repo, "shrink")
    report = analyze_delta(repo, base=grown, head=shrunk, policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="fast")
    assert not any(item["code"].startswith("CODE_HEALTH.OVERSIZED") for item in report["findings"])


def test_complexity_and_cross_old_code_duplication_are_advisory(tmp_path: Path) -> None:
    repo, _ = init_repo(tmp_path)
    duplicated = "\n".join(f"    value_{i} = {i}" for i in range(24))
    write(repo, "quwoquan_ops/ci/existing.py", f"def existing():\n{duplicated}\n")
    base = commit(repo, "existing source")
    branches = "\n".join(f"    if value == {i}:\n        value += {i}" for i in range(18))
    write(repo, "quwoquan_ops/ci/candidate.py", f"def complex_value(value):\n{duplicated}\n{branches}\n    return value\n")
    head = commit(repo)
    report = analyze_delta(repo, base=base, head=head, policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="full")
    codes = {item["code"] for item in report["findings"]}
    assert "CODE_HEALTH.COMPLEXITY_ADVISORY" in codes
    assert "CODE_HEALTH.DUPLICATION_ADVISORY" in codes
    assert report["terminal"] == "PR_WARN"


def test_duplication_advisory_requires_minimum_lines_and_percent_threshold(tmp_path: Path) -> None:
    repo, _ = init_repo(tmp_path)
    duplicated = "\n".join(f"    value_{i} = {i}" for i in range(24))
    write(repo, "quwoquan_ops/ci/existing.py", f"def existing():\n{duplicated}\n")
    base = commit(repo, "existing source")

    write(repo, "quwoquan_ops/ci/small.py", "def small():\n" + "\n".join(
        f"    value_{i} = {i}" for i in range(6)
    ) + "\n")
    small_head = commit(repo, "small duplicate")
    small_report = analyze_delta(
        repo, base=base, head=small_head,
        policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="full",
    )
    assert not any(item["code"] == "CODE_HEALTH.DUPLICATION_ADVISORY" for item in small_report["findings"])

    write(repo, "quwoquan_ops/ci/large.py", f"def large():\n{duplicated}\n")
    large_head = commit(repo, "large duplicate")
    large_report = analyze_delta(
        repo, base=base, head=large_head,
        policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="full",
    )
    advisory = next(
        item for item in large_report["findings"]
        if item["code"] == "CODE_HEALTH.DUPLICATION_ADVISORY"
    )
    assert advisory["path"] == "<candidate>"
    assert advisory["measure"]["measuredNewLines"] >= 20
    assert advisory["measure"]["percent"] > advisory["measure"]["threshold"]


def test_new_unreferenced_python_module_blocks_but_imported_module_passes(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    write(repo, "quwoquan_data/scripts/content/private_orphan.py", "def calculate():\n    return 1\n")
    first = commit(repo, "orphan")
    report = analyze_delta(repo, base=base, head=first, policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="fast")
    assert any(item["code"] == "CODE_HEALTH.NEW_PRIVATE_PYTHON_WITHOUT_ENTRY" for item in report["findings"])

    write(repo, "quwoquan_data/scripts/cli.py", "from quwoquan_data.scripts.content.private_orphan import calculate\nprint(calculate())\n")
    second = commit(repo, "wire entry")
    report = analyze_delta(repo, base=base, head=second, policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="fast")
    assert not any(item["code"] == "CODE_HEALTH.NEW_PRIVATE_PYTHON_WITHOUT_ENTRY" for item in report["findings"])


def test_rename_delete_and_atomic_migration_are_not_size_blockers(tmp_path: Path) -> None:
    repo, _ = init_repo(tmp_path)
    write(repo, "quwoquan_ops/ci/old_name.py", "value = 1\n" * 450)
    base = commit(repo, "source")
    git(repo, "mv", "quwoquan_ops/ci/old_name.py", "quwoquan_ops/ci/new_name.py")
    head = commit(repo, "rename")
    report = analyze_delta(repo, base=base, head=head, policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="full")
    assert report["summary"]["renamedFiles"] == 1
    assert not any(item["code"] == "CANDIDATE.SPLIT_REQUIRED" for item in report["findings"])
    (repo / "quwoquan_ops/ci/new_name.py").unlink()
    deleted = commit(repo, "delete")
    report = analyze_delta(repo, base=head, head=deleted, policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="full")
    assert report["summary"]["deletedFiles"] == 1
    assert report["terminal"] == "PASS"


def test_index_only_reads_staged_bytes_and_ignores_later_worktree_edits(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    target = write(repo, "quwoquan_ops/ci/staged_value.py", "VALUE = 1\n")
    git(repo, "add", str(target.relative_to(repo)))
    target.write_text("VALUE = 1\n" * 1001, encoding="utf-8")

    staged = analyze_delta(
        repo, base=base, head=base,
        policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml",
        mode="fast", explicit_paths=["quwoquan_ops/ci/staged_value.py"],
        working_tree=True, index_only=True,
    )
    worktree = analyze_delta(
        repo, base=base, head=base,
        policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml",
        mode="fast", explicit_paths=["quwoquan_ops/ci/staged_value.py"],
        working_tree=True,
    )
    assert staged["candidateSource"] == "index"
    assert staged["terminal"] == "PASS"
    assert worktree["terminal"] == "GATE_BLOCK"
    assert staged["evidenceFingerprint"]["digest"] != worktree["evidenceFingerprint"]["digest"]


def test_index_only_large_binary_delete_does_not_read_candidate_or_base_blob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _ = init_repo(tmp_path)
    target = repo / "quwoquan_ops/ci/large_artifact.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\0" * (4 * 1024 * 1024))
    base = commit(repo, "large binary baseline")
    target.unlink()
    git(repo, "add", "-A")

    def unexpected_blob(*args: object, **kwargs: object) -> bytes | None:
        raise AssertionError("deleted binary must not be read through blob helpers")

    monkeypatch.setattr(git_delta, "blob", unexpected_blob)
    monkeypatch.setattr(git_delta, "index_blob", unexpected_blob)

    delta = git_delta.working_tree_changes(
        repo, base, ["quwoquan_ops/ci/large_artifact.bin"], index_only=True,
    )

    assert delta == [
        git_delta.Change(
            status="D",
            path="quwoquan_ops/ci/large_artifact.bin",
            old_path=None,
            added=0,
            deleted=0,
            changed_new_lines=frozenset(),
        )
    ]


def test_default_cli_includes_untracked_source_and_binds_its_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _ = init_repo(tmp_path)
    target = write(repo, "quwoquan_ops/ci/untracked_value.py", "VALUE = 1\n")
    output = tmp_path / "report.json"
    monkeypatch.setattr(verify_incremental_code_health, "ROOT", repo)

    assert verify_incremental_code_health.main(["--mode", "fast", "--output", str(output)]) == 0
    first = json.loads(output.read_text(encoding="utf-8"))
    assert first["candidateSource"] == "working-tree"
    assert first["changedPaths"] == ["quwoquan_ops/ci/untracked_value.py"]
    assert first["categorySummary"]["handwritten-production"]["files"] == 1
    assert first["evidenceFingerprint"]["digest_payload"]["workspace"]["untracked_digest"] != (
        first["evidenceFingerprint"]["digest_payload"]["workspace"]["tracked_digest"]
    )

    target.write_text("VALUE = 2\n", encoding="utf-8")
    assert verify_incremental_code_health.main(["--mode", "fast", "--output", str(output)]) == 0
    second = json.loads(output.read_text(encoding="utf-8"))
    assert second["changedPaths"] == first["changedPaths"]
    assert second["evidenceFingerprint"]["digest"] != first["evidenceFingerprint"]["digest"]

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert (
        "verify_incremental_code_health.py --base HEAD --head HEAD --working-tree --mode full"
        in makefile
    )


def test_fingerprint_changes_for_range_policy_and_candidate_bytes(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    target = write(repo, "quwoquan_ops/ci/value.py", "VALUE = 1\n")
    head_one = commit(repo, "one")
    one = analyze_delta(repo, base=base, head=head_one, policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="fast")
    target.write_text("VALUE = 2\n", encoding="utf-8")
    head_two = commit(repo, "two")
    two = analyze_delta(repo, base=head_one, head=head_two, policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="fast")
    assert one["evidenceFingerprint"]["digest"] != two["evidenceFingerprint"]["digest"]

    policy_path = repo / "quwoquan_ops/policies/code_health_policy.yaml"
    policy_path.write_text(policy_path.read_text().replace("advisory: 800", "advisory: 799"), encoding="utf-8")
    changed_policy = analyze_delta(repo, base=head_one, head=head_two, policy_path=policy_path, mode="fast")
    assert two["evidenceFingerprint"]["digest"] != changed_policy["evidenceFingerprint"]["digest"]


def test_report_shape_is_digest_bound_and_ai_has_no_control_authority(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    write(repo, "quwoquan_ops/ci/value.py", "VALUE = 1\n")
    head = commit(repo)
    report = analyze_delta(repo, base=base, head=head, policy_path=repo / "quwoquan_ops/policies/code_health_policy.yaml", mode="fast")
    assert report["schema"] == REPORT_SCHEMA
    assert report["changedPathsDigest"].startswith("sha256:")
    assert report["policyDigest"].startswith("sha256:")
    assert report["implementationDigest"].startswith("sha256:")
    assert report["implementationDigest"] == report["evidenceFingerprint"]["digest_payload"]["execution"]["generator_digest"]
    assert report["evidenceFingerprint"]["ref"].startswith("evidence-fingerprint-v1:")
    assert report["rollout"]["automaticPromotion"] is False
    assert set(report["categorySummary"]) == {
        "handwritten-production", "test", "generated", "vendor",
        "contract-metadata", "config-data", "docs",
    }
    assert not {"promotionDecision", "gateStatus"} & set(json.loads(json.dumps(report)))
