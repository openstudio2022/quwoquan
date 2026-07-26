from __future__ import annotations

from content.source.fetch_text import extract_page_text
from content.source.research import network_io
from content.source.research.public_search import public_search_article_sources
from content.source.research.source_registry import _travel_registry_url_fetchable
from governance.coverage.source_registry import resolve_travel_source_runtime


def test_public_search_keeps_only_entity_detail_page(monkeypatch):
    html = """
    <a href="https://you.ctrip.com/sight/test100.html">测试地区景点列表</a>
    <a href="https://you.ctrip.com/sight/test100/200.html">
      Ctrip you.ctrip.com › sight › test100 › 200.html 测试山景区游玩攻略【携程攻略】
    </a>
    <a href="https://you.ctrip.com/sight/test100/201.html">其它景区游玩攻略</a>
    """
    monkeypatch.setattr(network_io, "curl_text", lambda _url, *, timeout: html)

    sources = public_search_article_sources("测试山景区", limit=1)

    assert len(sources) == 1
    assert sources[0]["url"] == "https://you.ctrip.com/sight/test100/200.html"
    assert sources[0]["title"] == "测试山景区游玩攻略【携程攻略】"
    assert sources[0]["sourceRole"] == "base"
    assert sources[0]["publishMediaMode"] == "text_only"


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
