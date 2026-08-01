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
]
