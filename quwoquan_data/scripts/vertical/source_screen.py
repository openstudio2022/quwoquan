"""排产前 sourceScreen 深核验（WP7 Phase 3）：升级自 master_list_probe 轻探测。

WP5 实测放弃主因（7/9）是运行时 sourceScreen 判「无权威主源」，即
sourceReadiness=ready 的轻探测口径（标题命中即 ready）存在 ~20-30% 乐观偏差。
本模块把深核验前置为独立排产阶段：

- 深核验口径（对齐 download 阶段的实质可用性）：
  * wiki（zh.wikipedia / zh.wikivoyage）：标题命中 且 非消歧义页 且
    intro extract ≥ MIN_EXTRACT_CHARS（有实质正文可供成稿）；
  * 百度百科：词条页存在 且 有实质词条内容（非拦截/缺失页）；
  * 任一主源达标 → ready；全部结论性缺失 → no_primary_source；
    网络断路/反爬拦截不结论 → 保持原状（pending 不误降级）。
- 回写（主清单 YAML 唯一真相源）：sourceReadiness 三态 + sourceScreenedAt
  （UTC ISO 8601）+ sourceScreenEvidence（命中主源 或 缺失归因）。
- 报告：ready 折扣率（核验前 ready → 核验后仍 ready）+ 扩源缺口清单，
  落 QWQ_OUTPUT_ROOT/data/local/runtime/coverage_expand/。

经 `qwq-data vertical source-screen` 暴露；陈旧核验按 --max-age-days 重验。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from _common.coverage_master_list import (
    dump_master_list_file,
    iter_master_leaves,
    load_master_list_file,
    master_list_files,
)
from _common import paths as _paths


def _screen_runtime_dir() -> Path:
    output_root = _paths.OUTPUT_ROOT
    if os.environ.get("QWQ_OUTPUT_ROOT"):
        output_root = Path(os.environ["QWQ_OUTPUT_ROOT"])
    elif os.environ.get("QWQ_DATA_ROOT"):
        output_root = Path(os.environ["QWQ_DATA_ROOT"])
    return output_root / "data" / "local" / "runtime" / "coverage_expand"

_WIKI_HOSTS = ("zh.wikipedia.org", "zh.wikivoyage.org")
MIN_EXTRACT_CHARS = 200

_BAIDU_MISS_MARKERS = ("百度百科尚未收录", "抱歉，您所访问的页面不存在", "浏览的页面不存在")
_BAIDU_BLOCK_MARKERS = ("安全验证", "验证码", "百度安全")


def _research_bridge() -> Any:
    import download.research_plan as research_plan  # noqa: PLC0415

    return research_plan


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _screen_terms(leaf: dict[str, Any]) -> list[str]:
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


def _wiki_deep_probe(bridge: Any, host: str, term: str) -> tuple[bool, bool, str]:
    """深核验单词条：(达标, 结论性, 证据)。

    达标 = 命中 + 非消歧义 + intro extract ≥ MIN_EXTRACT_CHARS。
    """
    data = bridge._wiki_api(
        host,
        {
            "action": "query",
            "titles": term,
            "redirects": "1",
            "prop": "extracts|pageprops",
            "exintro": 1,
            "explaintext": 1,
            "format": "json",
        },
    )
    query = data.get("query") if isinstance(data, dict) else None
    if not isinstance(query, dict):
        return False, False, ""
    for page in (query.get("pages") or {}).values():
        if not isinstance(page, dict) or int(page.get("pageid") or -1) <= 0:
            continue
        props = page.get("pageprops") or {}
        if "disambiguation" in props:
            return False, True, f"{host}:{term} 为消歧义页"
        extract = str(page.get("extract") or "")
        if len(extract) >= MIN_EXTRACT_CHARS:
            return True, True, f"{host}:{term} extract={len(extract)}ch"
        return False, True, f"{host}:{term} 正文过短({len(extract)}ch)"
    return False, True, ""


def _baidu_deep_probe(bridge: Any, term: str) -> tuple[bool, bool, str]:
    import urllib.parse

    url = f"https://baike.baidu.com/item/{urllib.parse.quote(term)}"
    text = bridge._curl_text(url, timeout=15)
    if not text:
        return False, False, ""
    if any(marker in text for marker in _BAIDU_BLOCK_MARKERS):
        return False, False, ""
    if any(marker in text for marker in _BAIDU_MISS_MARKERS):
        return False, True, ""
    hit = "百度百科" in text and term in text and len(text) > 30_000
    return hit, True, (f"baike.baidu.com:{term}" if hit else "")


def screen_leaf(leaf: dict[str, Any], *, sleep_seconds: float = 0.5, bridge: Any | None = None) -> dict[str, Any]:
    """深核验单叶子：{status, evidence}；status ∈ ready/no_primary_source/pending。"""
    bridge = bridge or _research_bridge()
    terms = _screen_terms(leaf)
    conclusive_all = bool(terms)
    miss_reasons: list[str] = []
    for term in terms:
        for host in _WIKI_HOSTS:
            hit, conclusive, evidence = _wiki_deep_probe(bridge, host, term)
            conclusive_all = conclusive_all and conclusive
            if hit:
                return {"status": "ready", "evidence": evidence}
            if evidence:
                miss_reasons.append(evidence)
            time.sleep(max(0.0, sleep_seconds))
        hit, conclusive, evidence = _baidu_deep_probe(bridge, term)
        conclusive_all = conclusive_all and conclusive
        if hit:
            return {"status": "ready", "evidence": evidence}
        time.sleep(max(0.0, sleep_seconds))
    if conclusive_all:
        return {
            "status": "no_primary_source",
            "evidence": "; ".join(miss_reasons[:3]) or "全主源结论性缺失",
        }
    return {"status": "pending", "evidence": ""}


def _screen_is_fresh(leaf: dict[str, Any], *, max_age_days: int) -> bool:
    stamp = str(leaf.get("sourceScreenedAt") or "")
    if not stamp:
        return False
    try:
        screened = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - screened <= timedelta(days=max_age_days)


def screen_master_list_sources(
    *,
    provinces: list[str],
    limit: int = 0,
    sleep_seconds: float = 0.5,
    max_age_days: int = 30,
    only_ready: bool = False,
) -> dict[str, Any]:
    """批量深核验并逐文件回写；输出折扣率与扩源缺口报告。

    - only_ready=True：只核验当前 ready 存量（WP5 折扣率实测场景）；
      否则核验 ready + pending（no_primary_source 除非陈旧不重验）。
    - 已有新鲜核验时间戳（≤ max_age_days）的叶子跳过。
    """
    report: dict[str, Any] = {
        "schemaVersion": "quwoquan_data.coverage_source_screen/1",
        "generatedAt": _now_iso(),
        "provinces": provinces,
        "screened": 0,
        "skippedFresh": 0,
        "skippedScope": 0,
        "readyBefore": 0,
        "readyConfirmed": 0,
        "readyDowngraded": 0,
        "pendingPromoted": 0,
        "noPrimarySource": 0,
        "inconclusive": 0,
        "readyDiscountRate": None,
        "expansionGaps": [],
        "files": [],
    }
    budget = int(limit) if limit else 0
    bridge = _research_bridge()
    for path in master_list_files(provinces=provinces):
        if budget and report["screened"] >= budget:
            break
        data = load_master_list_file(path)
        changed = False
        file_row = {"file": str(path), "screened": 0, "downgraded": 0, "promoted": 0}
        for district, leaf in iter_master_leaves(data):
            if budget and report["screened"] >= budget:
                break
            readiness = str(leaf.get("sourceReadiness") or "pending")
            if only_ready and readiness != "ready":
                report["skippedScope"] += 1
                continue
            if readiness == "no_primary_source" and _screen_is_fresh(leaf, max_age_days=max_age_days):
                report["skippedFresh"] += 1
                continue
            if _screen_is_fresh(leaf, max_age_days=max_age_days):
                report["skippedFresh"] += 1
                continue
            was_ready = readiness == "ready"
            if was_ready:
                report["readyBefore"] += 1
            verdict = screen_leaf(leaf, sleep_seconds=sleep_seconds, bridge=bridge)
            status = verdict["status"]
            if status == "pending":
                report["inconclusive"] += 1
                continue  # 不结论：不回写、不打时间戳（避免陈旧网络问题定格）
            report["screened"] += 1
            file_row["screened"] += 1
            leaf["sourceScreenedAt"] = _now_iso()
            leaf["sourceScreenEvidence"] = str(verdict.get("evidence") or "")
            if status == "ready":
                if was_ready:
                    report["readyConfirmed"] += 1
                else:
                    report["pendingPromoted"] += 1
                    file_row["promoted"] += 1
                leaf["sourceReadiness"] = "ready"
            else:
                report["noPrimarySource"] += 1
                if was_ready:
                    report["readyDowngraded"] += 1
                    file_row["downgraded"] += 1
                leaf["sourceReadiness"] = "no_primary_source"
                report["expansionGaps"].append(
                    {
                        "canonicalName": str(leaf.get("canonicalName") or ""),
                        "district": district,
                        "file": str(path),
                        "evidence": str(verdict.get("evidence") or ""),
                    }
                )
            changed = True
        if changed:
            dump_master_list_file(path, data)
        if file_row["screened"]:
            report["files"].append(file_row)
    if report["readyBefore"]:
        report["readyDiscountRate"] = round(
            report["readyConfirmed"] / report["readyBefore"], 4
        )
    screen_runtime_dir = _screen_runtime_dir()
    screen_runtime_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = screen_runtime_dir / f"source_screen_report_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report
