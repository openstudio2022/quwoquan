"""MediaWiki wikitext 结构解析：统一结构化 IR（五种通用块）+ 兼容 placements 视图。

从 `action=parse&prop=wikitext` 返回的 wikitext 解析出结构化 IR
（真相源契约见 `core/source_layout.py`）：

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

`parse_wikitext_placements` 由 IR 派生：placements **包含**
gallery / 表格行图 / infobox 图（修复武侯祠图库只剩 1 张的根因），并携带
placementType / groupId / coverCandidateRank。
"""
from __future__ import annotations

import re
from typing import Any

from core.section_outline import (
    SOURCE_OUTLINE_MIN_BODY_CHARS,
    match_heading,
    outline_required_sections,
    outline_to_dicts,
    parse_section_outline,
    slugify_section,
)
from core.source_layout import (
    build_layout,
    is_map_like,
    make_fact_row_block,
    make_figure_block,
    make_heading_block,
    make_list_item_block,
    make_paragraph_block,
    make_table_block,
)
from core.page_media import PageImagePlacement, PageImagePlacementType
from core.wiki_markup import (
    extract_file_links as _extract_file_links,
    file_caption as _caption_from_file_params,
    is_image_file as _is_image_file,
    is_file_reference,
    normalize_file_name as _normalize_file_name,
    split_top_level as _split_top_level,
    strip_file_links as _strip_file_links,
    strip_inline_markup,
)

# infobox/键值模板中的图片、图注与地图字段（key 归一小写后匹配）。
_INFOBOX_IMAGE_KEY_RE = re.compile(r"(?:image|img|photo|logo|图片|圖片|图像|圖像|照片)")
_INFOBOX_CAPTION_KEY_RE = re.compile(r"(?:caption|说明|說明)")
_INFOBOX_MAP_KEY_RE = re.compile(r"(?:map|pushpin|地图|地圖|位置图|位置圖)")
# 参考资料/导航/坐标类表格：对主页无价值，mappingDecision=dropped。

# MediaWiki cell 属性前缀（`| attrs | content` 的 attrs 段）：`key=value` 序列，
# value 可带或不带引号。源站手写属性常有 typo（如 `avlign=top`），按语法位置识别，
# 不按属性名白名单——凡「首个 | 之前是纯 key=value 串」都视为属性剥离。
# 合并单元格/复杂结构属性：命中即视为复杂表，不走 GFM 保真。




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
    template_match = re.match(r"^\s*\{\{\s*([^|}\n]+)", body)
    template_name = re.sub(r"[\s_-]+", "", template_match.group(1).casefold()) if template_match else ""
    if template_name in {"gallery", "图集", "圖集"}:
        group_id = builder.next_group_id("gal")
        for raw_line in body.splitlines()[1:]:
            value = raw_line.strip()
            if not value.startswith("|"):
                continue
            value = value[1:].strip()
            if not is_file_reference(value):
                continue
            parts = _split_top_level(value)
            file_name = _normalize_file_name(parts[0])
            if not _is_image_file(file_name):
                continue
            caption = strip_inline_markup("|".join(parts[1:])) if len(parts) > 1 else ""
            builder.add_figure(
                file_name=file_name,
                caption=caption,
                placement_type=PageImagePlacementType.GROUP_MEMBER.value,
                group_id=group_id,
            )
        return idx

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












def parse_wikitext_layout(
    wikitext: str,
    *,
    source_kind: str = "home_wikipedia",
    title: str = "",
) -> dict[str, Any]:
    from core.wiki_table import _consume_table_block

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
                placement_type=(
                    PageImagePlacementType.LEAD.value
                    if not builder.section_slug and builder.paragraph_index == 0
                    else PageImagePlacementType.INLINE.value
                ),
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
        placement_type = PageImagePlacementType(
            str(block.get("placementType") or PageImagePlacementType.INLINE.value)
        )
        placements.append(
            PageImagePlacement(
                file_title=str(block.get("fileTitle") or ""),
                caption=str(block.get("caption") or ""),
                section_slug=str(block.get("sectionSlug") or ""),
                paragraph_index=int(block.get("paragraphIndex") or 0),
                source_order=int(block.get("sourceOrder") or 0),
                placement_type=placement_type,
                group_id=str(block.get("groupId") or ""),
                cover_rank=int(block.get("coverCandidateRank") or 0),
                placeholder_id=f"source-inline-{int(block.get('sourceOrder') or 0) + 1:03d}",
                is_map_like=bool(block.get("isMapLike")),
            ).as_dict()
        )
    return sorted(placements, key=lambda row: int(row.get("sourceOrder") or 0))


def parse_wikitext_placements(
    wikitext: str,
    *,
    min_section_body_chars: int = SOURCE_OUTLINE_MIN_BODY_CHARS,
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
