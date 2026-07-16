"""Deterministic same-source image rendition candidates."""
from __future__ import annotations

import re
import urllib.parse

def candidate_image_urls(url: str) -> list[str]:
    """Return deterministic same-source high-resolution candidates.

    The candidates stay on the same host/path family and are only used for
    fetch attempts. Rights, relevance, source-unit ownership and pixel gates
    still run after bytes are downloaded.
    """
    raw = str(url or "").strip()
    if not raw:
        return []
    candidates: list[str] = []

    def _add(item: str) -> None:
        if item and item not in candidates:
            candidates.append(item)

    _add(raw)
    parsed = urllib.parse.urlparse(raw)
    if parsed.query:
        _add(urllib.parse.urlunparse(parsed._replace(query="", fragment="")))

    # Qunar-style compressed variants:
    #   foo.jpg_r_720x480x95_hash.jpg -> foo.jpg
    #   foo.jpg_r_600x600x95_hash.jpg -> foo.jpg
    stripped = re.sub(
        r"(?i)(\.(?:jpe?g|png|webp))_r_\d+x\d+(?:x\d+)?_[A-Za-z0-9]+(?:\.(?:jpe?g|png|webp))$",
        r"\1",
        urllib.parse.urlunparse(parsed._replace(query="", fragment="")),
    )
    _add(stripped)

    # Some CDNs append a post-extension rendition marker.
    stripped_bang = re.sub(
        r"(?i)(\.(?:jpe?g|png|webp))(?:![^/?#]+)$",
        r"\1",
        urllib.parse.urlunparse(parsed._replace(query="", fragment="")),
    )
    _add(stripped_bang)

    # Wikimedia thumb URLs keep the original file path before the final
    # size-prefixed segment.
    path_parts = parsed.path.split("/")
    if "/wikipedia/commons/thumb/" in parsed.path and len(path_parts) > 4:
        try:
            thumb_index = path_parts.index("thumb")
            original_parts = path_parts[:thumb_index] + path_parts[thumb_index + 1:-1]
            original_path = "/".join(original_parts)
            _add(urllib.parse.urlunparse(parsed._replace(path=original_path, query="", fragment="")))
        except ValueError:
            pass

    return candidates


