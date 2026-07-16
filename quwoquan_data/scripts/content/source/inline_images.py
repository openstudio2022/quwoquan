"""Convert rendered inline images into source-unit download candidates."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def build_inline_image_candidates(
    inline_images: Sequence[Mapping[str, Any]] | None,
    *,
    entity_id: str,
) -> list[dict[str, Any]]:
    """Keep source-provided URL, placeholder and caption without fabricating relevance."""
    candidates: list[dict[str, Any]] = []
    for row in inline_images or []:
        if not isinstance(row, Mapping):
            continue
        source_url = str(row.get("src") or "").strip()
        placeholder_id = str(row.get("placeholderId") or "").strip()
        if not source_url or not placeholder_id:
            continue
        caption = str(row.get("caption") or "").strip()
        candidates.append(
            {
                "url": source_url,
                "placeholderId": placeholder_id,
                "caption": caption,
                "relevance": caption,
            }
        )
    _ = entity_id
    return candidates
