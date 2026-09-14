# spec_ref: user-scoped exact-revision Wikipedia acquisition acceptance
"""Wikipedia client contract uses an exact revision for both evidence forms."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[4]
SKILL = ROOT / ".agents/skills/content-production"
sys.path.insert(0, str(ROOT / "quwoquan_data/scripts"))
spec = importlib.util.spec_from_file_location("mediawiki_exact_test", SKILL / "scripts/clients/mediawiki.py")
mediawiki = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mediawiki)


class FixtureClient:
    def __init__(self) -> None:
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append((url, kwargs))
        if "/w/api.php?" in url:
            query = parse_qs(urlsplit(url).query)
            assert query["rvprop"] == ["content|ids|timestamp"]
            return json.dumps({"query": {"pages": [{"pageid": 7, "title": "测试", "fullurl": "https://zh.wikipedia.org/wiki/测试", "revisions": [{"revid": 123, "slots": {"main": {"content": "== 简介 ==\n原始内容"}}}]}]}}).encode()
        assert url.endswith("/revision/123/with_html")
        assert "/page/" not in url
        return json.dumps({"id": 123, "key": "测试", "html": "<h2>简介</h2><p>Parsoid 正文</p>"}, ensure_ascii=False).encode()


def test_fetch_and_parse_materialize_two_revision_bound_evidence_files() -> None:
    client = FixtureClient()
    body = mediawiki.wiki_fetch({"title": "测试"}, client)
    envelope = json.loads(body)
    assert envelope["revision"] == envelope["withHtml"]["requestRevision"] == envelope["withHtml"]["response"]["id"] == 123
    assert all("/page/" not in url for url, _kwargs in client.urls)
    rows, texts = mediawiki.wiki_parse(body, {"title": "测试"})
    assert rows[0]["revision"] == 123
    assert any(path.endswith("source.wikitext") and value == "== 简介 ==\n原始内容" for path, value in texts.items())
    assert any(path.endswith("source.parsoid.html") and "Parsoid 正文" in value for path, value in texts.items())
    assert any(path.endswith("source.semantic.json") for path in texts)
    assert "Parsoid 正文" in texts[rows[0]["sourceMarkdownPath"]]


def test_parse_rejects_revision_mismatch() -> None:
    envelope = {"contract": "wikipedia_exact_revision_v1", "revision": 123, "query": {"query": {"pages": [{"pageid": 7, "title": "测试", "revisions": [{"revid": 123, "slots": {"main": {"content": "raw"}}}]}]}}, "withHtml": {"requestRevision": 123, "response": {"id": 124, "html": "<p>x</p>"}}}
    try:
        mediawiki.wiki_parse(json.dumps(envelope).encode(), {"title": "测试"})
    except ValueError as error:
        assert "同一 exact revision" in str(error)
    else:
        raise AssertionError("revision mismatch must fail closed")


class HeaderClient(FixtureClient):
    def get_with_headers(self, url, **kwargs):
        from types import SimpleNamespace
        self.urls.append((url, kwargs))
        return SimpleNamespace(body=json.dumps({"id": 123, "html": "<p>x</p>"}).encode(), headers={"content-revision-id": "124"})


def test_header_revision_mismatch_fails_without_page_fallback() -> None:
    client = HeaderClient()
    try:
        mediawiki.wiki_fetch({"title": "测试"}, client)
    except ValueError as error:
        assert "content-revision-id" in str(error)
    else:
        raise AssertionError("header mismatch must fail closed")
    assert all("/page/" not in url for url, _kwargs in client.urls)
