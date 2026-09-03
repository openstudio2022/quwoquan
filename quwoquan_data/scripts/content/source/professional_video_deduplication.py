"""Exact-content deduplication for professional video acquisition."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json

from content.source.professional_video_receipt import (
    load_professional_video_acquisition_receipt,
)


def source_identity(document: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(document["sourceRevision"]),
        str(document["sourceDigest"]),
        str(document["entityCatalogDigest"]),
    )


def _receipt_source_identity_header(path: Path) -> tuple[str, str, str] | None:
    """Read only the immutable identity header before current-schema validation.

    Historical receipts from another source identity are not candidates for
    deduplication and may predate the current receipt body schema.  A malformed
    header still fails closed because its identity cannot be proven foreign.
    """
    document = read_json(path)
    if not isinstance(document, Mapping):
        raise TypeError(
            f"professional video acquisition receipt header must be an object: {path}"
        )
    schema = document.get("schema")
    if schema == "quwoquan_data.professional_image_acquisition_receipt":
        return None
    if schema != "quwoquan_data.professional_video_acquisition_receipt":
        raise ValueError(
            f"professional video acquisition receipt header schema is invalid: {path}"
        )
    values: list[str] = []
    for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
        value = document.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "professional video acquisition receipt identity header is invalid: "
                f"{path} field={field}"
            )
        values.append(value)
    return values[0], values[1], values[2]


def prior_content_index(
    output_root: Path,
    *,
    current_receipt: Path,
    source_identity: tuple[str, str, str],
) -> dict[str, str]:
    index: dict[str, str] = {}
    receipts = output_root / "receipts"
    if not receipts.is_dir():
        return index
    for path in sorted(receipts.glob("*.json")):
        if path.resolve() == current_receipt.resolve():
            continue
        ref = path.relative_to(output_root).as_posix()
        header = _receipt_source_identity_header(path)
        if header is None or header != source_identity:
            continue
        receipt = load_professional_video_acquisition_receipt(ref, root=output_root)
        for row in receipt["assets"]:
            digest = str(row.get("contentSha256") or "")
            if row.get("acquisitionStatus") == "acquired" and digest:
                index.setdefault(digest, f"{ref}#{row['assetId']}")
    return index


def duplicate_source(
    row: Mapping[str, Any],
    *,
    seen: Mapping[str, str],
    prior: Mapping[str, str],
    frozen_reuse_digests: Mapping[str, str],
) -> str:
    """Return the earlier holder of these exact bytes, or empty when unique."""
    digest = str(row["contentSha256"])
    if not digest:
        return ""
    within_manifest = seen.get(digest, "")
    if within_manifest:
        return within_manifest
    # An explicit frozenAsset reuses a prior receipt's bytes on purpose, so the
    # prior holding it was bound to is evidence rather than a collision. The
    # exemption is asset-scoped and never covers a repeat inside one manifest.
    if frozen_reuse_digests.get(str(row["assetId"])) == digest:
        return ""
    return prior.get(digest, "")


__all__ = ["duplicate_source", "prior_content_index", "source_identity"]
