"""Public facade for registry-driven commercial article source discovery."""
from __future__ import annotations

from content.source.research.article_crawl_frontier import (
    discover_article_source_frontier,
    parse_public_search_results,
)
from content.source.research.article_frontier_contract import (
    ArticleFrontierRecord,
    ArticleSiteDiscoveryEvidence,
    ArticleSourceCandidate,
    ArticleSourceDiscoveryOutcome,
    DailyPageBudget,
    FileDailyPageBudget,
    FrontierDecision,
    InMemoryDailyPageBudget,
    PageBudgetReservation,
    PublicSearchResult,
)
from content.source.research.article_frontier_profile import (
    canonicalize_article_url,
)


def public_search_article_sources(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int,
) -> list[dict[str, object]]:
    """Compatibility facade; production callers should retain outcome evidence."""
    if limit <= 0:
        return []
    return discover_article_source_frontier(
        entity_id,
        entity_aliases=entity_aliases,
        limit=limit,
    ).source_documents()


__all__ = [
    "ArticleFrontierRecord",
    "ArticleSiteDiscoveryEvidence",
    "ArticleSourceCandidate",
    "ArticleSourceDiscoveryOutcome",
    "DailyPageBudget",
    "FileDailyPageBudget",
    "FrontierDecision",
    "InMemoryDailyPageBudget",
    "PageBudgetReservation",
    "PublicSearchResult",
    "canonicalize_article_url",
    "discover_article_source_frontier",
    "parse_public_search_results",
    "public_search_article_sources",
]
