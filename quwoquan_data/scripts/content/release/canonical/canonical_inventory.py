"""Transactional, constant-size canonical publish inventory pointer.

The canonical publish tree is a consumer projection.  Its disposable inventory
therefore lives beside the process-wide publish lock and uses SQLite only as a
local indexed sidecar.  A cold start scans the projection once.  Afterwards an
object transaction reads and mutates only the paths named by its immutable
delta; neither the pointer nor its digest serialises the complete file list.

The accumulator is an order-independent XOR of path-bound SHA-256 leaf hashes.
Together with exact file/byte counts it gives the hot path a deterministic CAS
root in O(delta) work.  Immutable release creation still performs the
authoritative full closure scan and can rebuild this sidecar from scratch.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical import canonical_video_inventory
from content.release.canonical.canonical_image_inventory import (
    assert_image_index_ready,
    assert_image_manifest_unique,
    bootstrap_image_index,
    sync_image_index_delta,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_bytes,
    _digest_file,
    _files,
    _json_bytes,
    _safe_rel,
    canonical_destination,
)
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)
from core.paths import publish_lock_path

INVENTORY_SCHEMA = "quwoquan_data.canonical_publish_inventory"
INVENTORY_ALGORITHM = "sha256-path-blob-xor-accumulator-v2"
_EMPTY_ACCUMULATOR = bytes(hashlib.sha256().digest_size)


def canonical_inventory_path(publish_root: Path) -> Path:
    lock_path = publish_lock_path(publish_root)
    return lock_path.with_name(f"{lock_path.stem}.inventory.sqlite3")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _valid_digest(value: str) -> bool:
    payload = value.removeprefix("sha256:")
    return (
        value.startswith("sha256:")
        and len(payload) == 64
        and all(character in "0123456789abcdef" for character in payload)
    )


def _leaf(path: str, sha256: str, size: int) -> dict[str, Any]:
    # The inventory is what the Merkle root and every fenced comparison are
    # computed over, so admitting a leaf is the same decision as admitting a
    # canonical file. Asking the shared rule here keeps a media body out of the
    # inventory even if some future producer bypasses the delta path.
    relative = canonical_destination(path, label="canonicalInventory.path")
    if not _valid_digest(sha256):
        raise ObjectTransactionError("canonical publish inventory digest drift")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ObjectTransactionError("canonical publish inventory byte count drift")
    normalized = relative.as_posix()
    return {
        "path": normalized,
        "sha256": sha256,
        "bytes": size,
        "leafHash": _sha256(
            b"blob\0"
            + normalized.encode("utf-8")
            + b"\0"
            + sha256.encode("ascii")
            + b"\0"
            + str(size).encode("ascii")
        ),
    }


def _xor(left: bytes, right_digest: str) -> bytes:
    right = bytes.fromhex(right_digest.removeprefix("sha256:"))
    if len(left) != len(right):
        raise ObjectTransactionError("canonical inventory accumulator drift")
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def _stats(*, accumulator: bytes, file_count: int, total_bytes: int) -> dict[str, Any]:
    if file_count < 0 or total_bytes < 0:
        raise ObjectTransactionError("canonical inventory counters drift")
    counters = file_count.to_bytes(8, "big") + total_bytes.to_bytes(16, "big")
    return {
        "algorithm": INVENTORY_ALGORITHM,
        "merkleRoot": _sha256(b"canonical-root-v2\0" + accumulator + counters),
        "fileCount": file_count,
        "totalBytes": total_bytes,
        "inventoryHash": _sha256(
            b"canonical-inventory-v2\0" + accumulator + counters
        ),
    }


def _document(
    *,
    publish_root: Path,
    revision: int,
    accumulator: bytes,
    file_count: int,
    total_bytes: int,
    pending_base_digest: str | None = None,
    pending_mutations: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    stable: dict[str, Any] = {
        "schema": INVENTORY_SCHEMA,
        "publishRoot": str(publish_root.resolve()),
        "revision": revision,
        "accumulator": "sha256:" + accumulator.hex(),
        "stats": _stats(
            accumulator=accumulator,
            file_count=file_count,
            total_bytes=total_bytes,
        ),
    }
    document = {**stable, "inventoryDigest": _digest_bytes(_json_bytes(stable))}
    if pending_base_digest is not None:
        document["pendingBaseInventoryDigest"] = pending_base_digest
        document["pendingMutations"] = [dict(row) for row in pending_mutations]
    return document


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE metadata (
          singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
          publish_root TEXT NOT NULL,
          revision INTEGER NOT NULL,
          accumulator TEXT NOT NULL,
          file_count INTEGER NOT NULL,
          total_bytes INTEGER NOT NULL,
          inventory_digest TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE entries (
          path TEXT PRIMARY KEY,
          sha256 TEXT NOT NULL,
          bytes INTEGER NOT NULL,
          leaf_hash TEXT NOT NULL
        ) WITHOUT ROWID
        """
    )


