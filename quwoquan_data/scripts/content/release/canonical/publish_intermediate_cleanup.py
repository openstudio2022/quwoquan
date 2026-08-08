"""Migrate legacy publish-local review receipts into protected evidence refs."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.canonical.canonical_inventory import (
    apply_inventory_delta,
    load_or_bootstrap_inventory,
    write_inventory,
)
from content.release.canonical.garbage_collection_contract import (
    json_digest,
    write_create_once_json,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_bytes,
    _digest_file,
    _json_bytes,
    _read_json,
    _safe_id,
    _safe_rel,
    _write_json,
)
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)
from content.release.canonical.publish_intermediate_cleanup_plan import (
    cleanup_candidates,
    cleanup_delta_entries,
    cleanup_receipt_files,
)

PLAN_SCHEMA = "quwoquan_data.publish_intermediate_cleanup_plan"
RECEIPT_SCHEMA = "quwoquan_data.publish_intermediate_cleanup_receipt"
_INTENT_SCHEMA = "quwoquan_data.publish_intermediate_cleanup_intent"
_WORKSPACE_REF = Path("data/local/workspace/publish-intermediate-cleanups")
_QUARANTINE_REF = Path(
    "data/local/workspace/quarantine/canonical-publish-intermediates"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_root(output_root: Path, cleanup_id: str) -> Path:
    return output_root.resolve() / _WORKSPACE_REF / cleanup_id


def _quarantine_root(output_root: Path, cleanup_id: str) -> Path:
    return output_root.resolve() / _QUARANTINE_REF / cleanup_id / "publish"


def _validate_plan(
    document: Mapping[str, Any],
    *,
    cleanup_id: str,
    plan_digest: str | None = None,
) -> str:
    actual = json_digest(document, excluded="planDigest")
    candidates = document.get("candidates")
    if (
        document.get("schema") != PLAN_SCHEMA
        or document.get("cleanupId") != cleanup_id
        or not isinstance(candidates, list)
        or document.get("candidateCount") != len(candidates)
        or document.get("inventoryDelta") != cleanup_delta_entries(candidates)
        or document.get("planDigest") != actual
        or (plan_digest is not None and plan_digest != actual)
    ):
        raise ObjectTransactionError("publish intermediate cleanup plan drift")
    refs = [str(row.get("ref") or "") for row in candidates]
    if len(refs) != len(set(refs)):
        raise ObjectTransactionError("publish intermediate cleanup candidate drift")
    for candidate in candidates:
        after = candidate.get("afterRights")
        if (
            not isinstance(after, Mapping)
            or _digest_bytes(_json_bytes(after)) != candidate.get("afterRightsSha256")
            or len(_json_bytes(after)) != candidate.get("afterRightsBytes")
        ):
            raise ObjectTransactionError("cleanup migrated rights plan drift")
    return actual


def _candidate_state(
    *,
    candidate: Mapping[str, Any],
    publish_root: Path,
    output_root: Path,
    quarantine_root: Path,
) -> tuple[bool, bool]:
    rights_path = publish_root / _safe_rel(
        str(candidate.get("rightsRef") or ""), label="cleanup.rightsRef"
    )
    if not rights_path.is_file() or rights_path.is_symlink():
        raise ObjectTransactionError("cleanup rights file is missing")
    rights_sha = _digest_file(rights_path)
    if rights_sha == candidate.get("beforeRightsSha256"):
        rights_migrated = False
    elif rights_sha == candidate.get("afterRightsSha256"):
        rights_migrated = True
        if _read_json(rights_path) != candidate.get("afterRights"):
            raise ObjectTransactionError("cleanup migrated rights bytes drift")
    else:
        raise ObjectTransactionError("cleanup rights bytes drift")
    relative = _safe_rel(str(candidate.get("ref") or ""), label="cleanup.ref")
    source = publish_root / relative
    quarantine = quarantine_root / relative
    if source.exists() and quarantine.exists():
        raise ObjectTransactionError(f"cleanup source/quarantine collision: {relative}")
    selected = source if source.exists() else quarantine
    if not selected.is_dir() or selected.is_symlink():
        raise ObjectTransactionError(f"cleanup candidate is missing: {relative}")
    quarantined = selected == quarantine
    if quarantined and not rights_migrated:
        raise ObjectTransactionError("cleanup receipts moved before rights migration")
    expected = {
        str(row["localRef"]): (str(row["receiptFileSha256"]), int(row["bytes"]))
        for row in candidate.get("receiptMigrations") or []
    }
    observed = cleanup_receipt_files(
        selected,
        relative_to=publish_root if selected == source else quarantine_root,
    )
    if {
        str(row["ref"]): (str(row["sha256"]), int(row["bytes"]))
        for row in observed
    } != expected:
        raise ObjectTransactionError(f"cleanup candidate bytes drift: {relative}")
    for migration in candidate.get("receiptMigrations") or []:
        external = output_root / _safe_rel(
            str(migration.get("externalRef") or ""),
            label="cleanup.externalReceiptRef",
        )
        if (
            not external.is_file()
            or external.is_symlink()
            or _digest_file(external) != migration.get("receiptFileSha256")
            or external.stat().st_size != migration.get("bytes")
        ):
            raise ObjectTransactionError("cleanup external receipt bytes drift")
    return rights_migrated, quarantined


def _append_journal(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


@canonical_publish_serialized
def plan_publish_intermediate_cleanup(
    *,
    cleanup_id: str,
    publish_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], Path]:
    """Freeze exact rights migrations and receipt deletions without mutation."""

    cleanup_id = _safe_id(cleanup_id, label="cleanupId")
    publish_root = publish_root.resolve()
    output_root = output_root.resolve()
    path = _cleanup_root(output_root, cleanup_id) / "plan.json"
    if path.is_file():
        persisted = _read_json(path)
        _validate_plan(persisted, cleanup_id=cleanup_id)
        if persisted.get("publishRoot") != str(publish_root):
            raise ObjectTransactionError("publish intermediate cleanup request drift")
        return persisted, path
    inventory = load_or_bootstrap_inventory(publish_root)
    candidates = cleanup_candidates(publish_root, output_root)
    delta = cleanup_delta_entries(candidates)
    after = (
        apply_inventory_delta(inventory, delta, publish_root=publish_root)
        if delta
        else inventory
    )
    document: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "cleanupId": cleanup_id,
        "status": "planned",
        "plannedAt": _now(),
        "publishRoot": str(publish_root),
        "beforeInventoryDigest": inventory["inventoryDigest"],
        "afterInventoryDigest": after["inventoryDigest"],
        "afterMerkle": after["stats"]["merkleRoot"],
        "inventoryDelta": delta,
        "candidates": candidates,
        "candidateCount": len(candidates),
        "quarantinedBytes": sum(int(row["bytes"]) for row in candidates),
    }
    document["planDigest"] = json_digest(document, excluded="planDigest")
    if not write_create_once_json(path, document):
        persisted = _read_json(path)
        if persisted != document:
            raise ObjectTransactionError("cleanup plan create-once collision")
        document = persisted
    _validate_plan(document, cleanup_id=cleanup_id)
    return document, path


@canonical_publish_serialized
def apply_publish_intermediate_cleanup(
    *,
    cleanup_id: str,
    plan_digest: str,
    publish_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], Path]:
    """Migrate rights first, quarantine receipts, then commit one inventory delta."""

    cleanup_id = _safe_id(cleanup_id, label="cleanupId")
    publish_root = publish_root.resolve()
    output_root = output_root.resolve()
    root = _cleanup_root(output_root, cleanup_id)
    plan = _read_json(root / "plan.json")
    actual_digest = _validate_plan(
        plan,
        cleanup_id=cleanup_id,
        plan_digest=plan_digest,
    )
    if plan.get("publishRoot") != str(publish_root):
        raise ObjectTransactionError("publish intermediate cleanup publishRoot drift")
    receipt_path = root / "apply.json"
    quarantine_root = _quarantine_root(output_root, cleanup_id)
    inventory = load_or_bootstrap_inventory(publish_root)
    if inventory["inventoryDigest"] not in {
        plan["beforeInventoryDigest"],
        plan["afterInventoryDigest"],
    }:
        raise ObjectTransactionError("publish changed after intermediate cleanup plan")
    states = [
        _candidate_state(
            candidate=candidate,
            publish_root=publish_root,
            output_root=output_root,
            quarantine_root=quarantine_root,
        )
        for candidate in plan["candidates"]
    ]
    if receipt_path.is_file():
        persisted = _read_json(receipt_path)
        if (
            persisted.get("schema") != RECEIPT_SCHEMA
            or persisted.get("planDigest") != actual_digest
            or persisted.get("receiptDigest")
            != json_digest(persisted, excluded="receiptDigest")
            or inventory["inventoryDigest"] != plan["afterInventoryDigest"]
            or any(state != (True, True) for state in states)
        ):
            raise ObjectTransactionError("publish intermediate cleanup receipt drift")
        return {**persisted, "idempotent": True}, receipt_path
    intent_stable = {
        "schema": _INTENT_SCHEMA,
        "cleanupId": cleanup_id,
        "planDigest": actual_digest,
        "beforeInventoryDigest": plan["beforeInventoryDigest"],
        "afterInventoryDigest": plan["afterInventoryDigest"],
    }
    intent_path = root / "apply_intent.json"
    if intent_path.is_file():
        persisted_intent = _read_json(intent_path)
        if any(persisted_intent.get(key) != value for key, value in intent_stable.items()):
            raise ObjectTransactionError("cleanup intent create-once collision")
    else:
        intent = {**intent_stable, "preparedAt": _now()}
        if not write_create_once_json(intent_path, intent) and _read_json(intent_path) != intent:
            raise ObjectTransactionError("cleanup intent create-once collision")
    journal_path = root / "apply.journal.jsonl"
    for candidate, state in zip(plan["candidates"], states, strict=True):
        rights_migrated, quarantined = state
        rights_path = publish_root / _safe_rel(
            str(candidate["rightsRef"]), label="cleanup.rightsRef"
        )
        if not rights_migrated:
            _write_json(rights_path, candidate["afterRights"])
            _append_journal(
                journal_path,
                {
                    "event": "rights_migrated",
                    "objectRef": candidate["objectRef"],
                    "rightsRef": candidate["rightsRef"],
                    "afterSha256": candidate["afterRightsSha256"],
                    "recordedAt": _now(),
                },
            )
        relative = _safe_rel(str(candidate["ref"]), label="cleanup.ref")
        source = publish_root / relative
        quarantine = quarantine_root / relative
        if not quarantined:
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            source.replace(quarantine)
            _append_journal(
                journal_path,
                {
                    "event": "receipts_quarantined",
                    "objectRef": candidate["objectRef"],
                    "quarantineRef": quarantine.relative_to(output_root).as_posix(),
                    "recordedAt": _now(),
                },
            )
        if _candidate_state(
            candidate=candidate,
            publish_root=publish_root,
            output_root=output_root,
            quarantine_root=quarantine_root,
        ) != (True, True):
            raise ObjectTransactionError("cleanup candidate did not reach final state")
    if inventory["inventoryDigest"] == plan["beforeInventoryDigest"]:
        after = apply_inventory_delta(
            inventory,
            plan["inventoryDelta"],
            publish_root=publish_root,
        )
        if (
            after["inventoryDigest"] != plan["afterInventoryDigest"]
            or after["stats"]["merkleRoot"] != plan["afterMerkle"]
        ):
            raise ObjectTransactionError("cleanup incremental inventory proof drift")
        write_inventory(publish_root, after)
        _append_journal(
            journal_path,
            {
                "event": "inventory_committed",
                "inventoryDigest": plan["afterInventoryDigest"],
                "recordedAt": _now(),
            },
        )
    quarantined_rows = [
        {
            "objectRef": candidate["objectRef"],
            "ref": candidate["ref"],
            "quarantineRef": (
                _quarantine_root(output_root, cleanup_id)
                / _safe_rel(str(candidate["ref"]), label="cleanup.ref")
            ).relative_to(output_root).as_posix(),
            "rightsRef": candidate["rightsRef"],
            "beforeRightsSha256": candidate["beforeRightsSha256"],
            "afterRightsSha256": candidate["afterRightsSha256"],
            "receiptMigrations": candidate["receiptMigrations"],
            "fileCount": candidate["fileCount"],
            "bytes": candidate["bytes"],
        }
        for candidate in plan["candidates"]
    ]
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "cleanupId": cleanup_id,
        "planDigest": actual_digest,
        "status": "applied",
        "appliedAt": _now(),
        "quarantined": quarantined_rows,
        "quarantinedCount": len(quarantined_rows),
        "quarantinedBytes": sum(int(row["bytes"]) for row in quarantined_rows),
        "afterInventoryDigest": plan["afterInventoryDigest"],
        "afterMerkle": plan["afterMerkle"],
        "journalRef": journal_path.relative_to(output_root).as_posix(),
        "permanentDeletion": False,
        "idempotent": False,
    }
    receipt["receiptDigest"] = json_digest(receipt, excluded="receiptDigest")
    if not write_create_once_json(receipt_path, receipt):
        persisted = _read_json(receipt_path)
        if persisted != receipt:
            raise ObjectTransactionError("cleanup receipt create-once collision")
        receipt = persisted
    return receipt, receipt_path


__all__ = [
    "PLAN_SCHEMA",
    "RECEIPT_SCHEMA",
    "apply_publish_intermediate_cleanup",
    "plan_publish_intermediate_cleanup",
]
