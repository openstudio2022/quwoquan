"""One-time backfill of tombstones for executions removed before the protocol.

存量 output 里有一批被 immutable release 引用、却已经不在磁盘上的 execution：它们在
墓碑协议存在之前就被清掉了，而 release 不可改写、task 不可重建，因此引用图对它们永久
`GATE_BLOCK`。这里补的是当时缺失的那一条终态记录，不是伪造证据——墓碑只声明「已永久
缺席」，既不复制产物也不为消失的字节补摘要。

之所以不能复用 `build_reference_graph`：它正是在这些引用上 fail closed，走不到能列出
它们的那一步。所以扫描走 `collect_execution_reference_sites` 的宽容读，判否留给墓碑
写入本身。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.canonical.garbage_collection_contract import (
    gc_workspace_root,
    json_digest,
    write_create_once_json,
)
from content.release.canonical.garbage_collection_reference_scan import (
    collect_absent_execution_proofs,
    collect_execution_reference_sites,
)
from content.release.canonical.garbage_collection_tombstone import (
    ExecutionReclaimReason,
    load_execution_tombstones,
    write_execution_tombstone,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_id,
)
from core.schema import assert_valid

TOMBSTONE_BACKFILL_SCHEMA = "quwoquan_data.canonical_gc_tombstone_backfill"


def _typed(code: str, detail: str) -> ObjectTransactionError:
    return ObjectTransactionError(f"GATE_BLOCK DATA.GC.{code}: {detail}")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def unresolved_execution_references(
    *,
    output_root: Path,
    publish_root: Path,
    release_root: Path,
) -> dict[str, tuple[dict[str, str], ...]]:
    """Return each execution reference that has no task, proof, or tombstone.

    Live tasks, reconciliation absence proofs and existing tombstones are all
    resolved states, so subtracting them leaves exactly the population the
    reference graph currently fails on.
    """

    output_root = output_root.resolve()
    tasks_root = output_root / "data/tasks"
    live = (
        {path.name for path in tasks_root.iterdir() if path.is_dir()}
        if tasks_root.is_dir() and not tasks_root.is_symlink()
        else set()
    )
    resolved = (
        live
        | collect_absent_execution_proofs(output_root)
        | set(load_execution_tombstones(output_root))
    )
    sites = collect_execution_reference_sites(
        output_root=output_root,
        publish_root=publish_root.resolve(),
        release_root=release_root.resolve(),
    )
    unresolved: dict[str, tuple[dict[str, str], ...]] = {}
    for execution_id, referrers in sorted(sites.items()):
        if execution_id in resolved:
            continue
        unresolved[execution_id] = tuple(
            {"ref": ref, "relation": relation}
            for ref, relation in sorted(referrers)
        )
    return unresolved


def backfill_absent_execution_tombstones(
    *,
    backfill_id: str,
    output_root: Path,
    publish_root: Path,
    release_root: Path,
    now: datetime | None = None,
) -> tuple[dict[str, Any], Path]:
    """Write one create-once tombstone per unresolvable execution reference."""

    backfill_id = _safe_id(backfill_id, label="backfillId")
    output_root = output_root.resolve()
    reclaimed_at = _iso(now or datetime.now(timezone.utc))
    unresolved = unresolved_execution_references(
        output_root=output_root,
        publish_root=publish_root,
        release_root=release_root,
    )
    written: list[dict[str, Any]] = []
    for execution_id, referrers in unresolved.items():
        if not referrers:
            raise _typed(
                "EXECUTION_TOMBSTONE_INVALID",
                f"unresolved execution has no referrer to record: {execution_id}",
            )
        document, path, created = write_execution_tombstone(
            output_root=output_root,
            execution_id=execution_id,
            reason=ExecutionReclaimReason.RECLAIMED_BEFORE_TOMBSTONE_PROTOCOL,
            reclaimed_at=reclaimed_at,
            referenced_by=referrers,
            backfill_id=backfill_id,
        )
        written.append(
            {
                "executionId": execution_id,
                "tombstoneRef": path.relative_to(output_root).as_posix(),
                "tombstoneDigest": str(document["tombstoneDigest"]),
                "referrerCount": len(referrers),
                "created": created,
            }
        )
    receipt: dict[str, Any] = {
        "schema": TOMBSTONE_BACKFILL_SCHEMA,
        "backfillId": backfill_id,
        "backfilledAt": reclaimed_at,
        "publishRoot": str(publish_root.resolve()),
        "releaseRoot": str(release_root.resolve()),
        "tombstones": written,
        "tombstoneCount": len(written),
    }
    receipt["receiptDigest"] = json_digest(receipt, excluded="receiptDigest")
    try:
        assert_valid(
            dict(receipt),
            "governance",
            "canonical_gc_tombstone_backfill",
            label=f"canonical GC tombstone backfill:{backfill_id}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _typed("TOMBSTONE_BACKFILL_INVALID", str(exc)) from exc
    path = (
        gc_workspace_root(output_root)
        / "tombstone-backfills"
        / backfill_id
        / "backfill.json"
    )
    if write_create_once_json(path, receipt):
        return receipt, path
    persisted = _read_json(path)
    if persisted.get("backfillId") != backfill_id or persisted.get(
        "receiptDigest"
    ) != json_digest(persisted, excluded="receiptDigest"):
        raise _typed(
            "TOMBSTONE_BACKFILL_INVALID",
            f"persisted backfill receipt drift: {backfill_id}",
        )
    return persisted, path


__all__ = [
    "TOMBSTONE_BACKFILL_SCHEMA",
    "backfill_absent_execution_tombstones",
    "unresolved_execution_references",
]
