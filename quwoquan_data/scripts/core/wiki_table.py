"""MediaWiki table parsing into the shared source-layout IR."""
from __future__ import annotations
import re
from core.source_layout import make_list_item_block, make_table_block
from core.wiki_markup import (
    extract_file_links as _extract_file_links,
    file_caption as _caption_from_file_params,
    split_top_level as _split_top_level,
    strip_file_links as _strip_file_links,
    strip_inline_markup,
)
from core.wiki_wikitext import _LayoutBuilder

_TABLE_DROP_HINT_RE = re.compile(r"(?:navbox|参考|參考|坐标|座標|coord|引用|footnotes)", re.IGNORECASE)

_CELL_ATTR_SEGMENT_RE = re.compile(
    r"^\s*[A-Za-z][A-Za-z0-9_-]*\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^|\s]+)"
    r"(?:\s+[A-Za-z][A-Za-z0-9_-]*\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^|\s]+))*\s*$"
)

_TABLE_COMPLEX_ATTR_RE = re.compile(r"(?:rowspan|colspan)\s*=", re.IGNORECASE)

def _strip_cell_attributes(cell: str) -> str:
    """剥离 wikitable 单元格属性前缀：`valign=top|正文` → `正文`。

    仅当首个顶层 `|` 之前是纯 `key=value` 属性串时剥离，避免误伤含 `|` 的正文。
    """
    raw = str(cell or "")
    if "|" not in raw:
        return raw
    head, rest = raw.split("|", 1)
    if "[[" in head or "{{" in head:
        return raw
    if _CELL_ATTR_SEGMENT_RE.match(head):
        return rest
    return raw

_BARE_ORDINAL_RE = re.compile(r"^[\s.、,，)）(（\[\]①-⑳㉑-㉟\d]+$")

def _is_bare_ordinal(text: str) -> bool:
    """判断一段文本是否只是序号/编号（如 ``1``、``2.``、``①``）而无语义。

    表格首列常是行号，用作行图 caption 会退化成无意义的 ``"1"``、``"2"``；
    这类主语禁止作为图注（契约「仅原图注，无图注不补」）。
    """
    stripped = str(text or "").strip()
    if not stripped:
        return True
    return bool(_BARE_ORDINAL_RE.match(stripped))

def _row_caption_subject(cells: list[str]) -> str:
    """行图 caption 兜底主语：取首个「非纯序号」的原文字段，找不到则空。"""
    for cell in cells:
        text = strip_inline_markup(_strip_file_links(cell))
        if text and not _is_bare_ordinal(text):
            return text
    return ""

def _table_row_sentence(headers: list[str], cells: list[str]) -> str:
    """把表格一行降维为事实句：首个非空 cell 做主语，其余按 `表头: 值` 连接。"""
    texts = [strip_inline_markup(_strip_file_links(cell)) for cell in cells]
    texts = [t for t in texts if t]
    if not texts:
        return ""
    subject = texts[0]
    rest: list[str] = []
    for pos, value in enumerate(texts[1:], start=1):
        header = headers[pos].strip() if pos < len(headers) else ""
        rest.append(f"{header} {value}".strip() if header else value)
    if not rest:
        return f"{subject}。"
    return f"{subject}：{'，'.join(rest)}。"

