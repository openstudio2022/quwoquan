"""来源结构化 IR（source.layout.json）唯一契约（真相源：百科主页结构化计划）。

多百科统一结构化中间层：per-sourceKind 前端（wikitext / baike HTML）解析产出
同一 IR schema，落盘 `sources/{unit}/source.layout.json`，供 source.md 渲染、
主页 page.md 组装、封面选择与质量门共同消费。

块类型收敛为六种通用块（不建 galleryIR 专用复杂结构）：

- ``heading``   章节标题（level/text/sectionSlug）
- ``paragraph`` 正文段落
- ``listItem``  列表项（含复杂 wikitable 逐行降维的事实句，带 listGroupId/origin）
- ``table``     简单矩形表格矩阵（headers/rows/caption/tableId），source.md 渲染为 GFM 表格
- ``figure``    图片占位（sourceOrder/sectionSlug/groupId/caption/fileTitle/placementType）
- ``factRow``   信息框键值行（key/value）

figure 附加语义字段：

- ``placementType``: ``lead`` | ``infoboxLead`` | ``locatorMap`` | ``inline`` | ``groupMember``
- ``coverCandidateRank``: -1 禁止做封面（地图/定位图）；0 未评级；>=1 infobox 顺序候选。
- ``caption``: **仅原图注**，无原图注必须为空串，禁止人为添加/虚构。
- ``groupId``: 宫格（gallery）/表格行图共享组 id，仅用于页尾相关图片保序。

表格映射策略在 IR 层记录 ``tables[].mappingDecision``：
``table``（矩形简单表保真为 GFM）| ``summary`` | ``orderedList`` | ``cards`` |
``gallery`` | ``dropped``。含行图/结构复杂的表仍逐行降维，保证行图 figure 锚定链不变。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from core.io import read_json, write_json

SOURCE_LAYOUT_SCHEMA_VERSION = "quwoquan_data.source_layout"
SOURCE_LAYOUT_FILE = "source.layout.json"

BLOCK_TYPES = frozenset({"heading", "paragraph", "listItem", "table", "figure", "factRow"})
PLACEMENT_TYPES = frozenset({"lead", "infoboxLead", "locatorMap", "inline", "groupMember"})
TABLE_MAPPING_DECISIONS = frozenset({"table", "summary", "orderedList", "cards", "gallery", "dropped"})

# 地图/定位/示意类图片：只可做辅助信息，不可做封面（plan §1/§4）。
_MAP_LIKE_RE = re.compile(
    r"(?:locat(?:or|ion)[ _-]?map|pushpin|地图|位置图|位置示意|区位图|行政区划|"
    r"路线图|路線圖|示意图|示意圖|分布图|分佈圖|coordinates?|坐标|座標|"
    r"\bmap\b|_map\.|-map\.|map_of|(?:^|[ _-])map(?:[ _-]|$))",
    re.IGNORECASE,
)
# logo/徽标/二维码等非实体视觉图，同样禁止做封面。
_NON_VISUAL_RE = re.compile(
    r"(?:\blogo\b|徽标|徽章|标志(?:\.|_|$)|二维码|二維碼|qr[ _-]?code|icon|"
    r"emblem|seal_of|flag_of)",
    re.IGNORECASE,
)


def is_map_like(file_title: str, caption: str = "") -> bool:
    """图片是否地图/定位/示意类（禁止封面，coverCandidateRank=-1）。"""
    hay = f"{file_title or ''} {caption or ''}"
    return bool(_MAP_LIKE_RE.search(hay))


def is_non_visual_subject(file_title: str, caption: str = "") -> bool:
    """图片是否 logo/徽标/二维码等非实体视觉主体（禁止封面）。"""
    hay = f"{file_title or ''} {caption or ''}"
    return bool(_NON_VISUAL_RE.search(hay))


def figure_id_for_order(source_order: int) -> str:
    """figure 稳定 id：AI 加工协议占位符 [[IMG:fig_NNN]] 与 IR 的对齐锚点。"""
    return f"fig_{int(source_order) + 1:03d}"


def make_heading_block(level: int, text: str, section_slug: str) -> dict[str, Any]:
    return {
        "type": "heading",
        "level": max(1, min(6, int(level))),
        "text": str(text or "").strip(),
        "sectionSlug": str(section_slug or ""),
    }


def make_paragraph_block(text: str, section_slug: str) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "text": str(text or "").strip(),
        "sectionSlug": str(section_slug or ""),
    }


def make_list_item_block(
    text: str,
    section_slug: str,
    *,
    list_group_id: str = "",
    origin: str = "",
) -> dict[str, Any]:
    return {
        "type": "listItem",
        "text": str(text or "").strip(),
        "sectionSlug": str(section_slug or ""),
        "listGroupId": str(list_group_id or ""),
        "origin": str(origin or ""),
    }


def make_table_block(
    *,
    headers: list[str],
    rows: list[list[str]],
    caption: str = "",
    section_slug: str = "",
    table_id: str = "",
) -> dict[str, Any]:
    """简单矩形表格矩阵块：cell 均为已剥离 wiki 标记的纯文本。"""
    return {
        "type": "table",
        "tableId": str(table_id or ""),
        "caption": str(caption or "").strip(),
        "headers": [str(h or "").strip() for h in headers],
        "rows": [[str(c or "").strip() for c in row] for row in rows],
        "sectionSlug": str(section_slug or ""),
    }


def make_fact_row_block(key: str, value: str, section_slug: str = "") -> dict[str, Any]:
    return {
        "type": "factRow",
        "key": str(key or "").strip(),
        "value": str(value or "").strip(),
        "sectionSlug": str(section_slug or ""),
    }


def make_figure_block(
    *,
    source_order: int,
    file_title: str,
    caption: str,
    section_slug: str,
    placement_type: str,
    group_id: str = "",
    cover_candidate_rank: int = 0,
) -> dict[str, Any]:
    if placement_type not in PLACEMENT_TYPES:
        raise ValueError(f"invalid placementType: {placement_type}")
    return {
        "type": "figure",
        "figureId": figure_id_for_order(source_order),
        "sourceOrder": int(source_order),
        "fileTitle": str(file_title or "").strip(),
        # 仅原图注；无原图注保持空串，禁止在任何层人为补注。
        "caption": str(caption or "").strip(),
        "sectionSlug": str(section_slug or ""),
        "groupId": str(group_id or ""),
        "placementType": placement_type,
        "coverCandidateRank": int(cover_candidate_rank),
        "isMapLike": is_map_like(file_title, caption),
    }


def build_layout(
    *,
    source_kind: str,
    extractor: str,
    title: str,
    blocks: list[dict[str, Any]],
    tables: list[dict[str, Any]] | None = None,
    parse_status: str = "ok",
    reject_reason: str = "",
    image_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """组装完整 IR 文档（source.layout.json 顶层结构）。

    ``image_evidence``：非开放图源（百度/搜狗）不采图，只记录存在性证据
    （如 {"imageCount": 5}），供质量门判断“源站有图但不可用”。
    """
    figures = [b for b in blocks if b.get("type") == "figure"]
    payload: dict[str, Any] = {
        "schema": SOURCE_LAYOUT_SCHEMA_VERSION,
        "sourceKind": str(source_kind or ""),
        "extractor": str(extractor or ""),
        "title": str(title or ""),
        "parseStatus": parse_status if parse_status in {"ok", "rejected"} else "rejected",
        "rejectReason": str(reject_reason or ""),
        "blocks": list(blocks),
        "figureCount": len(figures),
        "tables": list(tables or []),
    }
    if image_evidence is not None:
        payload["imageEvidence"] = dict(image_evidence)
    return payload


def rejected_layout(
    *,
    source_kind: str,
    extractor: str,
    title: str = "",
    reject_reason: str,
) -> dict[str, Any]:
    """结构化 reject：前端解析失败必须落原因，禁止静默降级回纯文本。"""
    return build_layout(
        source_kind=source_kind,
        extractor=extractor,
        title=title,
        blocks=[],
        parse_status="rejected",
        reject_reason=reject_reason or "parse_failed",
    )


def layout_figures(layout: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """按 sourceOrder 返回 IR 中全部 figure 块。"""
    if not isinstance(layout, Mapping):
        return []
    figures = [
        dict(block)
        for block in (layout.get("blocks") or [])
        if isinstance(block, Mapping) and block.get("type") == "figure"
    ]
    return sorted(figures, key=lambda row: int(row.get("sourceOrder") or 0))


def cover_candidates(layout: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """封面候选（排除地图/定位图与非实体视觉图），按 coverCandidateRank 升序。

    rank>=1（infobox 顺序候选）优先；rank==0（正文图，未评级）排其后，
    保持 sourceOrder 稳定序。rank==-1 或 map-like 一律排除。
    """
    ranked: list[dict[str, Any]] = []
    unranked: list[dict[str, Any]] = []
    for fig in layout_figures(layout):
        rank = int(fig.get("coverCandidateRank") or 0)
        if rank < 0 or fig.get("isMapLike"):
            continue
        if is_non_visual_subject(str(fig.get("fileTitle") or ""), str(fig.get("caption") or "")):
            continue
        if str(fig.get("placementType") or "") == "locatorMap":
            continue
        (ranked if rank >= 1 else unranked).append(fig)
    ranked.sort(key=lambda row: (int(row.get("coverCandidateRank") or 0), int(row.get("sourceOrder") or 0)))
    return ranked + unranked


def _gfm_cell(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).replace("|", r"\|").strip()


def _render_gfm_table(block: Mapping[str, Any]) -> list[str]:
    headers = [_gfm_cell(h) for h in (block.get("headers") or [])]
    rows = block.get("rows") or []
    if not headers or not rows:
        return []
    width = len(headers)
    lines: list[str] = []
    caption = str(block.get("caption") or "").strip()
    if caption:
        lines.append(f"**{caption}**")
        lines.append("")
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(" --- " for _ in headers) + "|")
    for row in rows:
        cells = [_gfm_cell(c) for c in row][:width]
        cells.extend("" for _ in range(width - len(cells)))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def render_source_markdown(
    layout: Mapping[str, Any] | None,
    *,
    figure_placeholder: bool = True,
) -> str:
    """从 IR 渲染 source.md 正文：底稿忠实还原（章节 + 图片原位占位 + 仅原图注）。

    - heading → ``#`` 级标题；paragraph → 段落；listItem → ``- `` 行；factRow → ``- 键：值``；
      table → GFM Markdown 表格（caption 作前导行，cell 内 ``|`` 转义、换行折叠为空格）。
    - figure（``figure_placeholder=True`` 时）→ 原位单图 ``:::figure`` 占位
      ``asset://source-inline-NNN``（NNN = sourceOrder+1，与 inlineImages 清单同序）；
      仅有原图注时带一行图注，**无原图注不补说明**。宫格/表格行图为连续单图占位，
      不引入 figuregroup 第二套语法。
    - 非开放图源（baike）传 ``figure_placeholder=False``：IR 无 figure 块时等价。
    """
    if not isinstance(layout, Mapping):
        return ""
    lines: list[str] = []
    fact_rows: list[str] = []

    def _flush_facts() -> None:
        nonlocal fact_rows
        if fact_rows:
            lines.extend([*fact_rows, ""])
            fact_rows = []

    for block in layout.get("blocks") or []:
        if not isinstance(block, Mapping):
            continue
        btype = block.get("type")
        if btype == "factRow":
            fact_rows.append(f"- {block.get('key')}：{block.get('value')}")
            continue
        _flush_facts()
        if btype == "heading":
            level = max(2, min(3, int(block.get("level") or 2)))
            lines.extend([f"{'#' * level} {block.get('text')}", ""])
        elif btype == "paragraph":
            lines.extend([str(block.get("text") or ""), ""])
        elif btype == "listItem":
            lines.append(f"- {block.get('text')}")
        elif btype == "table":
            lines.extend(["", *_render_gfm_table(block), ""])
        elif btype == "figure" and figure_placeholder:
            order = int(block.get("sourceOrder") or 0)
            caption = str(block.get("caption") or "").strip().replace("\n", " ")
            placeholder = f"source-inline-{order + 1:03d}"
            figure_lines = [":::figure", f"![{caption}](asset://{placeholder})"]
            if caption:
                figure_lines.append(caption)
            figure_lines.append(":::")
            lines.extend(["", *figure_lines, ""])
    _flush_facts()
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_RENDERED_HEADING_RE = re.compile(r"^(={2,6})\s*(.*?)\s*\1$")


def rendered_text_blocks(text: str) -> list[dict[str, Any]]:
    """Parse MediaWiki's expanded plaintext into heading/paragraph IR blocks."""
    blocks: list[dict[str, Any]] = []
    paragraph_lines: list[str] = []
    section_slug = ""

    def _flush_paragraph() -> None:
        nonlocal paragraph_lines
        paragraph = re.sub(r"\s+", " ", " ".join(paragraph_lines)).strip()
        paragraph_lines = []
        if paragraph:
            blocks.append(make_paragraph_block(paragraph, section_slug))

    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        heading = _RENDERED_HEADING_RE.match(line)
        if heading:
            _flush_paragraph()
            heading_text = heading.group(2).strip()
            section_slug = slugify_rendered_section(heading_text)
            blocks.append(
                make_heading_block(len(heading.group(1)), heading_text, section_slug)
            )
            continue
        if not line:
            _flush_paragraph()
            continue
        paragraph_lines.append(line)
    _flush_paragraph()
    return blocks


