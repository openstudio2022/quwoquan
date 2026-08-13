"""Byte-exact historical quarantine protection contracts."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
REPO_ROOT = DATA_ROOT.parent
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from quwoquan_ops.gate import verify_output_layout as repo_output_gate  # noqa: E402

from governance import output_layout_migration  # noqa: E402
from governance import protected_quarantine_evidence as evidence  # noqa: E402
from verify import verify_output_root_isolation as output_gate  # noqa: E402


def _applied_migration(data_output_root: Path) -> Path:
    plan, plan_path = output_layout_migration.plan_output_layout_migration(
        data_output_root=data_output_root
    )
    _, apply_path = output_layout_migration.apply_output_layout_migration(
        plan_path=plan_path,
        plan_digest=str(plan["planDigest"]),
    )
    return apply_path


def _quarantine(
    data_output_root: Path,
    *,
    name: str = "pilot-004-history",
    migrated: bool = False,
) -> Path:
    prefix = "local/workspace/quarantine" if migrated else "quarantine"
    root = data_output_root / prefix / name
    policies = root / "package/services/content/resources/common/policies"
    policies.mkdir(parents=True)
    (policies / "admission.yaml").write_bytes(b"mode: historical\n")
    config = root / "package/services/content/config"
    config.mkdir(parents=True)
    (config / "config.yaml").write_bytes(b"runtime: historical\n")
    version = root / "package/legal/2026-07"
    version.mkdir(parents=True)
    (version / "terms.txt").write_bytes(b"frozen evidence\n")
    os.symlink("2026-07", version.parent / "current")
    return root


def _migrated_quarantine(data_output_root: Path) -> tuple[Path, Path]:
    legacy = _quarantine(data_output_root)
    apply_path = _applied_migration(data_output_root)
    return (
        data_output_root / "local/workspace/quarantine" / legacy.name,
        apply_path,
    )


def test_receipt_binds_every_file_directory_and_internal_symlink(tmp_path: Path) -> None:
    output = tmp_path / "data"
    quarantine, apply_path = _migrated_quarantine(output)

    payload, receipt_path = evidence.protect_historical_quarantine(
        quarantine_root=quarantine,
        migration_apply_receipt=apply_path,
        data_output_root=output,
        reason="preserve revoked release evidence",
    )
    replay, replay_path = evidence.protect_historical_quarantine(
        quarantine_root=quarantine,
        migration_apply_receipt=apply_path,
        data_output_root=output,
        reason="preserve revoked release evidence",
    )

    assert replay_path == receipt_path
    assert replay == payload
    assert payload["status"] == "protected_read_only"
    assert payload["reusableSourceTruthAllowed"] is False
    assert payload["migrationSourceRef"] == "quarantine"
    assert payload["migrationDestinationRef"] == "local/workspace/quarantine"
    assert payload["migrationEntryFileCount"] == 3
    assert payload["fileCount"] == 3
    assert payload["symlinkCount"] == 1
    assert payload["files"] == sorted(payload["files"], key=lambda item: item["path"])
    assert all(str(item["sha256"]).startswith("sha256:") for item in payload["files"])
    assert receipt_path == (
        output
        / "local/cache/protected-quarantines"
        / str(payload["manifestDigest"]).removeprefix("sha256:")
        / "receipt.json"
    )
    validated, validated_root = evidence.validate_protected_quarantine_receipt(
        receipt_path,
        data_output_root=output,
    )
    assert validated == payload
    assert validated_root == quarantine.resolve()
    assert output_gate._output_source_truth_issues(output) == []
    assert repo_output_gate.output_layout_issues(output.parent) == []


def test_same_size_tree_mutation_cannot_be_reprotected(tmp_path: Path) -> None:
    output = tmp_path / "data"
    quarantine, apply_path = _migrated_quarantine(output)
    _, receipt_path = evidence.protect_historical_quarantine(
        quarantine_root=quarantine,
        migration_apply_receipt=apply_path,
        data_output_root=output,
    )
    policy = quarantine / "package/services/content/resources/common/policies/admission.yaml"
    original = policy.read_bytes()
    policy.write_bytes(b"x" * len(original))

    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="tree drift",
    ):
        evidence.validate_protected_quarantine_receipt(
            receipt_path,
            data_output_root=output,
        )
    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="existing protected quarantine receipt is invalid",
    ):
        evidence.protect_historical_quarantine(
            quarantine_root=quarantine,
            migration_apply_receipt=apply_path,
            data_output_root=output,
        )
    issues = output_gate._output_source_truth_issues(output)
    assert any("invalid protected quarantine evidence" in issue for issue in issues)
    assert any("reusable source truth is forbidden" in issue for issue in issues)
    repo_issues = repo_output_gate.output_layout_issues(output.parent)
    assert any("invalid protected quarantine evidence" in issue for issue in repo_issues)
    assert any("reusable source truth is forbidden" in issue for issue in repo_issues)
    # config.yaml 命中文件名启发式但内容无 secret:按内容真判据放行,
    # 不再作为 deployment configuration 误报(见 _contains_secret_material)。
    assert not any(
        "deployment configuration, TLS or secret material" in issue
        for issue in repo_issues
    )


def test_reason_change_cannot_issue_second_receipt_for_same_tree(tmp_path: Path) -> None:
    output = tmp_path / "data"
    quarantine, apply_path = _migrated_quarantine(output)
    evidence.protect_historical_quarantine(
        quarantine_root=quarantine,
        migration_apply_receipt=apply_path,
        data_output_root=output,
        reason="first frozen reason",
    )

    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="already protected",
    ):
        evidence.protect_historical_quarantine(
            quarantine_root=quarantine,
            migration_apply_receipt=apply_path,
            data_output_root=output,
            reason="replacement reason",
        )


def test_external_or_broken_symlink_is_not_protectable(tmp_path: Path) -> None:
    output = tmp_path / "data"
    quarantine, apply_path = _migrated_quarantine(output)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    os.symlink(outside, quarantine / "escaped")

    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="broken or escapes",
    ):
        evidence.protect_historical_quarantine(
            quarantine_root=quarantine,
            migration_apply_receipt=apply_path,
            data_output_root=output,
        )


def test_quarantine_root_symlink_cannot_claim_another_tree(tmp_path: Path) -> None:
    output = tmp_path / "data"
    quarantine, apply_path = _migrated_quarantine(output)
    alias = quarantine.parent / "pilot-004-alias"
    os.symlink(quarantine.name, alias)

    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="root must not be a symlink",
    ):
        evidence.protect_historical_quarantine(
            quarantine_root=alias,
            migration_apply_receipt=apply_path,
            data_output_root=output,
        )


def test_unrelated_migration_receipt_cannot_attest_a_quarantine(tmp_path: Path) -> None:
    output = tmp_path / "data"
    legacy = output / "local/article-source-frontier"
    legacy.mkdir(parents=True)
    (legacy / "evidence.json").write_text("{}\n", encoding="utf-8")
    apply_path = _applied_migration(output)
    quarantine = _quarantine(output, migrated=True)

    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="does not bind quarantine",
    ):
        evidence.protect_historical_quarantine(
            quarantine_root=quarantine,
            migration_apply_receipt=apply_path,
            data_output_root=output,
        )


def test_tampered_receipt_fails_closed_and_does_not_exempt_policies(tmp_path: Path) -> None:
    output = tmp_path / "data"
    quarantine, apply_path = _migrated_quarantine(output)
    _, receipt_path = evidence.protect_historical_quarantine(
        quarantine_root=quarantine,
        migration_apply_receipt=apply_path,
        data_output_root=output,
    )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["fileCount"] += 1
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")

    protected, receipt_issues = evidence.load_protected_quarantine_receipts(
        data_output_root=output
    )
    assert protected == {}
    assert any("tree drift" in issue for issue in receipt_issues)
    issues = output_gate._output_source_truth_issues(output)
    assert any("invalid protected quarantine evidence" in issue for issue in issues)
    assert any("reusable source truth is forbidden" in issue for issue in issues)
