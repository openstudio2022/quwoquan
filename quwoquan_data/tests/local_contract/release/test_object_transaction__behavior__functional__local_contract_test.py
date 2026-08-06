from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from content.release.canonical import object_transaction_audit as transaction
from content.release.canonical.application import (
    apply_object_transaction,
    replay_object_transaction,
    rollback_object_transaction,
)
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.object_transaction import (
    _source_asset_for_manifest_asset,
    _source_assets_by_ref,
)
from core.tree_integrity import tree_integrity_stats
from support.object_transaction_fixtures import (
    OBJECT_REF,
    TRANSACTION_ID,
    build_canonical,
    build_package,
)


def _audit(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    canonical = build_canonical(tmp_path)
    output = tmp_path / ".qwq_output"
    package = build_package(tmp_path, canonical)
    report = transaction.audit_object_transaction(
        publish_root=canonical,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        expected_canonical_merkle=load_or_bootstrap_inventory(canonical)["stats"][
            "merkleRoot"
        ],
    )
    return canonical, output, package, report


def test_audit_binds_current_merkle_freeze_policy_closure_and_review(
    tmp_path: Path,
) -> None:
    canonical = build_canonical(tmp_path)
    package = build_package(tmp_path, canonical)
    before = tree_integrity_stats(canonical)["merkleRoot"]

    with pytest.raises(
        transaction.ObjectTransactionError,
        match="current canonical Merkle",
    ):
        transaction.audit_object_transaction(
            publish_root=canonical,
            output_root=tmp_path / ".qwq_output",
            package_root=package,
            transaction_id=TRANSACTION_ID,
            expected_canonical_merkle="sha256:" + "0" * 64,
        )

    assert tree_integrity_stats(canonical)["merkleRoot"] == before


def test_apply_is_atomic_create_once_idempotent_and_has_no_layout_parent(
    tmp_path: Path,
) -> None:
    canonical, output, package, audit = _audit(tmp_path)

    applied = apply_object_transaction(
        publish_root=canonical,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        dry_run_attestation_sha256=audit["dryRunAttestationSha256"],
    )

    assert applied["status"] == "applied"
    assert (canonical / "entities" / OBJECT_REF / "_entity.json").is_file()
    assert (canonical / "tags/Topic/旅行/_definition.json").is_file()
    assert Path(applied["rollbackRef"]).is_dir()
    assert "releaseRef" not in applied
    serialized = json.dumps(applied, ensure_ascii=False)
    assert "publish-layout" not in serialized

    rerun = apply_object_transaction(
        publish_root=canonical,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        dry_run_attestation_sha256=audit["dryRunAttestationSha256"],
    )
    assert rerun["idempotent"] is True


def test_first_transaction_initializes_missing_canonical_publish_root(
    tmp_path: Path,
) -> None:
    canonical = build_canonical(tmp_path)
    package = build_package(tmp_path, canonical)
    shutil.rmtree(canonical)
    output = tmp_path / ".qwq_output"

    audit = transaction.audit_object_transaction(
        publish_root=canonical,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        expected_canonical_merkle=load_or_bootstrap_inventory(canonical)["stats"][
            "merkleRoot"
        ],
    )
    applied = apply_object_transaction(
        publish_root=canonical,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
    )

    assert applied["status"] == "applied"
    assert (canonical / "entities" / OBJECT_REF / "_entity.json").is_file()


def test_rollback_restores_before_merkle_and_preserves_transaction_evidence(
    tmp_path: Path,
) -> None:
    canonical, output, package, audit = _audit(tmp_path)
    applied = apply_object_transaction(
        publish_root=canonical,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        dry_run_attestation_sha256=audit["dryRunAttestationSha256"],
    )

    rolled_back = rollback_object_transaction(
        publish_root=canonical,
        output_root=output,
        transaction_id=TRANSACTION_ID,
    )

    assert rolled_back["restoredMerkle"] == applied["beforeMerkle"]
    assert not (canonical / "entities" / OBJECT_REF).exists()
    assert Path(rolled_back["rollbackRefPreserved"]).is_dir()
    assert not (
        output
        / "data/local/workspace/object-transactions"
        / TRANSACTION_ID
        / "rollback/canonical_before"
    ).exists()

    replayed = replay_object_transaction(
        publish_root=canonical,
        output_root=output,
        transaction_id=TRANSACTION_ID,
    )

    assert replayed["restoredMerkle"] == applied["afterMerkle"]
    assert (canonical / "entities" / OBJECT_REF).is_dir()


def test_entity_transaction_resolves_duplicate_source_asset_ids_by_full_reference(
    tmp_path: Path,
) -> None:
    execution = tmp_path / "execution"
    first = execution / "sources" / "first" / "assets"
    second = execution / "sources" / "second" / "assets"
    for directory, url in (
        (first, "https://upload.wikimedia.org/first.jpg"),
        (second, "https://upload.wikimedia.org/second.jpg"),
    ):
        directory.mkdir(parents=True)
        (directory / "image.jpg").write_bytes(b"image")
        (directory / "index.json").write_text(
            json.dumps(
                {
                    "assets": [
                        {
                            "sourceAssetId": "001_001",
                            "fileName": "image.jpg",
                            "url": url,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    source_ref, source_asset = _source_asset_for_manifest_asset(
        {
            "sourceAssetId": "001_001",
            "sourceAssetRef": "sources/second/assets/image.jpg",
        },
        _source_assets_by_ref(execution),
    )

    assert source_ref == "sources/second/assets/image.jpg"
    assert source_asset["url"] == "https://upload.wikimedia.org/second.jpg"
