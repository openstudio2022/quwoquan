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
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
    object_lineage,
)
from core.image_deduplication import perceptual_hash, perceptual_hash_distance
from core.content_library import resolve_media_holding
NEAR_DUP_HAMMING = 5

IMAGE_INDEX_SCHEMA = "quwoquan_data.canonical_image_inventory.v2"
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


def _source_url(value: Any) -> str:
    text = str(value or "").strip()
    parts = urlsplit(text)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), unquote(parts.path), parts.query, ""))


def _source_binding(asset: Mapping[str, Any]) -> tuple[str, str]:
    page = _source_url(asset.get("collectionPageUrl") or asset.get("sourceUrl"))
    binding = json.dumps(
        {"page": page, "sourceUrl": _source_url(asset.get("sourceUrl")),
         "originalAssetUrl": _source_url(asset.get("originalAssetUrl") or asset.get("directUrl"))},
        sort_keys=True,
    ) if page else ""
    return page, binding


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
        # 主页历史投影未持有 pHash；只读同一 CAS 的 exact bytes，复用既有算法。
        if not perceptual and not image_post and manifest.get("entityId"):
            holding = resolve_media_holding(str(raw.get("sha256") or ""))
            if _digest_file(holding) != raw.get("sha256"):
                raise ObjectTransactionError("DATA.POOL.IMAGE_BINDING_DRIFT: content library digest drift")
            perceptual = perceptual_hash(holding)
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
        source_page, source_binding = _source_binding(raw)
        identities.append(
            {
                "sourcePage": source_page,
                "sourceBinding": source_binding,
                "imagePost": image_post,
                "contentId": str(manifest.get("contentId") or manifest.get("entityId") or ""),
                "version": manifest.get("version") if type(manifest.get("version")) is int else 0,
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
          source_page TEXT NOT NULL,
          source_binding TEXT NOT NULL,
          image_post INTEGER NOT NULL,
          content_id TEXT NOT NULL,
          content_version INTEGER NOT NULL,
          PRIMARY KEY (manifest_path, asset_ordinal)
        ) WITHOUT ROWID
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS image_identities_sha256 "
        "ON image_identities(asset_sha256)"
    )
    for column in ("asset_id", "source_page"):
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS image_identities_{column} ON image_identities({column})"
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
            "asset_sha256, perceptual_hash, source_page, source_binding, image_post, "
            "content_id, content_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                manifest_path, ordinal, identity["assetId"], identity["sha256"],
                identity["perceptualHash"], identity["sourcePage"], identity["sourceBinding"],
                int(identity["imagePost"]), identity["contentId"], identity["version"],
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
    paths = tuple(sorted(set(paths) | {
        str(row[0]) for row in connection.execute(
            "SELECT path FROM entries WHERE path LIKE 'entities/%/manifest.json'"
        )
    }))
    for relative in paths:
        if not _indexed_manifest(relative):
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
        if not _indexed_manifest(relative):
            continue
        after = mutation.get("after")
        manifest = None
        if isinstance(after, Mapping):
            manifest = _read_manifest(
                publish_root / relative,
                expected_sha256=str(after.get("sha256") or ""),
            )
            # 删除旧行前校验，保留同路径旧绑定，不能让 replace 绕过 drift。
            assert_image_manifest_unique(connection, manifest=manifest, excluded_manifest_path=relative)
        connection.execute(
            "DELETE FROM image_perceptual_bands WHERE manifest_path = ?", (relative,)
        )
        connection.execute(
            "DELETE FROM image_identities WHERE manifest_path = ?", (relative,)
        )
        if manifest is not None:
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


def _indexed_manifest(path: str) -> bool:
    return path.startswith(("posts/", "entities/")) and path.endswith("/manifest.json") and "/_pool/" not in path


