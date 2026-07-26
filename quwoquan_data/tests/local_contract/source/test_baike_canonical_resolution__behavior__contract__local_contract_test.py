from __future__ import annotations

import sys
from pathlib import Path
import urllib.parse

import pytest


DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.source.research import network_io  # noqa: E402
from content.source.research.baike_com import (  # noqa: E402
    BaikePageResolution,
    geo_context_terms_from_ref,
    resolve_toutiao_baike_page,
)
from content.source.research.baidu_baike import (  # noqa: E402
    BaiduBaikeResolution,
    decode_baidu_baike_html,
    resolve_baidu_baike_page,
)
from content.source.research.auto_plan_homepage import (  # noqa: E402
    HomepageResearchInput,
    _candidate_sources,
)
from core.baike_source_contract import (  # noqa: E402
    BAIDU_BAIKE_CANONICAL_RESOLUTION,
    TOUTIAO_BAIKE_CANONICAL_RESOLUTION,
)
from content.source.contracts import (  # noqa: E402
    HomepageAuthorityProvider,
    QualifiedHomepageSource,
)


def _baidu_page(*, title: str, abstract: str) -> bytes:
    return (
        "<html><head>"
        f"<title>{title}_百度百科</title>"
        "</head><body>"
        f"<h1>{title}</h1><p>{abstract}</p>"
        "<dl><dt>位置</dt><dd>test-region-a绍兴市嵊州市</dd>"
        "<dt>开放时间</dt><dd>全年开放，具体安排以景区公告为准。</dd></dl>"
        "</body></html>"
    ).encode("utf-8")


def test_baidu_public_entry_decodes_dom_text() -> None:
    page = decode_baidu_baike_html(
        _baidu_page(
            title="嵊州越剧小镇",
            abstract="嵊州越剧小镇位于test-region-a嵊州市，是以越剧文化为主题的旅游目的地。",
        ),
        url="https://baike.baidu.com/item/%E5%B5%8A%E5%B7%9E%E8%B6%8A%E5%89%A7%E5%B0%8F%E9%95%87",
    )

    assert page is not None
    assert page.title == "嵊州越剧小镇"
    assert "test-region-a绍兴市嵊州市" in page.text
    assert "开放时间" in page.text


def test_baidu_public_entry_resolution_requires_exact_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _baidu_page(
        title="嵊州越剧小镇",
        abstract="嵊州越剧小镇位于test-region-a绍兴市嵊州市，展示越剧文化。",
    )
    monkeypatch.setattr(
        network_io,
        "fetch_http",
        lambda url, *, timeout: network_io.HttpFetchResult(
            returncode=0,
            status_code=200,
            final_url="https://baike.baidu.com/item/%E5%B5%8A%E5%B7%9E%E8%B6%8A%E5%89%A7%E5%B0%8F%E9%95%87",
            body=body,
        ),
    )

    result = resolve_baidu_baike_page(
        "嵊州越剧小镇",
        geo_context_terms=("test-region-a", "绍兴市", "嵊州市"),
    )

    assert result is not None
    assert result.title == "嵊州越剧小镇"
    assert result.url == "https://baike.baidu.com/item/%E5%B5%8A%E5%B7%9E%E8%B6%8A%E5%89%A7%E5%B0%8F%E9%95%87"
    assert result.match_confidence == BAIDU_BAIKE_CANONICAL_RESOLUTION.canonical_confidence


def _page(*, title: str, description: str) -> bytes:
    return (
        "<html><head>"
        f"<title>{title} - 快懂百科</title>"
        f'<meta name="description" content="{description}">'
        "</head></html>"
    ).encode("utf-8")


def _response(*, final_url: str, title: str, description: str) -> network_io.HttpFetchResult:
    return network_io.HttpFetchResult(
        returncode=0,
        status_code=200,
        final_url=final_url,
        body=_page(title=title, description=description),
    )


def test_exact_entity_resolves_only_to_contract_wikiid(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        assert timeout > 0
        calls.append(url)
        return _response(
            final_url="https://www.baike.com/wikiid/7360066735180479986",
            title="古堰画乡",
            description="古堰画乡位于test-region-a丽水市莲都区。",
        )

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)

    result = resolve_toutiao_baike_page(
        "古堰画乡",
        geo_context_terms=("test-region-a", "丽水市"),
    )

    assert result is not None
    assert result.title == "古堰画乡"
    assert result.matched_term == "古堰画乡"
    assert result.match_confidence == TOUTIAO_BAIKE_CANONICAL_RESOLUTION.canonical_confidence
    assert calls == [f"{TOUTIAO_BAIKE_CANONICAL_RESOLUTION.base_url}%E5%8F%A4%E5%A0%B0%E7%94%BB%E4%B9%A1"]


