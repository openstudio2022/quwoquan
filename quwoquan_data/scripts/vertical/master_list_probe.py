"""主清单源可用性预筛（WP2.4）：轻量探测百科主源有无，回填 sourceReadiness。

CLI-first 三段式的 [CLI prepare]：只探测「有无百科主源」（zh.wikipedia /
zh.wikivoyage 标题命中、百度百科词条页存在），不下载全文、不做质量终审；
质量与配图证据由 download 阶段承担。

回填口径（sourceReadiness 唯一真相源 = 主清单 yaml 本身）：
- ready             至少一个百科主源可用
- no_primary_source 三路探测均给出结论性缺失（不丢弃，等扩源补全）
- pending           保持不动（探测不结论：网络断路 / 反爬拦截 / 短路）

节流与断点续跑：
- 复用 download.research_plan 的 curl 层（自带 host 断路器 network_breaker）；
- 每个请求间 sleep --sleep-seconds（默认 0.5s）；
- 逐市州文件回写，重跑时默认跳过已 ready / no_primary_source 的叶子（--recheck 重探）。
"""
from __future__ import annotations

import time
import urllib.parse
from typing import Any

from _common.coverage_master_list import (
    dump_master_list_file,
    iter_master_leaves,
    load_master_list_file,
    master_list_files,
)

_WIKI_HOSTS = ("zh.wikipedia.org", "zh.wikivoyage.org")

# 百度百科词条缺失/拦截标记（存在页正文含词条内容；拦截页不可作缺失结论）。
_BAIDU_MISS_MARKERS = ("百度百科尚未收录", "抱歉，您所访问的页面不存在", "浏览的页面不存在")
_BAIDU_BLOCK_MARKERS = ("安全验证", "验证码", "百度安全")


def _research_bridge() -> Any:
    """加载 download.research_plan 真实 curl/wiki API 层（含断路器）。"""
    import download.research_plan as research_plan  # noqa: PLC0415

    return research_plan


def _probe_terms(leaf: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for value in (
        str(leaf.get("canonicalName") or ""),
        str(leaf.get("name") or ""),
        *[str(a) for a in (leaf.get("aliases") or [])],
    ):
        value = value.strip()
        if value and value not in terms:
            terms.append(value)
    return terms[:4]


def _wiki_probe(bridge: Any, host: str, term: str) -> tuple[bool, bool]:
    """返回 (命中, 结论性)。API 返回缺 query 视为网络/拦截不结论。"""
    data = bridge._wiki_api(
        host,
        {"action": "query", "titles": term, "redirects": "1", "format": "json"},
    )
    query = data.get("query") if isinstance(data, dict) else None
    if not isinstance(query, dict):
        return False, False
    for page in (query.get("pages") or {}).values():
        if isinstance(page, dict) and int(page.get("pageid") or -1) > 0:
            return True, True
    return False, True


def _baidu_probe(bridge: Any, term: str) -> tuple[bool, bool]:
    """百度百科词条页存在性；拦截/空响应不结论。"""
    url = f"https://baike.baidu.com/item/{urllib.parse.quote(term)}"
    text = bridge._curl_text(url, timeout=15)
    if not text:
        return False, False
    if any(marker in text for marker in _BAIDU_BLOCK_MARKERS):
        return False, False
    if any(marker in text for marker in _BAIDU_MISS_MARKERS):
        return False, True
    # 存在页 <title> 形如「{词条}_百度百科」。
    return ("百度百科" in text and term in text), True


def probe_leaf(leaf: dict[str, Any], *, sleep_seconds: float = 0.5) -> dict[str, Any]:
    """探测单叶子；返回 {status, evidence}；status ∈ ready/no_primary_source/pending。"""
    bridge = _research_bridge()
    terms = _probe_terms(leaf)
    conclusive_all = True
    for term in terms:
        for host in _WIKI_HOSTS:
            hit, conclusive = _wiki_probe(bridge, host, term)
            conclusive_all = conclusive_all and conclusive
            if hit:
                return {"status": "ready", "evidence": f"{host}:{term}"}
            time.sleep(max(0.0, sleep_seconds))
        hit, conclusive = _baidu_probe(bridge, term)
        conclusive_all = conclusive_all and conclusive
        if hit:
            return {"status": "ready", "evidence": f"baike.baidu.com:{term}"}
        time.sleep(max(0.0, sleep_seconds))
    if conclusive_all and terms:
        return {"status": "no_primary_source", "evidence": ""}
    return {"status": "pending", "evidence": ""}


def probe_master_list_sources(
    *,
    provinces: list[str],
    limit: int = 0,
    sleep_seconds: float = 0.5,
    recheck: bool = False,
) -> dict[str, Any]:
    """批量预筛并逐文件回填；返回汇总报告（stdout 消费）。"""
    report: dict[str, Any] = {
        "schemaVersion": "quwoquan_data.coverage_source_probe/1",
        "provinces": provinces,
        "probed": 0,
        "ready": 0,
        "noPrimarySource": 0,
        "inconclusive": 0,
        "skipped": 0,
        "files": [],
    }
    budget = int(limit) if limit else 0
    for path in master_list_files(provinces=provinces):
        if budget and report["probed"] >= budget:
            break
        data = load_master_list_file(path)
        changed = False
        file_row = {"file": str(path), "probed": 0, "ready": 0, "noPrimarySource": 0}
        for _, leaf in iter_master_leaves(data):
            if budget and report["probed"] >= budget:
                break
            readiness = str(leaf.get("sourceReadiness") or "pending")
            if readiness != "pending" and not recheck:
                report["skipped"] += 1
                continue
            verdict = probe_leaf(leaf, sleep_seconds=sleep_seconds)
            report["probed"] += 1
            file_row["probed"] += 1
            if verdict["status"] == "ready":
                report["ready"] += 1
                file_row["ready"] += 1
                if readiness != "ready":
                    leaf["sourceReadiness"] = "ready"
                    changed = True
            elif verdict["status"] == "no_primary_source":
                report["noPrimarySource"] += 1
                file_row["noPrimarySource"] += 1
                if readiness != "no_primary_source":
                    leaf["sourceReadiness"] = "no_primary_source"
                    changed = True
            else:
                report["inconclusive"] += 1
        if changed:
            dump_master_list_file(path, data)
        if file_row["probed"]:
            report["files"].append(file_row)
    return report
