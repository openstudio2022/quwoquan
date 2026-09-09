"""Post transaction source-asset lookup helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
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


def source_binding_refs(raw: Mapping[str, Any]) -> list[str]:
    """按声明顺序归一来源引用；唯一 manifest 不保留单数别名。"""
    refs = [*(str(ref or "").strip() for ref in raw.get("sourceAssetRefs") or []),
            str(raw.get("sourceAssetRef") or "").strip()]
    return list(dict.fromkeys(ref for ref in refs if ref))


def canonical_post_asset_row(
    raw: Mapping[str, Any], *, asset_source: Path, mime_type: str, object_key: str,
    source_assets_by_ref: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """普通发布和只读迁移复演共用资产身份、取得及派生绑定，不写 holder。"""
    from content.release.canonical.image_identity import canonical_asset_manifest_row
    refs = source_binding_refs(raw)
    sources = asset_sources({"sourceAssetRefs": refs}, source_assets_by_ref)
    row = canonical_asset_manifest_row(
        {key: value for key, value in raw.items() if key != "sourceAssetRef"},
        asset_source=asset_source, mime_type=mime_type, object_key=object_key,
    )
    row.update(sha256=_digest_file(asset_source), bytes=asset_source.stat().st_size)
    receipt_refs = [str(source.get("acquisitionReceiptRef") or "").strip() for source in sources]
    if any(not ref for ref in receipt_refs):
        raise ObjectTransactionError(f"post asset source lacks acquisitionReceiptRef：{row['assetId']}")
    row.update(sourceAssetRefs=refs, acquisitionReceiptRefs=list(dict.fromkeys(receipt_refs)))
    binding = _derivative_binding(sources, row, asset_source)
    # 派生绑定唯一来自已取得来源，不能保留 raw 中未被来源证明的值。
    row.pop("derivativeBinding", None)
    if binding is not None:
        row["derivativeBinding"] = binding
    return row


def _derivative_binding(sources, row, asset_source):
    bindings = {json.dumps(source["derivativeBinding"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                for source in sources if isinstance(source.get("derivativeBinding"), Mapping)}
    if len(bindings) > 1:
        raise ObjectTransactionError(f"post asset source derivativeBinding 不唯一：{row['assetId']}")
    if not bindings:
        return None
    binding = json.loads(next(iter(bindings)))
    expected = {"derivedSha256": row["sha256"], "derivedBytes": row["bytes"],
                "derivedMimeType": row["mimeType"], "derivedExtension": asset_source.suffix.lower()}
    if any(binding.get(key) != value for key, value in expected.items()):
        raise ObjectTransactionError(f"post asset source derivativeBinding 与发布字节不一致：{row['assetId']}")
    return binding


__all__ = ["asset_sources", "source_assets", "source_binding_refs", "canonical_post_asset_row"]
