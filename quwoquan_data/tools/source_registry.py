from __future__ import annotations

import urllib.parse
from typing import Any

from common import SOURCE_REGISTRY_PATH, read_yaml


DEFAULT_SOURCE_REGISTRY: dict[str, Any] = {
    "schemaVersion": "quwoquan_data.source_registry",
    "authoritySources": [
        {
            "sourceId": "wikipedia_zh",
            "domain": "zh.wikipedia.org",
            "sourceKind": "authority",
            "fetchPolicy": "open_html",
            "verticals": ["general", "travel", "auto", "image"],
            "mediaTypes": ["article"],
            "urlTemplate": "https://zh.wikipedia.org/wiki/{name_enc}",
            "defaultWeight": 100,
        },
        {
            "sourceId": "baidu_baike",
            "domain": "baike.baidu.com",
            "sourceKind": "authority",
            "fetchPolicy": "open_html",
            "verticals": ["general", "travel", "auto", "image"],
            "mediaTypes": ["article"],
            "urlTemplate": "https://baike.baidu.com/item/{name_enc}",
            "defaultWeight": 100,
        },
        {
            "sourceId": "sogou_baike",
            "domain": "baike.sogou.com",
            "sourceKind": "authority",
            "fetchPolicy": "open_html",
            "verticals": ["general", "travel", "auto", "image"],
            "mediaTypes": ["article"],
            "searchTemplate": "https://baike.sogou.com/Search.e?sp=S{query_enc}",
            "defaultWeight": 92,
        },
        {
            "sourceId": "kuaidong_baike",
            "domain": "www.baike.com",
            "sourceKind": "authority",
            "fetchPolicy": "pending_review",
            "verticals": ["general", "travel", "auto", "image"],
            "mediaTypes": ["article"],
            "searchTemplate": "https://www.baike.com/search?keyword={query_enc}",
            "defaultWeight": 86,
        },
        {
            "sourceId": "quark_baike",
            "domain": "quark.sm.cn",
            "sourceKind": "authority",
            "fetchPolicy": "pending_review",
            "verticals": ["general", "travel", "auto", "image"],
            "mediaTypes": ["article"],
            "searchTemplate": "https://quark.sm.cn/s?q={query_enc}",
            "defaultWeight": 80,
        },
        {
            "sourceId": "qiuwen_baike",
            "domain": "www.qiuwenbaike.cn",
            "sourceKind": "authority",
            "fetchPolicy": "pending_review",
            "verticals": ["general", "travel", "auto", "image"],
            "mediaTypes": ["article"],
            "searchTemplate": "https://www.qiuwenbaike.cn/index.php?search={query_enc}",
            "defaultWeight": 78,
        },
        {
            "sourceId": "zgbk",
            "domain": "www.zgbk.com",
            "sourceKind": "authority",
            "fetchPolicy": "open_html",
            "verticals": ["general", "travel", "auto", "image"],
            "mediaTypes": ["article"],
            "searchTemplate": "https://www.zgbk.com/ecph/words?SiteID=1&query={query_enc}",
            "defaultWeight": 82,
        },
    ],
    "contentSources": [
        {
            "sourceId": "toutiao",
            "domain": "so.toutiao.com",
            "sourceKind": "content",
            "fetchPolicy": "pending_review",
            "discoveryMode": "search_entry",
            "verticals": ["general", "travel", "auto"],
            "mediaTypes": ["article", "image"],
            "searchTemplate": "https://so.toutiao.com/search?keyword={query_enc}",
        },
        {
            "sourceId": "xiaohongshu",
            "domain": "www.xiaohongshu.com",
            "sourceKind": "content",
            "fetchPolicy": "manual_seed_only",
            "discoveryMode": "search_entry",
            "verticals": ["general", "travel", "auto", "image"],
            "mediaTypes": ["article", "image"],
            "searchTemplate": "https://www.xiaohongshu.com/search_result?keyword={query_enc}",
        },
        {
            "sourceId": "weibo",
            "domain": "s.weibo.com",
            "sourceKind": "content",
            "fetchPolicy": "pending_review",
            "discoveryMode": "search_entry",
            "verticals": ["general", "travel", "auto"],
            "mediaTypes": ["article", "image"],
            "searchTemplate": "https://s.weibo.com/weibo?q={query_enc}",
        },
        {
            "sourceId": "zhihu",
            "domain": "www.zhihu.com",
            "sourceKind": "content",
            "fetchPolicy": "pending_review",
            "discoveryMode": "search_entry",
            "verticals": ["general", "travel", "auto"],
            "mediaTypes": ["article"],
            "searchTemplate": "https://www.zhihu.com/search?type=content&q={query_enc}",
        },
        {
            "sourceId": "ctrip_travel",
            "domain": "you.ctrip.com",
            "sourceKind": "content",
            "fetchPolicy": "open_html",
            "discoveryMode": "search_entry",
            "verticals": ["travel"],
            "mediaTypes": ["article", "image"],
            "searchTemplate": "https://you.ctrip.com/searchsite/Sight?query={query_enc}",
        },
        {
            "sourceId": "mafengwo",
            "domain": "www.mafengwo.cn",
            "sourceKind": "content",
            "fetchPolicy": "open_html",
            "discoveryMode": "search_entry",
            "verticals": ["travel"],
            "mediaTypes": ["article", "image"],
            "searchTemplate": "https://www.mafengwo.cn/search/q.php?q={query_enc}",
        },
        {
            "sourceId": "qunar",
            "domain": "www.qunar.com",
            "sourceKind": "content",
            "fetchPolicy": "open_html",
            "discoveryMode": "search_entry",
            "verticals": ["travel"],
            "mediaTypes": ["article", "image"],
            "searchTemplate": "https://www.qunar.com/ss/search?wd={query_enc}",
        },
        {
            "sourceId": "qyer",
            "domain": "search.qyer.com",
            "sourceKind": "content",
            "fetchPolicy": "pending_review",
            "discoveryMode": "search_entry",
            "verticals": ["travel"],
            "mediaTypes": ["article", "image"],
            "searchTemplate": "https://search.qyer.com/index?wd={query_enc}",
        },
        {
            "sourceId": "pinterest",
            "domain": "www.pinterest.com",
            "sourceKind": "content",
            "fetchPolicy": "manual_seed_only",
            "discoveryMode": "search_entry",
            "verticals": ["image", "travel"],
            "mediaTypes": ["image"],
            "searchTemplate": "https://www.pinterest.com/search/pins/?q={query_enc}",
        },
        {
            "sourceId": "tuchong",
            "domain": "tuchong.com",
            "sourceKind": "content",
            "fetchPolicy": "open_html",
            "discoveryMode": "search_entry",
            "verticals": ["image", "travel"],
            "mediaTypes": ["image"],
            "searchTemplate": "https://tuchong.com/search?query={query_enc}",
        },
        {
            "sourceId": "five_hundred_px",
            "domain": "500px.com",
            "sourceKind": "content",
            "fetchPolicy": "pending_review",
            "discoveryMode": "search_entry",
            "verticals": ["image"],
            "mediaTypes": ["image"],
            "searchTemplate": "https://500px.com/search?type=photos&query={query_enc}",
        },
        {
            "sourceId": "lofter",
            "domain": "www.lofter.com",
            "sourceKind": "content",
            "fetchPolicy": "pending_review",
            "discoveryMode": "search_entry",
            "verticals": ["image", "general"],
            "mediaTypes": ["article", "image"],
            "searchTemplate": "https://www.lofter.com/front/search?q={query_enc}",
        },
        {
            "sourceId": "autohome",
            "domain": "sou.autohome.com.cn",
            "sourceKind": "content",
            "fetchPolicy": "pending_review",
            "discoveryMode": "search_entry",
            "verticals": ["auto"],
            "mediaTypes": ["article", "image"],
            "searchTemplate": "https://sou.autohome.com.cn/zonghe?q={query_enc}",
        },
        {
            "sourceId": "dongchedi",
            "domain": "www.dongchedi.com",
            "sourceKind": "content",
            "fetchPolicy": "pending_review",
            "discoveryMode": "search_entry",
            "verticals": ["auto"],
            "mediaTypes": ["article", "image"],
            "searchTemplate": "https://www.dongchedi.com/search?keyword={query_enc}",
        },
        {
            "sourceId": "yiche",
            "domain": "so.yiche.com",
            "sourceKind": "content",
            "fetchPolicy": "pending_review",
            "discoveryMode": "search_entry",
            "verticals": ["auto"],
            "mediaTypes": ["article", "image"],
            "searchTemplate": "https://so.yiche.com/search?keyword={query_enc}",
        },
    ],
}


