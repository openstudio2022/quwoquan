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

import download.fetch as fetch_mod  # noqa: E402


def test_extract_page_text_dispatches_by_registry_extractor():
    html = "<html><body><div>普通正文</div></body></html>".encode("utf-8")
    orig_wiki = fetch_mod._wikipedia_api_plaintext
    orig_baike = fetch_mod._baike_html_plaintext
    orig_qunar = fetch_mod._qunar_html_plaintext
    orig_official = fetch_mod._static_official_plaintext
    try:
        fetch_mod._wikipedia_api_plaintext = lambda url: "wiki正文"
        fetch_mod._baike_html_plaintext = lambda url: "baike正文"
        fetch_mod._qunar_html_plaintext = lambda html_bytes, url="": "qunar正文"
        fetch_mod._static_official_plaintext = lambda url: "official正文"
        assert fetch_mod.extract_page_text(html, "https://zh.wikipedia.org/wiki/九寨沟", extractor="wikipedia_api") == "wiki正文"
        assert fetch_mod.extract_page_text(html, "https://baike.baidu.com/item/九寨沟", extractor="baidu_baike_html") == "baike正文"
        assert fetch_mod.extract_page_text(html, "https://travel.qunar.com/p-oi123", extractor="qunar_html") == "qunar正文"
        assert fetch_mod.extract_page_text(html, "https://aba.gov.cn/detail", extractor="static_official_html") == "official正文"
        generic = fetch_mod.extract_page_text(html, "https://example.com/a", extractor="generic_html")
        assert "普通正文" in generic
    finally:
        fetch_mod._wikipedia_api_plaintext = orig_wiki
        fetch_mod._baike_html_plaintext = orig_baike
        fetch_mod._qunar_html_plaintext = orig_qunar
        fetch_mod._static_official_plaintext = orig_official


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


def test_fetch_source_payload_blocks_non_fetchable_registry_site():
    try:
        fetch_mod.fetch_source_payload("https://www.mafengwo.cn/i/123456.html")
    except RuntimeError as exc:
        assert "fetchable=false" in str(exc)
        return
    raise AssertionError("expected RuntimeError for non-fetchable travelogue site")


def test_fetch_source_payload_allows_source_level_fetchable_override():
    orig_http = fetch_mod._http_get_bytes
    try:
        fetch_mod._http_get_bytes = lambda url, timeout=20, max_redirects=4, max_retries=4: (
            200,
            "<html><body>沈阳世博园 游记 正文 门票 开放 交通 徒步 转场 返程</body></html>".encode("utf-8"),
            "",
        )
        payload = fetch_mod.fetch_source_payload(
            "https://you.ctrip.com/travels/shenyang155/4062166.html",
            source={"fetchable": True},
        )
    finally:
        fetch_mod._http_get_bytes = orig_http
    assert payload["statusCode"] == 200
    assert payload["runtime"]["sourceFetchableOverride"] is True
    assert "沈阳世博园" in payload["text"]


def test_fetch_source_payload_uses_dpm_official_registry_source():
    html = "<html><body>故宫博物院 开放时间 在线订票 交通路线 参观须知</body></html>"
    orig_http = fetch_mod._http_get_bytes
    orig_curl = fetch_mod._curl_get_text
    try:
        fetch_mod._http_get_bytes = lambda url, timeout=20, max_redirects=4, max_retries=4: (
            200,
            html.encode("utf-8"),
            "",
        )
        fetch_mod._curl_get_text = lambda url, timeout=90: html
        payload = fetch_mod.fetch_source_payload("https://www.dpm.org.cn/Home.html")
    finally:
        fetch_mod._http_get_bytes = orig_http
        fetch_mod._curl_get_text = orig_curl

    assert payload["runtime"]["siteId"] == "scenic_official"
    assert payload["runtime"]["extractor"] == "static_official_html"
    assert payload["runtime"]["fetchable"] is True
    assert "故宫博物院" in payload["text"]
    assert "在线订票" in payload["text"]


def test_fetch_source_payload_uses_source_extractor_override():
    orig_http = fetch_mod._http_get_bytes
    orig_curl = fetch_mod._curl_get_text
    try:
        fetch_mod._http_get_bytes = lambda url, timeout=20, max_redirects=4, max_retries=4: (_ for _ in ()).throw(
            AssertionError("wikipedia_api should fetch API evidence directly")
        )
        fetch_mod._curl_get_text = lambda url, timeout=90: (
            '{"query":{"pages":{"1":{"extract":"维基导游专用正文"}}}}'
        )
        payload = fetch_mod.fetch_source_payload(
            "https://zh.wikivoyage.org/wiki/雅安",
            source={"extractor": "wikipedia_api", "fetchable": True},
        )
    finally:
        fetch_mod._http_get_bytes = orig_http
        fetch_mod._curl_get_text = orig_curl
    assert payload["runtime"]["extractor"] == "wikipedia_api"
    assert payload["runtime"]["sourceExtractorOverride"] is True
    assert payload["runtime"]["rawFormat"] == "mediawiki_api_json"
    assert payload["text"] == "维基导游专用正文"