def slugify_rendered_section(text: str) -> str:
    """Keep rendered-text section keys identical to the wikitext parser."""
    from core.section_outline import slugify_section

    return slugify_section(text)


def merge_rendered_text_layout(
    layout: Mapping[str, Any], rendered_text: str
) -> dict[str, Any]:
    """Use template-expanded prose while retaining wikitext image placement.

    MediaWiki plaintext is the prose truth because it contains expanded inline
    templates.  Wikitext remains the structure truth for figures, infobox facts
    and tables.  Every retained figure keeps its original section and paragraph
    anchor; unmatched structural blocks are appended rather than discarded.
    """
    rendered_blocks = rendered_text_blocks(rendered_text)
    if not rendered_blocks:
        return rejected_layout(
            source_kind=str(layout.get("sourceKind") or "home_wikipedia"),
            extractor="wikipedia_api",
            title=str(layout.get("title") or ""),
            reject_reason="empty_rendered_text",
        )

    anchors_by_section: dict[str, list[tuple[int, int, dict[str, Any]]]] = {}
    for source_index, raw_block in enumerate(layout.get("blocks") or []):
        if not isinstance(raw_block, Mapping):
            continue
        if raw_block.get("type") not in {"figure", "factRow", "table"}:
            continue
        block = dict(raw_block)
        section = str(block.get("sectionSlug") or "")
        paragraph_index = int(block.get("paragraphIndex") or 0)
        anchors_by_section.setdefault(section, []).append(
            (paragraph_index, source_index, block)
        )
    for anchors in anchors_by_section.values():
        anchors.sort(key=lambda row: (row[0], row[1]))

    merged: list[dict[str, Any]] = []
    paragraph_indexes: dict[str, int] = {}
    consumed_sections: set[str] = set()

    def _emit_anchors(section: str, through_index: int | None = None) -> None:
        anchors = anchors_by_section.get(section, [])
        remaining: list[tuple[int, int, dict[str, Any]]] = []
        for paragraph_index, source_index, block in anchors:
            if through_index is None or paragraph_index <= through_index:
                merged.append(block)
            else:
                remaining.append((paragraph_index, source_index, block))
        anchors_by_section[section] = remaining
        if not remaining:
            consumed_sections.add(section)

    current_section = ""
    for block in rendered_blocks:
        if block.get("type") == "heading":
            _emit_anchors(current_section)
            current_section = str(block.get("sectionSlug") or "")
            merged.append(block)
            paragraph_indexes.setdefault(current_section, 0)
            continue
        paragraph_index = paragraph_indexes.get(current_section, 0)
        _emit_anchors(current_section, paragraph_index)
        merged.append(block)
        paragraph_indexes[current_section] = paragraph_index + 1
    _emit_anchors(current_section)

    for section, anchors in anchors_by_section.items():
        if section in consumed_sections:
            continue
        merged.extend(block for _paragraph, _source, block in anchors)

    image_evidence = layout.get("imageEvidence")
    return build_layout(
        source_kind=str(layout.get("sourceKind") or "home_wikipedia"),
        extractor="wikipedia_api",
        title=str(layout.get("title") or ""),
        blocks=merged,
        tables=[dict(row) for row in (layout.get("tables") or []) if isinstance(row, Mapping)],
        image_evidence=image_evidence if isinstance(image_evidence, Mapping) else None,
    )


