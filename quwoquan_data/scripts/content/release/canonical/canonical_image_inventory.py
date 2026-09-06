"""Indexed canonical image identities stored in the publish inventory sidecar.

The exact digest index is direct.  Perceptual candidates use ``radius + 1``
disjoint bit bands: if two hashes differ in at most ``radius`` bits, at least
one band is identical.  Every candidate is then checked with the exact Hamming
distance, so the index cannot introduce a false-negative duplicate decision.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
    object_lineage,
)
from core.image_deduplication import perceptual_hash_distance
NEAR_DUP_HAMMING = 5

IMAGE_INDEX_SCHEMA = "quwoquan_data.canonical_image_inventory"
_BAND_COUNT = NEAR_DUP_HAMMING + 1
_IMAGE_TABLES = frozenset(
    {"image_index_state", "image_identities", "image_perceptual_bands"}
)


def _image_tables(connection: sqlite3.Connection) -> frozenset[str]:
    return frozenset(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'image_%'"
        )
    )


def _image_identities(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    identities: list[dict[str, Any]] = []
    image_post = str(manifest.get("contentType") or "").strip() == "image"
    for ordinal, raw in enumerate(manifest.get("assets") or []):
        if not isinstance(raw, Mapping):
            continue
        kind = str(raw.get("kind") or "").strip()
        mime = str(raw.get("mimeType") or "").strip().lower()
        if not image_post and kind != "image" and not mime.startswith("image/"):
            continue
        perceptual = str(raw.get("perceptualHash") or "").strip().lower()
        if not perceptual:
            raise ObjectTransactionError(
                "canonical image asset requires perceptualHash for duplicate isolation"
            )
        try:
            if len(perceptual) != 16:
                raise ValueError("canonical pHash must be 64 bits")
            perceptual_hash_distance(perceptual, perceptual)
        except ValueError as exc:
            raise ObjectTransactionError(
                "canonical image asset perceptualHash is invalid"
            ) from exc
        identities.append(
            {
                "ordinal": ordinal,
                "assetId": str(raw.get("assetId") or "").strip()
                or "<unnamed-image>",
                "sha256": str(raw.get("sha256") or "").strip().lower(),
                "perceptualHash": perceptual,
            }
        )
    if image_post and not identities:
        raise ObjectTransactionError(
            "canonical image asset requires perceptualHash for duplicate isolation"
        )
    return tuple(identities)


def _bands(perceptual_hash: str) -> tuple[tuple[int, int, str], ...]:
    width = len(perceptual_hash) * 4
    bits = f"{int(perceptual_hash, 16):0{width}b}"
    base, remainder = divmod(width, _BAND_COUNT)
    start = 0
    rows: list[tuple[int, int, str]] = []
    for band in range(_BAND_COUNT):
        length = base + (1 if band < remainder else 0)
        end = start + length
        rows.append((width, band, bits[start:end]))
        start = end
    return tuple(rows)


def create_image_index_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS image_index_state (
          singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
          schema TEXT NOT NULL,
          inventory_digest TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS image_identities (
          manifest_path TEXT NOT NULL,
          asset_ordinal INTEGER NOT NULL,
          asset_id TEXT NOT NULL,
          asset_sha256 TEXT NOT NULL,
          perceptual_hash TEXT NOT NULL,
          PRIMARY KEY (manifest_path, asset_ordinal)
        ) WITHOUT ROWID
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS image_identities_sha256 "
        "ON image_identities(asset_sha256)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS image_perceptual_bands (
          manifest_path TEXT NOT NULL,
          asset_ordinal INTEGER NOT NULL,
          hash_width INTEGER NOT NULL,
          band INTEGER NOT NULL,
          band_value TEXT NOT NULL,
          PRIMARY KEY (manifest_path, asset_ordinal, band),
          FOREIGN KEY (manifest_path, asset_ordinal)
            REFERENCES image_identities(manifest_path, asset_ordinal)
            ON DELETE CASCADE
        ) WITHOUT ROWID
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS image_perceptual_band_lookup "
        "ON image_perceptual_bands(hash_width, band, band_value)"
    )


def _insert_manifest(
    connection: sqlite3.Connection,
    *,
    manifest_path: str,
    manifest: Mapping[str, Any],
) -> None:
    identities = _image_identities(manifest)
    for identity in identities:
        ordinal = int(identity["ordinal"])
        connection.execute(
            "INSERT INTO image_identities(manifest_path, asset_ordinal, asset_id, "
            "asset_sha256, perceptual_hash) VALUES (?, ?, ?, ?, ?)",
            (
                manifest_path,
                ordinal,
                identity["assetId"],
                identity["sha256"],
                identity["perceptualHash"],
            ),
        )
        connection.executemany(
            "INSERT INTO image_perceptual_bands(manifest_path, asset_ordinal, "
            "hash_width, band, band_value) VALUES (?, ?, ?, ?, ?)",
            [
                (manifest_path, ordinal, width, band, value)
                for width, band, value in _bands(str(identity["perceptualHash"]))
            ],
        )


def _read_manifest(path: Path, *, expected_sha256: str | None = None) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ObjectTransactionError(f"canonical post manifest is missing: {path}")
    if expected_sha256 is not None and _digest_file(path) != expected_sha256:
        raise ObjectTransactionError(
            f"canonical image index manifest digest drift: {path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ObjectTransactionError(
            f"canonical post manifest must be an object: {path}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ObjectTransactionError(
            f"canonical post manifest must be an object: {path}"
        )
    return payload


def bootstrap_image_index(
    connection: sqlite3.Connection,
    *,
    publish_root: Path,
    inventory_digest: str,
    manifest_paths: Sequence[str] | None = None,
) -> None:
    """Create the single-track index from a cold canonical projection scan."""
    tables = _image_tables(connection)
    if "image_index_state" in tables:
        if not _IMAGE_TABLES.issubset(tables):
            raise ObjectTransactionError("canonical image inventory structure drift")
        state = connection.execute(
            "SELECT schema, inventory_digest FROM image_index_state WHERE singleton = 1"
        ).fetchone()
        if state is None:
            raise ObjectTransactionError("canonical image inventory state drift")
        if state[0] != IMAGE_INDEX_SCHEMA or state[1] != inventory_digest:
            raise ObjectTransactionError("canonical image inventory state drift")
        return
    if tables & _IMAGE_TABLES:
        raise ObjectTransactionError("canonical image inventory structure drift")
    create_image_index_schema(connection)
    paths = tuple(manifest_paths) if manifest_paths is not None else tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT path FROM entries WHERE path LIKE 'posts/%/manifest.json' "
            "ORDER BY path"
        )
    )
    for relative in paths:
        if not relative.startswith("posts/") or not relative.endswith("/manifest.json"):
            continue
        entry = connection.execute(
            "SELECT sha256 FROM entries WHERE path = ?", (relative,)
        ).fetchone()
        if entry is None:
            raise ObjectTransactionError(
                f"canonical image inventory entry is missing: {relative}"
            )
        manifest = _read_manifest(
            publish_root / relative,
            expected_sha256=str(entry[0]),
        )
        assert_image_manifest_unique(
            connection,
            manifest=manifest,
            excluded_manifest_path=relative,
        )
        _insert_manifest(
            connection,
            manifest_path=relative,
            manifest=manifest,
        )
    connection.execute(
        "INSERT INTO image_index_state(singleton, schema, inventory_digest) "
        "VALUES (1, ?, ?)",
        (IMAGE_INDEX_SCHEMA, inventory_digest),
    )


def assert_image_index_ready(
    connection: sqlite3.Connection,
    *,
    inventory_digest: str,
) -> None:
    if not _IMAGE_TABLES.issubset(_image_tables(connection)):
        raise ObjectTransactionError("canonical image inventory structure drift")
    try:
        state = connection.execute(
            "SELECT schema, inventory_digest FROM image_index_state WHERE singleton = 1"
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise ObjectTransactionError("canonical image inventory is missing") from exc
    if (
        state is None
        or state[0] != IMAGE_INDEX_SCHEMA
        or state[1] != inventory_digest
    ):
        raise ObjectTransactionError("canonical image inventory state drift")


def sync_image_index_delta(
    connection: sqlite3.Connection,
    *,
    publish_root: Path,
    mutations: Sequence[Mapping[str, Any]],
    inventory_digest: str,
) -> None:
    """Apply manifest identity changes in the inventory metadata transaction."""
    for mutation in mutations:
        relative = str(mutation.get("path") or "")
        if not relative.startswith("posts/") or not relative.endswith("/manifest.json"):
            continue
        connection.execute(
            "DELETE FROM image_perceptual_bands WHERE manifest_path = ?", (relative,)
        )
        connection.execute(
            "DELETE FROM image_identities WHERE manifest_path = ?", (relative,)
        )
        after = mutation.get("after")
        if isinstance(after, Mapping):
            manifest = _read_manifest(
                publish_root / relative,
                expected_sha256=str(after.get("sha256") or ""),
            )
            assert_image_manifest_unique(
                connection,
                manifest=manifest,
                excluded_manifest_path=relative,
            )
            _insert_manifest(
                connection,
                manifest_path=relative,
                manifest=manifest,
            )
    updated = connection.execute(
        "UPDATE image_index_state SET inventory_digest = ? "
        "WHERE singleton = 1 AND schema = ?",
        (inventory_digest, IMAGE_INDEX_SCHEMA),
    )
    if updated.rowcount != 1:
        raise ObjectTransactionError("canonical image inventory state drift")


def assert_image_manifest_unique(
    connection: sqlite3.Connection,
    *,
    manifest: Mapping[str, Any],
    excluded_manifest_path: str,
) -> None:
    """Reject exact and radius-bounded duplicates using indexed candidates.

    Duplication is asked of the object, not of the file: the excluded manifest's
    own lineage covers the version being written and every version of it already
    published, so a forward-only successor is not a duplicate of what it
    supersedes while any other object holding the image still is.
    """

    excluded_lineage = object_lineage(excluded_manifest_path)
    accepted_pending: list[dict[str, Any]] = []
    for identity in _image_identities(manifest):
        candidates: dict[tuple[str, int], sqlite3.Row] = {}
        digest = str(identity["sha256"])
        if digest:
            for row in connection.execute(
                "SELECT manifest_path, asset_ordinal, asset_id, asset_sha256, "
                "perceptual_hash FROM image_identities "
                "WHERE asset_sha256 = ? AND manifest_path <> ?",
                (digest, excluded_manifest_path),
            ):
                candidates[(str(row[0]), int(row[1]))] = row
        for width, band, value in _bands(str(identity["perceptualHash"])):
            for row in connection.execute(
                "SELECT i.manifest_path, i.asset_ordinal, i.asset_id, "
                "i.asset_sha256, i.perceptual_hash FROM image_perceptual_bands b "
                "JOIN image_identities i ON i.manifest_path=b.manifest_path "
                "AND i.asset_ordinal=b.asset_ordinal WHERE b.hash_width=? "
                "AND b.band=? AND b.band_value=? AND i.manifest_path<>?",
                (width, band, value, excluded_manifest_path),
            ):
                candidates[(str(row[0]), int(row[1]))] = row
        peers = [
            {
                "manifestPath": row[0],
                "assetId": row[2],
                "sha256": row[3],
                "perceptualHash": row[4],
            }
            for row in candidates.values()
            if object_lineage(str(row[0])) != excluded_lineage
        ] + accepted_pending
        for peer in peers:
            peer_ref = str(peer.get("manifestPath") or "pending-post")
            peer_id = str(peer["assetId"])
            stable_asset_reuse = identity["assetId"] == peer_id
            if digest and digest == peer["sha256"] and not stable_asset_reuse:
                raise ObjectTransactionError(
                    "canonical image identity duplicated by sha256: "
                    f"{identity['assetId']} conflicts with {peer_ref}:{peer_id}"
                )
            if (
                perceptual_hash_distance(
                    str(identity["perceptualHash"]), str(peer["perceptualHash"])
                ) <= NEAR_DUP_HAMMING
                and not stable_asset_reuse
            ):
                raise ObjectTransactionError(
                    "canonical image identity duplicated by perceptualHash: "
                    f"{identity['assetId']} conflicts with {peer_ref}:{peer_id}"
                )
        accepted_pending.append(
            {**identity, "manifestPath": "pending-post"}
        )


__all__ = [
    "IMAGE_INDEX_SCHEMA",
    "assert_image_index_ready",
    "assert_image_manifest_unique",
    "bootstrap_image_index",
    "create_image_index_schema",
    "sync_image_index_delta",
]
