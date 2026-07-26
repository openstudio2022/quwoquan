"""fetch.py registry extractor dispatch contract tests."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import content.source.fetch_text as fetch_mod  # noqa: E402
import content.source.fetch_payload as payload_mod  # noqa: E402
import content.source.mediawiki_page as mediawiki_mod  # noqa: E402
from content.source.mediawiki_page import MediaWikiPageBundle  # noqa: E402
from content.source.research.text_match import _wiki_resolved_title_matches_entity  # noqa: E402


def _mediawiki_bundle(
    rendered_text: str,
    *,
    wikitext: str | None = None,
    requested_title: str = "九寨沟",
    resolved_title: str | None = None,
) -> MediaWikiPageBundle:
    resolved = resolved_title or requested_title
    revision_text = wikitext if wikitext is not None else rendered_text
    return MediaWikiPageBundle(
        requested_title=requested_title,
        resolved_title=resolved,
        redirect_chain=(
            (f"{requested_title} -> {resolved}",)
            if requested_title != resolved
            else ()
        ),
        page_id=1,
        revision_id=2,
        content_sha256="a" * 64,
        rendered_text=rendered_text,
        wikitext=revision_text,
        rendered_image_titles=(),
        raw='{"query":{}}',
    )


def test_mediawiki_page_bundle_preserves_resolved_redirect_identity():
    def fake_api(_host: str, _params: dict) -> dict:
        return {
            "query": {
                "redirects": [{"from": "南雁荡山", "to": "雁荡山"}],
                "pages": {
                    "1": {
                        "pageid": 1,
                        "title": "雁荡山",
                        "extract": "雁荡山正文",
                        "revisions": [
                            {"revid": 2, "slots": {"main": {"*": "雁荡山正文"}}}
                        ],
                        "images": [],
                    }
                },
            }
        }

    original = mediawiki_mod.network_io.wiki_api
    try:
        mediawiki_mod.network_io.wiki_api = fake_api
        payload = mediawiki_mod.fetch_mediawiki_page_bundle("zh.wikipedia.org", "南雁荡山")
    finally:
        mediawiki_mod.network_io.wiki_api = original

    assert payload is not None
    assert payload.requested_title == "南雁荡山"
    assert payload.resolved_title == "雁荡山"
    assert payload.redirect_chain == ("南雁荡山 -> 雁荡山",)
    assert payload.rendered_text == "雁荡山正文"
    assert not _wiki_resolved_title_matches_entity(payload.resolved_title, "南雁荡山")


def test_extract_page_text_dispatches_by_registry_extractor():
    html = "<html><body><div>普通正文</div></body></html>".encode("utf-8")
    orig_wiki = fetch_mod._wikipedia_api_plaintext
    orig_qunar = fetch_mod._qunar_html_plaintext
    orig_official = fetch_mod._static_official_plaintext
    try:
        fetch_mod._wikipedia_api_plaintext = lambda url: "wiki正文"
        fetch_mod._qunar_html_plaintext = lambda html_bytes, url="": "qunar正文"
        fetch_mod._static_official_plaintext = lambda url: "official正文"
        assert fetch_mod.extract_page_text(html, "https://zh.wikipedia.org/wiki/九寨沟", extractor="wikipedia_api") == "wiki正文"
        assert fetch_mod.extract_page_text(html, "https://travel.qunar.com/p-oi123", extractor="qunar_html") == "qunar正文"
        assert fetch_mod.extract_page_text(html, "https://aba.gov.cn/detail", extractor="static_official_html") == "official正文"
        generic = fetch_mod.extract_page_text(html, "https://example.com/a", extractor="generic_html")
        assert "普通正文" in generic
    finally:
        fetch_mod._wikipedia_api_plaintext = orig_wiki
        fetch_mod._qunar_html_plaintext = orig_qunar
        fetch_mod._static_official_plaintext = orig_official


def test_baidu_baike_html_adapter_fetches_public_entry_text(monkeypatch):
    body = (
        "<html><head><title>嵊州越剧小镇_百度百科</title></head>"
        "<body><h1>嵊州越剧小镇</h1>"
        "<p>嵊州越剧小镇位于test-region-a嵊州市，是越剧文化旅游目的地。</p>"
        "<dl><dt>位置</dt><dd>test-region-a嵊州市</dd></dl></body></html>"
    ).encode("utf-8")
    requested_urls: list[str] = []

    def fake_get(url: str, *, timeout: int):
        assert timeout > 0
        requested_urls.append(url)
        return 200, body, "application/json"

    monkeypatch.setattr(payload_mod, "_http_get_bytes", fake_get)

    result = payload_mod.fetch_source_payload(
        "https://baike.baidu.com/item/%E5%B5%8A%E5%B7%9E%E8%B6%8A%E5%89%A7%E5%B0%8F%E9%95%87",
        source={
            "sourceKind": "baidu_baike",
            "sourceTitle": "嵊州越剧小镇",
            "extractor": "baidu_baike_html",
        },
    )

    assert result["runtime"]["rawFormat"] == "baidu_baike_html"
    assert "嵊州越剧小镇位于test-region-a嵊州市" in result["text"]
    assert "位置" in result["text"] and "test-region-a嵊州市" in result["text"]
    assert len(requested_urls) == 1
    assert requested_urls[0].startswith("https://baike.baidu.com/item/")


def test_generic_html_extractor_preserves_inline_images_as_figures():
    html = (
        "<html><body><p>第一段正文。</p>"
        "<figure><img src='https://img.example/a.jpg' alt='湖边栈道'><figcaption>湖边栈道</figcaption></figure>"
        "<p>第二段正文。</p></body></html>"
    ).encode("utf-8")

    text = fetch_mod.extract_page_text(html, "https://example.com/a", extractor="generic_html")

    assert "第一段正文" in text
    assert ":::figure" in text
    assert "![湖边栈道](asset://source-inline-001)" in text
    assert text.index("第一段正文") < text.index(":::figure") < text.index("第二段正文")


def test_inline_images_capture_src_and_align_with_placeholders():
    """RC3：内联 <img> 的 src 被捕获，清单与正文 asset://source-inline-NNN 同序对齐。"""
    html = (
        "<html><body><p>九寨沟第一段。</p>"
        "<figure><img src='https://img.example/lake.jpg' alt='五花海'></figure>"
        "<p>九寨沟第二段。</p>"
        "<img data-src='https://img.example/falls.jpg' alt='珍珠滩瀑布'>"
        "<p>九寨沟第三段。</p></body></html>"
    ).encode("utf-8")

    text, inline = fetch_mod.extract_page_text_with_inline_images(
        html, "https://travel.qunar.com/youji/123", extractor="qunar_html"
    )

    # 正文与 extract_page_text 一致，占位按出现顺序排列。
    assert text == fetch_mod.extract_page_text(
        html, "https://travel.qunar.com/youji/123", extractor="qunar_html"
    )
    assert "![五花海](asset://source-inline-001)" in text
    assert "![珍珠滩瀑布](asset://source-inline-002)" in text
    assert text.index("source-inline-001") < text.index("source-inline-002")

    assert [row["placeholderId"] for row in inline] == [
        "source-inline-001",
        "source-inline-002",
    ]
    assert [row["src"] for row in inline] == [
        "https://img.example/lake.jpg",
        "https://img.example/falls.jpg",
    ]
    assert [row["caption"] for row in inline] == ["五花海", "珍珠滩瀑布"]