def inline_placeholder_for_figure(figure: Mapping[str, Any]) -> str:
    """figure 块 → source.md 占位 id（与 render_source_markdown 同一编号口径）。"""
    return f"source-inline-{int(figure.get('sourceOrder') or 0) + 1:03d}"


def write_source_layout(unit_dir: Path, layout: Mapping[str, Any]) -> Path:
    """落盘 source.layout.json（机器消费真相源）。"""
    path = Path(unit_dir) / SOURCE_LAYOUT_FILE
    write_json(path, dict(layout))
    return path


def read_source_layout(unit_dir: Path) -> dict[str, Any] | None:
    path = Path(unit_dir) / SOURCE_LAYOUT_FILE
    if not path.is_file():
        return None
    payload = read_json(path)
    return payload if isinstance(payload, dict) else None


__all__ = [
    "SOURCE_LAYOUT_SCHEMA_VERSION",
    "SOURCE_LAYOUT_FILE",
    "BLOCK_TYPES",
    "PLACEMENT_TYPES",
    "TABLE_MAPPING_DECISIONS",
    "is_map_like",
    "is_non_visual_subject",
    "figure_id_for_order",
    "make_heading_block",
    "make_paragraph_block",
    "make_list_item_block",
    "make_table_block",
    "make_fact_row_block",
    "make_figure_block",
    "build_layout",
    "rejected_layout",
    "layout_figures",
    "cover_candidates",
    "render_source_markdown",
    "rendered_text_blocks",
    "merge_rendered_text_layout",
    "inline_placeholder_for_figure",
    "write_source_layout",
    "read_source_layout",
]
