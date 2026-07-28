"""Canonical image identity projection shared by post transactions."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.image_deduplication import perceptual_hash


def canonical_asset_manifest_row(
    raw: Mapping[str, Any],
    *,
    asset_source: Path,
    mime_type: str,
    object_key: str,
) -> dict[str, Any]:
    row = {**raw, "objectKey": object_key}
    if str(raw.get("kind") or "").strip() == "image" or mime_type.startswith(
        "image/"
    ):
        row["perceptualHash"] = perceptual_hash(asset_source)
    return row


__all__ = ["canonical_asset_manifest_row"]