def test_inline_images_skip_data_uri_and_empty_src():
    """data:/空 src 不产生悬空占位，也不进入内联清单；真实图仍按序捕获。"""
    html = (
        "<html><body>"
        "<img src='data:image/gif;base64,R0lGODlh'>"
        "<img src=''>"
        "<p>正文一段。</p>"
        "<img src='https://img.example/real.jpg' alt='真实配图'>"
        "</body></html>"
    ).encode("utf-8")

    text, inline = fetch_mod.extract_page_text_with_inline_images(
        html, "https://example.com/a", extractor="generic_html"
    )

    assert "data:image" not in text
    assert text.count("asset://source-inline-") == 1
    assert "![真实配图](asset://source-inline-001)" in text
    assert [row["src"] for row in inline] == ["https://img.example/real.jpg"]


def test_inline_images_resolve_relative_src_against_page_url():
    """相对 src 按页面 URL 解析为绝对（同源就地下载需要绝对地址）。"""
    html = (
        "<html><body><p>正文。</p>"
        "<img src='/photos/p1.jpg' alt='栈道'>"
        "<img src='sub/p2.jpg' alt='栈道二'></body></html>"
    ).encode("utf-8")

    _text, inline = fetch_mod.extract_page_text_with_inline_images(
        html, "https://travel.qunar.com/youji/7870084", extractor="qunar_html"
    )

    assert [row["src"] for row in inline] == [
        "https://travel.qunar.com/photos/p1.jpg",
        "https://travel.qunar.com/youji/sub/p2.jpg",
    ]
    assert [row["rawSrc"] for row in inline] == ["/photos/p1.jpg", "sub/p2.jpg"]


