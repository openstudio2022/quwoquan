"""Post transaction source-asset lookup helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_rel,
)


def source_assets(execution_root: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for index_path in sorted(execution_root.rglob("assets/index.json")):
        relative_index = index_path.relative_to(execution_root)
        if "sources" not in relative_index.parts:
            continue
        for raw in _read_json(index_path).get("assets") or []:
            if not isinstance(raw, dict):
                continue
            file_name = str(raw.get("fileName") or "").strip()
            if file_name:
                source_path = index_path.parent / _safe_rel(
                    file_name,
                    label=f"{relative_index}.assets.fileName",
                )
                source_ref = source_path.relative_to(execution_root).as_posix()
                if source_ref in rows:
                    raise ObjectTransactionError(f"sourceAssetRef 重复：{source_ref}")
                rows[source_ref] = raw
    return rows


def asset_sources(
    raw: Mapping[str, Any],
    source_assets_by_ref: Mapping[str, dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    refs = [str(raw.get("sourceAssetRef") or "").strip()]
    refs.extend(str(item).strip() for item in raw.get("sourceAssetRefs") or [])
    refs = [ref for ref in refs if ref]
    if not refs:
        raise ObjectTransactionError("post asset 缺 sourceAssetRef 或 sourceAssetRefs")
    missing = [ref for ref in refs if ref not in source_assets_by_ref]
    if missing:
        raise ObjectTransactionError(
            "post asset sourceAssetRef 未指向来源资产：" + ", ".join(missing)
        )
    return tuple(source_assets_by_ref[ref] for ref in refs)


__all__ = ["asset_sources", "source_assets"]
