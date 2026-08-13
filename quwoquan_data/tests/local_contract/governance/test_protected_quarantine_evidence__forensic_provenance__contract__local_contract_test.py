# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-002
"""Forensic quarantine provenance: QUARANTINE.json is the registration credential.

受保护取证隔离以隔离区自身的 ``QUARANTINE.json``(要求
``recovery: retain_for_forensics_only``)为凭据登记,整棵树(含凭据文件本身)
被摘要冻结;任何漂移即 BLOCK,未登记的隔离区不得获得豁免。
"""
from __future__ import annotations

import json
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
from quwoquan_ops.gate import verify_root_layout as repo_root_gate  # noqa: E402

from governance import protected_quarantine_evidence as evidence  # noqa: E402
from verify import verify_output_root_isolation as output_gate  # noqa: E402

_MARKER = {
    "decision": "GATE_BLOCK/WAIT_CONTENT",
    "consumption": "forbidden",
    "recovery": "retain_for_forensics_only",
    "incident": "unauthorized scaled execution",
    "pids": [4167, 5219],
}


def _repo_layout(tmp_path: Path) -> tuple[Path, Path]:
    """构造只含 .qwq_output 的仿真仓库根,返回 (repo_root, data_output_root)。"""
    repo_root = tmp_path / "repo"
    data_output = repo_root / ".qwq_output" / "data"
    data_output.mkdir(parents=True)
    return repo_root, data_output


def _forensic_quarantine(
    data_output_root: Path,
    *,
    name: str = "unauthorized-scale-incident-20260808",
    marker: object = _MARKER,
) -> Path:
    root = data_output_root / "quarantine" / name
    specs_dir = root / "specs" / "feature-tree"
    specs_dir.mkdir(parents=True)
    (specs_dir / "spec.md").write_bytes(b"# frozen forensic source-truth copy\n")
    policies = root / "quwoquan_ops" / "policies"
    policies.mkdir(parents=True)
    (policies / "gates.yaml").write_bytes(b"mode: forensic-frozen\n")
    if marker is not None:
        (root / "QUARANTINE.json").write_text(
            json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return root


def test_registered_forensic_quarantine_passes_both_layout_gates(
    tmp_path: Path,
) -> None:
    repo_root, output = _repo_layout(tmp_path)
    quarantine = _forensic_quarantine(output)

    payload, receipt_path = evidence.protect_forensic_quarantine(
        quarantine_root=quarantine,
        data_output_root=output,
        reason="retain unauthorized execution forensics",
    )
    replay, replay_path = evidence.protect_forensic_quarantine(
        quarantine_root=quarantine,
        data_output_root=output,
        reason="retain unauthorized execution forensics",
    )

    assert replay_path == receipt_path
    assert replay == payload
    assert payload["provenance"] == "forensic"
    assert payload["status"] == "protected_read_only"
    assert payload["reusableSourceTruthAllowed"] is False
    assert payload["quarantineRef"] == f"quarantine/{quarantine.name}"
    assert payload["forensicMarkerPath"] == "QUARANTINE.json"
    assert str(payload["forensicMarkerSha256"]).startswith("sha256:")
    assert payload["forensicDecision"] == "GATE_BLOCK/WAIT_CONTENT"
    assert payload["forensicConsumption"] == "forbidden"
    assert payload["forensicRecovery"] == "retain_for_forensics_only"
    # 凭据文件本身也在冻结树内:摘要口径覆盖 QUARANTINE.json。
    assert payload["fileCount"] == 3
    frozen_paths = {item["path"] for item in payload["files"]}
    assert "QUARANTINE.json" in frozen_paths
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

    assert repo_output_gate.output_layout_issues(output.parent) == []
    assert repo_root_gate.root_layout_issues(repo_root) == []
    assert output_gate._output_layout_issues(root=output) == []
    assert output_gate._output_source_truth_issues(output) == []


def test_forensic_tree_drift_blocks_with_explicit_error(tmp_path: Path) -> None:
    repo_root, output = _repo_layout(tmp_path)
    quarantine = _forensic_quarantine(output)
    _, receipt_path = evidence.protect_forensic_quarantine(
        quarantine_root=quarantine,
        data_output_root=output,
    )
    frozen = quarantine / "specs" / "feature-tree" / "spec.md"
    original = frozen.read_bytes()
    frozen.write_bytes(b"x" * len(original))

    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="tree drift",
    ):
        evidence.validate_protected_quarantine_receipt(
            receipt_path,
            data_output_root=output,
        )
    protected, receipt_issues = evidence.load_protected_quarantine_receipts(
        data_output_root=output
    )
    assert protected == {}
    assert any("tree drift" in issue for issue in receipt_issues)
    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="existing protected quarantine receipt is invalid",
    ):
        evidence.protect_forensic_quarantine(
            quarantine_root=quarantine,
            data_output_root=output,
        )

    repo_issues = repo_output_gate.output_layout_issues(output.parent)
    assert any("invalid protected quarantine evidence" in issue for issue in repo_issues)
    assert any("unregistered quarantine is forbidden" in issue for issue in repo_issues)
    assert any("reusable source truth is forbidden" in issue for issue in repo_issues)
    assert repo_root_gate.root_layout_issues(repo_root) != []
    data_issues = output_gate._output_layout_issues(root=output)
    assert any("unregistered quarantine is forbidden" in issue for issue in data_issues)