def test_non_html_extractor_returns_no_inline_images():
    """wikipedia_api 等非 HTML extractor 的图片由 source plan 单一入口处理。"""
    orig_wiki = fetch_mod._wikipedia_api_plaintext
    try:
        fetch_mod._wikipedia_api_plaintext = lambda url: "维基正文"
        text, inline = fetch_mod.extract_page_text_with_inline_images(
            b"<html></html>",
            "https://zh.wikipedia.org/wiki/九寨沟",
            extractor="wikipedia_api",
        )
    finally:
        fetch_mod._wikipedia_api_plaintext = orig_wiki
    assert text == "维基正文"
    assert inline == []


def test_fetch_source_payload_blocks_non_fetchable_registry_site():
    try:
        payload_mod.fetch_source_payload("https://www.mafengwo.cn/i/123456.html")
    except RuntimeError as exc:
        assert "fetchable=false" in str(exc)
        return
    raise AssertionError("expected RuntimeError for non-fetchable travelogue site")


def test_fetch_source_payload_allows_source_level_fetchable_override():
    orig_http = payload_mod._http_get_bytes
    try:
        payload_mod._http_get_bytes = lambda url, timeout=20, max_bytes=0: (
            200,
            "<html><body>沈阳世博园 游记 正文 门票 开放 交通 徒步 转场 返程</body></html>".encode("utf-8"),
            "",
        )
        payload = payload_mod.fetch_source_payload(
            "https://you.ctrip.com/travels/shenyang155/4062166.html",
            source={"fetchable": True},
        )
    finally:
        payload_mod._http_get_bytes = orig_http
    assert payload["statusCode"] == 200
    assert payload["runtime"]["sourceFetchableOverride"] is True
    assert "沈阳世博园" in payload["text"]


def test_fetch_source_payload_returns_same_source_inline_images():
    """RC3：图文混排游记 payload 携带同源内联图清单（绝对 URL，与正文占位同序）。"""
    html = (
        "<html><body><p>九寨沟游记开篇正文段。</p>"
        "<figure><img src='/photo/lake.jpg' alt='五花海'></figure>"
        "<p>沿栈道继续走的第二段正文。</p>"
        "<img src='https://img.example/falls.jpg' alt='珍珠滩瀑布'>"
        "</body></html>"
    ).encode("utf-8")
    orig_http = payload_mod._http_get_bytes
    try:
        payload_mod._http_get_bytes = lambda url, timeout=20, max_bytes=0: (
            200,
            html,
            "",
        )
        payload = payload_mod.fetch_source_payload(
            "https://travel.qunar.com/youji/7870084",
            source={"extractor": "qunar_html", "fetchable": True},
        )
    finally:
        payload_mod._http_get_bytes = orig_http

    inline = payload["inlineImages"]
    assert [row["placeholderId"] for row in inline] == [
        "source-inline-001",
        "source-inline-002",
    ]
    # 相对 src 按页面 URL 解析为绝对，绝对 src 原样保留。
    assert [row["src"] for row in inline] == [
        "https://travel.qunar.com/photo/lake.jpg",
        "https://img.example/falls.jpg",
    ]
    # 正文占位与清单同序对齐。
    assert payload["text"].index("source-inline-001") < payload["text"].index("source-inline-002")


