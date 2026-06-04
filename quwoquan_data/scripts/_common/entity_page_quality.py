"""实体主页正文质量门。"""
from __future__ import annotations

from pathlib import Path


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
    return issues
