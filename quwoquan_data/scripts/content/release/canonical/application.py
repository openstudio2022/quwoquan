"""Apply, pointer rollback, and replay for audited canonical deltas."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.canonical_inventory import (
    apply_inventory_delta,
    canonical_inventory_path,
    load_or_bootstrap_inventory,
    validate_delta_materialization,
    write_inventory,
)
from content.release.canonical.object_transaction_contract import (
    APPLY_SCHEMA,
    LAYOUT_SCHEMA,
    ROLLBACK_SCHEMA,
    ObjectTransactionError,
    _digest_bytes,
    _json_bytes,
    _now,
    _read_json,
    _safe_id,
    _verify_package,
    _write_json,
)
from content.release.canonical.object_transaction_delta import (
    apply_forward_delta,
    apply_inverse_delta,
    load_transaction_delta,
    revert_applied_delta,
)
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)

POINTER_SCHEMA = "quwoquan_data.canonical_transaction_pointer"
REPLAY_SCHEMA = "quwoquan_data.object_transaction_replay"


def _pointer_document(
    *,
    report: Mapping[str, Any],
    state: str,
    active_merkle: str,
    active_inventory_digest: str,
    revision: int,
) -> dict[str, Any]:
    return {
        "schema": POINTER_SCHEMA,
        "transactionId": report["transactionId"],
        "executionId": report["executionId"],
        "state": state,
        "revision": revision,
        "activeMerkle": active_merkle,
        "activeInventoryDigest": active_inventory_digest,
        "beforeMerkle": report["beforeCanonical"]["merkleRoot"],
        "afterMerkle": report["afterCanonical"]["merkleRoot"],
        "fenceToken": report["fenceToken"],
        "deltaManifestDigest": report["deltaManifestDigest"],
        "updatedAt": _now(),
    }


def _verify_fence(report: Mapping[str, Any], delta: Mapping[str, Any]) -> None:
    expected = _digest_bytes(
        _json_bytes(
            {
                "transactionId": report["transactionId"],
                "beforeMerkle": report["beforeCanonical"]["merkleRoot"],
                "afterMerkle": report["afterCanonical"]["merkleRoot"],
                "deltaDigest": delta["deltaDigest"],
            }
        )
    )
    if report.get("fenceToken") != expected:
        raise ObjectTransactionError("canonical publish fence token mismatch")


def _recover_interrupted_forward(
    *,
    publish_root: Path,
    run_root: Path,
    delta: Mapping[str, Any],
) -> None:
    """Return an interrupted journal to its exact before pointer.

    Every entry is either still at its before state or already materialized with
    the frozen after digest.  Any third value is external drift and fails closed.
    """

    applied: list[dict[str, Any]] = []
    from content.release.canonical.object_transaction_contract import _digest_file

    for raw in delta.get("entries") or []:
        entry = dict(raw)
        destination = publish_root / str(entry["destination"])
        if entry["operation"] == "create":
            if not destination.exists():
                continue
            if not destination.is_file() or _digest_file(destination) != entry["sha256"]:
                raise ObjectTransactionError(
                    f"interrupted transaction destination drift: {entry['destination']}"
                )
            applied.append(entry)
            continue
        if not destination.is_file():
            raise ObjectTransactionError(
                f"interrupted transaction replacement is missing: {entry['destination']}"
            )
        digest = _digest_file(destination)
        if digest == entry["sha256"]:
            applied.append(entry)
        elif digest != entry["beforeSha256"]:
            raise ObjectTransactionError(
                f"interrupted transaction replacement drift: {entry['destination']}"
            )
    if applied:
        revert_applied_delta(
            publish_root=publish_root,
            run_root=run_root,
            entries=applied,
        )
    validate_delta_materialization(
        publish_root=publish_root,
        entries=list(delta.get("entries") or []),
        reverse=True,
    )


@canonical_publish_serialized
def apply_object_transaction(
    *,
    publish_root: Path,
    output_root: Path,
    package_root: Path,
    transaction_id: str,
    dry_run_attestation_sha256: str,
) -> dict[str, Any]:
    """CAS-apply one audited linear delta under the global publish fence."""
    from content.release.canonical.object_transaction_audit import (
        _transaction_root,
        _verify_attestation,
    )

    transaction_id = _safe_id(transaction_id, label="transactionId")
    run_root = _transaction_root(output_root, transaction_id)
    report_path = run_root / "audit_report.json"
    apply_path = run_root / "apply_report.json"
    if apply_path.is_file():
        applied = _read_json(apply_path)
        delta = load_transaction_delta(
            run_root=run_root,
            expected_digest=str(applied.get("deltaManifestDigest") or ""),
        )
        inventory = load_or_bootstrap_inventory(publish_root)
        if applied.get("schema") == APPLY_SCHEMA and (
            inventory["stats"]["merkleRoot"] == applied.get("afterMerkle")
        ):
            validate_delta_materialization(
                publish_root=publish_root,
                entries=list(delta["entries"]),
            )
            return {**applied, "idempotent": True}
        raise ObjectTransactionError(
            "transaction is not at its applied pointer; use canonical replay"
        )
    if not report_path.is_file():
        raise ObjectTransactionError("apply requires an audited transaction")
    report = _read_json(report_path)
    _verify_attestation(report, dry_run_attestation_sha256)
    if (
        report.get("transactionId") != transaction_id
        or report.get("targetLayout") != LAYOUT_SCHEMA
    ):
        raise ObjectTransactionError("audit transaction/layout binding mismatch")
    delta = load_transaction_delta(
        run_root=run_root,
        expected_digest=str(report.get("deltaManifestDigest") or ""),
    )
    _verify_fence(report, delta)
    before_merkle = str(report["beforeCanonical"]["merkleRoot"])
    intent_path = run_root / "apply_intent.json"
    inventory_path = canonical_inventory_path(publish_root)
    if intent_path.is_file() and not inventory_path.is_file():
        _recover_interrupted_forward(
            publish_root=publish_root,
            run_root=run_root,
            delta=delta,
        )
    current_inventory = load_or_bootstrap_inventory(publish_root)
    if intent_path.is_file():
        current_digest = current_inventory["inventoryDigest"]
        if current_digest == delta["afterInventoryDigest"]:
            _recover_interrupted_forward(
                publish_root=publish_root,
                run_root=run_root,
                delta=delta,
            )
            current_inventory = apply_inventory_delta(
                current_inventory,
                list(delta["entries"]),
                publish_root=publish_root,
                reverse=True,
            )
            write_inventory(publish_root, current_inventory)
        elif current_digest == delta["beforeInventoryDigest"]:
            _recover_interrupted_forward(
                publish_root=publish_root,
                run_root=run_root,
                delta=delta,
            )
        else:
            raise ObjectTransactionError(
                "interrupted transaction canonical inventory drift"
            )
    if (
        current_inventory["inventoryDigest"] != delta["beforeInventoryDigest"]
        or current_inventory["stats"]["merkleRoot"] != before_merkle
    ):
        raise ObjectTransactionError("audit after canonical publish CAS drift")
    package = _verify_package(
        package_root,
        canonical_root=publish_root,
        require_target_absent=True,
    )
    if any(
        package[key] != report.get(key)
        for key in ("packageSha256", "objectClosureDigest", "executionId")
    ):
        raise ObjectTransactionError("object package drift after audit")
    intent = {
        "schema": "quwoquan_data.object_transaction_apply_intent",
        "transactionId": transaction_id,
        "fenceToken": report["fenceToken"],
        "beforeMerkle": before_merkle,
        "afterMerkle": report["afterCanonical"]["merkleRoot"],
        "deltaManifestDigest": delta["deltaDigest"],
        "preparedAt": _now(),
    }
    if intent_path.is_file():
        persisted_intent = _read_json(intent_path)
        if any(
            persisted_intent.get(key) != intent[key]
            for key in (
                "transactionId",
                "fenceToken",
                "beforeMerkle",
                "afterMerkle",
                "deltaManifestDigest",
            )
        ):
            raise ObjectTransactionError("apply intent drift")
    else:
        _write_json(intent_path, intent)

    applied_entries = apply_forward_delta(
        publish_root=publish_root,
        run_root=run_root,
        manifest=delta,
    )
    try:
        after_inventory = apply_inventory_delta(
            current_inventory,
            list(delta["entries"]),
            publish_root=publish_root,
        )
        if (
            after_inventory["inventoryDigest"] != delta["afterInventoryDigest"]
            or after_inventory["stats"]["merkleRoot"]
            != report["afterCanonical"]["merkleRoot"]
        ):
            raise ObjectTransactionError("post-apply incremental canonical proof failed")
        validate_delta_materialization(
            publish_root=publish_root,
            entries=list(delta["entries"]),
        )
        write_inventory(publish_root, after_inventory)
    except BaseException:
        revert_applied_delta(
            publish_root=publish_root,
            run_root=run_root,
            entries=applied_entries,
        )
        raise

    pointer_path = run_root / "pointer.json"
    _write_json(
        pointer_path,
        _pointer_document(
            report=report,
            state="applied",
            active_merkle=str(after_inventory["stats"]["merkleRoot"]),
            active_inventory_digest=str(after_inventory["inventoryDigest"]),
            revision=1,
        ),
    )
    applied = {
        "schema": APPLY_SCHEMA,
        "transactionId": transaction_id,
        "executionId": report["executionId"],
        "status": "applied",
        "appliedAt": _now(),
        "beforeMerkle": before_merkle,
        "afterMerkle": report["afterCanonical"]["merkleRoot"],
        "beforeInventoryDigest": delta["beforeInventoryDigest"],
        "afterInventoryDigest": delta["afterInventoryDigest"],
        "objectKind": report["objectKind"],
        "objectRef": report["objectRef"],
        "objectClosureDigest": report["objectClosureDigest"],
        "dryRunAttestationSha256": dry_run_attestation_sha256,
        "fenceToken": report["fenceToken"],
        "deltaManifestDigest": delta["deltaDigest"],
        "deltaFileCount": len(delta["entries"]),
        "deltaBytes": delta["deltaBytes"],
        "rollbackRef": str(run_root / "delta"),
        "pointerRef": str(pointer_path),
        "idempotent": False,
    }
    _write_json(apply_path, applied)
    _write_json(
        run_root / "apply_completion.json",
        {
            "schema": "quwoquan_data.object_transaction_apply_completion",
            "transactionId": transaction_id,
            "fenceToken": report["fenceToken"],
            "afterMerkle": applied["afterMerkle"],
            "completedAt": applied["appliedAt"],
        },
    )
    return applied


@canonical_publish_serialized
def rollback_object_transaction(
    *,
    publish_root: Path,
    output_root: Path,
    transaction_id: str,
) -> dict[str, Any]:
    """Move the canonical pointer to the exact before revision via inverse delta."""
    from content.release.canonical.object_transaction_audit import _transaction_root

    transaction_id = _safe_id(transaction_id, label="transactionId")
    run_root = _transaction_root(output_root, transaction_id)
    audit_report = _read_json(run_root / "audit_report.json")
    apply_report = _read_json(run_root / "apply_report.json")
    if apply_report.get("schema") != APPLY_SCHEMA:
        raise ObjectTransactionError("apply report schema mismatch")
    delta = load_transaction_delta(
        run_root=run_root,
        expected_digest=str(apply_report.get("deltaManifestDigest") or ""),
    )
    _verify_fence(audit_report, delta)
    report_path = run_root / "rollback_report.json"
    current_inventory = load_or_bootstrap_inventory(publish_root)
    if report_path.is_file():
        persisted = _read_json(report_path)
        if current_inventory["stats"]["merkleRoot"] == persisted.get(
            "restoredMerkle"
        ):
            validate_delta_materialization(
                publish_root=publish_root,
                entries=list(delta["entries"]),
                reverse=True,
            )
            return {**persisted, "idempotent": True}
        raise ObjectTransactionError("rollback receipt exists but canonical pointer drifted")
    rollback_intent_path = run_root / "rollback_intent.json"
    if current_inventory["stats"]["merkleRoot"] == apply_report.get("beforeMerkle"):
        if not rollback_intent_path.is_file():
            raise ObjectTransactionError("rollback before canonical inventory drift")
        validate_delta_materialization(
            publish_root=publish_root,
            entries=list(delta["entries"]),
            reverse=True,
        )
        restored_inventory = current_inventory
    elif current_inventory["stats"]["merkleRoot"] != apply_report.get(
        "afterMerkle"
    ):
        raise ObjectTransactionError("rollback before canonical Merkle drift")
    else:
        if not rollback_intent_path.is_file():
            _write_json(
                rollback_intent_path,
                {
                    "schema": "quwoquan_data.object_transaction_rollback_intent",
                    "transactionId": transaction_id,
                    "deltaManifestDigest": delta["deltaDigest"],
                    "preparedAt": _now(),
                },
            )
        try:
            validate_delta_materialization(
                publish_root=publish_root,
                entries=list(delta["entries"]),
                reverse=True,
            )
        except ObjectTransactionError:
            apply_inverse_delta(
                publish_root=publish_root,
                run_root=run_root,
                manifest=delta,
            )
        restored_inventory = apply_inventory_delta(
            current_inventory,
            list(delta["entries"]),
            publish_root=publish_root,
            reverse=True,
        )
        try:
            if restored_inventory["stats"]["merkleRoot"] != apply_report.get(
                "beforeMerkle"
            ):
                raise ObjectTransactionError("rollback inverse delta Merkle mismatch")
            validate_delta_materialization(
                publish_root=publish_root,
                entries=list(delta["entries"]),
                reverse=True,
            )
            write_inventory(publish_root, restored_inventory)
        except BaseException:
            apply_forward_delta(
                publish_root=publish_root,
                run_root=run_root,
                manifest=delta,
            )
            raise
    pointer_path = run_root / "pointer.json"
    _write_json(
        pointer_path,
        _pointer_document(
            report=audit_report,
            state="rolled_back",
            active_merkle=str(restored_inventory["stats"]["merkleRoot"]),
            active_inventory_digest=str(restored_inventory["inventoryDigest"]),
            revision=2,
        ),
    )
    result = {
        "schema": ROLLBACK_SCHEMA,
        "transactionId": transaction_id,
        "status": "rolled_back",
        "rolledBackAt": _now(),
        "restoredMerkle": restored_inventory["stats"]["merkleRoot"],
        "restoredInventoryDigest": restored_inventory["inventoryDigest"],
        "rollbackRefPreserved": str(run_root / "delta"),
        "pointerRef": str(pointer_path),
        "deltaManifestDigest": delta["deltaDigest"],
        "idempotent": False,
    }
    _write_json(report_path, result)
    return result


@canonical_publish_serialized
def replay_object_transaction(
    *,
    publish_root: Path,
    output_root: Path,
    transaction_id: str,
) -> dict[str, Any]:
    """Replay a rolled-back immutable delta to the exact after revision."""
    from content.release.canonical.object_transaction_audit import _transaction_root

    transaction_id = _safe_id(transaction_id, label="transactionId")
    run_root = _transaction_root(output_root, transaction_id)
    audit_report = _read_json(run_root / "audit_report.json")
    apply_report = _read_json(run_root / "apply_report.json")
    rollback_report = _read_json(run_root / "rollback_report.json")
    if rollback_report.get("status") != "rolled_back":
        raise ObjectTransactionError("canonical replay requires a rollback receipt")
    delta = load_transaction_delta(
        run_root=run_root,
        expected_digest=str(apply_report.get("deltaManifestDigest") or ""),
    )
    _verify_fence(audit_report, delta)
    report_path = run_root / "replay_report.json"
    current_inventory = load_or_bootstrap_inventory(publish_root)
    if report_path.is_file():
        persisted = _read_json(report_path)
        if current_inventory["stats"]["merkleRoot"] == persisted.get(
            "restoredMerkle"
        ):
            validate_delta_materialization(
                publish_root=publish_root,
                entries=list(delta["entries"]),
            )
            return {**persisted, "idempotent": True}
        raise ObjectTransactionError("replay receipt exists but canonical pointer drifted")
    replay_intent_path = run_root / "replay_intent.json"
    if current_inventory["stats"]["merkleRoot"] == apply_report.get("afterMerkle"):
        if not replay_intent_path.is_file():
            raise ObjectTransactionError("replay after canonical inventory drift")
        validate_delta_materialization(
            publish_root=publish_root,
            entries=list(delta["entries"]),
        )
        restored_inventory = current_inventory
    elif current_inventory["stats"]["merkleRoot"] != apply_report.get(
        "beforeMerkle"
    ):
        raise ObjectTransactionError("replay before canonical Merkle drift")
    else:
        if replay_intent_path.is_file():
            _recover_interrupted_forward(
                publish_root=publish_root,
                run_root=run_root,
                delta=delta,
            )
        else:
            _write_json(
                replay_intent_path,
                {
                    "schema": "quwoquan_data.object_transaction_replay_intent",
                    "transactionId": transaction_id,
                    "deltaManifestDigest": delta["deltaDigest"],
                    "preparedAt": _now(),
                },
            )
        applied_entries = apply_forward_delta(
            publish_root=publish_root,
            run_root=run_root,
            manifest=delta,
        )
        try:
            restored_inventory = apply_inventory_delta(
                current_inventory,
                list(delta["entries"]),
                publish_root=publish_root,
            )
            if restored_inventory["stats"]["merkleRoot"] != apply_report.get(
                "afterMerkle"
            ):
                raise ObjectTransactionError("canonical replay proof failed")
            validate_delta_materialization(
                publish_root=publish_root,
                entries=list(delta["entries"]),
            )
            write_inventory(publish_root, restored_inventory)
        except BaseException:
            revert_applied_delta(
                publish_root=publish_root,
                run_root=run_root,
                entries=applied_entries,
            )
            raise
    pointer_path = run_root / "pointer.json"
    _write_json(
        pointer_path,
        _pointer_document(
            report=audit_report,
            state="replayed",
            active_merkle=str(restored_inventory["stats"]["merkleRoot"]),
            active_inventory_digest=str(restored_inventory["inventoryDigest"]),
            revision=3,
        ),
    )
    result = {
        "schema": REPLAY_SCHEMA,
        "transactionId": transaction_id,
        "status": "replayed",
        "replayedAt": _now(),
        "restoredMerkle": restored_inventory["stats"]["merkleRoot"],
        "restoredInventoryDigest": restored_inventory["inventoryDigest"],
        "pointerRef": str(pointer_path),
        "deltaManifestDigest": delta["deltaDigest"],
        "idempotent": False,
    }
    _write_json(report_path, result)
    return result


__all__ = [
    "apply_object_transaction",
    "replay_object_transaction",
    "rollback_object_transaction",
]
