"""Revision-specific Parsoid HTML -> loss-accounted source layout IR.

The parser deliberately recognises a small allowlist. Visible structures outside that
allowlist become ``unsupportedOpaque`` blocks; they are never silently discarded.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit

from generated.semantic_document import (
    CANONICALIZATION_VERSION, CAPABILITY_IDS, DIALECT_VERSION, OFFSET_ENCODING,
    SCHEMA_VERSION, DocumentEnvelope, InlineKind, NODE_REGISTRY, NodeKind,
    ProcessingDisposition, SemanticAsset, SemanticInline, SemanticLoss,
    SemanticNode, SourceAnchor, ValidationCode, validate_envelope,
)

from core.section_outline import slugify_section
from core.source_layout import (
    build_layout,
    make_fact_row_block,
    make_figure_block,
    make_heading_block,
    make_list_item_block,
    make_paragraph_block,
    make_table_block,
)

_NOISE_CLASSES = {"mw-editsection", "navbox", "metadata", "noprint", "ambox", "sistersitebox"}
_METADATA_TAGS = {"head", "meta", "link", "style", "script", "noscript", "template", "title", "base"}
_CONTAINER_TAGS = {"html", "body", "main", "article", "section", "div", "span"}
_INLINE_TAGS = {"a", "b", "strong", "i", "em", "small", "sub", "sup", "code", "q", "abbr", "br", "ruby", "rt", "rp", "span"}
_VISIBLE_BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "dl", "figure", "table", "aside", "blockquote", "pre"}


class _Node:
    def __init__(self, tag: str, attrs: dict[str, str] | None = None, parent: "_Node | None" = None, start: int = 0, end: int = 0):
        self.tag, self.attrs, self.parent, self.start, self.end = tag, attrs or {}, parent, start, end
        self.children: list[_Node | str] = []


class _Tree(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.line_offsets = [0]
        for match in re.finditer("\n", source):
            self.line_offsets.append(match.end())
        self.root = _Node("document", start=0, end=len(source))
        self.stack = [self.root]

    def source_offset(self) -> int:
        line, column = self.getpos()
        return self.line_offsets[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        start = self.source_offset()
        node = _Node(tag.lower(), {k.lower(): v or "" for k, v in attrs}, self.stack[-1], start=start)
        self.stack[-1].children.append(node)
        if tag.lower() not in {"br", "img", "hr", "meta", "link", "source", "wbr", "input"}:
            self.stack.append(node)
        else:
            node.end = start + len(self.get_starttag_text() or "")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag.lower():
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for pos in range(len(self.stack) - 1, 0, -1):
            if self.stack[pos].tag == tag:
                end = self.source.find(">", self.source_offset())
                self.stack[pos].end = len(self.source) if end < 0 else end + 1
                del self.stack[pos:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _raw(node: _Node, source: str) -> str:
    return source[node.start:node.end] if node.end >= node.start else ""


def _classes(node: _Node) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _is_noise(node: _Node) -> bool:
    classes = _classes(node)
    return bool(classes & _NOISE_CLASSES or node.attrs.get("role") in {"navigation", "presentation"})


def _text(node: _Node | str, *, hardbreak: str = "\n") -> str:
    if isinstance(node, str):
        return node
    if node.tag in _METADATA_TAGS or _is_noise(node):
        return ""
    if node.tag == "br":
        return hardbreak
    value = "".join(_text(child, hardbreak=hardbreak) for child in node.children)
    return re.sub(r"[ \t\f\v]+", " ", value)


def _clean_text(node: _Node | str) -> str:
    value = _text(node)
    value = re.sub(r" *\n *", "\n", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _source_anchor(node: _Node) -> dict[str, Any]:
    return {"origin": "parsoid_html", "start": node.start, "end": node.end, "selector": node.tag}


def _link_attributes(node: _Node) -> dict[str, Any]:
    href = node.attrs.get("href", "")
    parsed = urlsplit(href)
    if href.startswith("#") or parsed.fragment and (not parsed.scheme and not parsed.netloc):
        link_type = "section" if not "cite_note" in parsed.fragment else "internal"
    elif href.startswith("./") or href.startswith("../") or href.startswith("/"):
        link_type = "internal"
    elif parsed.scheme in {"http", "https"}:
        link_type = "external"
    else:
        link_type = "interwiki"
    return {"href": href, "linkType": link_type, "rel": node.attrs.get("rel", ""), "title": node.attrs.get("title", ""), "sourceAnchor": _source_anchor(node)}


def _ref_identity(node: _Node) -> tuple[str, str, str]:
    anchor = next(iter(_descendants(node, {"a"})), None)
    href = anchor.attrs.get("href", "") if anchor else ""
    fragment = unquote(urlsplit(href).fragment)
    identity = fragment or node.attrs.get("id", "")
    name = ""
    try:
        data_mw = json.loads(node.attrs.get("data-mw") or "{}")
        name = str((data_mw.get("attrs") or {}).get("name") or "")
        body_id = str((data_mw.get("body") or {}).get("id") or "")
        identity = body_id.removeprefix("mw-reference-text-") or identity
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return identity, href, name


def _inline_runs(node: _Node, *, exclude_reference_backlinks: bool = False) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []

    def add(kind: str, text: str = "", **extra: Any) -> None:
        if kind != "hardBreak":
            text = re.sub(r"\s+", " ", text)
            if not text.strip() and kind not in {"link", "footnoteRef"}:
                return
        row = {"type": kind}
        if text:
            row["text"] = text
        row.update(extra)
        runs.append(row)

    def walk(value: _Node | str, marks: tuple[str, ...] = (), lang: str = "") -> None:
        if isinstance(value, str):
            add("text", value, marks=list(marks), **({"lang": lang} if lang else {}))
            return
        if value.tag in _METADATA_TAGS or _is_noise(value):
            return
        if exclude_reference_backlinks and value.tag == "span" and "mw-cite-backlink" in _classes(value):
            return
        child_lang = value.attrs.get("lang", lang)
        if value.tag == "br":
            add("hardBreak", sourceAnchor=_source_anchor(value))
        elif value.tag == "sup" and ("reference" in _classes(value) or value.attrs.get("typeof", "").startswith("mw:Extension/ref")):
            identity, href, name = _ref_identity(value)
            add("footnoteRef", _clean_text(value), refId=identity, href=href, name=name, sourceAnchor=_source_anchor(value))
        elif value.tag == "a":
            add("link", _clean_text(value), marks=list(marks), **_link_attributes(value))
        elif value.tag in {"b", "strong", "i", "em", "sub", "sup", "code"}:
            mark = {"b": "strong", "strong": "strong", "i": "emphasis", "em": "emphasis", "sub": "sub", "sup": "sup", "code": "inlineCode"}[value.tag]
            for child in value.children:
                walk(child, marks + (mark,), child_lang)
        elif value.tag == "abbr":
            for child in value.children:
                walk(child, marks + ("abbr",), child_lang)
            if runs and value.attrs.get("title"):
                runs[-1]["abbrTitle"] = value.attrs["title"]
        elif value.tag == "ruby":
            add("text", _clean_text(value), marks=list(marks) + ["ruby"], rubyText=_clean_text(value), lang=child_lang)
        else:
            for child in value.children:
                walk(child, marks, child_lang)
    walk(node)
    return runs


def _descendants(node: _Node, tags: set[str]) -> Iterable[_Node]:
    for child in node.children:
        if isinstance(child, _Node):
            if child.tag in tags:
                yield child
            yield from _descendants(child, tags)


def _direct(node: _Node, tags: set[str]) -> list[_Node]:
    return [child for child in node.children if isinstance(child, _Node) and child.tag in tags]


def _int_attr(node: _Node, name: str) -> int:
    try:
        return max(1, int(node.attrs.get(name, "1")))
    except ValueError:
        return 1


def _cell_payload(cell: _Node, row: int, column: int, *, rowspan: int, colspan: int, header: bool) -> dict[str, Any]:
    inlines = _inline_runs(cell)
    return {
        "text": _clean_text(cell), "inlines": inlines,
        "blocks": [{"type": "paragraph", "text": _clean_text(cell), "inlines": inlines}] if _clean_text(cell) else [],
        "row": row, "column": column, "rowspan": rowspan, "colspan": colspan,
        "header": header, "covered": False, "scope": cell.attrs.get("scope", ""),
        "sortKey": cell.attrs.get("data-sort-value", cell.attrs.get("data-sort-key", "")),
        "sourceAnchor": _source_anchor(cell),
    }


def _logical_table(table: _Node) -> tuple[list[str], list[list[str]], list[list[dict[str, Any]]]]:
    physical: list[list[tuple[_Node, int, int, bool]]] = []
    for tr in _descendants(table, {"tr"}):
        cells = _direct(tr, {"th", "td"})
        if cells:
            physical.append([(cell, _int_attr(cell, "rowspan"), _int_attr(cell, "colspan"), cell.tag == "th") for cell in cells])
    grid: list[list[dict[str, Any] | None]] = []
    active: dict[int, tuple[int, dict[str, Any]]] = {}
    for rindex, row in enumerate(physical):
        logical: list[dict[str, Any] | None] = []
        col = 0
        def fill_active() -> None:
            nonlocal col
            while col in active:
                left, origin = active[col]
                while len(logical) <= col:
                    logical.append(None)
                logical[col] = {**origin, "row": rindex, "column": col, "covered": True, "originRow": origin["row"], "originColumn": origin["column"]}
                if left <= 1: del active[col]
                else: active[col] = (left - 1, origin)
                col += 1
        fill_active()
        for node, rowspan, colspan, is_header in row:
            fill_active()
            cell = _cell_payload(node, rindex, col, rowspan=rowspan, colspan=colspan, header=is_header)
            for offset in range(colspan):
                target = col + offset
                while len(logical) <= target: logical.append(None)
                logical[target] = cell if offset == 0 else {**cell, "column": target, "covered": True, "originRow": rindex, "originColumn": col}
                if rowspan > 1: active[target] = (rowspan - 1, cell)
            col += colspan
        fill_active()
        grid.append([item or {"text": "", "inlines": [], "blocks": [], "row": rindex, "column": pos, "rowspan": 1, "colspan": 1, "header": False, "covered": False, "scope": "", "sortKey": "", "sourceAnchor": _source_anchor(table)} for pos, item in enumerate(logical)])
    width = max((len(row) for row in grid), default=0)
    for rindex, row in enumerate(grid):
        row.extend({"text": "", "inlines": [], "blocks": [], "row": rindex, "column": pos, "rowspan": 1, "colspan": 1, "header": False, "covered": False, "scope": "", "sortKey": "", "sourceAnchor": _source_anchor(table)} for pos in range(len(row), width))
    header_count = 1 if grid and any(cell["header"] for cell in grid[0]) else 0
    headers = [cell["text"] for cell in grid[0]] if header_count else [f"column-{i + 1}" for i in range(width)]
    rows = [[cell["text"] for cell in row] for row in grid[header_count:]]
    return headers, rows, [[dict(cell) for cell in row] for row in grid]


def _grouped_directory(headers: list[str], grid: list[list[dict[str, Any]]]) -> bool:
    label = " ".join(headers).casefold()
    has_directory_label = bool(re.search(r"名称|名录|列表|项目|景点|人物|入祀人物|帝王|朝代|王朝|组|分组|name|item|site|person|dynasty|group", label))
    has_group_span = any(cell.get("rowspan", 1) > 1 for row in grid for cell in row if not cell.get("covered"))
    return len(headers) >= 2 and has_directory_label and (has_group_span or len(grid) >= 4)


def _is_reference_definition(node: _Node) -> bool:
    return node.tag == "li" and node.attrs.get("id", "").startswith("cite_note")


def _nearest(node: _Node, predicate: Any) -> _Node | None:
    current = node.parent
    while current:
        if predicate(current): return current
        current = current.parent
    return None


def _image_payload(image: _Node, *, source_order: int, placement_type: str, caption: str, section_slug: str, group_id: str) -> dict[str, Any]:
    resource = image.attrs.get("resource", "")
    link = _nearest(image, lambda n: n.tag == "a")
    original_href = link.attrs.get("href", "") if link else ""
    file_source = resource or original_href
    file_title = unquote(urlsplit(file_source).path.rsplit("/", 1)[-1]).replace("_", " ")
    if file_title and not file_title.lower().startswith("file:") and resource.startswith("./File:"):
        file_title = "File:" + file_title
    block = make_figure_block(source_order=source_order, file_title=file_title, caption=caption, section_slug=section_slug, placement_type=placement_type, group_id=group_id, cover_candidate_rank=-1 if placement_type == "locatorMap" else (source_order + 1 if placement_type == "infoboxLead" else 0))
    block.update(resource=resource, src=image.attrs.get("src", ""), srcset=image.attrs.get("srcset", ""), originalHref=original_href, alt=image.attrs.get("alt", ""), imageLink=_link_attributes(link) if link else {}, captionInlines=_inline_runs(next(iter(_descendants(_nearest(image, lambda n: n.tag == "figure") or image, {"figcaption"})), image)), order=source_order, sourceAnchor=_source_anchor(image))
    if placement_type == "locatorMap":
        block["assetIdentity"] = {"kind": "wikimedia_kartographer_render", "revisionBound": True, "resourceUrl": image.attrs.get("src", ""), "rightsDisposition": "generated_map_requires_attribution", "noise": False}
    return block


def parse_parsoid_layout(html_text: str, *, title: str = "", revision: int | str | None = None, source_kind: str = "home_wikipedia") -> dict[str, Any]:
    source = str(html_text or "")
    parser = _Tree(source)
    parser.feed(source)
    blocks: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    losses: list[dict[str, Any]] = []
    section_slug = ""
    source_order = 0
    group_seq = 0
    recognized = unsupported = 0
    disposition_counts = {item.value: 0 for item in ProcessingDisposition}
    emitted_images: set[int] = set()

    def attach(block: dict[str, Any], node: _Node, disposition: ProcessingDisposition = ProcessingDisposition.NORMALIZED) -> dict[str, Any]:
        block["sourceAnchor"] = {"origin": "parsoid_html", "start": node.start, "end": node.end, "selector": node.tag}
        block["disposition"] = disposition.value
        disposition_counts[disposition.value] += 1
        return block

    def add_opaque(node: _Node, reason: str) -> None:
        nonlocal unsupported
        text = _clean_text(node)
        if not text:
            return
        unsupported += 1
        raw_slice = _raw(node, source)
        fingerprint = hashlib.sha256(raw_slice.encode()).hexdigest()
        blocks.append(attach({"type": NodeKind.UNSUPPORTED_OPAQUE.value, "tag": node.tag, "text": text, "sectionSlug": section_slug, "reason": reason, "rawSlice": raw_slice, "rawSliceFingerprint": fingerprint}, node, ProcessingDisposition.UNSUPPORTED_OPAQUE))
        dispositions.append({"kind": node.tag, "disposition": ProcessingDisposition.UNSUPPORTED_OPAQUE.value, "reason": reason})
        losses.append({"code": "SEMANTIC.UNSUPPORTED_VISIBLE", "disposition": ProcessingDisposition.UNSUPPORTED_OPAQUE.value, "sourceAnchor": {"origin": "parsoid_html", "start": node.start, "end": node.end, "selector": node.tag}, "detailKey": reason})

    def walk(node: _Node, list_kind: str = "", depth: int = 0) -> None:
        nonlocal section_slug, source_order, group_seq, recognized
        if node.tag in _METADATA_TAGS:
            dispositions.append({"kind": node.tag, "disposition": ProcessingDisposition.METADATA_ONLY.value})
            disposition_counts[ProcessingDisposition.METADATA_ONLY.value] += 1
            return
        if _is_noise(node):
            dispositions.append({"kind": node.tag, "disposition": ProcessingDisposition.DROPPED_NOISE.value, "classes": sorted(_classes(node))})
            disposition_counts[ProcessingDisposition.DROPPED_NOISE.value] += 1
            return
        if node.tag == "div" and "hatnote" in _classes(node):
            text = _clean_text(node)
            if text:
                blocks.append(attach({"type": NodeKind.HATNOTE.value, "text": text, "inlines": _inline_runs(node), "sectionSlug": section_slug}, node))
                recognized += 1
            return
        if re.fullmatch(r"h[1-6]", node.tag):
            text = _clean_text(node)
            if text:
                level = int(node.tag[1])
                section_slug = slugify_section(text)
                block = make_heading_block(level, text, section_slug)
                block["inlines"] = _inline_runs(node)
                blocks.append(attach(block, node))
                recognized += 1
            return
        if node.tag == "p":
            text = _clean_text(node)
            if text:
                block = make_paragraph_block(text, section_slug)
                block["inlines"] = _inline_runs(node)
                block["hardbreakCount"] = sum(run["type"] in {"hardbreak", "hardBreak"} for run in block["inlines"])
                blocks.append(attach(block, node))
                recognized += 1
            return
        if node.tag == "ol" and ("references" in _classes(node) or node.attrs.get("typeof", "").startswith("mw:Extension/references")):
            for child in _direct(node, {"li"}): walk(child, list_kind, depth)
            return
        if node.tag in {"ul", "ol"} and "gallery" not in _classes(node):
            group_seq += 1
            group = f"list-{group_seq:03d}"
            children = _direct(node, {"li"})
            if not children:
                children = [item for item in _descendants(node, {"li"}) if _nearest(item, lambda value: value.tag in {"ul", "ol"}) is node]
            for child in children:
                text = " ".join(part.strip() for part in (_text(c) for c in child.children if not isinstance(c, _Node) or c.tag not in {"ul", "ol"}) if part.strip())
                if text:
                    block = make_list_item_block(text, section_slug, list_group_id=group, origin="parsoid")
                    block.update(listKind="ordered" if node.tag == "ol" else "unordered", depth=depth)
                    inline_host = _Node("span", parent=child, start=child.start, end=child.end)
                    inline_host.children = [c for c in child.children if not isinstance(c, _Node) or c.tag not in {"ul", "ol"}]
                    block["inlines"] = _inline_runs(inline_host)
                    blocks.append(attach(block, child)); recognized += 1
                for nested in _direct(child, {"ul", "ol"}):
                    walk(nested, nested.tag, depth + 1)
            return
        if node.tag == "dl":
            group_seq += 1
            group = f"definition-{group_seq:03d}"
            term = ""
            next_term: _Node | None = None
            for child in _direct(node, {"dt", "dd"}):
                value = _clean_text(child)
                if child.tag == "dt":
                    term = value
                    next_term = child
                elif value:
                    block = make_list_item_block(f"{term}：{value}" if term else value, section_slug, list_group_id=group, origin="parsoid_definition")
                    block.update(listKind="definition", term=term, definition=value, termInlines=_inline_runs(next_term) if next_term else [], definitionInlines=_inline_runs(child), depth=depth)
                    block["inlines"] = [*block["termInlines"], {"type": "text", "text": "："}, *block["definitionInlines"]] if term else block["definitionInlines"]
                    blocks.append(attach(block, child)); recognized += 1
            return
        if node.tag in {"figure", "gallery"} or "gallery" in _classes(node):
            group_seq += 1
            group = f"gallery-{group_seq:03d}" if node.tag == "gallery" or "gallery" in _classes(node) else ""
            images = list(_descendants(node, {"img"}))
            caption_nodes = list(_descendants(node, {"figcaption"}))
            caption = _clean_text(caption_nodes[0]) if caption_nodes else ""
            for image in images:
                if id(image) in emitted_images: continue
                block = _image_payload(image, source_order=source_order, placement_type="groupMember" if group else "inline", caption=caption, section_slug=section_slug, group_id=group)
                if block["fileTitle"] or block["src"]:
                    blocks.append(attach(block, image)); emitted_images.add(id(image))
                    source_order += 1; recognized += 1
            if not images:
                add_opaque(node, "figure_without_supported_image")
            return
        if node.tag == "table" and "infobox" not in _classes(node):
            headers, rows, logical_grid = _logical_table(node)
            caption_nodes = _direct(node, {"caption"})
            caption = _clean_text(caption_nodes[0]) if caption_nodes else ""
            table_id = f"table-{len(tables) + 1:03d}"
            grouped = _grouped_directory(headers, logical_grid)
            block = make_table_block(headers=headers, rows=rows, caption=caption, section_slug=section_slug, table_id=table_id, logical_grid=logical_grid, grouped_directory=grouped)
            blocks.append(attach(block, node))
            tables.append({"tableId": table_id, "caption": caption, "sectionSlug": section_slug, "rowCount": len(rows), "columnCount": len(headers), "logicalGrid": logical_grid, "mappingDecision": "groupedDirectory" if grouped else "table", "groupedDirectory": grouped})
            recognized += 1
            return
        if node.tag == "aside" or "infobox" in _classes(node):
            emitted = 0
            for descendant in _descendants(node, {"img", "tr"}):
                if descendant.tag == "img" and id(descendant) not in emitted_images:
                    classes = _classes(_nearest(descendant, lambda n: n.tag in {"td", "th"}) or descendant)
                    resource = descendant.attrs.get("resource", "")
                    placement = "locatorMap" if not resource or "infobox-full-data" in classes else "infoboxLead"
                    block = _image_payload(descendant, source_order=source_order, placement_type=placement, caption="", section_slug=section_slug, group_id="")
                    blocks.append(attach(block, descendant)); emitted_images.add(id(descendant)); source_order += 1; emitted += 1; recognized += 1
                elif descendant.tag == "tr":
                    cells = _direct(descendant, {"th", "td"})
                    if cells:
                        key = _clean_text(cells[0])
                        value = _clean_text(cells[1]) if len(cells) >= 2 else ""
                        key_inlines = _inline_runs(cells[0]); value_inlines = _inline_runs(cells[1]) if len(cells) >= 2 else []
                        if (key or key_inlines or value_inlines) and (value or value_inlines or len(cells) == 1):
                            block = make_fact_row_block(key, value, section_slug)
                            block.update(keyInlines=key_inlines, valueInlines=value_inlines, inlines=[*key_inlines, *([{"type": "text", "text": "："}, *value_inlines] if value else [])])
                            blocks.append(attach(block, descendant)); emitted += 1; recognized += 1
            if not emitted: add_opaque(node, "unsupported_factbox_shape")
            return
        if _is_reference_definition(node):
            ref_id = node.attrs.get("id", "")
            backlinks = [a.attrs.get("href", "") for a in _descendants(node, {"a"}) if "#cite_ref" in a.attrs.get("href", "")]
            definition_links = [{"type": "link", "text": _clean_text(a), **_link_attributes(a)} for a in _descendants(node, {"a"}) if "#cite_ref" not in a.attrs.get("href", "")]
            block = {"type": "footnoteDefinition", "refId": ref_id, "text": _clean_text(node), "inlines": _inline_runs(node, exclude_reference_backlinks=True), "definitionLinks": definition_links, "backlinks": backlinks, "order": len([b for b in blocks if b.get("type") == "footnoteDefinition"]), "sectionSlug": section_slug}
            blocks.append(attach(block, node)); recognized += 1
            return
        if node.tag in {"sup"} and ("reference" in _classes(node) or node.attrs.get("typeof", "").startswith("mw:Extension/ref")):
            text = _clean_text(node)
            blocks.append(attach({"type": NodeKind.FOOTNOTE_REFERENCE.value, "text": text, "refId": _ref_identity(node)[0], "href": _ref_identity(node)[1], "name": _ref_identity(node)[2], "sectionSlug": section_slug}, node))
            recognized += 1
            return
        if node.tag in {"blockquote", "pre"}:
            add_opaque(node, "visible_block_outside_p0_p1_allowlist")
            return
        if node.tag in _CONTAINER_TAGS or node.tag in {"document", "li", "dt", "dd", "tbody", "thead", "tfoot"}:
            if "infobox" in _classes(node):
                walk_aside = _Node("aside", node.attrs, node.parent); walk_aside.children = node.children
                walk(walk_aside); return
            for child in node.children:
                if isinstance(child, _Node):
                    walk(child, list_kind, depth)
                elif child.strip() and node.tag not in {"document", "html", "body"}:
                    add_opaque(node, "visible_text_in_unstructured_container"); break
            return
        if node.tag in _INLINE_TAGS:
            if _clean_text(node):
                add_opaque(node, "orphan_inline_content")
            return
        if _clean_text(node):
            add_opaque(node, "unknown_visible_structure")

    walk(parser.root)
    definitions = [b for b in blocks if b.get("type") == "footnoteDefinition"]
    if definitions:
        first, last = definitions[0]["sourceAnchor"], definitions[-1]["sourceAnchor"]
        blocks.append({"type": "footnoteList", "definitionIds": [b["refId"] for b in definitions], "count": len(definitions), "sectionSlug": section_slug, "sourceAnchor": {"origin": "parsoid_html", "start": first["start"], "end": last["end"], "selector": "ol.references"}, "disposition": ProcessingDisposition.NORMALIZED.value})
        recognized += 1; disposition_counts[ProcessingDisposition.NORMALIZED.value] += 1
    visible = recognized + unsupported
    coverage = 1.0 if visible == 0 else recognized / visible
    return build_layout(
        source_kind=source_kind,
        extractor="mediawiki_parsoid_exact_revision",
        title=title,
        blocks=blocks,
        tables=tables,
        capture_coverage={"wikitext": True, "parsoidHtml": True, "revisionSpecific": revision is not None},
        semantic_parse_coverage={"recognizedVisibleNodes": recognized, "unsupportedVisibleNodes": unsupported, "visibleCandidateNodes": visible, "visibleClassifiedNodes": recognized + unsupported, "allVisibleClassified": visible == recognized + unsupported, "classifiedNodeTotal": sum(disposition_counts.values()), "ratio": round(coverage, 6), "status": "complete" if unsupported == 0 and visible == recognized + unsupported else "partial", "homepageComplete": unsupported == 0 and visible == recognized + unsupported, "publicationDecision": "publish" if unsupported == 0 and visible == recognized + unsupported else "block", "dispositionCounts": disposition_counts},
        dispositions=dispositions,
        losses=losses,
        source_profile={"source": "wikipedia", "representation": "parsoid_html", "revision": revision, "parserProfile": "safe_allowlist_p0_p1"},
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, ProcessingDisposition | NodeKind | InlineKind):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _anchor(block: dict[str, Any], index: int, source_length: int) -> SourceAnchor:
    raw = block.get("sourceAnchor") or {}
    return SourceAnchor(
        origin=str(raw.get("origin") or "parsoid_html"),
        start=max(0, int(raw.get("start") or 0)),
        end=min(source_length, max(0, int(raw.get("end") or 0))),
        selector=str(raw.get("selector") or f"block[{index}]"),
    )


def _inline_kind(run: dict[str, Any]) -> InlineKind:
    kind = run.get("type")
    if kind == "link":
        return InlineKind.LINK
    if kind in {"hardbreak", "hardBreak"}:
        return InlineKind.HARD_BREAK
    if kind == "footnoteRef":
        return InlineKind.FOOTNOTE_REFERENCE
    marks = set(run.get("marks") or [])
    if {"strong", "emphasis"} <= marks:
        return InlineKind.BOLD_ITALIC
    if "strong" in marks:
        return InlineKind.BOLD
    if "emphasis" in marks:
        return InlineKind.ITALIC
    return InlineKind.TEXT


def _semantic_kind(block: dict[str, Any]) -> NodeKind:
    return {
        "heading": NodeKind.HEADING,
        "paragraph": NodeKind.PARAGRAPH,
        "listItem": NodeKind.LIST_ITEM,
        "table": NodeKind.TABLE,
        "figure": NodeKind.FIGURE,
        "factRow": NodeKind.FACT_ROW,
        "footnoteRef": NodeKind.FOOTNOTE_REFERENCE,
        "footnoteDefinition": NodeKind.FOOTNOTE_DEFINITION,
        "footnoteList": NodeKind.FOOTNOTE_LIST,
        NodeKind.HATNOTE.value: NodeKind.HATNOTE,
        NodeKind.UNSUPPORTED_OPAQUE.value: NodeKind.UNSUPPORTED_OPAQUE,
    }.get(str(block.get("type")), NodeKind.UNSUPPORTED_OPAQUE)


def _node(block: dict[str, Any], index: int, source: str) -> SemanticNode:
    kind = _semantic_kind(block)
    anchor = _anchor(block, index, len(source))
    disposition = ProcessingDisposition(str(block.get("disposition") or ProcessingDisposition.NORMALIZED.value))
    raw_slice = block.get("rawSlice")
    if kind == NodeKind.UNSUPPORTED_OPAQUE and raw_slice is None:
        raw_slice = source[anchor.start:anchor.end]
    raw_fingerprint = hashlib.sha256(str(raw_slice).encode()).hexdigest() if raw_slice is not None else None
    attributes = {key: value for key, value in block.items() if key not in {"type", "sourceAnchor", "disposition", "rawSlice", "rawSliceFingerprint", "inlines"}}
    inlines: list[SemanticInline] = []
    cursor = anchor.start
    for run in block.get("inlines") or []:
        text = str(run.get("text") or "")
        end = cursor if run.get("type") in {"hardbreak", "hardBreak"} else min(anchor.end, cursor + len(text))
        inlines.append(SemanticInline(_inline_kind(run), cursor, end, {key: value for key, value in run.items() if key not in {"type", "text"}}))
        cursor = end
    losses: tuple[SemanticLoss, ...] = ()
    if disposition == ProcessingDisposition.UNSUPPORTED_OPAQUE:
        losses = (SemanticLoss("SEMANTIC.UNSUPPORTED_VISIBLE", anchor, str(block.get("reason") or "unknown_visible_structure")),)
    payload = {"kind": kind.value, "disposition": disposition.value, "anchor": asdict(anchor), "attributes": attributes, "rawSliceFingerprint": raw_fingerprint}
    fingerprint = hashlib.sha256(_canonical(payload)).hexdigest()
    capabilities = tuple(sorted(NODE_REGISTRY[kind][1]))
    return SemanticNode(f"n{index + 1:06d}-{fingerprint[:12]}", kind, disposition, "wikipedia-parsoid-safe-v1", capabilities, losses, fingerprint, anchor, rawSlice=raw_slice, rawSliceFingerprint=raw_fingerprint, attributes=attributes, inlines=tuple(inlines))


def _directory_node(table_node: SemanticNode, index: int) -> SemanticNode:
    attrs = dict(table_node.attributes or {})
    grid = attrs.get("logicalGrid") or []
    headers = attrs.get("headers") or []
    group_column = next((pos for pos, value in enumerate(headers) if re.search(r"王朝|朝代|分组|区域|时期|组|dynasty|group", str(value), re.I)), 0)
    member_column = next((pos for pos, value in enumerate(headers) if re.search(r"入祀人物|人物|帝王|名称|member|person|name", str(value), re.I)), min(1, max(0, len(headers) - 1)))
    groups: list[dict[str, Any]] = []
    current_cell: dict[str, Any] = {}
    for order, row in enumerate(grid[1:] if grid and any(cell.get("header") for cell in grid[0]) else grid):
        if group_column < len(row) and not row[group_column].get("covered") and row[group_column].get("text"):
            current_cell = row[group_column]
        member_cell = row[member_column] if member_column < len(row) else {}
        member = str(member_cell.get("text") or "")
        label = str(current_cell.get("text") or "")
        if member:
            if not groups or groups[-1]["label"] != label:
                groups.append({"label": label, "inlines": current_cell.get("inlines") or [], "sourceAnchor": current_cell.get("sourceAnchor"), "members": []})
            groups[-1]["members"].append({"order": order, "text": member, "inlines": member_cell.get("inlines") or [], "sourceAnchor": member_cell.get("sourceAnchor")})
    directory_attrs = {"groups": groups, "sourceTableNodeId": table_node.nodeId, "logicalGrid": grid, "headers": headers}
    fingerprint = hashlib.sha256(_canonical(directory_attrs)).hexdigest()
    kind = NodeKind.GROUPED_DIRECTORY
    return SemanticNode(f"n{index + 1:06d}-{fingerprint[:12]}", kind, ProcessingDisposition.NORMALIZED, "wikipedia-parsoid-safe-v1", tuple(sorted(NODE_REGISTRY[kind][1])), (), fingerprint, table_node.sourceAnchor, attributes=directory_attrs)


def build_semantic_document(layout: dict[str, Any], html_text: str, *, revision: int | str) -> dict[str, Any]:
    nodes: list[SemanticNode] = []
    assets: dict[str, SemanticAsset] = {}
    for block in layout.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        node = _node(block, len(nodes), html_text)
        nodes.append(node)
        if node.kind == NodeKind.FIGURE:
            asset_id = str((node.attributes or {}).get("figureId") or node.nodeId)
            assets[asset_id] = SemanticAsset(asset_id, dict(node.attributes or {}))
        if node.kind == NodeKind.TABLE and bool((node.attributes or {}).get("groupedDirectory")):
            nodes.append(_directory_node(node, len(nodes)))
    required = tuple(sorted({cap for node in nodes for cap in node.requiredCapabilities}))
    losses = tuple(loss for node in nodes for loss in node.losses)
    source_map = {node.nodeId: node.sourceAnchor for node in nodes}
    # Authoring fingerprint covers semantic content and source bindings, excluding
    # both envelope self-identifiers. Canonical digest covers the complete canonical
    # envelope excluding only canonicalDigest itself.
    draft = DocumentEnvelope(SCHEMA_VERSION, DIALECT_VERSION, CANONICALIZATION_VERSION, OFFSET_ENCODING, tuple(nodes), required, assets, source_map, "wikipedia-parsoid-safe-v1", losses, "", "")
    draft_value = _json_value(asdict(draft))
    semantic_material = {key: value for key, value in draft_value.items() if key not in {"semanticFingerprint", "canonicalDigest"}}
    semantic_fingerprint = hashlib.sha256(_canonical(semantic_material)).hexdigest()
    envelope = DocumentEnvelope(SCHEMA_VERSION, DIALECT_VERSION, CANONICALIZATION_VERSION, OFFSET_ENCODING, tuple(nodes), required, assets, source_map, "wikipedia-parsoid-safe-v1", losses, semantic_fingerprint, "")
    value = _json_value(asdict(envelope))
    canonical_material = {key: item for key, item in value.items() if key != "canonicalDigest"}
    value["canonicalDigest"] = hashlib.sha256(_canonical(canonical_material)).hexdigest()
    result = validate_envelope(value, CAPABILITY_IDS)
    if result.code != ValidationCode.OK:
        raise ValueError(f"semantic envelope invalid: {result.code.value}:{result.detail}")
    return value


def verify_semantic_document(value: dict[str, Any]) -> dict[str, bool]:
    validation = validate_envelope(value, CAPABILITY_IDS)
    canonical_material = {key: item for key, item in value.items() if key != "canonicalDigest"}
    semantic_material = {key: item for key, item in value.items() if key not in {"semanticFingerprint", "canonicalDigest"}}
    raw_ok = True
    for node in value.get("nodes") or []:
        raw_slice = node.get("rawSlice")
        fingerprint = node.get("rawSliceFingerprint")
        if raw_slice is not None and hashlib.sha256(str(raw_slice).encode()).hexdigest() != fingerprint:
            raw_ok = False
    return {
        "generatedValidator": validation.code == ValidationCode.OK,
        "canonicalDigest": hashlib.sha256(_canonical(canonical_material)).hexdigest() == value.get("canonicalDigest"),
        "semanticFingerprint": hashlib.sha256(_canonical(semantic_material)).hexdigest() == value.get("semanticFingerprint"),
        "rawSliceFingerprints": raw_ok,
    }


__all__ = ["parse_parsoid_layout", "build_semantic_document", "verify_semantic_document"]
