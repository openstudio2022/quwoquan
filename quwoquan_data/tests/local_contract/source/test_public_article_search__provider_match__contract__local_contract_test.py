from __future__ import annotations

import copy
import json
import urllib.parse
from dataclasses import FrozenInstanceError

import pytest
from content.source.fetch_text import extract_page_text
from content.source.handler_fetch_contract import require_source_candidate_admission
from content.source.research import (
    article_frontier_profile,
    article_frontier_robots,
    auto_plan_article,
    network_io,
)
from content.source.research.public_search import (
    FileDailyPageBudget,
    InMemoryDailyPageBudget,
    canonicalize_article_url,
    discover_article_source_frontier,
)
from content.source.research.source_registry import _travel_registry_url_fetchable
from governance.coverage.source_registry import resolve_travel_source_runtime

SPEC_REF = (
    "specs/feature-tree/runtime/runtime-data-engineering/"
    "article-commercial-scale-closure/spec.md#gwt-001"
)


def test_file_daily_budget_resolves_current_disposable_root(
    monkeypatch,
    tmp_path,
):
    from core import paths

    monkeypatch.setattr(paths, "DATA_WORKSPACE_ROOT", tmp_path)
    budget = FileDailyPageBudget()

    assert budget.reserve(
        "frontier_test",
        day="2026-08-03",
        max_pages_per_day=1,
    ).allowed
    assert (tmp_path / "article-source-frontier" / "2026-08-03.json").is_file()


TERMS_URL = "https://terms.example.test/article"


def _site(
    *,
    allowed_paths: list[str] | None = None,
    strategy: dict | None = None,
    max_depth: int = 1,
    max_pages_per_day: int = 20,
    requests_per_second: float = 1000.0,
) -> dict:
    return {
        "siteId": "frontier_test",
        "platform": "测试旅行指南",
        "category": "travelogue",
        "domains": ["guide.example.test"],
        "urlPatterns": ["https://guide.example.test/*"],
        "fetchable": True,
        "extractor": "generic_html",
        "licensePolicy": "factual_citation_only",
        "qualityTier": "B",
        "siteCrawlProfile": {
            "crawlAllowed": True,
            "contentLanes": ["article"],
            "articleCommercialAdmission": "commercial_release",
            "allowedPaths": allowed_paths or ["https://guide.example.test/article/*"],
            "fetchMode": "html",
            "extractor": "generic_html",
            "rightsPolicy": "factual_citation_only",
            "robotsPolicy": "respect_robots_txt",
            "loginPolicy": "public_only",
            "termsUrl": TERMS_URL,
            "rateLimit": {
                "maxRequestsPerSecond": requests_per_second,
                "backoffOnStatus": [403, 429],
            },
            "discoveryStrategy": strategy
            or {
                "mode": "content_search",
                "searchProvider": "brave_public",
                "seedAxes": ["entity"],
                "queryTemplates": ["{entity} site:guide.example.test/article"],
                "precheckGates": ["light_fetch", "entity_anchor"],
            },
            "maxDepth": max_depth,
            "maxPagesPerDay": max_pages_per_day,
        },
    }


def _response(
    url: str,
    *,
    status: int = 200,
    body: str = "",
    returncode: int = 0,
) -> network_io.HttpFetchResult:
    return network_io.HttpFetchResult(
        returncode=returncode,
        status_code=status,
        final_url=url,
        body=body.encode("utf-8"),
    )


def _install_registry(monkeypatch: pytest.MonkeyPatch, site: dict) -> None:
    article_frontier_robots._RATE_LIMITERS.clear()
    monkeypatch.setattr(
        article_frontier_profile,
        "iter_travel_registry_sites",
        lambda: [site],
    )


def _mediawiki_site() -> dict:
    site = _site(
        allowed_paths=["https://guide.example.test/wiki/*"],
        strategy={
            "mode": "entity_seeded_scan",
            "seedAxes": ["entity"],
            "precheckGates": ["light_fetch", "entity_anchor"],
        },
    )
    site["urlPatterns"] = ["https://guide.example.test/wiki/*"]
    site["extractor"] = "wikipedia_api"
    profile = site["siteCrawlProfile"]
    profile["fetchMode"] = "mediawiki_api"
    profile["extractor"] = "wikipedia_api"
    return site


