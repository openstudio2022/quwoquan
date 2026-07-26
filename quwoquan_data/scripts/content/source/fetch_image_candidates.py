"""Deterministic same-source image rendition candidates."""
from __future__ import annotations

import re
import urllib.parse


def _wikimedia_rendition_url(url: str, *, width: int) -> str:
    parsed = urllib.parse.urlparse(url)
    marker = "/wikipedia/commons/"
    if parsed.hostname != "upload.wikimedia.org" or marker not in parsed.path:
        return ""
    if "/wikipedia/commons/thumb/" in parsed.path:
        return ""
    relative = parsed.path.split(marker, 1)[1]
    parts = relative.split("/")
    if len(parts) < 3:
        return ""
    file_name = parts[-1]
    if not re.search(r"\.(?:jpe?g|png|webp)$", file_name, re.IGNORECASE):
        return ""
    thumb_path = f"{marker}thumb/{relative}/{width}px-{file_name}"
    return urllib.parse.urlunparse(parsed._replace(path=thumb_path, query="", fragment=""))


def page_image_candidate_urls(url: str, *, rendition_width: int) -> list[str]:
    """Prefer a bounded same-file Commons rendition before the original."""

    candidates: list[str] = []
    rendition = _wikimedia_rendition_url(url, width=rendition_width)
    if rendition:
        candidates.append(rendition)
    for candidate in candidate_image_urls(url):
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates

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

