"""Evidence-safe tag projection for canonical entity homepages."""
from __future__ import annotations

from typing import Any

from core.content_tags import resolved_content_tag_refs


def homepage_tag_refs(
    domain: str,
    etype: str,
    _name: str,
    payload: dict[str, Any],
) -> list[str]:
    """Project entity kind and administrative tags without static fact claims."""

    provided: list[str] = [f"Entity/{domain}/{etype}"]
    if isinstance(payload, dict):
        geo_tag_ref = str(payload.get("geoTagRef") or "").strip()
        if geo_tag_ref:
            provided.append(geo_tag_ref)
        provided.extend(
            str(item).strip()
            for item in (payload.get("geoTagRefs") or [])
            if str(item).strip()
        )
    brief: dict[str, Any] = (
        {"tagRefs": list(dict.fromkeys(provided))} if provided else {}
    )
    return resolved_content_tag_refs(brief, "article")