def _peers(connection: sqlite3.Connection, identity: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: dict[tuple[str, int], Any] = {}
    for column, value in (("asset_id", identity["assetId"]), ("asset_sha256", identity["sha256"]), ("source_page", identity["sourcePage"])):
        if value:
            for row in connection.execute(f"SELECT * FROM image_identities WHERE {column} = ?", (value,)):
                rows[(str(row[0]), int(row[1]))] = row
    for width, band, value in _bands(str(identity["perceptualHash"])):
        for row in connection.execute(
            "SELECT i.* FROM image_perceptual_bands b JOIN image_identities i "
            "ON i.manifest_path=b.manifest_path AND i.asset_ordinal=b.asset_ordinal "
            "WHERE b.hash_width=? AND b.band=? AND b.band_value=?", (width, band, value),
        ):
            rows[(str(row[0]), int(row[1]))] = row
    return [dict(zip(
        ("manifestPath", "ordinal", "assetId", "sha256", "perceptualHash", "sourcePage", "sourceBinding", "imagePost", "contentId", "version"), row,
    )) for _, row in sorted(rows.items())]


def _conflict(identity: Mapping[str, Any], peer: Mapping[str, Any], *, path: str) -> str | None:
    same_id = identity["assetId"] == peer["assetId"]
    same_bytes = bool(identity["sha256"]) and identity["sha256"] == peer["sha256"]
    same_source = bool(identity["sourceBinding"]) and identity["sourceBinding"] == peer["sourceBinding"]
    if same_id and (not same_bytes or not same_source):
        return "DATA.POOL.IMAGE_BINDING_DRIFT: canonical image assetId bytes/source binding drift"
    pending = peer.get("pending", False)
    same_logical = bool(identity["contentId"]) and identity["contentId"] == peer["contentId"]
    same_path = path == peer["manifestPath"] and not pending and same_logical
    same_version_lineage = (
        not pending and same_logical
        and identity["version"] > 0 and peer["version"] > 0
        and identity["version"] != peer["version"]
    )
    if same_id and (same_path or same_version_lineage):
        return None
    # 封面/正文/主页共享稳定资产不是第二作品；image Post 内重复仍拒绝。
    if same_id and same_bytes and same_source and not (identity["imagePost"] and peer["imagePost"]):
        return None
    if same_bytes:
        return "DATA.POOL.IMAGE_SHA256_DUPLICATE: canonical image identity duplicated by sha256"
    if perceptual_hash_distance(str(identity["perceptualHash"]), str(peer["perceptualHash"])) <= NEAR_DUP_HAMMING:
        return "DATA.POOL.IMAGE_PERCEPTUAL_DUPLICATE: canonical image identity duplicated by perceptualHash"
    if identity["imagePost"] and peer["imagePost"] and identity["sourcePage"] and identity["sourcePage"] == peer["sourcePage"]:
        # 同一多图作品中不同资产保留；跨 Post 的作品页占用不能被换字节绕过。
        if not pending and not same_path and not same_version_lineage:
            return "DATA.POOL.IMAGE_SOURCE_WORK_DUPLICATE: canonical image source work duplicated"
    return None


def image_manifest_conflicts(
    connection: sqlite3.Connection, *, manifest: Mapping[str, Any], excluded_manifest_path: str,
    candidate_peers: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """返回与 publish 相同的精确冲突事实，不选择或批准候选。"""
    conflicts: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    declared = [
        {**identity, "manifestPath": str(candidate["objectRef"]) + "/manifest.json"}
        for candidate in candidate_peers for identity in _image_identities(candidate["manifest"])
    ]
    for identity in _image_identities(manifest):
        for peer in _peers(connection, identity) + declared + pending:
            error = _conflict(identity, peer, path=excluded_manifest_path)
            if error:
                code, detail = error.split(":", 1)
                conflicts.append({"code": code, "detail": detail.strip(), "assetId": identity["assetId"], "peerAssetId": peer["assetId"], "objectRef": excluded_manifest_path.removesuffix("/manifest.json"), "dependencyRefs": [str(peer["manifestPath"]).removesuffix("/manifest.json")]})
        pending.append({**identity, "manifestPath": excluded_manifest_path, "pending": True})
    return conflicts


def assert_image_manifest_unique(connection: sqlite3.Connection, *, manifest: Mapping[str, Any], excluded_manifest_path: str) -> None:
    conflicts = image_manifest_conflicts(connection, manifest=manifest, excluded_manifest_path=excluded_manifest_path)
    if conflicts:
        first = conflicts[0]
        raise ObjectTransactionError(f"{first['code']}: {first['detail']}: {first['assetId']} conflicts with {first['dependencyRefs'][0]}:{first['peerAssetId']}")


@contextmanager
def readonly_image_inventory(publish_root: Path):
    """热读使用只读 SQLite；冷读只构造一次内存索引，不写 sidecar/池。"""
    from content.release.canonical.canonical_inventory import canonical_inventory_path, _metadata_document
    path = canonical_inventory_path(publish_root)
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) if path.is_file() else sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        if path.is_file():
            document = _metadata_document(connection, publish_root=publish_root)
            assert_image_index_ready(connection, inventory_digest=str(document["inventoryDigest"]))
        else:
            create_image_index_schema(connection)
            for prefix in ("posts", "entities"):
                for manifest_path in sorted((publish_root / prefix).rglob("manifest.json")):
                    relative = manifest_path.relative_to(publish_root).as_posix()
                    if _indexed_manifest(relative):
                        _insert_manifest(connection, manifest_path=relative, manifest=_read_manifest(manifest_path))
        yield connection
    except sqlite3.DatabaseError as exc:
        raise ObjectTransactionError("DATA.POOL.IMAGE_INVENTORY_INVALID: canonical image inventory query failed") from exc
    finally:
        connection.close()


__all__ = [
    "IMAGE_INDEX_SCHEMA",
    "assert_image_index_ready",
    "assert_image_manifest_unique",
    "bootstrap_image_index",
    "create_image_index_schema",
    "image_manifest_conflicts",
    "readonly_image_inventory",
    "sync_image_index_delta",
]
