from __future__ import annotations

from collections import Counter

from _common.creator_pool.source_registry import iter_creator_source_sites, validate_creator_source_registry


REQUIRED_FIELDS = {
    "siteId",
    "verticals",
    "chinaAnalogLabel",
    "candidateRole",
    "crawlAllowed",
    "validationOnly",
    "rightsPolicy",
    "rateLimit",
    "sourceKind",
}


def test_creator_source_registry_contract() -> None:
    issues = validate_creator_source_registry()
    assert issues == []
    sites = iter_creator_source_sites()
    assert len(sites) >= 30
    for site in sites:
        assert REQUIRED_FIELDS.issubset(site)
        assert site["chinaAnalogLabel"]
        assert isinstance(site["crawlAllowed"], bool)
        assert isinstance(site["validationOnly"], bool)
        assert site["rateLimit"]["requestsPerMinute"] > 0
        assert "example." not in str(site.get("homepageUrl") or "")
        assert not any("example." in str(domain) for domain in site.get("domains") or [])


def test_creator_source_registry_travel_photo_representation() -> None:
    sites = iter_creator_source_sites()
    region_counts = Counter(str(site.get("regionClass") or "") for site in sites)
    both_verticals = [
        site
        for site in sites
        if {"travel", "photography"}.issubset({str(ref) for ref in site.get("verticals") or []})
    ]
    assert len(both_verticals) >= 10
    assert region_counts["non_china"] >= 15
    assert region_counts["china"] >= 10
    assert any(site["siteId"] == "tpoty" for site in both_verticals)
    assert any(site["siteId"] == "tuchong" for site in both_verticals)