def test_fetch_source_payload_uses_dpm_official_registry_source():
    html = "<html><body>故宫博物院 开放时间 在线订票 交通路线 参观须知</body></html>"
    orig_http = payload_mod._http_get_bytes
    orig_curl = fetch_mod._curl_get_text
    try:
        payload_mod._http_get_bytes = lambda url, timeout=20, max_bytes=0: (
            200,
            html.encode("utf-8"),
            "",
        )
        fetch_mod._curl_get_text = lambda url, timeout=90: html
        payload = payload_mod.fetch_source_payload("https://www.dpm.org.cn/Home.html")
    finally:
        payload_mod._http_get_bytes = orig_http
        fetch_mod._curl_get_text = orig_curl

    assert payload["runtime"]["siteId"] == "scenic_official"
    assert payload["runtime"]["extractor"] == "static_official_html"
    assert payload["runtime"]["fetchable"] is True
    assert "故宫博物院" in payload["text"]
    assert "在线订票" in payload["text"]


def test_fetch_source_payload_uses_source_extractor_override():
    orig_http = payload_mod._http_get_bytes
    orig_bundle = payload_mod.fetch_mediawiki_page_bundle_for_url
    try:
        payload_mod._http_get_bytes = lambda url, timeout=20, max_bytes=0: (_ for _ in ()).throw(
            AssertionError("wikipedia_api should fetch API evidence directly")
        )
        payload_mod.fetch_mediawiki_page_bundle_for_url = lambda _url, **_kwargs: _mediawiki_bundle(
            "维基导游专用正文",
            requested_title="雅安",
        )
        payload = payload_mod.fetch_source_payload(
            "https://zh.wikivoyage.org/wiki/雅安",
            source={"extractor": "wikipedia_api", "fetchable": True},
        )
    finally:
        payload_mod._http_get_bytes = orig_http
        payload_mod.fetch_mediawiki_page_bundle_for_url = orig_bundle
    assert payload["runtime"]["extractor"] == "wikipedia_api"
    assert payload["runtime"]["sourceExtractorOverride"] is True
    assert payload["runtime"]["rawFormat"] == "mediawiki_api_json"
    assert payload["text"] == "维基导游专用正文"


def test_mediawiki_page_bundle_follows_image_continuation_without_silent_cap():
    seen: list[dict] = []

    def fake_api(_host: str, params: dict) -> dict:
        seen.append(dict(params))
        if "imcontinue" in params:
            return {
                "query": {
                    "pages": {"1": {"pageid": 1, "images": [{"title": "File:b.jpg"}]}}
                }
            }
        return {
            "continue": {"imcontinue": "1|b.jpg", "continue": "||"},
            "query": {
                "pages": {
                    "1": {
                        "pageid": 1,
                        "title": "黄果树瀑布",
                        "extract": "黄果树瀑布稳定百科正文",
                        "revisions": [
                            {"revid": 2, "slots": {"main": {"*": "黄果树瀑布稳定百科正文"}}}
                        ],
                        "images": [{"title": "File:a.jpg"}],
                    }
                }
            },
        }

    original = mediawiki_mod.network_io.wiki_api
    try:
        mediawiki_mod.network_io.wiki_api = fake_api
        bundle = mediawiki_mod.fetch_mediawiki_page_bundle("zh.wikipedia.org", "黄果树瀑布")
    finally:
        mediawiki_mod.network_io.wiki_api = original

    assert bundle is not None
    assert bundle.rendered_image_titles == ("File:a.jpg", "File:b.jpg")
    assert len(seen) == 2


