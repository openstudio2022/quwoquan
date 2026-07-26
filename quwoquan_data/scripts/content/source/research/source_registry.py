"""Provider-policy projections for source discovery.

There are intentionally no per-entity URLs, image hints, or reject words in
this module. Candidates come from provider discovery and must pass title,
entity, body, and rights checks before any download starts.
"""
from __future__ import annotations

import fnmatch
import urllib.parse
from pathlib import Path

import yaml

from governance.entity_reference import entity_aliases


_TRAVEL_PROVIDER_PATH = Path(__file__).resolve().parents[4] / "verticals" / "travel" / "providers.yaml"


def _providers() -> tuple[dict[str, object], ...]:
    document = yaml.safe_load(_TRAVEL_PROVIDER_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("travel providers must be an object")
    sites = document.get("sites")
    if not isinstance(sites, list):
        raise ValueError("travel providers.sites must be an array")
    return tuple(site for site in sites if isinstance(site, dict))


def _travel_registry_url_fetchable(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not host:
        return False
    normalized_url = urllib.parse.urlunparse(urllib.parse.urlparse(url))
    matches: list[tuple[int, dict[str, object]]] = []
    for site in _providers():
        domains = tuple(
            str(item).lower() for item in (site.get("domains") or ()) if str(item).strip()
        )
        patterns = tuple(
            str(item) for item in (site.get("urlPatterns") or ()) if str(item).strip()
        )
        domain_hits = tuple(
            domain for domain in domains if host == domain or host.endswith(f".{domain}")
        )
        pattern_hits = tuple(
            pattern for pattern in patterns if fnmatch.fnmatch(normalized_url, pattern)
        )
        if domain_hits or pattern_hits:
            matches.append((max((len(value) for value in (*domain_hits, *pattern_hits)), default=0), site))
    if not matches:
        return False
    return bool(max(matches, key=lambda item: item[0])[1].get("fetchable"))


def _known_official_website(entity_id: str) -> str:
    del entity_id
    return ""


def _known_article_sources(entity_id: str) -> list[dict[str, str]]:
    del entity_id
    return []


def _known_entity_aliases(entity_id: str) -> list[str]:
    return list(entity_aliases(entity_id))


def _known_image_search_hints(entity_id: str) -> dict[str, list[str]]:
    return {"aliases": list(entity_aliases(entity_id)), "commonsCategories": []}
