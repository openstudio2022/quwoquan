"""Shared constants and text cleanup for public-source providers."""
from __future__ import annotations

import html
import re
import unicodedata
import urllib.parse

from core.media_processing_policy import MEDIA_PROCESSING_POLICY

_OPENVERSE_API = "https://api.openverse.org/images/"

_QUNAR_SEARCH_API = "https://touch.travel.qunar.com/search"

_BASE_DRAFT_IMAGE_CANDIDATES = MEDIA_PROCESSING_POLICY.base_draft_image_candidates

def _strip_html(value: str) -> str:
    text = re.sub(r"(?is)<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    # Commons metadata and rendered MediaWiki captions may contain bidi
    # isolates or zero-width format controls. They are display transport
    # markers, never source facts, and must not escape into publishable media
    # captions or relevance fields.
    text = "".join(char for char in text if unicodedata.category(char) != "Cf")
    return re.sub(r"\s+", " ", text).strip()


def _canonical_terms_url(
    value: object,
    *,
    license_name: object,
    source_url: object,
) -> str:
    """Return one public HTTPS rights URL for Wikimedia-derived assets."""
    raw = str(value or "").strip()
    parsed = urllib.parse.urlsplit(raw)
    host = str(parsed.hostname or "").lower()
    if parsed.scheme == "http" and host in {
        "creativecommons.org",
        "www.creativecommons.org",
    }:
        return urllib.parse.urlunsplit(
            ("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment)
        )
    if parsed.scheme == "https":
        return raw
    source = str(source_url or "").strip()
    source_parts = urllib.parse.urlsplit(source)
    if (
        "public domain" in str(license_name or "").lower()
        and source_parts.scheme == "https"
        and source_parts.hostname == "commons.wikimedia.org"
    ):
        return source
    return ""
