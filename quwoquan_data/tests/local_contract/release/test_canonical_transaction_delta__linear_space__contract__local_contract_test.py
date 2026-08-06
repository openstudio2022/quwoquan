from __future__ import annotations

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from content.release.canonical import object_transaction_audit as audit_module
from content.release.canonical.application import apply_object_transaction
from content.release.canonical.canonical_inventory import (
    apply_inventory_delta,
    canonical_inventory_path,
    load_or_bootstrap_inventory,
    write_inventory,
)
from content.release.canonical.object_transaction_audit import audit_object_transaction
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from core.tree_integrity import tree_integrity_stats
from support.object_transaction_fixtures import (
    TRANSACTION_ID,
    build_canonical,
    build_package,
)


def _bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def test_transaction_persists_only_delta_not_whole_canonical_tree(
    tmp_path: Path,
) -> None:
    canonical = build_canonical(tmp_path)
    large_existing_payload = "x" * (2 * 1024 * 1024)
    profile = canonical / "creators/creator_a/profile.json"
    profile.write_text(
        json.dumps({"creatorId": "creator_a", "padding": large_existing_payload}),
        encoding="utf-8",
    )
    package = build_package(tmp_path, canonical)
    output = tmp_path / ".qwq_output"
    before_bytes = _bytes(canonical)

    audit = audit_object_transaction(
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

    transaction_root = (
        output
        / "data/local/workspace/object-transactions"
        / TRANSACTION_ID
    )
    assert not (transaction_root / "staging/canonical").exists()
    assert not (transaction_root / "rollback/canonical_before").exists()
    assert applied["deltaBytes"] < before_bytes / 4
    assert _bytes(transaction_root) < before_bytes / 2
    assert applied["deltaFileCount"] > 0
    assert audit["candidateValidationMode"] == "incremental_inventory_delta"
    assert not any(transaction_root.glob("candidate-*"))
    inventory_stats = load_or_bootstrap_inventory(canonical)["stats"]
    full_scan_stats = tree_integrity_stats(canonical)
    assert inventory_stats["fileCount"] == full_scan_stats["fileCount"]
    assert inventory_stats["totalBytes"] == full_scan_stats["totalBytes"]


def test_object_hot_path_defers_full_closure_scan_until_release(
    monkeypatch,
    tmp_path: Path,
) -> None:
    canonical = build_canonical(tmp_path)
    package = build_package(tmp_path, canonical)
    output = tmp_path / ".qwq_output"

    def _unexpected_full_scan(_root: Path) -> dict:
        raise AssertionError("per-object transaction called full closure scan")

    monkeypatch.setattr(audit_module, "validate_publish_invariants", _unexpected_full_scan)
    audit = audit_object_transaction(
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


def test_cross_campaign_apply_uses_publish_root_fence_and_merkle_cas(
    tmp_path: Path,
) -> None:
    canonical = build_canonical(tmp_path)
    package_one = build_package(tmp_path, canonical)
    package_two = tmp_path / "package-two"
    import shutil

    shutil.copytree(package_one, package_two)
    package_document_path = package_two / "object_transaction_package.json"
    package_document = json.loads(package_document_path.read_text(encoding="utf-8"))
    package_document["transactionId"] = "object-two"
    package_document_path.write_text(
        json.dumps(package_document, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    before = load_or_bootstrap_inventory(canonical)["stats"]["merkleRoot"]
    output_one = tmp_path / "lane-homepage"
    output_two = tmp_path / "lane-video"
    audit_one = audit_object_transaction(
        publish_root=canonical,
        output_root=output_one,
        package_root=package_one,
        transaction_id=TRANSACTION_ID,
        expected_canonical_merkle=before,
    )
    audit_two = audit_object_transaction(
        publish_root=canonical,
        output_root=output_two,
        package_root=package_two,
        transaction_id="object-two",
        expected_canonical_merkle=before,
    )

    calls = (
        (output_one, package_one, TRANSACTION_ID, audit_one),
        (output_two, package_two, "object-two", audit_two),
    )

    def apply(call: tuple[Path, Path, str, dict]) -> str:
        output, package, transaction_id, audit = call
        try:
            result = apply_object_transaction(
                publish_root=canonical,
                output_root=output,
                package_root=package,
                transaction_id=transaction_id,
                dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
            )
            return str(result["status"])
        except ObjectTransactionError as exc:
            return f"blocked:{exc}"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply, calls))

    assert results.count("applied") == 1
    assert sum(result.startswith("blocked:") for result in results) == 1
    assert any("CAS drift" in result for result in results)


def test_inventory_hot_pointer_stays_constant_size_through_one_thousand_deltas(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical-index"
    canonical.mkdir()
    inventory = load_or_bootstrap_inventory(canonical)
    size_at_one_hundred = 0

    for index in range(1_000):
        payload = f"object-{index}".encode()
        inventory = apply_inventory_delta(
            inventory,
            [
                {
                    "destination": f"tags/load-test/{index}.json",
                    "operation": "create",
                    "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload),
                }
            ],
            publish_root=canonical,
        )
        assert "entries" not in inventory
        assert len(inventory["pendingMutations"]) == 1
        write_inventory(canonical, inventory)
        inventory = load_or_bootstrap_inventory(canonical)
        if index == 99:
            size_at_one_hundred = canonical_inventory_path(canonical).stat().st_size

    assert inventory["revision"] == 1_000
    assert inventory["stats"]["fileCount"] == 1_000
    assert len(json.dumps(inventory, sort_keys=True)) < 1_024
    database = canonical_inventory_path(canonical)
    assert database.stat().st_size < size_at_one_hundred * 15
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 1_000
