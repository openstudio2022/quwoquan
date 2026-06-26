"""实体主页正文质量门。"""
from __future__ import annotations

import re
from pathlib import Path

from _common import quality_gates as qg


# 真实历史标记：年份/朝代/世纪/建置沿革动词等（用于「历史沿革」章节语义校验）。
_HISTORY_MARKERS = (
    "朝", "代", "世纪", "公元", "建于", "始建", "设立", "设置", "建置", "置县",
    "改名", "更名", "撤", "并入", "隶属", "划归", "年间", "年（", "年(", "民国", "清", "明", "宋", "唐",
)
_YEAR_RE = re.compile(r"(?:1[0-9]{3}|20[0-9]{2})\s*年|[一二三四五六七八九十]+世纪")
_SECTION_RE = re.compile(r"(?ms)^##\s+([^\n]+)\n(.*?)(?=^##\s|\Z)")


FORBIDDEN_ENTITY_PAGE_PHRASES = (
    "内容冷启动",
    "搜索承接",
    "推荐召回",
    "小艺主动服务",
    "App、SEO 渲染",
    "SEO 渲染",
    "服务侧导入",
    "资产闭环说明",
    "后续内容生产建议",
    "推荐系统",
    "发布索引",
    "冷启动内容库",
    "当前主页只负责保留语义",
)


def entity_page_quality_issues(page_path: Path, *, label: str = "") -> list[str]:
    """拦截工程提示词/模板污染进入面向读者的实体主页。"""
    if not page_path.is_file():
        return [f"{label}: page.md 缺失" if label else "page.md 缺失"]
    text = page_path.read_text(encoding="utf-8")
    prefix = f"{label}: " if label else ""
    issues: list[str] = []
    for phrase in FORBIDDEN_ENTITY_PAGE_PHRASES:
        if phrase in text:
            issues.append(f"{prefix}entity homepage contains engineering/template phrase: {phrase}")
    if "## 为什么值得关注" in text and "属于「" in text and "实体" in text:
        issues.append(f"{prefix}entity homepage looks like generated system explainer, not reader-facing copy")
    issues.extend(f"{prefix}{issue}" for issue in qg.intra_doc_repetition_issues(text))
    issues.extend(
        f"{prefix}{issue}"
        for issue in qg.section_balance_issues(text, max_ratio=qg.SECTION_BALANCE_MAX_RATIO_HOMEPAGE)
    )
    issues.extend(f"{prefix}{issue}" for issue in qg.timeline_monotonicity_issues(text))
    issues.extend(_history_section_issues(text, prefix))
    return issues


def _history_section_issues(text: str, prefix: str) -> list[str]:
    """章节语义门：若存在「历史沿革」，其正文须含真实历史标记，否则应省略或补真实历史。

    直击「把地质成因/景区评级当历史沿革」这类语义错配（如诺水河）。
    """
    issues: list[str] = []
    for heading, body in _SECTION_RE.findall(text):
        title = heading.strip()
        if "历史沿革" not in title and "历史" != title.strip():
            continue
        if _YEAR_RE.search(body) or any(m in body for m in _HISTORY_MARKERS):
            continue
        issues.append(
            f"{prefix}「{title}」缺少真实历史（无年份/朝代/建置沿革等标记），"
            "应省略该章节或补真实历史，勿把地质成因/评级塞进历史沿革"
        )
    return issues
