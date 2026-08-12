"""Entity transaction source-asset lookup helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_rel,
)


def safe_asset_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ObjectTransactionError("manifest asset 缺 assetId")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def source_assets_by_ref(execution_root: Path) -> dict[str, dict[str, Any]]:
    """Index source metadata by its execution-unique asset reference.

    ``sourceAssetId`` is only unique inside one source unit (for example every
    source starts at ``001_001``). Promotion therefore resolves metadata through
    the already persisted ``sourceAssetRef`` path.
    """

    rows: dict[str, dict[str, Any]] = {}
    for index_path in sorted((execution_root / "sources").glob("*/assets/index.json")):
        for row in _read_json(index_path).get("assets") or []:
            if not isinstance(row, dict):
                continue
            file_name = str(row.get("fileName") or "").strip()
            if not file_name:
                raise ObjectTransactionError(f"{index_path}: source asset 缺 fileName")
            asset_path = index_path.parent / _safe_rel(
                file_name,
                label=f"{index_path}.assets.fileName",
            )
            asset_ref = asset_path.relative_to(execution_root).as_posix()
            if asset_ref in rows:
                raise ObjectTransactionError(f"sourceAssetRef 重复：{asset_ref}")
            rows[asset_ref] = row
    return rows


def source_asset_for_manifest_asset(
    raw: Mapping[str, Any],
    source_assets: Mapping[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    source_asset_ref = str(raw.get("sourceAssetRef") or "").strip()
    if not source_asset_ref:
        raise ObjectTransactionError("manifest asset 缺 sourceAssetRef")
    source_asset = source_assets.get(source_asset_ref)
    if source_asset is None:
        raise ObjectTransactionError(
            f"manifest asset 的 sourceAssetRef 未指向来源资产：{source_asset_ref}"
        )
    declared_id = str(raw.get("sourceAssetId") or "").strip()
    actual_id = str(source_asset.get("sourceAssetId") or "").strip()
    if declared_id and declared_id != actual_id:
        raise ObjectTransactionError(
            "manifest asset sourceAssetId 与 sourceAssetRef 目标不一致："
            f"{declared_id}!={actual_id}"
        )
    return source_asset_ref, source_asset


__all__ = ["safe_asset_id", "source_asset_for_manifest_asset", "source_assets_by_ref"]
