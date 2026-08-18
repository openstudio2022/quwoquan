"""Validate one historical receipt/CAS binding used by current video acquisition."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json

from content.source.professional_video_rebind_historical import (
    HISTORICAL_PROVENANCE_FIELDS,
    validate_historical_video_receipt,
    validate_historical_video_receipt_path,
)
from content.source.professional_video_receipt import (
    ACCEPTED_DECISIONS,
    canonical_child,
    file_digest,
)

_PROVENANCE_FIELDS = HISTORICAL_PROVENANCE_FIELDS


def resolve_frozen_video_asset(
    item: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any],
    output_root: Path,
    receipt_cache: dict[str, tuple[dict[str, Any], str]],
) -> Path | None:
    """Return exact CAS bytes after receipt, provenance and identity verification."""
    frozen = item.get("frozenAsset")
    if frozen is None:
        return None
    if not isinstance(frozen, Mapping):
        raise TypeError(f"{item.get('assetId')}: frozenAsset must be an object")
    physical = manifest.get("frozenPhysicalInput")
    if not isinstance(physical, Mapping):
        raise TypeError(
            f"{item.get('assetId')}: frozenAsset requires frozenPhysicalInput"
        )
    receipt_ref = str(frozen.get("sourceReceiptRef") or "")
    expected_header = {
        "sourceReceiptRef": receipt_ref,
        "sourceReceiptDigest": str(frozen.get("sourceReceiptDigest") or ""),
        "sourceReceiptFileSha256": str(frozen.get("sourceReceiptFileSha256") or ""),
    }
    if any(physical.get(field) != value for field, value in expected_header.items()):
        raise ValueError(
            f"{item.get('assetId')}: frozen receipt binding differs from manifest"
        )
    if receipt_ref not in receipt_cache:
        receipt_path = canonical_child(
            output_root,
            receipt_ref,
            label="frozen professional video receiptRef",
        )
        receipt = validate_historical_video_receipt(read_json(receipt_path))
        validate_historical_video_receipt_path(
            receipt_path, manifest_digest=str(receipt["manifestDigest"])
        )
        receipt_cache[receipt_ref] = (receipt, file_digest(receipt_path))
    receipt, receipt_file_sha = receipt_cache[receipt_ref]
    if (
        receipt.get("receiptDigest") != frozen.get("sourceReceiptDigest")
        or receipt_file_sha != frozen.get("sourceReceiptFileSha256")
        or receipt.get("manifestDigest") != physical.get("sourceManifestDigest")
        or receipt.get("sourceRevision") != physical.get("sourceRevision")
        or receipt.get("sourceDigest") != physical.get("sourceDigest")
        or receipt.get("entityCatalogDigest") != physical.get("entityCatalogDigest")
    ):
        raise ValueError(
            f"{item.get('assetId')}: frozen physical receipt identity drift"
        )
    matches = [
        row for row in receipt["assets"] if row.get("assetId") == item.get("assetId")
    ]
    if len(matches) != 1:
        raise ValueError(
            f"{item.get('assetId')}: frozen receipt asset is missing or ambiguous"
        )
    source_row = matches[0]
    if (
        source_row.get("acquisitionStatus") != "acquired"
        or source_row.get("distributionDecision") not in ACCEPTED_DECISIONS
        or any(source_row.get(field) != item.get(field) for field in _PROVENANCE_FIELDS)
        or source_row.get("assetRef") != frozen.get("assetRef")
        or source_row.get("contentSha256") != frozen.get("contentSha256")
        or source_row.get("bytes") != frozen.get("bytes")
    ):
        raise ValueError(
            f"{item.get('assetId')}: frozen asset provenance or bytes binding drift"
        )
    asset = canonical_child(
        output_root,
        str(frozen.get("assetRef") or ""),
        label=f"{item.get('assetId')}.frozenAsset.assetRef",
    )
    if (
        asset.is_symlink()
        or not asset.is_file()
        or file_digest(asset) != frozen.get("contentSha256")
        or asset.stat().st_size != frozen.get("bytes")
    ):
        raise ValueError(f"{item.get('assetId')}: frozen CAS bytes drift")
    return asset


__all__ = ["resolve_frozen_video_asset"]
