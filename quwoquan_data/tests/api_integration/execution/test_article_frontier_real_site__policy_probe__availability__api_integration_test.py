"""Real public-site probe for the commercial article crawl frontier.

spec_ref: specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md#gwt-001
"""

from __future__ import annotations

import os

import pytest
from content.source.mediawiki_page import mediawiki_title_from_url
from content.source.research.public_search import discover_article_source_frontier
from content.source.research.wiki_media import _mediawiki_page_images


@pytest.mark.api_integration
def test_wikivoyage_article_frontier_real_site_probe() -> None:
    entity = os.environ.get("QWQ_ARTICLE_FRONTIER_PROBE_ENTITY", "乌镇").strip()
    assert entity, "QWQ_ARTICLE_FRONTIER_PROBE_ENTITY must not be blank"

    outcome = discover_article_source_frontier(
        entity,
        limit=3,
        site_ids=frozenset({"wikivoyage_zh"}),
    )

    if not outcome.candidates:
        pytest.fail(
            "GATE_BLOCK: real Wikivoyage article frontier probe produced no admitted "
            f"public source; issues={[issue.as_dict() for issue in outcome.issues]}; "
            f"evidence={outcome.as_evidence()}"
        )
    evidence = outcome.as_evidence()
    qualified: list[tuple[object, list[dict[str, object]]]] = []
    for candidate in outcome.candidates:
        host, title = mediawiki_title_from_url(candidate.canonical_url)
        images = _mediawiki_page_images(
            host,
            title,
            entity_id=entity,
            limit=4,
        )
        if len(images) >= 2:
            qualified.append((candidate, images))
    if not qualified:
        pytest.fail(
            "GATE_BLOCK: DATA.MEDIA.PUBLISHABLE_SHORTFALL; admitted Wikivoyage "
            "pages discovered for 乌镇 but no page yielded at least two "
            f"same-source qualified images; evidence={evidence}"
        )
    candidate, images = qualified[0]
    assert candidate.site_id == "wikivoyage_zh"
    assert candidate.canonical_url.startswith("https://zh.wikivoyage.org/wiki/")
    assert candidate.discovery_method in {
        "entity_seeded_scan",
        "mediawiki_api_search",
    }
    assert len(images) >= 2
    assert len({str(image["collectionPageUrl"]) for image in images}) == 1
    assert str(images[0]["collectionPageUrl"]) == candidate.canonical_url
    assert evidence["sources"][0]["sourceUseMode"] == "factual_reference_only"
    assert any(
        row["decision"] == "accepted" for row in evidence["sites"][0]["frontier"]
    )
