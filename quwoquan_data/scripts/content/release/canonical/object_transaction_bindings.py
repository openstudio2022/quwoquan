"""Pure binding checks shared by canonical object transaction validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def collect_object_keys(value: Any) -> set[str]:
    """Collect every canonical media object key from one JSON value."""

    result: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "objectKey" and isinstance(child, str) and child:
                result.add(child)
            result.update(collect_object_keys(child))
    elif isinstance(value, list):
        for child in value:
            result.update(collect_object_keys(child))
    return result


def verify_entity_manifest_asset_binding(
    manifest: Mapping[str, Any],
    rights: Mapping[str, Any],
) -> None:
    """Require the entity manifest to retain the rights-bound media identity."""

    manifest_assets = manifest.get("assets")
    if not isinstance(manifest_assets, list):
        raise TypeError("entity manifest.assets 必须为 list")
    by_asset_id: dict[str, Mapping[str, Any]] = {}
    for raw in manifest_assets:
        if not isinstance(raw, Mapping):
            raise TypeError("entity manifest.assets item 必须为 object")
        asset_id = str(raw.get("assetId") or "").strip()
        if not asset_id or asset_id in by_asset_id:
            raise ValueError("entity manifest assetId 为空或重复")
        by_asset_id[asset_id] = raw

    right_assets = rights.get("assets")
    if not isinstance(right_assets, list):
        raise TypeError("entity rights binding assets 必须为 list")
    by_right_asset_id = {
        str(raw.get("assetId") or "").strip(): raw
        for raw in right_assets
        if isinstance(raw, Mapping)
    }
    if (
        not by_right_asset_id
        or "" in by_right_asset_id
        or set(by_asset_id) != set(by_right_asset_id)
    ):
        raise ValueError("entity manifest 与 rights assetId 闭包不一致")
    for asset_id, manifest_asset in by_asset_id.items():
        rights_asset = by_right_asset_id[asset_id]
        if (
            str(manifest_asset.get("sha256") or "")
            != str(rights_asset.get("assetSha256") or "")
            or manifest_asset.get("bytes") != rights_asset.get("assetBytes")
        ):
            raise ValueError(f"entity manifest 与 rights digest/bytes 漂移：{asset_id}")


__all__ = ["collect_object_keys", "verify_entity_manifest_asset_binding"]
