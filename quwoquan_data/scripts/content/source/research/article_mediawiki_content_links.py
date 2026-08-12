"""MediaWiki content-link selection for entity-seeded article discovery."""
from __future__ import annotations

import urllib.parse
from collections.abc import Mapping

from content.source.research.article_frontier_contract import PublicSearchResult
from content.source.research.article_frontier_profile import (
    article_url_allowed,
    canonicalize_article_url,
)
from content.source.research.article_site_page import PageParser

MEDIAWIKI_SEARCH_METHOD = "mediawiki_api_search"
ENTITY_SEEDED_METHOD = "entity_seeded_scan"
ENTITY_SEEDED_PAGE_LINK_METHOD = "entity_seeded_page_link"


def mediawiki_content_page_links(
    parser: PageParser,
    *,
    final_url: str,
    site: Mapping[str, object],
    limit: int,
) -> tuple[PublicSearchResult, ...]:
    """Return bounded, same-origin MediaWiki main-namespace content links."""

    origin = urllib.parse.urlsplit(final_url).netloc.casefold()
    selected: list[PublicSearchResult] = []
    seen: set[str] = set()
    prioritized = (*parser.related_content_links, *parser.content_links)
    for link in prioritized:
        canonical_url = canonicalize_article_url(link.url)
        parsed = urllib.parse.urlsplit(canonical_url)
        if (
            not canonical_url
            or canonical_url == final_url
            or parsed.netloc.casefold() != origin
            or not article_url_allowed(canonical_url, site)
            or "/wiki/" not in parsed.path
        ):
            continue
        page_title = urllib.parse.unquote(
            parsed.path.split("/wiki/", 1)[1].split("/", 1)[0]
        )
        if not page_title or ":" in page_title or canonical_url in seen:
            continue
        seen.add(canonical_url)
        selected.append(PublicSearchResult(link.title, canonical_url))
        if len(selected) >= limit:
            break
    return tuple(selected)


__all__ = [
    "ENTITY_SEEDED_METHOD",
    "ENTITY_SEEDED_PAGE_LINK_METHOD",
    "MEDIAWIKI_SEARCH_METHOD",
    "mediawiki_content_page_links",
]