def load_source_registry() -> dict[str, Any]:
    if SOURCE_REGISTRY_PATH.exists():
        payload = read_yaml(SOURCE_REGISTRY_PATH)
        return payload if isinstance(payload, dict) else DEFAULT_SOURCE_REGISTRY
    return DEFAULT_SOURCE_REGISTRY


def authority_sources(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = registry.get("authoritySources") or []
    return [row for row in rows if isinstance(row, dict)]


def content_sources(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = registry.get("contentSources") or []
    return [row for row in rows if isinstance(row, dict)]


def prioritized_content_sources(
    registry: dict[str, Any],
    *,
    target_verticals: list[str],
    media_modes: list[str],
    platform_priority: list[str],
) -> list[dict[str, Any]]:
    priority_map = {source_id: index for index, source_id in enumerate(platform_priority)}
    rows: list[dict[str, Any]] = []
    wanted_verticals = set(target_verticals or [])
    wanted_media = set(media_modes or [])
    for row in content_sources(registry):
        verticals = {str(item).strip() for item in row.get("verticals", []) if str(item).strip()}
        media_types = {str(item).strip() for item in row.get("mediaTypes", []) if str(item).strip()}
        if wanted_verticals and not (verticals & wanted_verticals or "general" in verticals):
            continue
        if wanted_media and not (media_types & wanted_media):
            continue
        rows.append(row)
    rows.sort(
        key=lambda row: (
            priority_map.get(str(row.get("sourceId", "")).strip(), 10_000),
            str(row.get("sourceId", "")).strip(),
        )
    )
    return rows


def _format_template(template: str, query: str, entity_name: str) -> str:
    return (
        template.replace("{query}", query)
        .replace("{query_enc}", urllib.parse.quote(query))
        .replace("{entity_name}", entity_name)
        .replace("{entity_name_enc}", urllib.parse.quote(entity_name))
        .replace("{name}", entity_name)
        .replace("{name_enc}", urllib.parse.quote(entity_name))
    )


def authority_source_url(source: dict[str, Any], entity_name: str) -> str:
    template = str(source.get("urlTemplate") or source.get("searchTemplate") or "").strip()
    return _format_template(template, entity_name, entity_name) if template else ""


def content_source_url(source: dict[str, Any], *, query: str, entity_name: str) -> str:
    template = str(source.get("searchTemplate") or source.get("urlTemplate") or "").strip()
    return _format_template(template, query, entity_name) if template else ""


def source_fetch_policy(source: dict[str, Any]) -> str:
    return str(source.get("fetchPolicy") or "pending_review").strip() or "pending_review"

