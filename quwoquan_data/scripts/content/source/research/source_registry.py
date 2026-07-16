"""Read-only travel source registry access for source planning."""
from __future__ import annotations

import urllib.parse
from pathlib import Path

import yaml

from content.source.research.text_match import _dedupe_terms

_TRAVEL_SOURCE_REGISTRY = Path(__file__).resolve().parents[4] / "verticals" / "travel" / "sources" / "source_registry.yaml"

def _known_image_reject_terms(entity_id: str) -> list[str]:
    """Curated cross-entity visual reject terms from the travel registry."""
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return []
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    terms: list[str] = []
    for row in data.get("knownImageRejectTerms") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        values = row.get("rejectTerms") if isinstance(row.get("rejectTerms"), list) else []
        terms.extend(str(value).strip() for value in values if str(value).strip())
    return _dedupe_terms(terms, limit=32)

def _known_official_website(entity_id: str) -> str:
    """Curated official-site seed from the travel source registry."""
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return ""
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ""
    for row in data.get("knownOfficialSites") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        url = str(row.get("url") or "").strip()
        if url.startswith(("http://", "https://")):
            return url
    return ""

def _travel_registry_url_fetchable(url: str) -> bool:
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return False
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return False
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not host:
        return False
    for site in data.get("sites") or []:
        if not isinstance(site, dict):
            continue
        domains = [str(item).lower() for item in (site.get("domains") or []) if str(item).strip()]
        if not domains:
            continue
        if any(host == domain or host.endswith(f".{domain}") for domain in domains):
            return bool(site.get("fetchable"))
    return False

def _known_article_sources(entity_id: str) -> list[dict[str, str]]:
    """Curated article-lane seed sources from the travel source registry."""
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return []
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    rows: list[dict[str, str]] = []
    for index, row in enumerate(data.get("knownArticleSources") or [], start=1):
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        url = str(row.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        explicit_fetchable = row.get("fetchable")
        if explicit_fetchable is not None:
            if not bool(explicit_fetchable):
                continue
        elif not _travel_registry_url_fetchable(url):
            continue
        rows.append(
            {
                "source_id": str(row.get("sourceId") or f"article_registry_base_{index}").strip(),
                "platform": str(row.get("platform") or "垂类专业站").strip(),
                "url": url,
                "category": str(row.get("category") or "travelogue").strip(),
                "title": str(row.get("title") or "").strip(),
                "fetchable": bool(row.get("fetchable")),
            }
        )
    return rows

def _known_entity_aliases(entity_id: str) -> list[str]:
    """Curated entity aliases that are valid across source discovery lanes."""
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return []
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    aliases: list[str] = []
    for row in data.get("knownEntityAliases") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        values = row.get("aliases") if isinstance(row.get("aliases"), list) else []
        aliases.extend(str(value).strip() for value in values if str(value).strip())
    return _dedupe_terms(aliases, limit=16)

def _known_image_search_hints(entity_id: str) -> dict[str, list[str]]:
    """Curated visual-discovery hints from the travel source registry.

    These are discovery inputs only. They do not bypass asset-level license,
    entity-relevance, creator, watermark, or collection gates.
    """
    if not _TRAVEL_SOURCE_REGISTRY.is_file():
        return {"aliases": [], "commonsCategories": []}
    try:
        data = yaml.safe_load(_TRAVEL_SOURCE_REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"aliases": [], "commonsCategories": []}
    aliases: list[str] = []
    categories: list[str] = []
    for row in data.get("knownImageSearchHints") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("entity") or "").strip() != entity_id:
            continue
        raw_aliases = row.get("aliases") if isinstance(row.get("aliases"), list) else []
        raw_categories = (
            row.get("commonsCategories") if isinstance(row.get("commonsCategories"), list) else []
        )
        aliases.extend(str(value).strip() for value in raw_aliases if str(value).strip())
        categories.extend(str(value).strip() for value in raw_categories if str(value).strip())
    return {
        "aliases": _dedupe_terms(aliases, limit=16),
        "commonsCategories": _dedupe_terms(categories, limit=12),
    }
