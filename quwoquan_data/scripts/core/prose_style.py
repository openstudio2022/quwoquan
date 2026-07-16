"""文风门：禁止机械化、千篇一律的固定收尾小标题（真相源：docs 规格 §7）。

「它到底适合谁 / 这条线适合谁 / 适合谁」每篇一个固定小节，生硬重复。取舍判断应自然
融入叙述收尾，不另起固定标题。本模块同时供 post review 与目录静态门复用。
"""
from __future__ import annotations

import re

# 作为独立小节标题出现即阻断（精确到标题行，正文中自然提到不算）。
MECHANICAL_ENDING_TITLES = (
    "它到底适合谁",
    "这条线适合谁",
    "这趟适合谁",
    "到底适合谁",
    "适合谁",
)

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*$", re.MULTILINE)


def mechanical_ending_title_issues(markdown: str) -> list[str]:
    """返回机械收尾标题问题清单（按标题行精确匹配）。"""
    issues: list[str] = []
    for heading in _HEADING_RE.findall(markdown or ""):
        text = heading.strip().strip("：:").strip()
        for banned in MECHANICAL_ENDING_TITLES:
            if text == banned or text.endswith(banned):
                issues.append(
                    f"机械收尾标题『{heading.strip()}』：取舍判断请自然融入叙述收尾，"
                    f"禁止 {list(MECHANICAL_ENDING_TITLES)} 之类固定小标题"
                )
                break
    return issues


__all__ = ["MECHANICAL_ENDING_TITLES", "mechanical_ending_title_issues"]
