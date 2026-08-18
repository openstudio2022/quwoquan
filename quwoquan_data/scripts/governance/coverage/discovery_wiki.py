"""MediaWiki category discovery adapter."""
from __future__ import annotations

import time
from typing import Any

from content.source.research.network_io import NetworkFetchError
from governance.coverage.discovery_shared import (
    _RETRY_BACKOFF_MULTIPLIER,
    _WIKI_CATEGORY_DEPTH,
    _WIKI_CATEGORY_PAGE_LIMIT,
    _WIKI_HOST,
    _WIKI_RETRY_BACKOFF_SECONDS,
    _WIKI_RETRY_LIMIT,
    wiki_category_seeds,
    _category_blocked,
    _research_network,
    _title_blocked,
)


def _wiki_api_with_retry(
    bridge: Any,
    host: str,
    params: dict[str, str | int],
    *,
    retries: int = _WIKI_RETRY_LIMIT,
    backoff_seconds: float = _WIKI_RETRY_BACKOFF_SECONDS,
) -> dict[str, Any]:
    """wiki API 带限流退避：请求未完成时按指数退避重试，耗尽仍失败则上抛。

    2026-07-09 实测：连续分类请求会触发 zh.wikipedia 限流返回非 JSON 体。
    退避耗尽后失败必须留在失败态，由调用方把该分类记入缺口，不得静默凑数。
    """
    delay = backoff_seconds
    for attempt in range(max(1, retries)):
        try:
            return bridge.wiki_api(host, params)
        except NetworkFetchError:
            if attempt + 1 >= retries:
                raise
            time.sleep(delay)
            delay *= _RETRY_BACKOFF_MULTIPLIER
    raise NetworkFetchError(
        f"https://{host}/w/api.php",
        status_code=0,
        returncode=-1,
        reason="retry budget is not positive",
    )


def _wiki_category_members(
    bridge: Any,
    category: str,
) -> tuple[list[str], list[str], bool]:
    """返回 (条目标题, 子分类标题, 请求是否完整)；带 cmcontinue 翻页。"""
    pages: list[str] = []
    subcats: list[str] = []
    cont: str | None = None
    for _ in range(_WIKI_CATEGORY_PAGE_LIMIT):
        params: dict[str, str | int] = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": 500,
            "format": "json",
        }
        if cont:
            params["cmcontinue"] = cont
        try:
            data = _wiki_api_with_retry(bridge, _WIKI_HOST, params)
        except NetworkFetchError:
            return pages, subcats, False
        members = ((data.get("query") or {}).get("categorymembers")) or []
        for member in members:
            # 注意：条目主命名空间 ns=0 是 falsy，禁止用 `or -1` 兜底（会把全部条目丢成 -1）。
            raw_ns = member.get("ns")
            ns = int(raw_ns) if raw_ns is not None else -1
            title = str(member.get("title") or "")
            if ns == 0 and title:
                pages.append(title)
            elif ns == 14 and title:
                subcats.append(title)
        cont = ((data.get("continue") or {}).get("cmcontinue")) or None
        if not cont:
            break
    return pages, subcats, True


def _wiki_page_details(
    bridge: Any,
    titles: list[str],
    *,
    failed_batches: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """批量取条目 intro extract + categories（50/批）。"""
    details: dict[str, dict[str, Any]] = {}
    for index in range(0, len(titles), 50):
        chunk = titles[index : index + 50]
        try:
            data = _wiki_api_with_retry(
                bridge,
                _WIKI_HOST,
                {
                    "action": "query",
                    "prop": "extracts|categories|pageprops",
                    "titles": "|".join(chunk),
                    "exintro": 1,
                    "explaintext": 1,
                    "exlimit": "max",
                    "cllimit": "max",
                    "redirects": "1",
                    "format": "json",
                },
            )
        except NetworkFetchError:
            if failed_batches is not None:
                failed_batches.append("|".join(chunk))
            continue
        for page in ((data.get("query") or {}).get("pages") or {}).values():
            if not isinstance(page, dict):
                continue
            title = str(page.get("title") or "")
            if not title or int(page.get("pageid") or -1) <= 0:
                continue
            details[title] = {
                "pageid": int(page.get("pageid") or 0),
                "qid": str((page.get("pageprops") or {}).get("wikibase_item") or ""),
                "extract": str(page.get("extract") or "")[:1200],
                "categories": [
                    str(category.get("title") or "")
                    for category in (page.get("categories") or [])
                ],
            }
    return details


def discover_wiki_candidates(
    province: str,
    *,
    max_depth: int = _WIKI_CATEGORY_DEPTH,
    limit: int | None = None,
    bridge: Any | None = None,
    failed_units: list[str] | None = None,
) -> list[dict[str, Any]]:
    """省级 wiki 分类树递归发现（含政府名录镜像分类）。

    对 MediaWiki 主机的请求间隔由 `network_io.wiki_api` 按主机统一节流，
    这里不再另行 sleep，避免同一约束出现两个执行点。
    """
    bridge = bridge or _research_network()
    seeds = wiki_category_seeds(province)
    seen_cats: set[str] = set()
    seen_pages: set[str] = set()
    page_sources: dict[str, list[str]] = {}
    queue: list[tuple[str, int]] = [(seed, 0) for seed in seeds]
    while queue:
        category, depth = queue.pop(0)
        if category in seen_cats or depth > max_depth:
            continue
        seen_cats.add(category)
        pages, subcats, ok = _wiki_category_members(bridge, category)
        if not ok:
            if failed_units is not None:
                failed_units.append(category)
            continue
        for title in pages:
            if _title_blocked(title):
                continue
            page_sources.setdefault(title, []).append(category)
            seen_pages.add(title)
        for subcategory in subcats:
            if not _category_blocked(subcategory):
                queue.append((subcategory, depth + 1))
        if limit and len(seen_pages) >= limit:
            break
    titles = sorted(seen_pages)[:limit]
    details = _wiki_page_details(
        bridge,
        titles,
        failed_batches=failed_units,
    )
    out: list[dict[str, Any]] = []
    for title in titles:
        detail = details.get(title) or {}
        out.append(
            {
                "name": title,
                "province": province,
                "source": "wiki_category",
                "identityRefs": {
                    "qid": str(detail.get("qid") or ""),
                    "wikipediaPageId": int(detail.get("pageid") or 0),
                },
                "sourceCategories": sorted(set(page_sources.get(title) or [])),
                "categories": detail.get("categories") or [],
                "extract": detail.get("extract") or "",
            }
        )
    return out
