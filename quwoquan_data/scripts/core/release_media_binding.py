"""Bind immutable release object media refs to the public MediaAsset authority."""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_PRIVATE_MEDIA_FIELDS = {
    "objectKey",
    "cdnUrl",
    "thumbnailUrl",
    "coverUrl",
    "videoUrl",
}


def bind_release_object_media_assets(
    *,
    objects_root: Path,
    manifest: Mapping[str, Any],
) -> None:
    """Remove private CAS details and inject canonical identity bindings."""

    rows = manifest.get("assets")
    if not isinstance(rows, list):
        raise ValueError("release media manifest assets must be an array")
    authority: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"release media manifest assets[{index}] must be an object")
        asset_id = str(row.get("assetId") or "").strip()
        if not asset_id or asset_id in authority:
            raise ValueError(f"release MediaAsset identity invalid or duplicated: {asset_id}")
        authority[asset_id] = row

    def bind(node: Any, *, source: Path) -> bool:
        if isinstance(node, list):
            changed = False
            for item in node:
                changed = bind(item, source=source) or changed
            return changed
        if not isinstance(node, dict):
            return False
        changed = False
        asset_id = str(node.get("assetId") or "").strip()
        if asset_id:
            row = authority.get(asset_id)
            if row is None:
                raise ValueError(
                    "release object asset is absent from MediaAsset authority: "
                    f"{source}:{asset_id}"
                )
            kind = str(row.get("kind") or "").strip()
            sha256 = str(row.get("sha256") or "").strip()
            declared_kind = str(node.get("kind") or "").strip()
            declared_sha256 = str(node.get("sha256") or "").strip()
            if declared_kind and declared_kind != kind:
                raise ValueError(f"release object asset kind drift: {source}:{asset_id}")
            if declared_sha256 and declared_sha256 != sha256:
                raise ValueError(f"release object asset sha256 drift: {source}:{asset_id}")
            if node.get("kind") != kind:
                node["kind"] = kind
                changed = True
            if node.get("sha256") != sha256:
                node["sha256"] = sha256
                changed = True
            for field in _PRIVATE_MEDIA_FIELDS:
                if field in node:
                    node.pop(field)
                    changed = True
        for value in node.values():
            changed = bind(value, source=source) or changed
        return changed

    # Release objects are consumer payloads, not a copy of canonical private
    # storage metadata. Sanitize governed consumer JSON so asset.refs and rights
    # snapshots cannot retain CAS keys after manifests have been rebound.
    # Independently signed/reviewed receipts are immutable evidence, however:
    # rewriting their assetSnapshot would invalidate both their schema and
    # receiptDigest before release admission can revalidate them.
    paths = sorted(objects_root.rglob("*.json"))
    for path in paths:
        relative = path.relative_to(objects_root)
        if "asset_reviews" in relative.parts:
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        if not bind(document, source=path):
            continue
        path.write_text(
            json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )


__all__ = ["bind_release_object_media_assets"]
