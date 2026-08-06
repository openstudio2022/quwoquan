"""Object-local media closure and source-funnel readback for homepages."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.io import read_json, write_json
from core.paths import execution_root

HOMEPAGE_SOURCE_ASSET_RECEIPT_REF = "evidence/source_asset_receipt.json"
_RIGHTS_STATUSES = ("verified", "unverified", "restricted", "unknown")


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _source_unit_path(execution_id: str, source_ref: str) -> Path:
    ref = Path(str(source_ref or "").strip())
    if not str(ref) or ref.is_absolute() or ref.name != "source.md":
        raise ValueError(f"homepage sourceRef must be a relative source.md ref: {source_ref!r}")
    root = execution_root(execution_id).resolve()
    path = (root / ref).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError(f"homepage sourceRef is not readable: {source_ref}")
    return path.parent


def homepage_source_asset_counts(execution_id: str, source_ref: str) -> dict[str, Any]:
    """Re-derive the download CLI funnel from one immutable source unit."""
    unit = _source_unit_path(execution_id, source_ref)
    meta = read_json(unit / "meta.json")
    index = read_json(unit / "assets" / "index.json")
    if not isinstance(meta, Mapping) or not isinstance(index, Mapping):
        raise TypeError(f"homepage source unit metadata is invalid: {unit}")
    assets = [row for row in (index.get("assets") or []) if isinstance(row, Mapping)]
    funnel = meta.get("assetFunnel") if isinstance(meta.get("assetFunnel"), Mapping) else {}
    accepted = _nonnegative_int(meta.get("assetCount")) or len(assets)
    discovered = max(_nonnegative_int(funnel.get("candidateCount")), accepted)
    planned = discovered
    fetch_failures = funnel.get("fetchFailures") if isinstance(funnel.get("fetchFailures"), list) else []
    downloaded = max(accepted, discovered - len(fetch_failures))
    rights = Counter(
        str(row.get("rightsAuditStatus") or "unknown")
        if str(row.get("rightsAuditStatus") or "unknown") in _RIGHTS_STATUSES
        else "unknown"
        for row in assets
    )
    return {
        "sourceUnitRef": str(Path(source_ref).parent).replace("\\", "/"),
        "sourceRef": str(source_ref).replace("\\", "/"),
        "displayName": str(meta.get("title") or meta.get("entityName") or unit.name),
        "provider": str(meta.get("platform") or meta.get("sourceKind") or "unknown"),
        "plannedAssetCount": planned,
        "discoveredAssetCount": discovered,
        "downloadedAssetCount": downloaded,
        "acceptedAssetCount": accepted,
        "rejectedAssetCount": max(0, discovered - accepted),
        **{
            f"{status}AssetCount": rights[status]
            for status in _RIGHTS_STATUSES
        },
    }


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_homepage_source_asset_receipt(
    execution_id: str,
    *,
    object_ref: str,
    source_ref: str,
    assets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    source_counts = homepage_source_asset_counts(execution_id, source_ref)
    asset_rows = [row for row in assets if isinstance(row, Mapping)]
    cover_ids = [
        str(row.get("assetId") or "").strip()
        for row in asset_rows
        if str(row.get("role") or "") == "cover" and str(row.get("assetId") or "").strip()
    ]
    media_ids = [
        str(row.get("assetId") or "").strip()
        for row in asset_rows
        if str(row.get("assetId") or "").strip()
    ]
    stable = {
        "schema": "quwoquan_data.homepage_source_asset_receipt",
        "executionId": execution_id,
        "objectRef": object_ref,
        "assetCount": len(media_ids),
        "heroAssetId": cover_ids[0] if len(cover_ids) == 1 else "",
        "mediaAssetIds": media_ids,
        "usagePositions": [
            {
                "assetId": str(row.get("assetId") or ""),
                "position": str(row.get("role") or "related"),
            }
            for row in asset_rows
            if str(row.get("assetId") or "").strip()
        ],
        "sourceAssetCounts": [source_counts],
    }
    return {**stable, "receiptDigest": _digest(stable)}


def write_homepage_source_asset_receipt(
    execution_id: str,
    *,
    entity_dir: Path,
    object_ref: str,
    source_ref: str,
    assets: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], str]:
    receipt = build_homepage_source_asset_receipt(
        execution_id,
        object_ref=object_ref,
        source_ref=source_ref,
        assets=assets,
    )
    path = entity_dir / HOMEPAGE_SOURCE_ASSET_RECEIPT_REF
    write_json(path, receipt)
    for row in receipt["sourceAssetCounts"]:
        print(
            "[homepage] Source assets: "
            f"displayName={row['displayName']} provider={row['provider']} "
            f"assets={row['acceptedAssetCount']} planned={row['plannedAssetCount']} "
            f"discovered={row['discoveredAssetCount']} downloaded={row['downloadedAssetCount']} "
            f"accepted={row['acceptedAssetCount']} rejected={row['rejectedAssetCount']} "
            f"verified={row['verifiedAssetCount']} unverified={row['unverifiedAssetCount']} "
            f"restricted={row['restrictedAssetCount']} unknown={row['unknownAssetCount']}",
            flush=True,
        )
    return receipt, HOMEPAGE_SOURCE_ASSET_RECEIPT_REF


def homepage_manifest_media_issues(
    entity_dir: Path,
    manifest: Mapping[str, Any],
    entity_payload: Mapping[str, Any],
    label: str,
) -> list[str]:
    """Require exact hero/media/source-funnel closure for an accepted homepage."""
    issues: list[str] = []
    assets = [row for row in (manifest.get("assets") or []) if isinstance(row, Mapping)]
    asset_ids = [str(row.get("assetId") or "").strip() for row in assets]
    asset_ids = [value for value in asset_ids if value]
    covers = [
        str(row.get("assetId") or "").strip()
        for row in assets
        if str(row.get("role") or "") == "cover"
    ]
    if not assets:
        issues.append(f"{label}: accepted homepage manifest.assets must not be empty")
    if len(covers) != 1 or not covers[0]:
        issues.append(f"{label}: accepted homepage requires exactly one hero cover asset")
    if str(manifest.get("heroAssetId") or "") != (covers[0] if len(covers) == 1 else ""):
        issues.append(f"{label}: manifest.heroAssetId drift from role=cover asset")
    if list(manifest.get("mediaAssetIds") or []) != asset_ids:
        issues.append(f"{label}: manifest.mediaAssetIds drift from manifest.assets")
    image_refs = [str(value).strip() for value in entity_payload.get("imageSourceRefs") or [] if str(value).strip()]
    if not image_refs:
        issues.append(f"{label}: accepted homepage _entity.imageSourceRefs must not be empty")
    receipt_ref = str(manifest.get("sourceAssetReceiptRef") or "")
    receipt_path = entity_dir / receipt_ref
    if receipt_ref != HOMEPAGE_SOURCE_ASSET_RECEIPT_REF or not receipt_path.is_file():
        issues.append(f"{label}: homepage source asset receipt is missing")
        return issues
    try:
        receipt = read_json(receipt_path)
    except (OSError, ValueError, TypeError) as exc:
        issues.append(f"{label}: homepage source asset receipt is unreadable: {exc}")
        return issues
    stable = {key: value for key, value in receipt.items() if key != "receiptDigest"}
    if receipt.get("receiptDigest") != _digest(stable):
        issues.append(f"{label}: homepage source asset receipt digest mismatch")
    if manifest.get("sourceAssetReceiptDigest") != receipt.get("receiptDigest"):
        issues.append(f"{label}: homepage sourceAssetReceiptDigest drift")
    if receipt.get("heroAssetId") != manifest.get("heroAssetId"):
        issues.append(f"{label}: homepage receipt heroAssetId drift")
    if receipt.get("mediaAssetIds") != manifest.get("mediaAssetIds"):
        issues.append(f"{label}: homepage receipt mediaAssetIds drift")
    if receipt.get("sourceAssetCounts") != manifest.get("sourceAssetCounts"):
        issues.append(f"{label}: homepage sourceAssetCounts drift between receipt and manifest")
    if receipt.get("assetCount") != len(asset_ids):
        issues.append(f"{label}: homepage receipt assetCount drift")
    return issues


__all__ = [
    "HOMEPAGE_SOURCE_ASSET_RECEIPT_REF",
    "build_homepage_source_asset_receipt",
    "homepage_manifest_media_issues",
    "homepage_source_asset_counts",
    "write_homepage_source_asset_receipt",
]