def _metadata_document(
    connection: sqlite3.Connection,
    *,
    publish_root: Path,
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT publish_root, revision, accumulator, file_count, total_bytes, "
        "inventory_digest FROM metadata WHERE singleton = 1"
    ).fetchone()
    if row is None or row["publish_root"] != str(publish_root.resolve()):
        raise ObjectTransactionError("canonical publish inventory metadata drift")
    accumulator_text = str(row["accumulator"] or "")
    if not _valid_digest(accumulator_text):
        raise ObjectTransactionError("canonical publish inventory accumulator drift")
    document = _document(
        publish_root=publish_root,
        revision=int(row["revision"]),
        accumulator=bytes.fromhex(accumulator_text.removeprefix("sha256:")),
        file_count=int(row["file_count"]),
        total_bytes=int(row["total_bytes"]),
    )
    if document["inventoryDigest"] != row["inventory_digest"]:
        raise ObjectTransactionError("canonical publish inventory metadata digest drift")
    return document


def _bootstrap_inventory(publish_root: Path, path: Path) -> dict[str, Any]:
    rows = [
        _leaf(
            item.relative_to(publish_root).as_posix(),
            _digest_file(item),
            item.stat().st_size,
        )
        for item in _files(publish_root)
    ]
    accumulator = _EMPTY_ACCUMULATOR
    for row in rows:
        accumulator = _xor(accumulator, str(row["leafHash"]))
    document = _document(
        publish_root=publish_root,
        revision=0,
        accumulator=accumulator,
        file_count=len(rows),
        total_bytes=sum(int(row["bytes"]) for row in rows),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with _connect(temporary) as connection:
            _create_schema(connection)
            connection.executemany(
                "INSERT INTO entries(path, sha256, bytes, leaf_hash) VALUES (?, ?, ?, ?)",
                [
                    (row["path"], row["sha256"], row["bytes"], row["leafHash"])
                    for row in rows
                ],
            )
            connection.execute(
                "INSERT INTO metadata(singleton, publish_root, revision, accumulator, "
                "file_count, total_bytes, inventory_digest) VALUES (1, ?, ?, ?, ?, ?, ?)",
                (
                    document["publishRoot"],
                    document["revision"],
                    document["accumulator"],
                    document["stats"]["fileCount"],
                    document["stats"]["totalBytes"],
                    document["inventoryDigest"],
                ),
            )
            manifest_paths = tuple(
                str(row["path"])
                for row in rows
                if str(row["path"]).startswith("posts/")
                and str(row["path"]).endswith("/manifest.json")
            )
            bootstrap_image_index(
                connection,
                publish_root=publish_root,
                inventory_digest=str(document["inventoryDigest"]),
                manifest_paths=manifest_paths,
            )
            canonical_video_inventory.bootstrap_video_index(
                connection,
                publish_root=publish_root,
                inventory_digest=str(document["inventoryDigest"]),
                manifest_paths=manifest_paths,
            )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return document


def _validate_document_shape(
    document: Mapping[str, Any],
    *,
    publish_root: Path,
) -> dict[str, Any]:
    revision = document.get("revision")
    accumulator = str(document.get("accumulator") or "")
    stats = document.get("stats")
    if (
        document.get("schema") != INVENTORY_SCHEMA
        or document.get("publishRoot") != str(publish_root.resolve())
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 0
        or not _valid_digest(accumulator)
        or not isinstance(stats, Mapping)
    ):
        raise ObjectTransactionError("canonical publish inventory shape drift")
    expected = _document(
        publish_root=publish_root,
        revision=revision,
        accumulator=bytes.fromhex(accumulator.removeprefix("sha256:")),
        file_count=int(stats.get("fileCount", -1)),
        total_bytes=int(stats.get("totalBytes", -1)),
    )
    pending_base = document.get("pendingBaseInventoryDigest")
    pending = document.get("pendingMutations")
    if pending_base is not None or pending is not None:
        if not _valid_digest(str(pending_base or "")) or not isinstance(pending, list):
            raise ObjectTransactionError("canonical inventory pending mutation drift")
        expected["pendingBaseInventoryDigest"] = pending_base
        expected["pendingMutations"] = pending
    if dict(document) != expected:
        raise ObjectTransactionError("canonical publish inventory digest drift")
    return expected


def validate_inventory(
    document: Mapping[str, Any],
    *,
    publish_root: Path,
) -> dict[str, Any]:
    expected = _validate_document_shape(document, publish_root=publish_root)
    if "pendingMutations" in expected:
        return expected
    path = canonical_inventory_path(publish_root)
    if not path.is_file():
        raise ObjectTransactionError("canonical publish inventory is missing")
    try:
        with _connect(path) as connection:
            current = _metadata_document(connection, publish_root=publish_root)
    except (OSError, sqlite3.DatabaseError) as exc:
        raise ObjectTransactionError(
            f"canonical publish inventory is unreadable: {path}"
        ) from exc
    if current != expected:
        raise ObjectTransactionError("canonical publish inventory pointer drift")
    return expected


def load_or_bootstrap_inventory(publish_root: Path) -> dict[str, Any]:
    path = canonical_inventory_path(publish_root)
    if not path.is_file():
        return _bootstrap_inventory(publish_root, path)
    try:
        with _connect(path) as connection:
            document = _metadata_document(connection, publish_root=publish_root)
            bootstrap_image_index(
                connection,
                publish_root=publish_root,
                inventory_digest=str(document["inventoryDigest"]),
            )
            canonical_video_inventory.bootstrap_video_index(
                connection,
                publish_root=publish_root,
                inventory_digest=str(document["inventoryDigest"]),
            )
            return document
    except (OSError, sqlite3.DatabaseError) as exc:
        raise ObjectTransactionError(
            f"canonical publish inventory is unreadable: {path}"
        ) from exc


def _entry(
    connection: sqlite3.Connection,
    destination: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT path, sha256, bytes, leaf_hash FROM entries WHERE path = ?",
        (destination,),
    ).fetchone()
    if row is None:
        return None
    expected = _leaf(str(row["path"]), str(row["sha256"]), int(row["bytes"]))
    if expected["leafHash"] != row["leaf_hash"]:
        raise ObjectTransactionError("canonical publish inventory entry drift")
    return expected


def apply_inventory_delta(
    inventory: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    *,
    publish_root: Path,
    reverse: bool = False,
) -> dict[str, Any]:
    current = validate_inventory(inventory, publish_root=publish_root)
    accumulator = bytes.fromhex(
        str(current["accumulator"]).removeprefix("sha256:")
    )
    file_count = int(current["stats"]["fileCount"])
    total_bytes = int(current["stats"]["totalBytes"])
    mutations: list[dict[str, Any]] = []
    ordered = list(reversed(entries)) if reverse else list(entries)
    destinations = [str(row.get("destination") or "") for row in ordered]
    if len(destinations) != len(set(destinations)):
        raise ObjectTransactionError("canonical inventory delta contains duplicate paths")
    path = canonical_inventory_path(publish_root)
    with _connect(path) as connection:
        for raw in ordered:
            destination = _safe_rel(
                str(raw.get("destination") or ""), label="delta.destination"
            ).as_posix()
            operation = raw.get("operation")
            current_row = _entry(connection, destination)
            after_row = (
                _leaf(
                    destination,
                    str(raw.get("sha256") or ""),
                    int(raw.get("bytes") or 0),
                )
                if operation in {"create", "replace"}
                else None
            )
            before_row = None
            if operation in {"replace", "delete"}:
                before_row = _leaf(
                    destination,
                    str(raw.get("beforeSha256") or ""),
                    int(raw.get("beforeBytes") or 0),
                )
            if operation == "delete" and ("sha256" in raw or "bytes" in raw):
                raise ObjectTransactionError(
                    "canonical inventory delete must bind only before bytes"
                )
            if operation not in {"create", "replace", "delete"}:
                raise ObjectTransactionError(
                    f"invalid canonical inventory operation: {operation}"
                )
            expected_current = after_row if reverse else before_row
            desired = before_row if reverse else after_row
            if current_row != expected_current:
                action = "inverse" if reverse else str(operation)
                raise ObjectTransactionError(
                    f"canonical inventory {action} CAS drift: {destination}"
                )
            if current_row is not None:
                accumulator = _xor(accumulator, str(current_row["leafHash"]))
                file_count -= 1
                total_bytes -= int(current_row["bytes"])
            if desired is not None:
                accumulator = _xor(accumulator, str(desired["leafHash"]))
                file_count += 1
                total_bytes += int(desired["bytes"])
            mutations.append(
                {"path": destination, "before": current_row, "after": desired}
            )
    return _document(
        publish_root=publish_root,
        revision=int(current["revision"]) + 1,
        accumulator=accumulator,
        file_count=file_count,
        total_bytes=total_bytes,
        pending_base_digest=str(current["inventoryDigest"]),
        pending_mutations=mutations,
    )


def write_inventory(publish_root: Path, document: Mapping[str, Any]) -> None:
    pending = _validate_document_shape(document, publish_root=publish_root)
    mutations = pending.get("pendingMutations")
    if not isinstance(mutations, list):
        current = load_or_bootstrap_inventory(publish_root)
        if current != pending:
            raise ObjectTransactionError("canonical inventory write has no delta")
        return
    path = canonical_inventory_path(publish_root)
    try:
        with _connect(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = _metadata_document(connection, publish_root=publish_root)
            if current["inventoryDigest"] != pending["pendingBaseInventoryDigest"]:
                raise ObjectTransactionError("canonical inventory write CAS drift")
            assert_image_index_ready(
                connection,
                inventory_digest=str(current["inventoryDigest"]),
            )
            canonical_video_inventory.assert_video_index_ready(
                connection,
                inventory_digest=str(current["inventoryDigest"]),
            )
            for mutation in mutations:
                if not isinstance(mutation, Mapping):
                    raise ObjectTransactionError("canonical inventory mutation drift")
                destination = str(mutation.get("path") or "")
                before = mutation.get("before")
                after = mutation.get("after")
                if _entry(connection, destination) != before:
                    raise ObjectTransactionError(
                        f"canonical inventory mutation CAS drift: {destination}"
                    )
                if after is None:
                    connection.execute("DELETE FROM entries WHERE path = ?", (destination,))
                else:
                    row = _leaf(
                        destination,
                        str(after.get("sha256") or ""),
                        int(after.get("bytes") or 0),
                    )
                    connection.execute(
                        "INSERT INTO entries(path, sha256, bytes, leaf_hash) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(path) DO UPDATE SET sha256=excluded.sha256, "
                        "bytes=excluded.bytes, leaf_hash=excluded.leaf_hash",
                        (row["path"], row["sha256"], row["bytes"], row["leafHash"]),
                    )
            sync_image_index_delta(
                connection,
                publish_root=publish_root,
                mutations=mutations,
                inventory_digest=str(pending["inventoryDigest"]),
            )
            canonical_video_inventory.sync_video_index_delta(
                connection,
                publish_root=publish_root,
                mutations=mutations,
                inventory_digest=str(pending["inventoryDigest"]),
            )
            connection.execute(
                "UPDATE metadata SET revision=?, accumulator=?, file_count=?, "
                "total_bytes=?, inventory_digest=? WHERE singleton=1",
                (
                    pending["revision"],
                    pending["accumulator"],
                    pending["stats"]["fileCount"],
                    pending["stats"]["totalBytes"],
                    pending["inventoryDigest"],
                ),
            )
            connection.commit()
    except (OSError, sqlite3.DatabaseError) as exc:
        raise ObjectTransactionError("canonical inventory SQLite transaction failed") from exc


@canonical_publish_serialized
def assert_canonical_image_unique(
    *,
    publish_root: Path,
    manifest: Mapping[str, Any],
    excluded_manifest_path: str,
) -> None:
    """Fail closed against the versioned image identity sidecar."""
    inventory = load_or_bootstrap_inventory(publish_root)
    path = canonical_inventory_path(publish_root)
    try:
        with _connect(path) as connection:
            assert_image_index_ready(
                connection,
                inventory_digest=str(inventory["inventoryDigest"]),
            )
            assert_image_manifest_unique(
                connection,
                manifest=manifest,
                excluded_manifest_path=excluded_manifest_path,
            )
    except (OSError, sqlite3.DatabaseError) as exc:
        raise ObjectTransactionError("canonical image inventory query failed") from exc


def validate_delta_materialization(
    *,
    publish_root: Path,
    entries: Sequence[Mapping[str, Any]],
    reverse: bool = False,
) -> None:
    for raw in entries:
        destination = publish_root / _safe_rel(
            str(raw.get("destination") or ""), label="delta.destination"
        )
        expects_absence = (
            reverse and raw.get("operation") == "create"
        ) or (not reverse and raw.get("operation") == "delete")
        if expects_absence:
            if destination.exists():
                raise ObjectTransactionError(
                    f"rolled-back canonical path still exists: {destination}"
                )
            continue
        digest_key = "beforeSha256" if reverse else "sha256"
        bytes_key = "beforeBytes" if reverse else "bytes"
        if (
            not destination.is_file()
            or destination.is_symlink()
            or _digest_file(destination) != raw.get(digest_key)
            or destination.stat().st_size != raw.get(bytes_key)
        ):
            raise ObjectTransactionError(
                f"canonical delta materialization drift: {destination}"
            )


assert_canonical_video_unique = canonical_video_inventory.assert_canonical_video_unique


__all__ = [
    "INVENTORY_SCHEMA",
    "apply_inventory_delta",
    "assert_canonical_image_unique",
    "assert_canonical_video_unique",
    "canonical_inventory_path",
    "load_or_bootstrap_inventory",
    "validate_delta_materialization",
    "validate_inventory",
    "write_inventory",
]
