from __future__ import annotations

import json
import urllib.parse

import pytest
from content.source.research import (
    article_frontier_profile,
    article_frontier_robots,
    network_io,
)
from content.source.research.article_frontier_contract import InMemoryDailyPageBudget
from content.source.research.article_site_page import PageParser
from content.source.research.public_search import discover_article_source_frontier

SPEC_REF = (
    "specs/feature-tree/runtime/runtime-data-engineering/"
    "article-commercial-scale-closure/spec.md#gwt-001"
)
TERMS_URL = "https://terms.example.test/article"
ORIGIN = "https://guide.example.test"


def _response(
    url: str,
    *,
    status: int = 200,
    body: str = "",
) -> network_io.HttpFetchResult:
    return network_io.HttpFetchResult(
        returncode=0,
        status_code=status,
        final_url=url,
        body=body.encode("utf-8"),
    )


def _mediawiki_site() -> dict[str, object]:
    return {
        "siteId": "frontier_test",
        "platform": "测试百科",
        "category": "encyclopedia",
        "domains": ["guide.example.test"],
        "urlPatterns": [f"{ORIGIN}/wiki/*"],
        "fetchable": True,
        "extractor": "wikipedia_api",
        "licensePolicy": "factual_citation_only",
        "qualityTier": "B",
        "siteCrawlProfile": {
            "crawlAllowed": True,
            "contentLanes": ["article"],
            "articleCommercialAdmission": "commercial_release",
            "allowedPaths": [f"{ORIGIN}/wiki/*"],
            "fetchMode": "mediawiki_api",
            "extractor": "wikipedia_api",
            "rightsPolicy": "factual_citation_only",
            "robotsPolicy": "respect_robots_txt",
            "loginPolicy": "public_only",
            "termsUrl": TERMS_URL,
            "rateLimit": {
                "maxRequestsPerSecond": 1000.0,
                "backoffOnStatus": [403, 429],
            },
            "discoveryStrategy": {
                "mode": "entity_seeded_scan",
                "seedAxes": ["entity"],
                "precheckGates": ["light_fetch", "entity_anchor"],
            },
            "maxDepth": 1,
            "maxPagesPerDay": 20,
        },
    }


def test_page_parser_separates_mediawiki_content_links_from_shell_links() -> None:
    parser = PageParser(f"{ORIGIN}/wiki/exact")

    parser.feed(
        "<html><body>"
        '<a href="/wiki/shell">shell</a>'
        '<div id="mw-content-text"><div class="mw-parser-output">'
        '<a href="/wiki/content">content</a>'
        '<h2>参见</h2><a href="/wiki/related">related</a>'
        "</div></div>"
        '<a href="/wiki/footer">footer</a>'
        "</body></html>"
    )

    assert [row.title for row in parser.links] == [
        "shell",
        "content",
        "related",
        "footer",
    ]
    assert [row.title for row in parser.content_links] == ["content", "related"]
    assert [row.title for row in parser.related_content_links] == ["related"]


def test_entity_seeded_content_link_precedes_broad_mediawiki_search_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity = "测试山景区"
    exact = f"{ORIGIN}/wiki/{urllib.parse.quote(entity)}"
    direct = f"{ORIGIN}/wiki/{urllib.parse.quote('直接关联条目')}"
    broad = f"{ORIGIN}/wiki/{urllib.parse.quote('广域搜索条目')}"
    fetched: list[str] = []

    article_frontier_robots._RATE_LIMITERS.clear()
    monkeypatch.setattr(
        article_frontier_profile,
        "iter_travel_registry_sites",
        lambda: [_mediawiki_site()],
    )

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        del timeout
        fetched.append(url)
        if url == TERMS_URL:
            return _response(url, body="terms")
        if url == f"{ORIGIN}/robots.txt":
            return _response(url, body="User-agent: *\nAllow: /\n")
        if url.startswith(f"{ORIGIN}/w/api.php?"):
            return _response(
                url,
                body=json.dumps(
                    {"query": {"search": [{"ns": 0, "title": "广域搜索条目"}]}},
                    ensure_ascii=False,
                ),
            )
        if url == exact:
            return _response(
                url,
                body=(
                    f"<html><head><title>{entity}</title></head><body>"
                    '<a href="/wiki/shell">shell</a>'
                    '<div id="mw-content-text"><div class="mw-parser-output">'
                    '<a href="/wiki/Special:Random">special</a>'
                    + "".join(
                        f'<a href="/wiki/general-{index}">一般链接{index}</a>'
                        for index in range(24)
                    )
                    + '<h2 id="参见">参见</h2>'
                    f'<a href="{direct}">直接关联条目</a>'
                    f'<a href="{direct}#duplicate">重复链接</a>'
                    f"</div></div>{entity}步道资料。"
                    "</body></html>"
                ),
            )
        if url == direct:
            return _response(
                url,
                body=(
                    "<html><head><title>直接关联条目</title></head><body>"
                    '<div id="mw-content-text"><div class="mw-parser-output">'
                    f'<a href="{exact}">{entity}</a>的历史与步道资料。'
                    "</div></div></body></html>"
                ),
            )
        if url == broad:
            return _response(
                url,
                body=(
                    "<html><head><title>广域搜索条目</title></head><body>"
                    f'<a href="{exact}">{entity}</a>的广域搜索资料。'
                    "</body></html>"
                ),
            )
        raise AssertionError(f"unexpected fetch: {url}")

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)

    outcome = discover_article_source_frontier(
        entity,
        topics=("步道",),
        limit=2,
        daily_budget=InMemoryDailyPageBudget(),
    )

    assert [candidate.canonical_url for candidate in outcome.candidates] == [
        exact,
        direct,
    ]
    assert [candidate.discovery_method for candidate in outcome.candidates] == [
        "entity_seeded_scan",
        "entity_seeded_page_link",
    ]
    assert fetched.count(direct) == 1
    assert broad not in fetched
    assert any(
        row.canonical_url == direct
        and row.parent_url == exact
        and row.depth == 1
        and row.decision.value == "accepted"
        for row in outcome.sites[0].frontier
    )
