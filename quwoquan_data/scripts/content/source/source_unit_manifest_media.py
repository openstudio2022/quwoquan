"""Media-specific manifest assembly for canonical source units."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def apply_image_collection_manifest_defaults(
    manifest: dict[str, Any],
    *,
    source_kind: str,
    asset_index: Sequence[Mapping[str, Any]],
) -> None:
    """Add deterministic image-collection placement and funnel evidence."""
    if source_kind != "image_collection" or not asset_index:
        return
    manifest["imagePlacements"] = [
        {
            "fileName": row["fileName"],
            "caption": row["caption"],
            "sourceOrder": index,
            "placementType": row["placementType"],
        }
        for index, row in enumerate(asset_index)
    ]
    manifest.setdefault(
        "assetFunnel",
        {
            "candidateCount": len(asset_index),
            "keptCount": len(asset_index),
            "droppedCount": 0,
            "dedupeRemoved": 0,
            "quotaMode": "complete_source_page",
            "drops": [],
            "fetchFailures": [],
        },
    )
