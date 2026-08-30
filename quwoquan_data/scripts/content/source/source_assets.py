"""Read source-unit assets as typed candidate rows for content composition."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import relative_execution_ref

from content.source.rights_decision_projection import projected_distribution_decision
from content.source.source_unit import (
    SOURCE_UNIT_ASSET_INDEX,
    SOURCE_UNIT_MANIFEST,
    iter_source_units,
)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def object_image_candidates(object_dir: Path, execution_id: str) -> list[dict[str, Any]]:
    """Return traceable image rows from the source-unit asset index.

    ``assets/index.json`` is the enumeration truth.  A later governed review
    may move a rejected byte into an object-local evidence subdirectory, but
    that must not make the indexed asset disappear from disposition closure.
    Publish admission still requires the indexed top-level byte to exist.
    """
    candidates: list[dict[str, Any]] = []
    for unit in iter_source_units(object_dir):
        meta_path = unit / SOURCE_UNIT_MANIFEST
        source_meta = read_json(meta_path) if meta_path.is_file() else {}
        index_path = unit / SOURCE_UNIT_ASSET_INDEX
        asset_index = read_json(index_path) if index_path.is_file() else {}
        indexed_assets = [
            asset
            for asset in asset_index.get("assets") or []
            if isinstance(asset, Mapping)
        ]
        assets_dir = unit / "assets"
        if not assets_dir.is_dir():
            continue
        source_md = unit / "source.md"
        source_ref = relative_execution_ref(source_md, execution_id) if source_md.is_file() else ""
        for asset_meta in indexed_assets:
            file_name = str(asset_meta.get("fileName") or "").strip()
            relative = Path(file_name)
            if (
                not file_name
                or relative.name != file_name
                or relative.suffix.lower() not in _IMAGE_EXTS
            ):
                continue
            asset_path = assets_dir / file_name
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
                    # 出处事实的显式声明位随行传递，供准入侧做出处类别裁决。
                    # 这三个键不与 ``creator`` 归并：归并后「上传者与权利人是否
                    # 同一主体」就没有两个可比较的载体了。
                    "credit": asset_meta.get("credit") or "",
                    "uploader": asset_meta.get("uploader") or "",
                    "description": asset_meta.get("description") or "",
                    "collectionPageUrl": asset_meta.get("collectionPageUrl") or asset_meta.get("sourceUrl") or "",
                    "license": asset_meta.get("license") or "",
                    "termsUrl": asset_meta.get("termsUrl") or "",
                    "licenseSnapshot": asset_meta.get("licenseSnapshot") or "",
                    "authorizationProof": asset_meta.get("authorizationProof") or "",
                    "usageScope": asset_meta.get("usageScope") or "",
                    "modelReleaseStatus": asset_meta.get("modelReleaseStatus") or "",
                    "acquisitionStatus": asset_meta.get("acquisitionStatus") or "",
                    "rightsStatus": asset_meta.get("rightsStatus") or "",
                    "authorizationRequired": asset_meta.get("authorizationRequired"),
                    **projected_distribution_decision(asset_meta),
                    "rightsIssues": list(asset_meta.get("rightsIssues") or []),
                    "rightsAuditStatus": asset_meta.get("rightsAuditStatus") or "",
                    "rightsAuditIssues": list(asset_meta.get("rightsAuditIssues") or []),
                    "sourceUrl": asset_meta.get("sourceUrl") or "",
                    "isRepresentativeVisual": asset_meta.get("isRepresentativeVisual"),
                    "visualSubject": asset_meta.get("visualSubject") or "",
                    "visualSubjectEvidence": list(
                        asset_meta.get("visualSubjectEvidence") or []
                    ),
                }
            )
    return candidates
