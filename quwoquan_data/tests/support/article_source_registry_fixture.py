"""The article source registry identity a deliverable article source unit carries.

`source_unit_meta` admits an article-lane unit only through the registry branch, so
every fixture that writes one has to carry the same registry binding the planner
mints. Keeping it here rather than beside a download-gate fixture lets callers take
the binding without also taking that module's autouse execution-root teardown.
"""
from __future__ import annotations

from typing import Any

ARTICLE_SOURCE_UNIT_IDENTITY: dict[str, str] = {
    "source_kind": "travelogue",
    "extractor": "qunar_html",
    "policy_revision": "article-source-registry-v1",
    "source_use_mode": "factual_reference_only",
    "rights_mode": "factual_reference_only",
}


def article_source_registry_binding(
    *,
    platform: str,
    url: str,
    site_id: str = "qunar_guide",
) -> dict[str, Any]:
    """The registry identity and attribution an article source unit must carry.

    Article-lane source units inherit their post-manifest attribution from the
    registry entry that admitted them, so a fixture that writes one has to carry
    the same binding the planner mints. Travelogue sites have no encyclopedia
    attribution mapping, which is why the attribution is minted here rather than
    resolved from the site id.
    """
    from content.source.research.article_frontier_contract import (
        public_article_source_attribution,
    )

    return {
        "articleSiteId": site_id,
        "sourceDiscoveryProfileDigest": "sha256:" + "b" * 64,
        "articleCommercialAdmission": "commercial_release",
        "sourceAttribution": public_article_source_attribution(
            platform=platform,
            canonical_url=url,
            terms_url="https://example.com/terms",
            captured_at="2026-08-05T00:00:00Z",
        ),
    }


__all__ = ["ARTICLE_SOURCE_UNIT_IDENTITY", "article_source_registry_binding"]
