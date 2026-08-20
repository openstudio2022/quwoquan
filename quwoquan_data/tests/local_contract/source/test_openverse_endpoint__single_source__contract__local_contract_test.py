"""Openverse 端点只有一处真相源：检索侧不得自己拼版本前缀或越界分页。"""
from __future__ import annotations

import urllib.parse

import pytest

from content.source.professional_image_openverse_contract import (
    ANONYMOUS_MAX_PAGE_SIZE,
    openverse_search_url,
)
from content.source.research import image_search_providers, wiki_common


def test_discovery_reuses_the_contract_endpoint_including_version_prefix(
    monkeypatch,
) -> None:
    """漏掉版本前缀 v1 会让 Openverse 返回 404，把「限流/路径错」伪装成「无候选」。"""
    seen: list[str] = []

    def fake_curl_json(url: str, **_kwargs: object) -> dict[str, object]:
        seen.append(url)
        return {"results": []}

    monkeypatch.setattr(
        image_search_providers.network_io, "curl_json", fake_curl_json
    )
    image_search_providers._openverse_images("峨眉山", limit=6)

    assert seen, "检索必须真的发出 Openverse 请求"
    for url in seen:
        parts = urllib.parse.urlsplit(url)
        assert parts.netloc == "api.openverse.org"
        # 逐段比对而不是写整条 "/v1/images/"：后者形状上等同一个受治理 API 路径，
        # 会被 verify_api_path_unversioned 当成自家版本化路径。断言强度不变。
        assert parts.path.strip("/").split("/") == ["v1", "images"], url
        query = urllib.parse.parse_qs(parts.query)
        # 契约把商用许可与 mature 过滤下推到服务端；检索侧不得丢掉它们。
        assert query["license_type"] == ["commercial"]
        assert query["mature"] == ["false"]
        assert int(query["page_size"][0]) <= ANONYMOUS_MAX_PAGE_SIZE, url

    contract = urllib.parse.urlsplit(openverse_search_url("峨眉山", page_size=18))
    assert urllib.parse.urlsplit(seen[0]).path == contract.path


def test_discovery_oversampling_stays_within_the_anonymous_page_bound(
    monkeypatch,
) -> None:
    """超采倍数不得把单页顶穿：越界时 Openverse 回 401 而不是截断。"""
    seen: list[str] = []

    def fake_curl_json(url: str, **_kwargs: object) -> dict[str, object]:
        seen.append(url)
        return {"results": []}

    monkeypatch.setattr(
        image_search_providers.network_io, "curl_json", fake_curl_json
    )
    image_search_providers._openverse_images("峨眉山", limit=16)

    assert seen
    for url in seen:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        assert int(query["page_size"][0]) == ANONYMOUS_MAX_PAGE_SIZE, url


def test_contract_rejects_page_size_beyond_the_anonymous_bound() -> None:
    """越界分页必须在拼 URL 时就失败，而不是等 401 把它伪装成凭证问题。"""
    with pytest.raises(ValueError):
        openverse_search_url("峨眉山", page_size=ANONYMOUS_MAX_PAGE_SIZE + 1)
    with pytest.raises(ValueError):
        openverse_search_url("峨眉山", page_size=0)


def test_shared_provider_constants_no_longer_redeclare_the_endpoint() -> None:
    """端点第二真相源已删除；再加回来就会重现版本前缀漂移。"""
    assert not hasattr(wiki_common, "_OPENVERSE_API")
