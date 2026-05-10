"""
旅行向 URL 发现辅助（合规优先）。

- Wikivoyage 发现逻辑已集中在 crawl_topic_pool._wikivoyage_opensearch_urls。
- 对马蜂窝 / 小红书 / 微博 / 头条等强反爬或登录墙站点，本模块**不**默认抓取 HTML；
  仅提供「搜索入口 URL」模板，便于人工在浏览器中打开后把落地文章 URL 写入
  runtime/seed/travel_urls_by_topic.ndjson，再由 crawl pool-bootstrap --travel-seed 合并入池。
"""

from __future__ import annotations

import urllib.parse


def mafengwo_search_url(query: str) -> str:
    return "https://www.mafengwo.cn/search/q.php?q=" + urllib.parse.quote(query)


def ctrip_search_url(query: str) -> str:
    return "https://you.ctrip.com/sight/search?q=" + urllib.parse.quote(query)


def qunar_search_url(query: str) -> str:
    return "https://www.qunar.com/ss/search?wd=" + urllib.parse.quote(query)


def portal_urls_for_attraction(name: str) -> dict[str, str]:
    q = f"{name} 攻略"
    return {
        "mafengwo_search": mafengwo_search_url(q),
        "ctrip_search": ctrip_search_url(name),
        "qunar_search": qunar_search_url(name),
    }
