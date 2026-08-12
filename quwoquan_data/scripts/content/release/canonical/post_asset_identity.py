"""Canonical identity binding for post media assets."""

from __future__ import annotations

from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
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


__all__ = ["freeze_canonical_video_poster_identities"]