def _consume_table_block(
    lines: list[str], start: int, builder: _LayoutBuilder
) -> int:
    """消费 `{|...|}` wikitable：逐行降维 listItem 事实句 + 行图 figure。"""
    group_id = builder.next_group_id("tbl")
    idx = start + 1
    headers: list[str] = []
    rows: list[list[str]] = []
    current_row: list[str] = []
    caption_text = ""
    has_complex_attrs = _TABLE_COMPLEX_ATTR_RE.search(lines[start]) is not None
    saw_nested_table = False
    depth = 1
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if stripped.startswith("{|"):
            depth += 1
            saw_nested_table = True
            idx += 1
            continue
        if stripped.startswith("|}"):
            depth -= 1
            idx += 1
            if depth <= 0:
                break
            continue
        if stripped.startswith("|+"):
            caption_text = strip_inline_markup(stripped[2:])
            idx += 1
            continue
        if stripped.startswith("|-"):
            if current_row:
                rows.append(current_row)
                current_row = []
            idx += 1
            continue
        if _TABLE_COMPLEX_ATTR_RE.search(stripped):
            has_complex_attrs = True
        if stripped.startswith("!"):
            body = stripped.lstrip("!")
            for cell in re.split(r"!!", body):
                cleaned = strip_inline_markup(_strip_cell_attributes(cell))
                if cleaned:
                    headers.append(cleaned)
            idx += 1
            continue
        if stripped.startswith("|"):
            body = stripped[1:]
            for cell in _split_top_level(body.replace("||", "\u0001"), "\u0001"):
                current_row.append(_strip_cell_attributes(cell))
            idx += 1
            continue
        # 换行续写的 cell 内容并入最后一个 cell。
        if current_row:
            current_row[-1] = f"{current_row[-1]}\n{line}"
        idx += 1
    if current_row:
        rows.append(current_row)

    table_id = group_id

    # 简单矩形表（无行图/无合并单元格/无嵌套/表头齐全）保真为 table block，
    # source.md 渲染为 GFM 表格；复杂表保持逐行降维，行图 figure 锚定链不变。
    has_row_files = any(
        _extract_file_links(cell) for row_cells in rows for cell in row_cells
    )
    row_texts = [
        [strip_inline_markup(_strip_file_links(cell)) for cell in row_cells]
        for row_cells in rows
    ]
    row_texts = [row for row in row_texts if any(cell for cell in row)]
    simple_rectangular = (
        len(headers) >= 2
        and len(row_texts) >= 2
        and not has_row_files
        and not has_complex_attrs
        and not saw_nested_table
        and all(len(row) <= len(headers) for row in row_texts)
        and not _TABLE_DROP_HINT_RE.search(caption_text or "")
    )
    if simple_rectangular:
        builder.blocks.append(
            make_table_block(
                headers=headers,
                rows=row_texts,
                caption=caption_text,
                section_slug=builder.section_slug,
                table_id=table_id,
            )
        )
        builder.tables.append(
            {
                "tableId": table_id,
                "caption": caption_text,
                "sectionSlug": builder.section_slug,
                "rowCount": len(row_texts),
                "columnCount": len(headers),
                "listItemCount": 0,
                "figureCount": 0,
                "mappingDecision": "table",
                "listGroupId": "",
            }
        )
        return idx

    list_group_id = builder.next_group_id("lst")
    item_count = 0
    figure_count = 0
    for row_cells in rows:
        row_files: list[tuple[str, str]] = []
        for cell in row_cells:
            for file_name, params, _s, _e in _extract_file_links(cell):
                row_files.append((file_name, _caption_from_file_params(params)))
        sentence = _table_row_sentence(headers, row_cells)
        # 行图 caption 兜底主语：跳过纯序号首列，取首个有语义的原文字段。
        caption_subject = _row_caption_subject(row_cells)
        if sentence:
            builder.blocks.append(
                make_list_item_block(
                    sentence,
                    builder.section_slug,
                    list_group_id=list_group_id,
                    origin="wikitable",
                )
            )
            item_count += 1
        for file_name, caption in row_files:
            # 行图 caption 优先原图注，其次「非序号」行主语（原文事实字段）；
            # 两者皆无则留空（禁止用行号 1/2/3 造假图注）。
            builder.add_figure(
                file_name=file_name,
                caption=caption or caption_subject,
                placement_type="groupMember",
                group_id=table_id,
            )
            figure_count += 1
    if _TABLE_DROP_HINT_RE.search(caption_text or "") or (not item_count and not figure_count):
        decision = "dropped"
    elif figure_count and not item_count:
        decision = "gallery"
    else:
        decision = "orderedList"
    builder.tables.append(
        {
            "tableId": table_id,
            "caption": caption_text,
            "sectionSlug": builder.section_slug,
            "rowCount": len(rows),
            "listItemCount": item_count,
            "figureCount": figure_count,
            "mappingDecision": decision,
            "listGroupId": list_group_id if item_count else "",
        }
    )
    return idx
