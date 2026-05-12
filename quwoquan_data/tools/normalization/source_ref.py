from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

_UNSAFE_RE = re.compile(r"[^\w\u4e00-\u9fff.-]+", flags=re.U)
_SEP_RE = re.compile(r"[_\-.]{2,}")


def normalize_domain(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def _safe_component(value: str, *, fallback: str) -> str:
    text = str(value or "").strip()
    text = _UNSAFE_RE.sub("_", text)
    text = _SEP_RE.sub("_", text).strip("_.-")
    return text or fallback


def title_fragment(page_title: str, *, fallback: str = "source") -> str:
    fragment = _safe_component(page_title, fallback=fallback)
    return fragment[:48] if len(fragment) > 48 else fragment


def build_source_ref(
    *,
    source_url: str,
    page_title: str = "",
    catalog_topic_id: str = "",
    source_markdown_path: str = "",
) -> str:
    parsed = urlparse(str(source_url or "").strip())
    domain = normalize_domain(parsed.netloc) or "local"
    title = str(page_title or "").strip()
    if not title and source_markdown_path:
        title = Path(source_markdown_path).stem
    if not title and parsed.path:
        title = Path(parsed.path).stem
    if not title:
        title = str(catalog_topic_id or "source")
    domain_part = _safe_component(domain.replace(".", "_"), fallback="source")
    title_part = title_fragment(title, fallback="source")
    digest = hashlib.sha1(
        f"{source_url}|{page_title}|{catalog_topic_id}|{source_markdown_path}".encode("utf-8")
    ).hexdigest()[:8]
    return f"{domain_part}__{title_part}__{digest}"