def test_wikipedia_api_payload_falls_back_to_http_bytes_when_curl_fails():
    orig_http = fetch_mod._http_get_bytes
    orig_curl = fetch_mod._curl_get_text

    def fake_http(url: str, timeout=20, max_redirects=4, max_retries=4):
        _ = (timeout, max_redirects, max_retries)
        assert "/w/api.php?" in url
        return (
            200,
            '{"query":{"pages":{"1":{"extract":"黄果树瀑布稳定百科正文"}}}}'.encode("utf-8"),
            "",
        )

    try:
        fetch_mod._curl_get_text = lambda url, timeout=90: (_ for _ in ()).throw(
            RuntimeError("curl transient failure")
        )
        fetch_mod._http_get_bytes = fake_http
        payload = fetch_mod.fetch_source_payload(
            "https://zh.wikipedia.org/wiki/%E9%BB%84%E6%9E%9C%E6%A0%91%E7%80%91%E5%B8%83"
        )
    finally:
        fetch_mod._http_get_bytes = orig_http
        fetch_mod._curl_get_text = orig_curl

    assert payload["statusCode"] == 200
    assert payload["runtime"]["extractor"] == "wikipedia_api"
    assert payload["runtime"]["rawFormat"] == "mediawiki_api_json"
    assert payload["text"] == "黄果树瀑布稳定百科正文"


def test_wikipedia_api_payload_repairs_malformed_mediawiki_unicode_escape_for_parse_only():
    raw = '{"query":{"pages":{"1":{"extract":"中国 \\uWikivoyage 旅行正文"}}}}'
    orig_curl = fetch_mod._curl_get_text
    try:
        fetch_mod._curl_get_text = lambda url, timeout=90: raw
        payload = fetch_mod.fetch_source_payload(
            "https://zh.wikivoyage.org/wiki/中国",
            source={"extractor": "wikipedia_api", "fetchable": True},
        )
    finally:
        fetch_mod._curl_get_text = orig_curl

    assert payload["htmlBytes"] == raw.encode("utf-8")
    assert payload["text"] == "中国 \\uWikivoyage 旅行正文"


def test_wikipedia_api_payload_carries_rights_checked_image_assets():
    def fake_curl(url: str, timeout: int = 90) -> str:
        if "prop=extracts" in url:
            return '{"query":{"pages":{"1":{"extract":"九寨沟位于四川省阿坝藏族羌族自治州。"}}}}'
        if "prop=pageimages%7Cimages" in url or "prop=pageimages|images" in url:
            return '{"query":{"pages":{"1":{"images":[{"title":"File:Jiuzhaigou.jpg"}]}}}}'
        if "prop=imageinfo" in url:
            return (
                '{"query":{"pages":{"2":{"title":"File:Jiuzhaigou.jpg","imageinfo":[{'
                '"url":"https://upload.wikimedia.org/wikipedia/commons/a/a1/Jiuzhaigou.jpg",'
                '"descriptionurl":"https://commons.wikimedia.org/wiki/File:Jiuzhaigou.jpg",'
                '"mime":"image/jpeg","width":1200,"height":800,'
                '"extmetadata":{'
                '"LicenseShortName":{"value":"CC BY-SA 4.0"},'
                '"LicenseUrl":{"value":"https://creativecommons.org/licenses/by-sa/4.0/"},'
                '"Artist":{"value":"Example Photographer"}'
                '}}]}}}}'
            )
        raise AssertionError(f"unexpected url {url}")

    orig_curl = fetch_mod._curl_get_text
    try:
        fetch_mod._curl_get_text = fake_curl
        payload = fetch_mod.fetch_source_payload(
            "https://zh.wikivoyage.org/wiki/九寨沟",
            source={"extractor": "wikipedia_api", "fetchable": True},
        )
    finally:
        fetch_mod._curl_get_text = orig_curl
    assert payload["text"].startswith("九寨沟位于")
    asset = payload["assets"][0]
    assert asset["license"] == "CC BY-SA 4.0"
    assert asset["credit"] == "Example Photographer"
    assert asset["sourceUrl"].startswith("https://commons.wikimedia.org/")
    assert asset["termsUrl"].startswith("https://creativecommons.org/")
    assert asset["usageScope"] == "wikimedia_commons_open_license_publish_candidate"


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
    <!-- <meta name="description" content="金华双龙风景旅游区位于浙江省金华市北郊的金华山麓，是国家首批AAAA级旅游景区、国家级风景名胜区和国家森林公园。"> -->
    </head><body>景区公告</body></html>
    """

    orig_curl = fetch_mod._curl_get_text
    try:
        fetch_mod._curl_get_text = lambda url, timeout=90: shell
        text = fetch_mod._static_official_plaintext("http://www.shuanglongdong.com/")
    finally:
        fetch_mod._curl_get_text = orig_curl
    assert "金华双龙风景旅游区位于浙江省金华市北郊" in text
    assert "国家级风景名胜区" in text


def test_wikipedia_api_plaintext_follows_redirects():
    seen: dict[str, str] = {}

    def fake_curl(url: str, timeout: int = 90) -> str:
        seen["url"] = url
        return '{"query":{"pages":{"1":{"extract":"惠山古镇位于江苏省无锡市梁溪区。"}}}}'

    orig_curl = fetch_mod._curl_get_text
    try:
        fetch_mod._curl_get_text = fake_curl
        text = fetch_mod._wikipedia_api_plaintext("https://zh.wikipedia.org/wiki/惠山古镇")
    finally:
        fetch_mod._curl_get_text = orig_curl
    assert "惠山古镇位于江苏省无锡市梁溪区" in text
    assert "redirects=1" in seen["url"]


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"fetch registry dispatch tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
