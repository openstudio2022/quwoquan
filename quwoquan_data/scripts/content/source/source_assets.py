"""Read source-unit assets as typed candidate rows for content composition."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.io import read_json
from core.paths import relative_execution_ref
from content.source.source_unit import (
    SOURCE_UNIT_ASSET_INDEX,
    SOURCE_UNIT_MANIFEST,
    iter_source_units,
)


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def object_image_candidates(object_dir: Path, execution_id: str) -> list[dict[str, Any]]:
    """Return traceable image candidates from the object's accepted source units."""
    candidates: list[dict[str, Any]] = []
    for unit in iter_source_units(object_dir):
        meta_path = unit / SOURCE_UNIT_MANIFEST
        source_meta = read_json(meta_path) if meta_path.is_file() else {}
        index_path = unit / SOURCE_UNIT_ASSET_INDEX
        asset_index = read_json(index_path) if index_path.is_file() else {}
        by_file_name = {
            str(asset.get("fileName") or ""): asset
            for asset in asset_index.get("assets") or []
            if isinstance(asset, Mapping)
        }
        assets_dir = unit / "assets"
        if not assets_dir.is_dir():
            continue
        source_md = unit / "source.md"
        source_ref = relative_execution_ref(source_md, execution_id) if source_md.is_file() else ""
        for asset_path in sorted(assets_dir.iterdir()):
            if not asset_path.is_file() or asset_path.suffix.lower() not in _IMAGE_EXTS:
                continue
            asset_meta = by_file_name.get(asset_path.name, {})
            candidates.append(
                {
                    "path": asset_path,
                    "sourceRef": source_ref,
                    "sourceAssetId": asset_meta.get("sourceAssetId") or "",
                    "sourceAssetRef": relative_execution_ref(asset_path, execution_id),
                    "sha256": asset_meta.get("sha256") or "",
                    "caption": asset_meta.get("caption", ""),
                    "relevance": asset_meta.get("relevance", ""),
                    "sourceTitle": source_meta.get("title") or "",
                    "sourceKind": source_meta.get("sourceKind") or source_meta.get("category") or "",
                    "researchLane": source_meta.get("researchLane") or "",
                    "sourceCollectionId": asset_meta.get("sourceCollectionId") or "",
                    "creator": asset_meta.get("creator") or asset_meta.get("credit") or "",
                    "collectionPageUrl": asset_meta.get("collectionPageUrl") or asset_meta.get("sourceUrl") or "",
                    "license": asset_meta.get("license") or "",
                    "termsUrl": asset_meta.get("termsUrl") or "",
                    "licenseSnapshot": asset_meta.get("licenseSnapshot") or "",
                    "authorizationProof": asset_meta.get("authorizationProof") or "",
                    "usageScope": asset_meta.get("usageScope") or "",
                    "modelReleaseStatus": asset_meta.get("modelReleaseStatus") or "",
                    "rightsAuditStatus": asset_meta.get("rightsAuditStatus") or "",
                    "rightsAuditIssues": list(asset_meta.get("rightsAuditIssues") or []),
                }
            )
    return candidates