def test_ambiguous_entity_uses_city_qualified_search_without_changing_identity(
    monkeypatch: pytest.MonkeyPatch,
):
    requested_terms: list[str] = []

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        assert timeout > 0
        term = urllib.parse.unquote(url).rsplit("/", 1)[-1]
        requested_terms.append(term)
        if term == "西湖":
            return _response(
                final_url="https://www.baike.com/wikiid/7231409871634874402",
                title="昆明湖",
                description="昆明湖位于北京市海淀区，古称西湖。",
            )
        return _response(
            final_url="https://www.baike.com/wikiid/7261415731643695145",
            title="西湖",
            description="西湖位于test-region-a杭州市西湖区。",
        )

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)

    result = resolve_toutiao_baike_page(
        "西湖",
        geo_context_terms=("test-region-a", "杭州市", "西湖区"),
    )

    assert result is not None
    assert result.title == "西湖"
    assert result.matched_term == "杭州西湖"
    assert requested_terms == ["西湖", "杭州西湖"]


def test_exact_title_with_wrong_region_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        network_io,
        "fetch_http",
        lambda _url, *, timeout: _response(
            final_url="https://www.baike.com/wikiid/118559190450243118",
            title="狮子岩",
            description="狮子岩位于贵州省贵阳市，是当地山地景观。",
        ),
    )

    assert resolve_toutiao_baike_page(
        "狮子岩",
        geo_context_terms=("test-region-a", "舟山市", "定海区"),
    ) is None


def test_alias_requires_matching_geo_context(monkeypatch: pytest.MonkeyPatch):
    responses = {
        "云和仙宫湖景区": network_io.HttpFetchResult(
            returncode=0,
            status_code=404,
            final_url="https://www.baike.com/wiki/%E4%BA%91%E5%92%8C%E4%BB%99%E5%AE%AB%E6%B9%96%E6%99%AF%E5%8C%BA",
            body=b"",
        ),
        "仙宫湖": _response(
            final_url="https://www.baike.com/wikiid/123456789",
            title="仙宫湖",
            description="仙宫湖位于test-region-a丽水市云和县。",
        ),
    }

    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        assert timeout > 0
        decoded_url = urllib.parse.unquote(url)
        term = next(term for term in responses if decoded_url.endswith(term))
        return responses[term]

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)

    result = resolve_toutiao_baike_page(
        "云和仙宫湖景区",
        entity_aliases=("仙宫湖",),
        geo_context_terms=("test-region-a", "丽水市", "云和县"),
    )

    assert result is not None
    assert result.matched_term == "仙宫湖"
    assert result.match_confidence == TOUTIAO_BAIKE_CANONICAL_RESOLUTION.alias_confidence


def test_alias_with_wrong_region_is_rejected(monkeypatch: pytest.MonkeyPatch):
    def fake_fetch(url: str, *, timeout: int) -> network_io.HttpFetchResult:
        assert timeout > 0
        return _response(
            final_url="https://www.baike.com/wikiid/123456789",
            title="仙宫湖",
            description="仙宫湖位于福建省福州市。",
        )

    monkeypatch.setattr(network_io, "fetch_http", fake_fetch)

    assert resolve_toutiao_baike_page(
        "云和仙宫湖景区",
        entity_aliases=("仙宫湖",),
        geo_context_terms=("test-region-a", "丽水市", "云和县"),
    ) is None


def test_non_contract_redirect_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        network_io,
        "fetch_http",
        lambda url, *, timeout: _response(
            final_url="https://www.baike.com/search?keyword=%E5%8F%A4%E5%A0%B0%E7%94%BB%E4%B9%A1",
            title="古堰画乡",
            description="古堰画乡位于test-region-a丽水市。",
        ),
    )

    assert resolve_toutiao_baike_page("古堰画乡") is None


def test_geo_context_terms_are_derived_from_canonical_tag_ref():
    assert geo_context_terms_from_ref("地域/地球/亚洲/中国/test-region-a/丽水市/莲都区") == (
        "test-region-a",
        "丽水市",
        "莲都区",
    )
    assert geo_context_terms_from_ref("地域/未知") == ()


def test_verified_wikiid_resolution_enters_homepage_source_plan(tmp_path: Path):
    qualified_source = QualifiedHomepageSource(
        provider=HomepageAuthorityProvider.TOUTIAO_BAIKE,
        title="古堰画乡景区",
        url="https://www.baike.com/wikiid/7360066735180479986",
    )
    sources = _candidate_sources(HomepageResearchInput(
        execution_id="20260717--travel-homepage-coverage--test-region-a--scale-004",
        entity_id="古堰画乡",
        entity_aliases=("古堰画乡景区",),
        vertical="travel",
        plan_dir=tmp_path,
        report={"sourceUnavailable": []},
        updated=[],
        qualified_homepage_source=qualified_source,
        wiki_page_images=(),
        prior_image_pool=(),
        voyage_page_images=(),
        commons=(),
        hint_commons=(),
        wikidata_commons=(),
        openverse=(),
        rejected_source_urls=frozenset(),
        force=True,
    ))

    source = next(row for row in sources if row["source_id"] == "home_toutiao_baike")
    assert [row["source_id"] for row in sources] == ["home_toutiao_baike"]
    assert source["url"] == qualified_source.url
    assert source["sourceKind"] == "toutiao_baike"
    assert source["extractor"] == "toutiao_baike_html"
    assert source["policyRevision"] == "encyclopedia-primary"