def _default_fetch(
    url: str,
    *,
    search_html: str,
    pages: dict[str, str] | None = None,
    robots: str = "User-agent: *\nAllow: /\n",
) -> network_io.HttpFetchResult:
    if url == TERMS_URL:
        return _response(url, body="<html><title>Terms</title></html>")
    if url == "https://guide.example.test/robots.txt":
        return _response(url, body=robots)
    if url.startswith("https://search.brave.com/search?"):
        return _response(url, body=search_html)
    if pages and url in pages:
        return _response(url, body=pages[url])
    raise AssertionError(f"unexpected fetch: {url}")


def test_frontier_canonical_dedupe_and_entity_alias_relevance(monkeypatch):
    _install_registry(monkeypatch, _site())
    relevant = "https://guide.example.test/article/200.html"
    irrelevant = "https://guide.example.test/article/201.html"
    search_html = f"""
    <a href="{relevant}?utm_source=test#part">测试山别名游玩攻略</a>
    <a href="{relevant}">重复结果</a>
    <a href="{irrelevant}">其它景区游玩攻略</a>
    """
    pages = {
        relevant: (
            "<html><head><title>测试山别名游玩攻略</title>"
            f'<link rel="canonical" href="{relevant}"></head>'
            "<body>测试山景区提供公开步道信息。</body></html>"
        ),
        irrelevant: (
            "<html><head><title>其它景区游玩攻略</title></head>"
            "<body>本文只介绍另一处景区。</body></html>"
        ),
    }
    monkeypatch.setattr(
        network_io,
        "fetch_http",
        lambda url, *, timeout: _default_fetch(
            url,
            search_html=search_html,
            pages=pages,
        ),
    )

    outcome = discover_article_source_frontier(
        "测试山景区",
        entity_aliases=("测试山别名",),
        topics=("步道",),
        limit=2,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert [source.canonical_url for source in outcome.candidates] == [relevant]
    assert outcome.candidates[0].relevance_score == 0.99
    assert outcome.source_documents()[0]["sourceUseMode"] == "factual_reference_only"
    assert outcome.source_documents()[0]["articleSiteId"] == "frontier_test"
    assert (
        article_frontier_profile.resolve_article_source_binding(
            relevant,
            site_id="frontier_test",
            profile_digest=outcome.candidates[0].profile_digest,
        )["siteId"]
        == "frontier_test"
    )
    require_source_candidate_admission(
        outcome.source_documents()[0],
        require_commercial_article_binding=True,
    )
    assert any(
        row.reason == "entity_alias_topic_relevance_failed"
        for row in outcome.sites[0].frontier
    )
    assert canonicalize_article_url(f"{relevant}?utm_source=x#part") == relevant
    assert outcome.as_evidence()["schema"] == (
        "quwoquan.content.article_source_discovery_evidence"
    )


def test_commercial_article_fetch_binding_rejects_registry_profile_drift(monkeypatch):
    site = _site()
    _install_registry(monkeypatch, site)
    digest = article_frontier_profile.article_profile_digest(site)
    site["siteCrawlProfile"]["allowedPaths"] = ["https://guide.example.test/renamed/*"]

    with pytest.raises(ValueError, match="profile drift"):
        article_frontier_profile.resolve_article_source_binding(
            "https://guide.example.test/article/200.html",
            site_id="frontier_test",
            profile_digest=digest,
        )


def test_commercial_article_fetch_binding_rejects_missing_site_identity(monkeypatch):
    _install_registry(monkeypatch, _site())
    source = {
        "source_id": "frontier_test_001",
        "url": "https://guide.example.test/article/200.html",
        "platform": "测试旅行指南",
        "category": "travelogue",
        "sourceKind": "travelogue",
        "researchLane": "article",
        "relevance": "覆盖测试山景区",
        "match": {
            "accepted": True,
            "reason": "entity_alias_topic_relevance",
            "matchedEntityName": "测试山景区",
            "matchedAlias": "测试山景区",
            "matchedFields": ["title"],
            "relevanceScore": 0.99,
        },
        "articleCommercialAdmission": "commercial_release",
        "sourceDiscoveryProfileDigest": article_frontier_profile.article_profile_digest(
            _site()
        ),
    }

    with pytest.raises(ValueError, match="articleSiteId"):
        require_source_candidate_admission(
            source,
            require_commercial_article_binding=True,
        )


def test_frontier_robots_deny_discards_without_fetching_page(monkeypatch):
    _install_registry(monkeypatch, _site())
    candidate = "https://guide.example.test/article/deny.html"
    fetched: list[str] = []

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        fetched.append(url)
        return _default_fetch(
            url,
            search_html=f'<a href="{candidate}">测试山景区攻略</a>',
            robots="User-agent: *\nDisallow: /article/\n",
        )

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)
    outcome = discover_article_source_frontier(
        "测试山景区",
        limit=1,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert outcome.candidates == ()
    assert candidate not in fetched
    assert any(row.reason == "robots_denied" for row in outcome.sites[0].frontier)


def test_frontier_allowed_paths_fail_closed_before_page_fetch(monkeypatch):
    _install_registry(monkeypatch, _site())
    outside = "https://guide.example.test/list/200.html"
    fetched: list[str] = []

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        fetched.append(url)
        return _default_fetch(
            url,
            search_html=f'<a href="{outside}">测试山景区列表</a>',
        )

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)
    outcome = discover_article_source_frontier(
        "测试山景区",
        limit=1,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert outcome.candidates == ()
    assert outside not in fetched
    assert any(
        row.reason == "outside_allowed_paths" for row in outcome.sites[0].frontier
    )


def test_frontier_admits_only_registry_commercial_article_crawl_sites(monkeypatch):
    admitted = _site()
    not_fetchable = copy.deepcopy(admitted)
    not_fetchable["siteId"] = "not_fetchable"
    not_fetchable["fetchable"] = False
    robots_bypass = copy.deepcopy(admitted)
    robots_bypass["siteId"] = "robots_bypass"
    robots_bypass["siteCrawlProfile"]["robotsPolicy"] = "bypass"
    reference_only = copy.deepcopy(admitted)
    reference_only["siteId"] = "reference_only"
    reference_only["siteCrawlProfile"]["articleCommercialAdmission"] = "reference_only"
    monkeypatch.setattr(
        article_frontier_profile,
        "iter_travel_registry_sites",
        lambda: [not_fetchable, robots_bypass, reference_only, admitted],
    )

    assert [
        row["siteId"] for row in article_frontier_profile.article_search_sites()
    ] == ["frontier_test"]


def test_wikipedia_article_profile_is_registry_admitted() -> None:
    sites = {
        str(row["siteId"]): row
        for row in article_frontier_profile.article_search_sites()
    }

    wikipedia = sites["wikipedia_zh"]
    profile = wikipedia["siteCrawlProfile"]
    assert profile["fetchMode"] == "mediawiki_api"
    assert profile["contentLanes"] == ["article"]
    assert profile["articleCommercialAdmission"] == "commercial_release"
    assert article_frontier_profile.article_url_allowed(
        "https://zh.wikipedia.org/wiki/%E5%8D%97%E6%B5%94%E9%95%87",
        wikipedia,
    )


def test_frontier_rate_limit_and_backoff_are_enforced(monkeypatch):
    candidate = "https://guide.example.test/article/rate.html"
    site = _site(
        strategy={
            "mode": "entity_seeded_scan",
            "seedAxes": ["entity"],
            "seedUrls": [candidate],
            "precheckGates": ["light_fetch", "entity_anchor"],
        },
        requests_per_second=2.0,
    )
    _install_registry(monkeypatch, site)
    candidate_attempts = 0
    sleeps: list[float] = []
    monkeypatch.setattr(article_frontier_robots.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(
        article_frontier_robots.time,
        "sleep",
        lambda seconds: sleeps.append(seconds),
    )

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        nonlocal candidate_attempts
        if url == TERMS_URL:
            return _response(url, body="terms")
        if url == "https://guide.example.test/robots.txt":
            return _response(url, body="User-agent: *\nAllow: /\n")
        if url == candidate:
            candidate_attempts += 1
            if candidate_attempts == 1:
                return _response(url, status=429)
            return _response(
                url,
                body="<html><title>测试山景区攻略</title><body>测试山景区步道。</body></html>",
            )
        raise AssertionError(url)

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)
    outcome = discover_article_source_frontier(
        "测试山景区",
        limit=1,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert len(outcome.candidates) == 1
    assert candidate_attempts == 2
    assert any(seconds >= 0.5 for seconds in sleeps)
    assert any(seconds >= 1.0 for seconds in sleeps)


def test_mediawiki_api_search_discovers_canonical_seed_before_admission(
    monkeypatch,
):
    _install_registry(monkeypatch, _mediawiki_site())
    exact = (
        "https://guide.example.test/wiki/%E6%B5%8B%E8%AF%95%E5%B1%B1%E6%99%AF%E5%8C%BA"
    )
    compound_false_hit = "https://guide.example.test/wiki/%E5%85%B6%E4%BB%96%E5%9C%B0%E7%82%B9"
    related = "https://guide.example.test/wiki/%E6%B5%8B%E8%AF%95%E5%8E%BF"
    fetched: list[str] = []

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        fetched.append(url)
        if url == TERMS_URL:
            return _response(url, body="terms")
        if url.startswith("https://guide.example.test/w/api.php?"):
            return _response(
                url,
                body=json.dumps(
                    {
                        "query": {
                            "search": [
                                {"ns": 0, "title": "其他地点"},
                                {"ns": 0, "title": "测试县"},
                                {"ns": 1, "title": "讨论:测试山景区"},
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
            )
        if url == "https://guide.example.test/robots.txt":
            return _response(url, body="User-agent: *\nAllow: /\n")
        if url == exact:
            return _response(url, status=404)
        if url == compound_false_hit:
            return _response(
                url,
                body=(
                    "<html><title>其他地点旅行指南</title><body>"
                    "良测试山景区附近有餐厅，但页面没有实体链接。"
                    "</body></html>"
                ),
            )
        if url == related:
            return _response(
                url,
                body=(
                    "<html><title>测试县旅行指南</title><body>"
                    '<a href="/wiki/%E6%B5%8B%E8%AF%95%E5%B1%B1%E6%99%AF%E5%8C%BA">'
                    "测试山景区</a>位于测试县，页面介绍步道与交通。"
                    "</body></html>"
                ),
            )
        raise AssertionError(url)

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)
    outcome = discover_article_source_frontier(
        "测试山景区",
        topics=("步道",),
        limit=1,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert [candidate.canonical_url for candidate in outcome.candidates] == [related]
    assert outcome.candidates[0].discovery_method == "mediawiki_api_search"
    assert any("/w/api.php?" in url for url in fetched)
    assert any(
        row.discovery_method == "mediawiki_api_search"
        and row.reason == "mediawiki_search_results:2"
        and row.decision.value == "expanded"
        for row in outcome.sites[0].frontier
    )
    assert any(
        row.canonical_url == exact and row.reason == "page_unreadable"
        for row in outcome.sites[0].frontier
    )
    assert any(
        row.canonical_url == compound_false_hit
        and row.reason == "entity_alias_topic_relevance_failed"
        for row in outcome.sites[0].frontier
    )


def test_mediawiki_search_accepts_long_exact_entity_anchor_in_related_body(
    monkeypatch,
):
    _install_registry(monkeypatch, _mediawiki_site())
    entity = "成都大熊猫繁育研究基地"
    exact = f"https://guide.example.test/wiki/{urllib.parse.quote(entity)}"
    related = f"https://guide.example.test/wiki/{urllib.parse.quote('大熊猫')}"

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        if url == TERMS_URL:
            return _response(url, body="terms")
        if url.startswith("https://guide.example.test/w/api.php?"):
            return _response(
                url,
                body=json.dumps(
                    {"query": {"search": [{"ns": 0, "title": "大熊猫"}]}},
                    ensure_ascii=False,
                ),
            )
        if url == "https://guide.example.test/robots.txt":
            return _response(url, body="User-agent: *\nAllow: /\n")
        if url == exact:
            return _response(url, status=404)
        if url == related:
            return _response(
                url,
                body=(
                    "<html><title>大熊猫</title><body>"
                    "成都大熊猫繁育研究基地承担大熊猫迁地保护与公众教育。"
                    "</body></html>"
                ),
            )
        raise AssertionError(url)

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)
    outcome = discover_article_source_frontier(
        entity,
        topics=("迁地保护",),
        limit=1,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert [candidate.canonical_url for candidate in outcome.candidates] == [related]
    assert outcome.candidates[0].relevance_score == 0.99


def test_mediawiki_api_search_network_failure_is_typed_availability_blocker(
    monkeypatch,
):
    _install_registry(monkeypatch, _mediawiki_site())

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        if url == TERMS_URL:
            return _response(url, body="terms")
        if url.startswith("https://guide.example.test/w/api.php?"):
            return _response(url, status=0, returncode=6)
        if url == "https://guide.example.test/robots.txt":
            return _response(url, body="User-agent: *\nAllow: /\n")
        if url.startswith("https://guide.example.test/wiki/"):
            return _response(url, status=404)
        raise AssertionError(url)

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)
    outcome = discover_article_source_frontier(
        "测试山景区",
        limit=1,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert outcome.candidates == ()
    assert any(
        issue.code.value == "DATA.INFRA.NETWORK_UNREACHABLE"
        and issue.recovery.value == "retry_source_discovery"
        for issue in outcome.issues
    )
    assert any(
        row.discovery_method == "mediawiki_api_search"
        and row.decision.value == "blocked"
        and row.reason == "DATA.INFRA.NETWORK_UNREACHABLE"
        for row in outcome.sites[0].frontier
    )


def test_declared_sitemap_and_pagination_expand_but_undeclared_do_not(
    monkeypatch,
):
    sitemap = "https://guide.example.test/sitemap.xml"
    pagination = "https://guide.example.test/list?page=1"
    detail_a = "https://guide.example.test/article/a.html"
    detail_b = "https://guide.example.test/article/b.html"
    site = _site(
        allowed_paths=["https://guide.example.test/*"],
        strategy={
            "mode": "site_listing_scan",
            "seedAxes": ["entity", "site_listing"],
            "sitemapUrls": [sitemap],
            "pagination": {
                "urlTemplate": "https://guide.example.test/list?page={page}",
                "startPage": 1,
                "maxPages": 1,
            },
            "precheckGates": ["light_fetch", "entity_anchor"],
        },
        max_depth=2,
    )
    _install_registry(monkeypatch, site)
    pages = {
        sitemap: f"<urlset><url><loc>{detail_a}</loc></url></urlset>",
        pagination: f'<html><a href="{detail_b}">测试山景区第二页攻略</a></html>',
        detail_a: "<html><title>测试山景区甲攻略</title><body>测试山景区步道。</body></html>",
        detail_b: "<html><title>测试山景区乙攻略</title><body>测试山景区交通。</body></html>",
    }
    monkeypatch.setattr(
        network_io,
        "fetch_http",
        lambda url, *, timeout: _default_fetch(
            url,
            search_html="",
            pages=pages,
        ),
    )

    outcome = discover_article_source_frontier(
        "测试山景区",
        limit=2,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert {candidate.canonical_url for candidate in outcome.candidates} == {
        detail_a,
        detail_b,
    }
    methods = {row.discovery_method for row in outcome.sites[0].frontier}
    assert {"declared_sitemap", "declared_pagination"} <= methods

    undeclared = _site(
        strategy={
            "mode": "site_listing_scan",
            "seedAxes": ["site_listing"],
            "precheckGates": ["light_fetch"],
        }
    )
    _install_registry(monkeypatch, undeclared)
    second = discover_article_source_frontier(
        "测试山景区",
        limit=1,
        daily_budget=InMemoryDailyPageBudget(),
    )
    assert second.candidates == ()
    assert any(issue.code.value == "DATA.CONTRACT.INVALID" for issue in second.issues)


def test_declared_frontier_does_not_expand_past_max_depth(monkeypatch):
    sitemap = "https://guide.example.test/sitemap.xml"
    detail = "https://guide.example.test/article/depth.html"
    site = _site(
        allowed_paths=["https://guide.example.test/*"],
        strategy={
            "mode": "site_listing_scan",
            "seedAxes": ["site_listing"],
            "sitemapUrls": [sitemap],
            "precheckGates": ["light_fetch"],
        },
        max_depth=0,
        max_pages_per_day=10,
    )
    _install_registry(monkeypatch, site)
    fetched: list[str] = []

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        fetched.append(url)
        return _default_fetch(
            url,
            search_html="",
            pages={sitemap: f"<urlset><url><loc>{detail}</loc></url></urlset>"},
        )

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)
    outcome = discover_article_source_frontier(
        "测试山景区",
        limit=1,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert detail not in fetched
    assert any(row.reason == "max_depth_exceeded" for row in outcome.sites[0].frontier)


def test_frontier_enforces_daily_pages_and_immutability(monkeypatch):
    sitemap = "https://guide.example.test/sitemap.xml"
    detail = "https://guide.example.test/article/depth.html"
    site = _site(
        allowed_paths=["https://guide.example.test/*"],
        strategy={
            "mode": "site_listing_scan",
            "seedAxes": ["site_listing"],
            "sitemapUrls": [sitemap],
            "precheckGates": ["light_fetch"],
        },
        max_depth=0,
        max_pages_per_day=1,
    )
    _install_registry(monkeypatch, site)
    monkeypatch.setattr(
        network_io,
        "fetch_http",
        lambda url, *, timeout: _default_fetch(
            url,
            search_html="",
            pages={sitemap: f"<urlset><url><loc>{detail}</loc></url></urlset>"},
        ),
    )

    outcome = discover_article_source_frontier(
        "测试山景区",
        limit=1,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert outcome.candidates == ()
    assert outcome.sites[0].pages_reserved == 1
    assert any(
        row.reason in {"max_depth_exceeded", "max_pages_per_day_exhausted"}
        for row in outcome.sites[0].frontier
    )
    with pytest.raises(FrozenInstanceError):
        outcome.sites[0].site_id = "mutated"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        outcome.sites.append("mutated")  # type: ignore[attr-defined]


def test_network_unavailable_is_typed_blocked_not_synthetic_success(monkeypatch):
    candidate = "https://guide.example.test/article/network.html"
    _install_registry(
        monkeypatch,
        _site(
            strategy={
                "mode": "entity_seeded_scan",
                "seedAxes": ["entity"],
                "seedUrls": [candidate],
                "precheckGates": ["light_fetch", "entity_anchor"],
            }
        ),
    )

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        if url == TERMS_URL:
            return _response(url, body="terms")
        if url == "https://guide.example.test/robots.txt":
            return _response(url, body="User-agent: *\nAllow: /\n")
        return _response(url, status=0, returncode=6)

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)
    outcome = discover_article_source_frontier(
        "测试山景区",
        limit=1,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert outcome.candidates == ()
    assert any(
        issue.code.value == "DATA.INFRA.NETWORK_UNREACHABLE" for issue in outcome.issues
    )
    assert any(row.decision.value == "blocked" for row in outcome.sites[0].frontier)


@pytest.mark.parametrize("article_commercial_mode", [True, False])
def test_article_plan_mainline_retains_frontier_evidence(
    monkeypatch,
    tmp_path,
    article_commercial_mode,
):
    ctrip_site = {
        **_site(
            allowed_paths=["https://you.ctrip.com/sight/*/*.html"],
        ),
        "siteId": "ctrip_sight_guide",
        "platform": "携程景点指南",
        "domains": ["you.ctrip.com"],
        "urlPatterns": ["https://you.ctrip.com/sight/*/*.html"],
        "extractor": "ctrip_sight_html",
    }
    ctrip_site["siteCrawlProfile"]["allowedPaths"] = [
        "https://you.ctrip.com/sight/*/*.html"
    ]
    candidate = "https://you.ctrip.com/sight/test100/200.html"
    _install_registry(monkeypatch, ctrip_site)

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        if url == TERMS_URL:
            return _response(url, body="terms")
        if url == "https://you.ctrip.com/robots.txt":
            return _response(url, body="User-agent: *\nAllow: /\n")
        if url.startswith("https://search.brave.com/search?"):
            return _response(
                url,
                body=f'<a href="{candidate}">测试山景区游玩攻略</a>',
            )
        if url == candidate:
            return _response(
                url,
                body="<html><title>测试山景区游玩攻略</title><body>测试山景区步道。</body></html>",
            )
        raise AssertionError(url)

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)
    outcome = discover_article_source_frontier(
        "测试山景区",
        limit=1,
        daily_budget=InMemoryDailyPageBudget(),
    )
    frontier_call: dict[str, object] = {}

    def fake_frontier(*args, **kwargs):
        frontier_call["entityId"] = args[0]
        frontier_call["topics"] = tuple(kwargs.get("topics") or ())
        return outcome

    monkeypatch.setattr(
        auto_plan_article,
        "discover_article_source_frontier",
        fake_frontier,
    )
    monkeypatch.setattr(
        auto_plan_article,
        "_homepage_urls_from_current_plan",
        lambda *args, **kwargs: set(),
    )
    report = {"candidates": [], "articleSourceDiscovery": []}
    issues: list[str] = []
    updated: list[dict] = []

    auto_plan_article.write_article_lane(
        execution_id="20260728--travel-article-frontier--test--pilot-001",
        entity_id="测试山景区",
        entity_type="景区",
        vertical="travel",
        selected_lanes={"article"},
        report=report,
        issues=issues,
        updated=updated,
        plan_dir=tmp_path,
        entity_aliases=["测试山景区"],
        topic_terms=["步道"],
        related_wiki_titles=[],
        voyage_url="",
        voyage_page_images=[],
        external_links=[],
        rejected_source_urls=set(),
        prior_article_sources=[],
        homepage_sources=[],
        required_article_bases=1,
        article_commercial_mode=article_commercial_mode,
        force=True,
    )

    plan = json.loads((tmp_path / "article_source_plan.json").read_text())
    assert report["articleSourceDiscovery"][0]["frontierDigest"].startswith("sha256:")
    assert plan["payload"]["sources"][0]["url"] == candidate
    assert plan["payload"]["sources"][0]["sourceUseMode"] == ("factual_reference_only")
    assert frontier_call == {
        "entityId": "测试山景区",
        "topics": ("步道",),
    }
    assert SPEC_REF.endswith("#gwt-001")


def test_ctrip_detail_runtime_overrides_non_fetchable_travelogue_site():
    url = "https://you.ctrip.com/sight/test100/200.html"

    assert _travel_registry_url_fetchable(url) is True
    assert resolve_travel_source_runtime(url) == {
        "siteId": "ctrip_sight_guide",
        "platform": "携程景点指南",
        "category": "travelogue",
        "fetchable": True,
        "extractor": "ctrip_sight_html",
        "licensePolicy": "factual_citation_only",
        "qualityTier": "B",
        "articleCommercialAdmission": "commercial_release",
        "matched": True,
    }


def test_ctrip_extractor_ignores_navigation_and_reviews():
    html = """
    <html><body>
      <nav>详情介绍 用户问答 用户点评</nav>
      <main>
        旅游攻略社区&gt;目的地&gt;测试山景区&gt;
        <h1>测试山景区</h1>
        <p>测试山景区提供森林步道、观景台与瀑布景观。</p>
        <p>开放时间与游览动线应以景区当天公告为准。</p>
        用户问答更多
        <p>这段问答和点评不得进入文章底稿。</p>
      </main>
    </body></html>
    """

    text = extract_page_text(html.encode(), extractor="ctrip_sight_html")

    assert text.startswith("旅游攻略社区>")
    assert "森林步道" in text
    assert "这段问答和点评" not in text
