"""只投影消费者 manifest/profile 资产，不改写采用来源、审核或追加式 records。"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_PRIVATE_MEDIA_FIELDS = frozenset({"objectKey", "cdnUrl", "thumbnailUrl", "coverUrl", "videoUrl"})


def _authority(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = manifest.get("assets")
    if not isinstance(rows, list):
        raise ValueError("release media manifest assets must be an array")
    authority: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("release media manifest asset must be an object")
        asset_id = str(row.get("assetId") or "").strip()
        if not asset_id or asset_id in authority:
            raise ValueError("release MediaAsset identity invalid or duplicated")
        authority[asset_id] = row
    return authority


def _consumer_documents(objects_root: Path) -> list[Path]:
    paths: list[Path] = []
    for kind, name in (("entities", "manifest.json"), ("posts", "manifest.json"), ("creators", "profile.json")):
        for path in sorted((objects_root / kind).rglob(name)):
            relative = path.relative_to(objects_root)
            if any(part in {"sources", "records"} for part in relative.parts):
                continue
            if any(part.is_symlink() for part in (path, *path.parents)):
                raise ValueError(f"release consumer manifest symlink: {path}")
            paths.append(path)
    return paths


def _bind_asset(node: object, authority: Mapping[str, Mapping[str, Any]], owner: str) -> bool:
    if not isinstance(node, dict):
        raise ValueError("release consumer asset must be an object")
    asset_id = str(node.get("assetId") or "").strip()
    row = authority.get(asset_id)
    if row is None:
        raise ValueError(f"release object asset is absent from MediaAsset authority: {owner}:{asset_id}")
    if owner not in (row.get("ownerRefs") or []):
        raise ValueError(f"release object asset owner drift: {owner}:{asset_id}")
    for field in ("kind", "sha256"):
        if node.get(field) != row.get(field) or not node.get(field):
            raise ValueError(f"release object asset {field} drift: {owner}:{asset_id}")
    removed = _PRIVATE_MEDIA_FIELDS.intersection(node)
    for field in removed:
        del node[field]
    return bool(removed)


def bind_release_object_media_assets(*, objects_root: Path, manifest: Mapping[str, Any]) -> None:
    """发布 staging 内一次投影；先校验所有资产，不将证据文件作为可改写消费者。"""
    authority = _authority(manifest)
    pending: list[tuple[Path, dict[str, Any]]] = []
    for path in _consumer_documents(objects_root):
        document = json.loads(path.read_bytes())
        if not isinstance(document, dict) or not isinstance(document.get("assets"), list):
            raise ValueError(f"release consumer manifest assets missing: {path}")
        owner = path.parent.relative_to(objects_root).as_posix()
        changed = False
        for asset in document["assets"]:
            changed = _bind_asset(asset, authority, owner) or changed
        if changed:
            pending.append((path, document))
    for path, document in pending:
        path.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


__all__ = ["bind_release_object_media_assets"]
