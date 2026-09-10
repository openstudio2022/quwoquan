"""Canonical identity binding for post media assets."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _safe_rel,
)


def freeze_canonical_video_poster_identities(
    assets: list[dict[str, Any]],
) -> None:
    """Bind each canonical video to the exact poster asset in its package."""

    by_id: dict[str, dict[str, Any]] = {}
    for asset in assets:
        asset_id = str(asset.get("assetId") or "").strip()
        if not asset_id or asset_id in by_id:
            raise ObjectTransactionError(
                f"post canonical assetId is missing or duplicated: {asset_id!r}"
            )
        by_id[asset_id] = asset
    for asset in assets:
        kind = str(asset.get("kind") or "").strip()
        mime = str(asset.get("mimeType") or "").strip().lower()
        if kind != "video" and not mime.startswith("video/"):
            continue
        asset_id = str(asset["assetId"])
        poster_asset_id = str(asset.get("posterAssetId") or "").strip()
        poster = by_id.get(poster_asset_id)
        if poster is None or str(poster.get("kind") or "").strip() != "image":
            raise ObjectTransactionError(
                f"post canonical video 缺 exact poster asset binding：{asset_id}"
            )
        poster_file_name = str(poster.get("fileName") or "").strip()
        poster_sha256 = str(poster.get("sha256") or "").strip().lower()
        if not poster_file_name or not poster_sha256:
            raise ObjectTransactionError(
                f"post canonical video poster identity 不完整：{asset_id}"
            )
        claimed_file_name = str(asset.get("posterFileName") or "").strip()
        claimed_sha256 = str(asset.get("posterSha256") or "").strip().lower()
        if claimed_file_name and claimed_file_name != poster_file_name:
            raise ObjectTransactionError(
                f"post canonical video posterFileName drift：{asset_id}"
            )
        if claimed_sha256 and claimed_sha256 != poster_sha256:
            raise ObjectTransactionError(
                f"post canonical video posterSha256 drift：{asset_id}"
            )
        asset["posterFileName"] = poster_file_name
        asset["posterSha256"] = poster_sha256


def project_canonical_post_asset_paths(
    assets: list[dict[str, Any]], *, destination_paths: Mapping[str, str],
) -> list[dict[str, Any]]:
    """先按原路径验证封面绑定，再只在包投影中按稳定资产身份重命名。"""
    projected = deepcopy(assets)
    # 原声明必须先与原封面身份吻合，不能删除旧 claim 后用新路径掩盖漂移。
    freeze_canonical_video_poster_identities(projected)
    asset_ids = {str(asset["assetId"]).strip() for asset in projected}
    if set(destination_paths) != asset_ids:
        raise ObjectTransactionError("post canonical asset destination mapping identity 不完整")
    destinations = {
        asset_id: _safe_rel(path, label="canonical asset destination").as_posix()
        for asset_id, path in destination_paths.items()
    }
    if len(set(destinations.values())) != len(destinations):
        raise ObjectTransactionError("post canonical asset destination mapping 路径重复")
    for asset in projected:
        destination = destinations[str(asset["assetId"]).strip()]
        asset.update(path=destination, fileName=destination)
        kind = str(asset.get("kind") or "").strip()
        mime = str(asset.get("mimeType") or "").strip().lower()
        if kind == "video" or mime.startswith("video/"):
            poster_id = str(asset["posterAssetId"]).strip()
            asset["posterFileName"] = destinations[poster_id]
    freeze_canonical_video_poster_identities(projected)
    return projected


__all__ = ["freeze_canonical_video_poster_identities", "project_canonical_post_asset_paths"]
