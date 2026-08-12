"""Indexed exact identities for canonical video content and its poster.

Video duplicate isolation is deliberately byte-exact.  Image perceptual
identity remains owned by ``canonical_image_inventory``; this index only binds
the canonical MP4 digest to the exact poster asset selected by the video
manifest.
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
)
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)

VIDEO_INDEX_SCHEMA = "quwoquan_data.canonical_video_inventory"
_VIDEO_TABLES = frozenset({"video_index_state", "video_identities"})


def _valid_sha256(value: str) -> bool:
    payload = value.removeprefix("sha256:")
    return (
        value.startswith("sha256:")
        and len(payload) == 64
        and all(character in "0123456789abcdef" for character in payload)
    )


def _video_tables(connection: sqlite3.Connection) -> frozenset[str]:
    return frozenset(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'video_%'"
        )
    )


def _video_identities(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    if str(manifest.get("contentType") or "").strip() != "video":
        return ()
    execution_id = str(manifest.get("executionId") or "").strip()
    if not execution_id:
        raise ObjectTransactionError(
            "canonical video identity requires executionId"
        )
    assets = tuple(
        item for item in (manifest.get("assets") or ()) if isinstance(item, Mapping)
    )
    assets_by_id: dict[str, Mapping[str, Any]] = {}
    for asset in assets:
        asset_id = str(asset.get("assetId") or "").strip()
        if not asset_id:
            continue
        if asset_id in assets_by_id:
            raise ObjectTransactionError(
                f"canonical video manifest has duplicate assetId: {asset_id}"
            )
        assets_by_id[asset_id] = asset

    identities: list[dict[str, Any]] = []
    for ordinal, raw in enumerate(assets):
        kind = str(raw.get("kind") or "").strip()
        mime = str(raw.get("mimeType") or "").strip().lower()
        if kind != "video" and not mime.startswith("video/"):
            continue
        asset_id = str(raw.get("assetId") or "").strip()
        content_sha256 = str(raw.get("sha256") or "").strip().lower()
        poster_asset_id = str(raw.get("posterAssetId") or "").strip()
        poster_sha256 = str(raw.get("posterSha256") or "").strip().lower()
        poster_file_name = str(raw.get("posterFileName") or "").strip()
        if not asset_id or not _valid_sha256(content_sha256):
            raise ObjectTransactionError(
                "canonical video asset requires a valid exact sha256 identity"
            )
        if not poster_asset_id or not _valid_sha256(poster_sha256):
            raise ObjectTransactionError(
                "canonical video asset requires a valid exact posterSha256 identity"
            )
        poster = assets_by_id.get(poster_asset_id)
        if (
            poster is None
            or str(poster.get("kind") or "").strip() != "image"
            or str(poster.get("sha256") or "").strip().lower() != poster_sha256
            or str(poster.get("fileName") or "").strip() != poster_file_name
        ):
            raise ObjectTransactionError(
                f"canonical video poster identity binding drift: {asset_id}"
            )
        identities.append(
            {
                "ordinal": ordinal,
                "executionId": execution_id,
                "assetId": asset_id,
                "contentSha256": content_sha256,
                "posterAssetId": poster_asset_id,
                "posterSha256": poster_sha256,
            }
        )
    if not identities:
        raise ObjectTransactionError(
            "canonical video manifest requires an exact video identity"
        )
    return tuple(identities)


def create_video_index_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS video_index_state (
          singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
          schema TEXT NOT NULL,
          inventory_digest TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS video_identities (
          manifest_path TEXT NOT NULL,
          asset_ordinal INTEGER NOT NULL,
          execution_id TEXT NOT NULL,
          asset_id TEXT NOT NULL,
          content_sha256 TEXT NOT NULL,
          poster_asset_id TEXT NOT NULL,
          poster_sha256 TEXT NOT NULL,
          PRIMARY KEY (manifest_path, asset_ordinal)
        ) WITHOUT ROWID
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS video_identities_content_sha256 "
        "ON video_identities(content_sha256)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS video_identities_poster_sha256 "
        "ON video_identities(poster_sha256)"
    )


def _read_manifest(path: Path, *, expected_sha256: str | None = None) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ObjectTransactionError(f"canonical post manifest is missing: {path}")
    if expected_sha256 is not None and _digest_file(path) != expected_sha256:
        raise ObjectTransactionError(
            f"canonical video index manifest digest drift: {path}"
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


def _insert_manifest(
    connection: sqlite3.Connection,
    *,
    manifest_path: str,
    manifest: Mapping[str, Any],
) -> None:
    for identity in _video_identities(manifest):
        connection.execute(
            "INSERT INTO video_identities(manifest_path, asset_ordinal, execution_id, "
            "asset_id, content_sha256, poster_asset_id, poster_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                manifest_path,
                identity["ordinal"],
                identity["executionId"],
                identity["assetId"],
                identity["contentSha256"],
                identity["posterAssetId"],
                identity["posterSha256"],
            ),
        )


def bootstrap_video_index(
    connection: sqlite3.Connection,
    *,
    publish_root: Path,
    inventory_digest: str,
    manifest_paths: Sequence[str] | None = None,
) -> None:
    """Create the exact video index from the canonical projection once."""
    tables = _video_tables(connection)
    if "video_index_state" in tables:
        if not _VIDEO_TABLES.issubset(tables):
            raise ObjectTransactionError("canonical video inventory structure drift")
        state = connection.execute(
            "SELECT schema, inventory_digest FROM video_index_state WHERE singleton = 1"
        ).fetchone()
        if (
            state is None
            or state[0] != VIDEO_INDEX_SCHEMA
            or state[1] != inventory_digest
        ):
            raise ObjectTransactionError("canonical video inventory state drift")
        return
    if tables & _VIDEO_TABLES:
        raise ObjectTransactionError("canonical video inventory structure drift")
    create_video_index_schema(connection)
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
                f"canonical video inventory entry is missing: {relative}"
            )
        manifest = _read_manifest(
            publish_root / relative,
            expected_sha256=str(entry[0]),
        )
        assert_video_manifest_unique(
            connection,
            manifest=manifest,
            excluded_manifest_path=relative,
        )
        _insert_manifest(connection, manifest_path=relative, manifest=manifest)
    connection.execute(
        "INSERT INTO video_index_state(singleton, schema, inventory_digest) "
        "VALUES (1, ?, ?)",
        (VIDEO_INDEX_SCHEMA, inventory_digest),
    )


def assert_video_index_ready(
    connection: sqlite3.Connection,
    *,
    inventory_digest: str,
) -> None:
    if not _VIDEO_TABLES.issubset(_video_tables(connection)):
        raise ObjectTransactionError("canonical video inventory structure drift")
    try:
        state = connection.execute(
            "SELECT schema, inventory_digest FROM video_index_state WHERE singleton = 1"
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise ObjectTransactionError("canonical video inventory is missing") from exc
    if (
        state is None
        or state[0] != VIDEO_INDEX_SCHEMA
        or state[1] != inventory_digest
    ):
        raise ObjectTransactionError("canonical video inventory state drift")


def sync_video_index_delta(
    connection: sqlite3.Connection,
    *,
    publish_root: Path,
    mutations: Sequence[Mapping[str, Any]],
    inventory_digest: str,
) -> None:
    """Apply video manifest identities in the inventory metadata transaction."""
    for mutation in mutations:
        relative = str(mutation.get("path") or "")
        if not relative.startswith("posts/") or not relative.endswith("/manifest.json"):
            continue
        connection.execute(
            "DELETE FROM video_identities WHERE manifest_path = ?", (relative,)
        )
        after = mutation.get("after")
        if isinstance(after, Mapping):
            manifest = _read_manifest(
                publish_root / relative,
                expected_sha256=str(after.get("sha256") or ""),
            )
            assert_video_manifest_unique(
                connection,
                manifest=manifest,
                excluded_manifest_path=relative,
            )
            _insert_manifest(connection, manifest_path=relative, manifest=manifest)
    updated = connection.execute(
        "UPDATE video_index_state SET inventory_digest = ? "
        "WHERE singleton = 1 AND schema = ?",
        (inventory_digest, VIDEO_INDEX_SCHEMA),
    )
    if updated.rowcount != 1:
        raise ObjectTransactionError("canonical video inventory state drift")


def assert_video_manifest_unique(
    connection: sqlite3.Connection,
    *,
    manifest: Mapping[str, Any],
    excluded_manifest_path: str,
) -> None:
    """Reject exact video or exact poster reuse outside the target object."""
    accepted_pending: list[dict[str, Any]] = []
    for identity in _video_identities(manifest):
        rows = connection.execute(
            "SELECT manifest_path, execution_id, asset_id, content_sha256, "
            "poster_asset_id, poster_sha256 FROM video_identities "
            "WHERE (content_sha256 = ? OR poster_sha256 = ?) AND manifest_path <> ?",
            (
                identity["contentSha256"],
                identity["posterSha256"],
                excluded_manifest_path,
            ),
        )
        peers = [
            {
                "manifestPath": row[0],
                "executionId": row[1],
                "assetId": row[2],
                "contentSha256": row[3],
                "posterAssetId": row[4],
                "posterSha256": row[5],
            }
            for row in rows
        ] + accepted_pending
        for peer in peers:
            peer_ref = str(peer.get("manifestPath") or "pending-post")
            peer_execution = str(peer.get("executionId") or "pending-execution")
            if identity["contentSha256"] == peer["contentSha256"]:
                raise ObjectTransactionError(
                    "canonical video identity duplicated by content sha256: "
                    f"{identity['assetId']} conflicts with "
                    f"{peer_execution}:{peer_ref}:{peer['assetId']}"
                )
            if identity["posterSha256"] == peer["posterSha256"]:
                raise ObjectTransactionError(
                    "canonical video identity duplicated by poster sha256: "
                    f"{identity['posterAssetId']} conflicts with "
                    f"{peer_execution}:{peer_ref}:{peer['posterAssetId']}"
                )
        accepted_pending.append({**identity, "manifestPath": "pending-post"})


@canonical_publish_serialized
def assert_canonical_video_unique(
    *,
    publish_root: Path,
    manifest: Mapping[str, Any],
    excluded_manifest_path: str,
) -> None:
    """Fail closed against exact canonical video and poster identities."""
    from content.release.canonical.canonical_inventory import (
        _connect,
        canonical_inventory_path,
        load_or_bootstrap_inventory,
    )

    inventory = load_or_bootstrap_inventory(publish_root)
    try:
        with _connect(canonical_inventory_path(publish_root)) as connection:
            assert_video_index_ready(
                connection,
                inventory_digest=str(inventory["inventoryDigest"]),
            )
            assert_video_manifest_unique(
                connection,
                manifest=manifest,
                excluded_manifest_path=excluded_manifest_path,
            )
    except (OSError, sqlite3.DatabaseError) as exc:
        raise ObjectTransactionError("canonical video inventory query failed") from exc


__all__ = [
    "VIDEO_INDEX_SCHEMA",
    "assert_canonical_video_unique",
    "assert_video_index_ready",
    "assert_video_manifest_unique",
    "bootstrap_video_index",
    "create_video_index_schema",
    "sync_video_index_delta",
]
