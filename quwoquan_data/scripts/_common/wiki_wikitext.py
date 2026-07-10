"""MediaWiki wikitext 结构解析：统一结构化 IR（五种通用块）+ 兼容 placements 视图。

从 `action=parse&prop=wikitext` 返回的 wikitext 解析出结构化 IR
（真相源契约见 `_common/source_layout.py`）：

- `== 标题 ==` / `=== 标题 ===` → ``heading``
- 正文行（剥离模板/ref/内链标记后）→ ``paragraph``
- `{{Infobox ...}}` 等键值模板 → ``factRow`` + infobox 图（``placementType=infoboxLead``，
  地图/定位字段 → ``locatorMap`` 且 ``coverCandidateRank=-1``）
- `[[File:...|thumb|caption]]` 行内图 → ``figure``（``placementType=inline``，仅原图注）
- `<gallery>` 宫格 → 连续 ``figure``（共享 ``groupId``，保原顺序与原图注）
- `; term : def` 定义列表 → ``listItem``（``origin=wikidefinition``，剥离原始 `;`/`:` 语法）
- `{| wikitable |}` 简单矩形表（无行图/无合并单元格/无嵌套）→ ``table`` 矩阵块
  （source.md 渲染 GFM 表格，``mappingDecision=table``）；含行图/复杂表仍逐行降维
  ``listItem`` 事实句 + 行图 ``figure``（共享 ``groupId``），``mappingDecision``
  记 orderedList/gallery/dropped；cell 属性前缀（含无引号 `valign=top|`、typo
  `avlign=top|`）按语法位置剥离

`parse_wikitext_placements` 保留旧签名，改由 IR 派生：placements 现在**包含**
gallery / 表格行图 / infobox 图（修复武侯祠图库只剩 1 张的根因），并携带
placementType / groupId / coverCandidateRank。
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
from _common.source_layout import (
    build_layout,
    is_map_like,
    make_fact_row_block,
    make_figure_block,
    make_heading_block,
    make_list_item_block,
    make_paragraph_block,
    make_table_block,
)

# [[File:Name]] / [[File:Name|thumb|caption]] / [[文件:Name|...]]（无嵌套 caption 的快速路径）
_WIKI_FILE_RE = re.compile(
    r"\[\[(?:File|文件|Image|图像|圖像):([^\]|#]+)(?:\|([^\]]*))?\]\]",
    re.IGNORECASE,
)
_FILE_PREFIX_RE = re.compile(r"^(?:File|文件|Image|图像|圖像):", re.IGNORECASE)
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
_IMAGE_EXT_RE = re.compile(r"\.(?:jpe?g|png|webp|gif|svg|tiff?)$", re.IGNORECASE)

# infobox/键值模板中的图片、图注与地图字段（key 归一小写后匹配）。
_INFOBOX_IMAGE_KEY_RE = re.compile(r"(?:image|img|photo|logo|图片|圖片|图像|圖像|照片)")
_INFOBOX_CAPTION_KEY_RE = re.compile(r"(?:caption|说明|說明)")
_INFOBOX_MAP_KEY_RE = re.compile(r"(?:map|pushpin|地图|地圖|位置图|位置圖)")
# 参考资料/导航/坐标类表格：对主页无价值，mappingDecision=dropped。
_TABLE_DROP_HINT_RE = re.compile(r"(?:navbox|参考|參考|坐标|座標|coord|引用|footnotes)", re.IGNORECASE)

# MediaWiki cell 属性前缀（`| attrs | content` 的 attrs 段）：`key=value` 序列，
# value 可带或不带引号。源站手写属性常有 typo（如 `avlign=top`），按语法位置识别，
# 不按属性名白名单——凡「首个 | 之前是纯 key=value 串」都视为属性剥离。
_CELL_ATTR_SEGMENT_RE = re.compile(
    r"^\s*[A-Za-z][A-Za-z0-9_-]*\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^|\s]+)"
    r"(?:\s+[A-Za-z][A-Za-z0-9_-]*\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^|\s]+))*\s*$"
)
# 合并单元格/复杂结构属性：命中即视为复杂表，不走 GFM 保真。
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


def _split_top_level(params: str, sep: str = "|") -> list[str]:
    """按顶层分隔符切分（忽略 [[...]] / {{...}} 嵌套内的分隔符）。"""
    parts: list[str] = []
    buf: list[str] = []
    depth_link = 0
    depth_tpl = 0
    i = 0
    text = str(params or "")
    while i < len(text):
        two = text[i : i + 2]
        if two == "[[":
            depth_link += 1
            buf.append(two)
            i += 2
            continue
        if two == "]]" and depth_link:
            depth_link -= 1
            buf.append(two)
            i += 2
            continue
        if two == "{{":
            depth_tpl += 1
            buf.append(two)
            i += 2
            continue
        if two == "}}" and depth_tpl:
            depth_tpl -= 1
            buf.append(two)
            i += 2
            continue
        ch = text[i]
        if ch == sep and not depth_link and not depth_tpl:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def strip_inline_markup(text: str) -> str:
    """剥离行内 wiki 标记：ref、模板、内链、粗斜体、HTML 标签，保留可读文本。"""
    out = str(text or "")
    out = re.sub(r"(?is)<ref[^>/]*/>", "", out)
    out = re.sub(r"(?is)<ref[^>]*>.*?</ref>", "", out)
    out = re.sub(r"(?is)<!--.*?-->", "", out)
    # 嵌套模板从内向外剥离（有限轮次防御非闭合输入）。
    for _ in range(6):
        stripped = re.sub(r"\{\{[^{}]*\}\}", "", out)
        if stripped == out:
            break
        out = stripped
    # 内链：[[target|display]] → display；[[target]] → target。
    for _ in range(4):
        stripped = re.sub(
            r"\[\[(?![^\]]*?(?:File|文件|Image|图像|圖像):)([^\[\]|]*)(?:\|([^\[\]]*))?\]\]",
            lambda m: (m.group(2) if m.group(2) is not None else m.group(1)) or "",
            out,
        )
        if stripped == out:
            break
        out = stripped
    # 外链：[url label] → label；[url] → 空。
    out = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", out)
    out = re.sub(r"\[https?://[^\]]+\]", "", out)
    out = re.sub(r"'''''|'''|''", "", out)
    out = re.sub(r"(?is)<br\s*/?>", " ", out)
    out = re.sub(r"(?is)<[^>]+>", "", out)
    return re.sub(r"[ \t]+", " ", out).strip()


def _caption_from_file_params(params: str) -> str:
    """从 [[File:...|a|b|caption]] 提取原图注（跳过布局 token；支持嵌套内链）。"""
    parts = [p.strip() for p in _split_top_level(str(params or "")) if p.strip()]
    for part in reversed(parts):
        lower = part.lower()
        if lower in _LAYOUT_TOKENS:
            continue
        if re.match(r"^x?\d+px$", lower):
            continue
        if re.match(r"^(?:upright|alt|link|lang|page|class)\s*=", lower):
            continue
        caption = strip_inline_markup(part)
        if caption:
            return caption
    return ""


def _normalize_file_name(name: str) -> str:
    return _FILE_PREFIX_RE.sub("", str(name or "").strip()).strip().replace(" ", "_")


def _extract_file_links(text: str) -> list[tuple[str, str, int, int]]:
    """提取行内全部 [[File:...]] 链接（支持 caption 内嵌套 [[...]]）。

    返回 [(fileName, params, start, end)]，start/end 为原文中的偏移，供剔除。
    """
    out: list[tuple[str, str, int, int]] = []
    raw = str(text or "")
    i = 0
    while True:
        start = raw.find("[[", i)
        if start < 0:
            break
        head = raw[start + 2 : start + 12]
        if not _FILE_PREFIX_RE.match(head):
            i = start + 2
            continue
        depth = 1
        j = start + 2
        while j < len(raw) and depth:
            if raw[j : j + 2] == "[[":
                depth += 1
                j += 2
            elif raw[j : j + 2] == "]]":
                depth -= 1
                j += 2
            else:
                j += 1
        if depth:
            break
        inner = raw[start + 2 : j - 2]
        parts = _split_top_level(inner)
        file_name = _normalize_file_name(parts[0])
        params = "|".join(parts[1:]) if len(parts) > 1 else ""
        if file_name:
            out.append((file_name, params, start, j))
        i = j
    return out


def _strip_file_links(text: str) -> str:
    links = _extract_file_links(text)
    if not links:
        return text
    out = []
    cursor = 0
    for _, _, start, end in links:
        out.append(text[cursor:start])
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def _is_image_file(file_name: str) -> bool:
    return bool(_IMAGE_EXT_RE.search(str(file_name or "")))


class _LayoutBuilder:
    """逐行状态机的可变累加器。"""

    def __init__(self) -> None:
        self.blocks: list[dict[str, Any]] = []
        self.tables: list[dict[str, Any]] = []
        self.source_order = 0
        self.section_slug = ""
        self.paragraph_index = 0
        self.group_seq = 0
        self.infobox_rank = 0

    def next_group_id(self, prefix: str) -> str:
        self.group_seq += 1
        return f"{prefix}-{self.group_seq:03d}"

    def add_figure(
        self,
        *,
        file_name: str,
        caption: str,
        placement_type: str,
        group_id: str = "",
        cover_rank: int = 0,
    ) -> None:
        if not _is_image_file(file_name):
            return
        if placement_type != "locatorMap" and (
            is_map_like(file_name, caption)
        ):
            placement_type = "locatorMap"
            cover_rank = -1
        block = make_figure_block(
            source_order=self.source_order,
            file_title=file_name,
            caption=caption,
            section_slug=self.section_slug,
            placement_type=placement_type,
            group_id=group_id,
            cover_candidate_rank=cover_rank,
        )
        block["paragraphIndex"] = self.paragraph_index
        self.blocks.append(block)
        self.source_order += 1


def _consume_template_block(
    lines: list[str], start: int, builder: _LayoutBuilder
) -> int:
    """消费一个多行 `{{...}}` 模板；键值参数 >=3 时按 infobox 提取。返回下一行号。"""
    depth = 0
    body_lines: list[str] = []
    idx = start
    while idx < len(lines):
        line = lines[idx]
        depth += line.count("{{") - line.count("}}")
        body_lines.append(line)
        idx += 1
        if depth <= 0:
            break
    body = "\n".join(body_lines)
    params: list[tuple[str, str]] = []
    for raw_line in body.splitlines():
        match = re.match(r"^\s*\|\s*([^=|]+?)\s*=\s*(.*)$", raw_line)
        if match:
            params.append((match.group(1).strip(), match.group(2).strip()))
    if len(params) < 3:
        return idx
    # 图片/图注字段配对：按 key 的数字后缀（image2 ↔ caption2；无后缀共用 ""）。
    captions_by_suffix: dict[str, str] = {}
    for key, value in params:
        key_l = key.lower()
        if _INFOBOX_CAPTION_KEY_RE.search(key_l):
            suffix = "".join(ch for ch in key_l if ch.isdigit())
            cleaned = strip_inline_markup(value)
            if cleaned:
                captions_by_suffix.setdefault(suffix, cleaned)
    for key, value in params:
        key_l = key.lower()
        is_map_key = bool(_INFOBOX_MAP_KEY_RE.search(key_l))
        is_image_key = bool(_INFOBOX_IMAGE_KEY_RE.search(key_l)) and not _INFOBOX_CAPTION_KEY_RE.search(key_l)
        if is_image_key or is_map_key:
            file_name = ""
            embedded = _extract_file_links(value)
            if embedded:
                file_name = embedded[0][0]
            else:
                candidate = _normalize_file_name(value)
                if _is_image_file(candidate):
                    file_name = candidate
            if not file_name:
                continue
            if is_map_key:
                builder.add_figure(
                    file_name=file_name,
                    caption="",
                    placement_type="locatorMap",
                    cover_rank=-1,
                )
                continue
            suffix = "".join(ch for ch in key_l if ch.isdigit())
            caption = captions_by_suffix.get(suffix, "")
            builder.infobox_rank += 1
            builder.add_figure(
                file_name=file_name,
                caption=caption,
                placement_type="infoboxLead",
                cover_rank=builder.infobox_rank,
            )
            continue
        if _INFOBOX_CAPTION_KEY_RE.search(key_l):
            continue  # 图注字段只服务 figure caption 配对，不落 factRow。
        cleaned_value = strip_inline_markup(value)
        cleaned_key = strip_inline_markup(key)
        if cleaned_key and cleaned_value:
            builder.blocks.append(
                make_fact_row_block(cleaned_key, cleaned_value, builder.section_slug)
            )
    return idx


def _consume_gallery_block(
    lines: list[str], start: int, builder: _LayoutBuilder
) -> int:
    """消费 `<gallery>...</gallery>` 宫格：降维为连续 figure（共享 groupId）。"""
    group_id = builder.next_group_id("gal")
    idx = start
    # 起始行可能是 `<gallery ...>` 单独一行，也可能同一行含条目。
    first_line = lines[idx]
    inline_rest = re.sub(r"(?is)^.*?<gallery[^>]*>", "", first_line)
    idx += 1
    entries: list[str] = []
    if inline_rest.strip() and "</gallery>" not in inline_rest:
        entries.append(inline_rest)
    closed = "</gallery>" in first_line
    while idx < len(lines) and not closed:
        line = lines[idx]
        if "</gallery>" in line:
            head = line.split("</gallery>", 1)[0]
            if head.strip():
                entries.append(head)
            closed = True
            idx += 1
            break
        entries.append(line)
        idx += 1
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        parts = _split_top_level(entry)
        file_name = _normalize_file_name(parts[0])
        if not _is_image_file(file_name):
            continue
        caption = strip_inline_markup("|".join(parts[1:])) if len(parts) > 1 else ""
        builder.add_figure(
            file_name=file_name,
            caption=caption,
            placement_type="groupMember",
            group_id=group_id,
        )
    return idx


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


def parse_wikitext_layout(
    wikitext: str,
    *,
    source_kind: str = "home_wikipedia",
    title: str = "",
) -> dict[str, Any]:
    """解析 wikitext → 统一结构化 IR（source.layout.json 顶层结构）。"""
    text = str(wikitext or "")
    if not text.strip():
        return build_layout(
            source_kind=source_kind,
            extractor="wikipedia_api",
            title=title,
            blocks=[],
            parse_status="rejected",
            reject_reason="empty_wikitext",
        )
    text = re.sub(r"(?is)<!--.*?-->", "", text)
    text = re.sub(r"(?is)<ref[^>/]*/>", "", text)
    text = re.sub(r"(?is)<ref[^>]*>.*?</ref>", "", text)

    builder = _LayoutBuilder()
    lines = text.splitlines()
    paragraph_buf: list[str] = []

    def _flush_paragraph() -> None:
        nonlocal paragraph_buf
        joined = strip_inline_markup(" ".join(paragraph_buf))
        paragraph_buf = []
        if joined and len(joined) >= 2:
            builder.blocks.append(make_paragraph_block(joined, builder.section_slug))
            builder.paragraph_index += 1

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()

        heading = match_heading(line) if stripped.startswith("=") else None
        if heading is not None:
            _flush_paragraph()
            level, heading_title = heading
            builder.section_slug = slugify_section(heading_title)
            builder.paragraph_index = 0
            builder.blocks.append(
                make_heading_block(level, strip_inline_markup(heading_title), builder.section_slug)
            )
            idx += 1
            continue

        if not stripped:
            _flush_paragraph()
            idx += 1
            continue

        if stripped.startswith("{{"):
            _flush_paragraph()
            idx = _consume_template_block(lines, idx, builder)
            continue

        if re.match(r"(?is)^<gallery\b", stripped) or "<gallery" in stripped.lower():
            _flush_paragraph()
            idx = _consume_gallery_block(lines, idx, builder)
            continue

        if stripped.startswith("{|"):
            _flush_paragraph()
            idx = _consume_table_block(lines, idx, builder)
            continue

        # 行内图片：先提取 figure，再把剩余文本进段落缓冲。
        file_links = _extract_file_links(line)
        for file_name, params, _s, _e in file_links:
            builder.add_figure(
                file_name=file_name,
                caption=_caption_from_file_params(params),
                placement_type="inline",
            )
        remainder = _strip_file_links(line)
        # 定义列表行（; term / ; term : def / : def）：MediaWiki definition list，
        # 不解析会把 `;滃洲县县长` 这类原始语法漏进 source.md（秀山岛问题根因）。
        definition_match = re.match(r"^\s*([;:]+)\s*(.+)$", remainder)
        if definition_match and not definition_match.group(2).lstrip().startswith(("{", "|")):
            _flush_paragraph()
            marker, body = definition_match.groups()
            if marker.startswith(";"):
                parts = _split_top_level(body, ":")
                term = strip_inline_markup(parts[0])
                definition = strip_inline_markup(":".join(parts[1:])) if len(parts) > 1 else ""
                item_text = f"{term}：{definition}" if term and definition else (term or definition)
            else:
                item_text = strip_inline_markup(body)
            if item_text:
                builder.blocks.append(
                    make_list_item_block(item_text, builder.section_slug, origin="wikidefinition")
                )
            idx += 1
            continue
        # 列表行（* / #）：独立 listItem，不并入段落。
        list_match = re.match(r"^\s*[*#]+\s*(.+)$", remainder)
        if list_match:
            _flush_paragraph()
            item_text = strip_inline_markup(list_match.group(1))
            if item_text:
                builder.blocks.append(
                    make_list_item_block(item_text, builder.section_slug, origin="wikilist")
                )
            idx += 1
            continue
        if remainder.strip():
            paragraph_buf.append(remainder)
        idx += 1
    _flush_paragraph()

    paragraphs = [b for b in builder.blocks if b.get("type") == "paragraph"]
    if not paragraphs and not builder.tables and builder.source_order == 0:
        return build_layout(
            source_kind=source_kind,
            extractor="wikipedia_api",
            title=title,
            blocks=builder.blocks,
            tables=builder.tables,
            parse_status="rejected",
            reject_reason="no_content_blocks",
        )
    return build_layout(
        source_kind=source_kind,
        extractor="wikipedia_api",
        title=title,
        blocks=builder.blocks,
        tables=builder.tables,
    )


def placements_from_layout(layout: dict[str, Any]) -> list[dict[str, Any]]:
    """从 IR 派生 placements 视图（含 gallery/表格行图/infobox 图，保 sourceOrder）。"""
    placements: list[dict[str, Any]] = []
    for block in layout.get("blocks") or []:
        if not isinstance(block, dict) or block.get("type") != "figure":
            continue
        placements.append(
            {
                "fileName": str(block.get("fileTitle") or ""),
                "caption": str(block.get("caption") or ""),
                "sectionSlug": str(block.get("sectionSlug") or ""),
                "paragraphIndex": int(block.get("paragraphIndex") or 0),
                "sourceOrder": int(block.get("sourceOrder") or 0),
                "placementType": str(block.get("placementType") or "inline"),
                "groupId": str(block.get("groupId") or ""),
                "coverCandidateRank": int(block.get("coverCandidateRank") or 0),
                "isMapLike": bool(block.get("isMapLike")),
            }
        )
    return sorted(placements, key=lambda row: int(row.get("sourceOrder") or 0))


def parse_wikitext_placements(
    wikitext: str,
    *,
    min_section_body_chars: int = 120,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """解析 wikitext → (sectionOutline, imagePlacements)。

    placements 由结构化 IR 派生：包含正文行内图、gallery 宫格图、表格行图与
    infobox 图（此前只识别行内 `[[File:...]]`，导致图库/表格图整组丢失）。
    """
    if not wikitext:
        return [], []
    outline_nodes = outline_required_sections(
        parse_section_outline(wikitext),
        min_body_chars=min_section_body_chars,
    )
    section_outline = outline_to_dicts(outline_nodes)
    layout = parse_wikitext_layout(wikitext)
    return section_outline, placements_from_layout(layout)


def enrich_meta_from_wikitext(meta: dict[str, Any], wikitext: str) -> dict[str, Any]:
    """把 wikitext 解析结果合并进 source unit meta（不覆盖已有非空字段）。"""
    outline, placements = parse_wikitext_placements(wikitext)
    out = dict(meta)
    if outline and not out.get("sectionOutline"):
        out["sectionOutline"] = outline
    if placements and not out.get("imagePlacements"):
        out["imagePlacements"] = placements
    return out
