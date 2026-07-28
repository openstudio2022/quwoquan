"""Real public-site probe for the commercial article crawl frontier.

spec_ref: specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md#gwt-001
"""
from __future__ import annotations

import os

import pytest

from content.source.research.public_search import (
    InMemoryDailyPageBudget,
    discover_article_source_frontier,
)


@pytest.mark.api_integration
def test_wikivoyage_article_frontier_real_site_probe() -> None:
    entity = os.environ.get("QWQ_ARTICLE_FRONTIER_PROBE_ENTITY", "九寨沟").strip()
    assert entity, "QWQ_ARTICLE_FRONTIER_PROBE_ENTITY must not be blank"

    outcome = discover_article_source_frontier(
        entity,
        limit=1,
        site_ids=frozenset({"wikivoyage_zh"}),
        daily_budget=InMemoryDailyPageBudget(),
    )

    if not outcome.candidates:
        pytest.fail(
            "GATE_BLOCK: real Wikivoyage article frontier probe produced no admitted "
            f"public source; issues={[issue.as_dict() for issue in outcome.issues]}; "
            f"evidence={outcome.as_evidence()}"
        )
    candidate = outcome.candidates[0]
    evidence = outcome.as_evidence()
    assert candidate.site_id == "wikivoyage_zh"
    assert candidate.canonical_url.startswith("https://zh.wikivoyage.org/wiki/")
    assert evidence["sources"][0]["sourceUseMode"] == "factual_reference_only"
    assert any(
        row["decision"] == "accepted"
        for row in evidence["sites"][0]["frontier"]
    )