def test_tampering_with_the_credential_marker_is_drift(tmp_path: Path) -> None:
    _, output = _repo_layout(tmp_path)
    quarantine = _forensic_quarantine(output)
    _, receipt_path = evidence.protect_forensic_quarantine(
        quarantine_root=quarantine,
        data_output_root=output,
    )
    marker_path = quarantine / "QUARANTINE.json"
    tampered = dict(_MARKER)
    tampered["incident"] = "REWRITTEN NARRATIVE OF EXECUTION"
    marker_path.write_text(
        json.dumps(tampered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="drift",
    ):
        evidence.validate_protected_quarantine_receipt(
            receipt_path,
            data_output_root=output,
        )
    protected, receipt_issues = evidence.load_protected_quarantine_receipts(
        data_output_root=output
    )
    assert protected == {}
    assert any("drift" in issue for issue in receipt_issues)


def test_unregistered_forensic_quarantine_stays_blocked(tmp_path: Path) -> None:
    repo_root, output = _repo_layout(tmp_path)
    _forensic_quarantine(output)

    repo_issues = repo_output_gate.output_layout_issues(output.parent)
    assert any("unregistered quarantine is forbidden" in issue for issue in repo_issues)
    assert any("reusable source truth is forbidden" in issue for issue in repo_issues)
    root_issues = repo_root_gate.root_layout_issues(repo_root)
    assert any("unregistered quarantine is forbidden" in issue for issue in root_issues)
    data_issues = output_gate._output_layout_issues(root=output)
    assert any("unregistered quarantine is forbidden" in issue for issue in data_issues)


def test_empty_quarantine_container_is_not_an_issue(tmp_path: Path) -> None:
    repo_root, output = _repo_layout(tmp_path)
    (output / "quarantine").mkdir()

    assert repo_output_gate.output_layout_issues(output.parent) == []
    assert repo_root_gate.root_layout_issues(repo_root) == []
    assert output_gate._output_layout_issues(root=output) == []


def test_marker_without_forensic_recovery_cannot_be_registered(tmp_path: Path) -> None:
    _, output = _repo_layout(tmp_path)
    missing_recovery = {key: value for key, value in _MARKER.items() if key != "recovery"}
    quarantine = _forensic_quarantine(output, marker=missing_recovery)

    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="retain_for_forensics_only",
    ):
        evidence.protect_forensic_quarantine(
            quarantine_root=quarantine,
            data_output_root=output,
        )
    wrong_recovery = dict(_MARKER)
    wrong_recovery["recovery"] = "restore_when_convenient"
    (quarantine / "QUARANTINE.json").write_text(
        json.dumps(wrong_recovery, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="retain_for_forensics_only",
    ):
        evidence.protect_forensic_quarantine(
            quarantine_root=quarantine,
            data_output_root=output,
        )
    assert not (output / "local/cache/protected-quarantines").exists()
    repo_issues = repo_output_gate.output_layout_issues(output.parent)
    assert any("unregistered quarantine is forbidden" in issue for issue in repo_issues)


def test_marker_must_exist_and_declare_forbidden_consumption(tmp_path: Path) -> None:
    _, output = _repo_layout(tmp_path)
    no_marker = _forensic_quarantine(output, name="incident-without-marker", marker=None)
    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="forensic marker is missing",
    ):
        evidence.protect_forensic_quarantine(
            quarantine_root=no_marker,
            data_output_root=output,
        )

    permissive = dict(_MARKER)
    permissive["consumption"] = "allowed"
    consuming = _forensic_quarantine(
        output, name="incident-with-consumable-marker", marker=permissive
    )
    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="consumption",
    ):
        evidence.protect_forensic_quarantine(
            quarantine_root=consuming,
            data_output_root=output,
        )


def test_migration_path_cannot_masquerade_as_forensic(tmp_path: Path) -> None:
    """forensic 登记只认 quarantine/<child>;其他路径即使有 marker 也不可登记。"""
    _, output = _repo_layout(tmp_path)
    stray = output / "local" / "workspace" / "quarantine" / "stray-forensic"
    stray.mkdir(parents=True)
    (stray / "QUARANTINE.json").write_text(
        json.dumps(_MARKER, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with pytest.raises(
        evidence.ProtectedQuarantineEvidenceError,
        match="one direct child of quarantine",
    ):
        evidence.protect_forensic_quarantine(
            quarantine_root=stray,
            data_output_root=output,
        )