def test_mediawiki_source_qualification_omits_image_inventory() -> None:
    seen: list[dict] = []

    def fake_api(_host: str, params: dict) -> dict:
        seen.append(dict(params))
        return {
            "query": {
                "pages": {
                    "1": {
                        "pageid": 1,
                        "title": "测试景区",
                        "extract": "测试景区稳定百科正文",
                        "revisions": [
                            {"revid": 2, "slots": {"main": {"*": "测试景区稳定百科正文"}}}
                        ],
                    }
                }
            }
        }

    original = mediawiki_mod.network_io.wiki_api
    try:
        mediawiki_mod.network_io.wiki_api = fake_api
        bundle = mediawiki_mod.fetch_mediawiki_page_bundle(
            "zh.wikipedia.org",
            "测试景区",
            include_images=False,
        )
    finally:
        mediawiki_mod.network_io.wiki_api = original

    assert bundle is not None
    assert bundle.rendered_image_titles == ()
    assert len(seen) == 1
    assert seen[0]["prop"] == "extracts|revisions"
    assert "imlimit" not in seen[0]


def test_wikipedia_api_payload_only_carries_text_layout_not_second_image_path():
    orig_bundle = payload_mod.fetch_mediawiki_page_bundle_for_url
    try:
        payload_mod.fetch_mediawiki_page_bundle_for_url = lambda _url, **_kwargs: _mediawiki_bundle(
            "== 概述 ==\n九寨沟正文段落。",
            wikitext="== 概述 ==\n九寨沟正文段落。\n[[File:Jiuzhaigou.jpg|thumb|五花海]]\n",
        )
        payload = payload_mod.fetch_source_payload(
            "https://zh.wikivoyage.org/wiki/九寨沟",
            source={"extractor": "wikipedia_api", "fetchable": True},
        )
    finally:
        payload_mod.fetch_mediawiki_page_bundle_for_url = orig_bundle
    # 结构化口径：layout ok 时 source 正文从 IR 渲染（章节 + 图片原位占位 + 仅原图注）。
    assert "## 概述" in payload["text"]
    assert "九寨沟正文段落。" in payload["text"]
    assert "![五花海](asset://source-inline-001)" in payload["text"]
    # 统一结构化 IR 随 payload 返回（wikitext 前端），供 write_source_unit 落盘。
    layout = payload["layout"]
    assert layout["parseStatus"] == "ok"
    figures = [b for b in layout["blocks"] if b["type"] == "figure"]
    assert figures and figures[0]["fileTitle"] == "Jiuzhaigou.jpg"
    assert figures[0]["caption"] == "五花海"
    assert "assets" not in payload


def test_static_official_plaintext_reads_ems517_api_payload():
    payload = {
        "code": 0,
        "data": {
            "title": "峨眉山景区公告",
            "content": "<div>金顶索道因天气原因临时调整运营时间，请提前查看最新通知。</div>",
        },
    }
    orig_curl = fetch_mod._curl_get_text
    try:
        fetch_mod._curl_get_text = lambda url, timeout=90: __import__("json").dumps(payload, ensure_ascii=False)
        text = fetch_mod._static_official_plaintext("http://www.ems517.com/new_api/api/article/123")
    finally:
        fetch_mod._curl_get_text = orig_curl
    assert "峨眉山景区公告" in text
    assert "金顶索道" in text


