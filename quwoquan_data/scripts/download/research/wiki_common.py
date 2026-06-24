"""Shared constants and text cleanup for public-source providers."""
from __future__ import annotations

import html
import os
import re

_OPENVERSE_API = "https://api.openverse.org/v1/images/"

_QUNAR_SEARCH_API = "https://touch.travel.qunar.com/search"

_BASE_DRAFT_IMAGE_CANDIDATES = max(1, int(os.environ.get("QWQ_BASE_DRAFT_IMAGE_CANDIDATES", "8")))

def _strip_html(value: str) -> str:
    text = re.sub(r"(?is)<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()
