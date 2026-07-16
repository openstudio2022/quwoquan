"""Stable identifiers for source-screen evidence and source image collections."""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

from content.source.source_unit import slugify


def source_screen_report_ref(entity_id: str, source_id: str) -> str:
    """Return a collision-free, readable source-screen evidence filename stem."""
    raw = f"{entity_id}__{source_id}"
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"{(safe.strip('._-') or digest)[:120]}_{digest}"


def stable_source_image_collection_id(
    *,
    entity_id: str,
    source_id: str,
    spec: Mapping[str, Any],
) -> str:
    """Resolve the cross-work identity for images attached to one source unit."""
    existing = str(spec.get("sourceCollectionId") or "").strip()
    if existing and existing != f"article:{source_id}":
        return existing
    key = str(
        spec.get("authorizationProof")
        or spec.get("sourceUrl")
        or spec.get("url")
        or spec.get("collectionPageUrl")
        or source_id
    ).strip()
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"source_image:{slugify(entity_id)[:48]}:{digest}"
