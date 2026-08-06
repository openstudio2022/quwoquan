from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.output_layout_migration import (
    OutputLayoutMigrationError,
    apply_output_layout_migration,
    plan_output_layout_migration,
)


def _legacy_output(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    (root / "local/source-acquisition/cas").mkdir(parents=True)
    (root / "local/source-acquisition/cas/asset.bin").write_bytes(b"asset")
    (root / "quarantine/incident").mkdir(parents=True)
    (root / "quarantine/incident/evidence.json").write_text(
        '{"protected":true}\n',
        encoding="utf-8",
    )
    return root


def test_output_layout_migration_is_digest_bound_byte_preserving_and_idempotent(
    tmp_path: Path,
) -> None:
    root = _legacy_output(tmp_path)

    plan, plan_path = plan_output_layout_migration(data_output_root=root)
    assert plan["status"] == "planned"
    assert plan["totalFileCount"] == 2

    receipt, receipt_path = apply_output_layout_migration(
        plan_path=plan_path,
        plan_digest=str(plan["planDigest"]),
    )
    assert receipt["status"] == "applied"
    assert receipt_path.is_file()
    assert not (root / "local/source-acquisition").exists()
    assert not (root / "quarantine").exists()
    assert (root / "local/workspace/source-acquisition/cas/asset.bin").read_bytes() == b"asset"
    assert json.loads(
        (root / "local/workspace/quarantine/incident/evidence.json").read_text(
            encoding="utf-8"
        )
    ) == {"protected": True}

    replay, replay_path = apply_output_layout_migration(
        plan_path=plan_path,
        plan_digest=str(plan["planDigest"]),
    )
    assert replay_path == receipt_path
    assert replay == receipt


def test_output_layout_migration_rejects_plan_digest_substitution(tmp_path: Path) -> None:
    root = _legacy_output(tmp_path)
    plan, plan_path = plan_output_layout_migration(data_output_root=root)

    with pytest.raises(OutputLayoutMigrationError, match="digest binding mismatch"):
        apply_output_layout_migration(
            plan_path=plan_path,
            plan_digest="sha256:" + "0" * 64,
        )

    assert (root / "local/source-acquisition/cas/asset.bin").is_file()
    assert plan["status"] == "planned"


def test_output_layout_migration_replay_rechecks_exact_destination_bytes(
    tmp_path: Path,
) -> None:
    root = _legacy_output(tmp_path)
    plan, plan_path = plan_output_layout_migration(data_output_root=root)
    apply_output_layout_migration(
        plan_path=plan_path,
        plan_digest=str(plan["planDigest"]),
    )
    migrated = root / "local/workspace/source-acquisition/cas/asset.bin"
    migrated.write_bytes(b"other")

    with pytest.raises(OutputLayoutMigrationError, match="byte identity drift"):
        apply_output_layout_migration(
            plan_path=plan_path,
            plan_digest=str(plan["planDigest"]),
        )