def test_static_official_plaintext_reads_ems517_spa_shell_via_api():
    html_shell = "<html><body><div id='app'></div></body></html>"

    def fake_curl(url: str, timeout: int = 90) -> str:
        if url.endswith("/new/visitor?preferential=1"):
            return html_shell
        if url.endswith("/api/category/31"):
            return (
                '{"code":0,"data":{"title":"景区公告","itemId":"31",'
                '"content":"<div>景区今日开放，建议错峰出行。</div>"}}'
            )
        if "api/category/" in url:
            return '{"code":0,"data":{"title":"分栏","content":"<div>游览须知</div>"}}'
        if "api/notice/list" in url:
            return (
                '{"code":0,"data":{"records":[{"title":"公告一",'
                '"content":"<div>雷洞坪区域临时交通管制。</div>"}]}}'
            )
        if "api/article/list" in url:
            return (
                '{"code":0,"data":{"records":[{"title":"攻略一",'
                '"content":"<div>观日出需注意保暖。</div>"}]}}'
            )
        raise AssertionError(f"unexpected url {url}")

    orig_curl = fetch_mod._curl_get_text
    try:
        fetch_mod._curl_get_text = fake_curl
        text = fetch_mod._static_official_plaintext("http://www.ems517.com/new/visitor?preferential=1")
    finally:
        fetch_mod._curl_get_text = orig_curl
    assert "景区今日开放" in text
    assert "雷洞坪区域临时交通管制" in text
    assert "观日出需注意保暖" in text


def test_static_official_plaintext_reads_public_spa_bundle_copy():
    shell = "<html><head><title>加载中...</title></head><body><script src=js/app.abc.js></script></body></html>"
    bundle = (
        "window.x=JSON.parse('{\"jp\":\"観光地概況\","
        "\"cn\":\"蜀南竹海景区全年开放\","
        "\"intro\":\"蜀南竹海旅游度假区竭诚为您服务，竹文化和山水游憩是核心特色。\"}')"
    )

    def fake_curl(url: str, timeout: int = 90) -> str:
        if url == "https://www.snzh.cn/":
            return shell
        if url == "https://www.snzh.cn/js/app.abc.js":
            return bundle
        raise AssertionError(f"unexpected url {url}")

    orig_curl = fetch_mod._curl_get_text
    try:
        fetch_mod._curl_get_text = fake_curl
        text = fetch_mod._static_official_plaintext("https://www.snzh.cn/")
    finally:
        fetch_mod._curl_get_text = orig_curl
    assert "蜀南竹海景区全年开放" in text
    assert "竹文化和山水游憩" in text
    assert "観光地概況" not in text


def test_static_official_plaintext_reads_commented_meta_description():
    shell = """
    <html><head>
    <!-- <meta name="description" content="金华双龙风景旅游区位于test-region-a金华市北郊的金华山麓，是国家首批AAAA级旅游景区、国家级风景名胜区和国家森林公园。"> -->
    </head><body>景区公告</body></html>
    """

    orig_curl = fetch_mod._curl_get_text
    try:
        fetch_mod._curl_get_text = lambda url, timeout=90: shell
        text = fetch_mod._static_official_plaintext("http://www.shuanglongdong.com/")
    finally:
        fetch_mod._curl_get_text = orig_curl
    assert "金华双龙风景旅游区位于test-region-a金华市北郊" in text
    assert "国家级风景名胜区" in text


def test_wikipedia_api_plaintext_follows_redirects():
    original = mediawiki_mod.fetch_mediawiki_page_bundle_for_url
    try:
        mediawiki_mod.fetch_mediawiki_page_bundle_for_url = lambda _url: _mediawiki_bundle(
            "惠山古镇位于江苏省无锡市梁溪区。",
            requested_title="惠山古镇",
        )
        text = fetch_mod._wikipedia_api_plaintext("https://zh.wikipedia.org/wiki/惠山古镇")
    finally:
        mediawiki_mod.fetch_mediawiki_page_bundle_for_url = original
    assert "惠山古镇位于江苏省无锡市梁溪区" in text


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"fetch registry dispatch tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
