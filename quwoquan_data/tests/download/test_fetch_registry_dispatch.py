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


def test_fetch_source_payload_blocks_non_fetchable_registry_site():
    try:
        fetch_mod.fetch_source_payload("https://www.mafengwo.cn/i/123456.html")
    except RuntimeError as exc:
        assert "fetchable=false" in str(exc)
        return
    raise AssertionError("expected RuntimeError for non-fetchable travelogue site")


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


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"fetch registry dispatch tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
