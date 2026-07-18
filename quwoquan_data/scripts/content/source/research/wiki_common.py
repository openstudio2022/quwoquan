"""Shared constants and text cleanup for public-source providers."""
from __future__ import annotations

import html
import re
import unicodedata
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
