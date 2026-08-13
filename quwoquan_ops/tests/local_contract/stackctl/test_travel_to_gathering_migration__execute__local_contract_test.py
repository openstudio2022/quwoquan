"""M6 travel-service -> Gathering target-only 迁移控制面契约（CLI 与 execute 阶段）。

由 1000 行硬顶拆分自根目录
test_travel_to_gathering_migration__local_contract_test.py；测试逐字搬移，
共享构造 helper 见 quwoquan_ops/tests/support/travel_to_gathering_migration_test_support.py。

spec_ref: specs/feature-tree/travel-journey/spec.md#dom-001
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.migrations.travel_to_gathering import control_plane
from quwoquan_ops.tests.support.travel_to_gathering_migration_test_support import (
    DIGEST_A,
    DIGEST_B,
    _reseal,
    _source_snapshot,
    _target_contract,
    _write_snapshot,
)


def test_migration_help_renders_parity_requirements(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        stackctl.build_parser().parse_args(
            ["migration", "travel-to-gathering", "--help"]
        )

    assert exit_info.value.code == 0
    assert "100% parity migration receipt" in capsys.readouterr().out


def test_prod_dry_run_is_gate_block_and_writes_output_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    source_path = tmp_path / "source.json"
    snapshot = _source_snapshot()
    snapshot["environment"] = "prod"
    _reseal(snapshot)
    _write_snapshot(source_path, snapshot)
    source_before = source_path.read_bytes()
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    args = argparse.Namespace(
        env="prod",
        phase="dry-run",
        source_snapshot=str(source_path),
        target_snapshot="",
        report_dir=str(output / "prod-dry-run"),
    )

    result = control_plane.execute(args)

    assert result["exitCode"] == 2
    report = json.loads(
        (output / "prod-dry-run/report.json").read_text(encoding="utf-8")
    )
    assert report["errorCode"] == "PROD_PHASE_FORBIDDEN"
    assert report["writeSet"] == []
    assert source_path.read_bytes() == source_before
    assert {path.name for path in (output / "prod-dry-run").iterdir()} == {
        "report.json"
    }


def test_alpha_dry_run_validates_in_memory_and_emits_receipt_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    source_path = tmp_path / "source.json"
    snapshot = _source_snapshot()
    _write_snapshot(source_path, snapshot)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = argparse.Namespace(
        env="alpha",
        phase="dry-run",
        source_snapshot=str(source_path),
        target_snapshot="",
        report_dir=str(output / "alpha-dry-run"),
    )

    result = control_plane.execute(args)
    receipt = json.loads(
        (output / "alpha-dry-run/receipt.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 0
    assert receipt["status"] == "passed"
    assert receipt["executionMode"] == "zero_write"
    assert receipt["writeSet"] == []
    assert receipt["mapping"]["targetDocumentCount"] > 0
    assert receipt["mapping"]["targetDocumentsEmitted"] is False
    assert {path.name for path in (output / "alpha-dry-run").iterdir()} == {
        "receipt.json",
        "report.json",
    }


def test_receipt_path_outside_qwq_output_is_rejected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    forbidden = tmp_path / "forbidden"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    args = argparse.Namespace(
        env="alpha",
        phase="inventory",
        source_snapshot="",
        target_snapshot="",
        report_dir=str(forbidden),
    )

    result = control_plane.execute(args)

    assert result["exitCode"] == 2
    assert result["details"][0].startswith("OUTPUT_PATH_FORBIDDEN:")
    assert not forbidden.exists()


def test_digest_mismatch_fails_before_mapping(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    source_path = tmp_path / "source.json"
    snapshot = _source_snapshot()
    snapshot["targetContractDigest"] = DIGEST_B
    _reseal(snapshot)
    _write_snapshot(source_path, snapshot)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = argparse.Namespace(
        env="alpha",
        phase="inventory",
        source_snapshot=str(source_path),
        target_snapshot="",
        report_dir=str(output / "digest"),
    )

    result = control_plane.execute(args)

    assert result["exitCode"] == 2
    report = json.loads((output / "digest/report.json").read_text(encoding="utf-8"))
    assert report["errorCode"] == "TARGET_CONTRACT_DIGEST_MISMATCH"


def test_missing_canonical_generated_contract_digest_fails_fast(
    tmp_path: Path,
) -> None:
    with pytest.raises(control_plane.MigrationControlError) as raised:
        control_plane.resolve_target_contract(tmp_path)

    assert raised.value.code == "TARGET_CONTRACT_DIGEST_MISSING"


def test_stackctl_parser_exposes_cutover_and_rollback_contract() -> None:
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "gamma",
            "--phase",
            "rollback",
            "--cutover-receipt",
            "cutover.json",
            "--approval-receipt",
            "approval.json",
            "--target-restore-receipt",
            "restore.json",
            "--post-restore-parity-receipt",
            "parity.json",
            "--rollback-mode",
            "target_snapshot",
            "--rollback-candidate-digest",
            DIGEST_A,
        ]
    )

    assert args.migration_command == "travel-to-gathering"
    assert args.phase == "rollback"
    assert args.rollback_mode == "target_snapshot"
    assert args.cutover_receipt == "cutover.json"
    assert args.target_restore_receipt == "restore.json"
