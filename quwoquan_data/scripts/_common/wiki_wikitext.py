"""MediaWiki wikitext 结构解析：章节 outline + 图片段落锚点 + 语义 caption。

从 `action=parse&prop=wikitext` 或 revisions 返回的 wikitext 解析：
- `== 标题 ==` / `=== 标题 ===` → sectionOutline（与 section_outline 同源 slug 语义）
- `[[File:Name|thumb|caption]]` → imagePlacements（sectionSlug + paragraphIndex + caption）

供 download 阶段写入 source unit meta.json，finalize placement 消费段落锚点。
"""
from __future__ import annotations

import re
from typing import Any

from _common.section_outline import (
    match_heading,
    outline_required_sections,
    outline_to_dicts,
    parse_section_outline,
    slugify_section,
)

# [[File:Name]] / [[File:Name|thumb|caption]] / [[文件:Name|...]]
_WIKI_FILE_RE = re.compile(
    r"\[\[(?:File|文件):([^\]|#]+)(?:\|([^\]]*))?\]\]",
    re.IGNORECASE,
)
_LAYOUT_TOKENS = frozenset(
    {
        "thumb",
        "thumbnail",
        "frame",
        "frameless",
        "border",
        "left",
        "right",
        "center",
        "none",
        "upright",
        "缩略图",
        "有框",
        "无框",
        "左",
        "右",
        "居中",
    }
)


def _caption_from_file_params(params: str) -> str:
    """从 [[File:...|a|b|caption]] 提取人类可读 caption（跳过布局 token）。"""
    parts = [p.strip() for p in str(params or "").split("|") if p.strip()]
    for part in reversed(parts):
        lower = part.lower()
        if lower in _LAYOUT_TOKENS:
            continue
        if re.match(r"^\d+px$", lower):
            continue
        if re.match(r"^x\d+px$", lower):
            continue
        return part
    return ""


def _normalize_file_name(name: str) -> str:
    return str(name or "").strip().replace(" ", "_")


def parse_wikitext_placements(
    wikitext: str,
    *,
    min_section_body_chars: int = 120,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """解析 wikitext → (sectionOutline, imagePlacements)。"""
    if not wikitext:
        return [], []

    outline_nodes = outline_required_sections(
        parse_section_outline(wikitext),
        min_body_chars=min_section_body_chars,
    )
    section_outline = outline_to_dicts(outline_nodes)

    current_slug = ""
    paragraph_index = 0
    placements: list[dict[str, Any]] = []
    source_order = 0
    buffer_nonempty = False

    for line in wikitext.splitlines():
        heading = match_heading(line)
        if heading is not None:
            current_slug = slugify_section(heading[1])
            paragraph_index = 0
            buffer_nonempty = False
            continue

        stripped = line.strip()
        if not stripped:
            if buffer_nonempty:
                paragraph_index += 1
                buffer_nonempty = False
            continue

        buffer_nonempty = True
        for match in _WIKI_FILE_RE.finditer(line):
            file_name = _normalize_file_name(match.group(1))
            caption = _caption_from_file_params(match.group(2) or "")
            placements.append(
                {
                    "fileName": file_name,
                    "caption": caption,
                    "sectionSlug": current_slug,
                    "paragraphIndex": paragraph_index,
                    "sourceOrder": source_order,
                }
            )
            source_order += 1

    return section_outline, placements


def enrich_meta_from_wikitext(meta: dict[str, Any], wikitext: str) -> dict[str, Any]:
    """把 wikitext 解析结果合并进 source unit meta（不覆盖已有非空字段）。"""
    outline, placements = parse_wikitext_placements(wikitext)
    out = dict(meta)
    if outline and not out.get("sectionOutline"):
        out["sectionOutline"] = outline
    if placements and not out.get("imagePlacements"):
        out["imagePlacements"] = placements
    return out
