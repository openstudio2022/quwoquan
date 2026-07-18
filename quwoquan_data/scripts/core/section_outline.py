"""章节大纲解析：从来源 / 成品 Markdown 提取标题层级与每节正文规模。

唯一职责：把含 wiki `== 标题 ==` / `=== 标题 ===` 或 markdown `## 标题` /
`### 标题` 的纯文本，解析为有序 outline 节点（level/title/slug/charStart/
bodyChars/paragraphs），供三方共享的单一 outline 真相源（R24/R-CS01）：

- compose：下发原文章节结构，要求 Agent 保留有实质内容的 H2/H3。
- placement：按章节锚点把配图定位到对应 `##`/`###` 标题下。
- gate：校验关键章节（有实质正文）是否在成品中被静默丢弃。

本模块只读解析，**不修改** `content_evidence.clean_source_markdown` 的文本契约。
注意：`source.clean.md` 已把 wiki `==` 标题压成无标记纯文本行，会丢层级；因此
outline 必须从仍含 `==`/`===` 的 `source.md`（或成品 `page.md` 的 `##`）解析。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

# markdown 标题：## 标题 / ### 标题（行首 1-6 个 #，后随空白与标题文本）。
_MD_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
# wiki 标题：== 标题 == / === 标题 ===（行首 2-6 个 =，与 content_evidence 同源语义）。
_WIKI_HEADING_RE = re.compile(r"^\s*(={2,6})\s*(.+?)\s*=*\s*$")
# slug 归一化时剔除的标点（中英文括号 / 顿号 / 标点等），便于跨清洗版本做章节匹配。
_SLUG_DROP_RE = re.compile(r"""[（）()\[\]【】「」『』·.,，。:：;；!！?？"'""''`~～\s—\-/]+""")
SOURCE_OUTLINE_MIN_BODY_CHARS = 120


def match_heading(line: str) -> tuple[int, str] | None:
    """识别一行是否标题，返回 (level, title)。level = 标记长度（`##`/`==` 均为 2）。

    单一真相源：parse_section_outline 与 asset_placement 的章节锚点共用本函数，
    避免两套标题正则漂移（R24/R-CS01）。
    """
    md = _MD_HEADING_RE.match(line)
    if md:
        return len(md.group(1)), md.group(2).strip()
    wiki = _WIKI_HEADING_RE.match(line)
    if wiki:
        return len(wiki.group(1)), wiki.group(2).strip()
    return None


def slugify_section(title: str) -> str:
    """章节标题 → 稳定 slug（剔除标点 / 空白），供锚点匹配；保留中英文与数字。"""
    return _SLUG_DROP_RE.sub("", str(title or "").strip())


@dataclass
class SectionNode:
    """一个 outline 节点：标题层级 + 在原文中的位置 + 本节正文规模。"""

    level: int
    title: str
    slug: str
    char_start: int
    body_chars: int = 0
    paragraphs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "title": self.title,
            "slug": self.slug,
            "charStart": self.char_start,
            "bodyChars": self.body_chars,
            "paragraphCount": len(self.paragraphs),
        }


def parse_section_outline(text: str) -> list[SectionNode]:
    """解析文本中的标题节，逐节统计去空白正文字数与自然段。

    - 同时识别 wiki `==/===` 与 markdown `##/###`（一行不会同时命中两者）。
    - 首个标题之前的导语 / frontmatter 不计入任何节（由封面 / lead 逻辑单独处理）。
    - paragraphs 按空行切分，供段落级配图定位（P1）；P0 主要消费 bodyChars 与 slug。
    """
    if not text:
        return []
    nodes: list[SectionNode] = []
    current: SectionNode | None = None
    buffer: list[str] = []
    char_offset = 0

    def _flush() -> None:
        nonlocal buffer
        if current is not None:
            body = "\n".join(buffer).strip()
            current.body_chars = len(re.sub(r"\s+", "", body))
            current.paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        buffer = []

    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\n")
        heading = match_heading(line)
        if heading is not None:
            _flush()
            level, title = heading
            current = SectionNode(
                level=level,
                title=title,
                slug=slugify_section(title),
                char_start=char_offset,
            )
            nodes.append(current)
        elif current is not None:
            buffer.append(line)
        char_offset += len(raw_line)
    _flush()
    return nodes


def outline_to_dicts(outline: list[SectionNode]) -> list[dict[str, Any]]:
    """序列化为可写入 entity_page_input.json / meta.json 的纯字典列表。"""
    return [node.to_dict() for node in outline]


# 百科真正的附录节（引用/链接/注释类）：允许 Agent 在 PII/无关内容清理时整节省略，
# 不纳入关键章节覆盖门。注意：只收敛 wiki 引用/链接/注释类附录，
# 实质内容节（如「其他」常含原文事实）不得擅自排除出覆盖门。
_OUTLINE_APPENDIX_TITLES = frozenset(
    {
        "参考资料",
        "參考資料",
        "参考文献",
        "參考文獻",
        "外部链接",
        "外部連結",
        "注释",
        "註釋",
        "脚注",
        "腳註",
        "参见",
        "參見",
        "備註",
        "备注",
        "延伸阅读",
        "延伸閱讀",
        "相关条目",
        "相關條目",
        "参考",
        "參考",
        "参考来源",
        "參考來源",
        "资料来源",
        "資料來源",
        "来源",
        "來源",
        "相关书籍",
        "相關書籍",
    }
)


def outline_required_sections(
    outline: list[SectionNode],
    *,
    min_body_chars: int = 200,
) -> list[SectionNode]:
    """有实质正文（>= min_body_chars 去空白字）的关键章节，供覆盖门校验。"""
    return [
        node
        for node in outline
        if node.body_chars >= min_body_chars
        and node.title.strip() not in _OUTLINE_APPENDIX_TITLES
    ]


def render_outline_tree(outline: list[SectionNode], *, indent: str = "  ") -> str:
    """渲染为 prompt 可读的层级清单，提示 Agent 保留对应 H2/H3 标题。"""
    if not outline:
        return ""
    base_level = min(node.level for node in outline)
    lines: list[str] = []
    for node in outline:
        depth = max(0, node.level - base_level)
        marker = "#" * node.level
        lines.append(f"{indent * depth}- `{marker} {node.title}`（约 {node.body_chars} 字）")
    return "\n".join(lines)


def render_outline_tree_from_dicts(rows: list[dict[str, Any]], *, indent: str = "  ") -> str:
    """从 entity_page_input.json 透传的 outline 字典列表渲染层级清单（供 prompt 复用）。"""
    nodes = [
        SectionNode(
            level=int(row.get("level") or 2),
            title=str(row.get("title") or ""),
            slug=str(row.get("slug") or ""),
            char_start=int(row.get("charStart") or 0),
            body_chars=int(row.get("bodyChars") or 0),
        )
        for row in (rows or [])
        if isinstance(row, dict) and str(row.get("title") or "").strip()
    ]
    return render_outline_tree(nodes, indent=indent)


def section_titles(outline: list[SectionNode]) -> list[str]:
    """按出现顺序返回标题列表（去重保序）。"""
    seen: set[str] = set()
    out: list[str] = []
    for node in outline:
        title = node.title.strip()
        if title and title not in seen:
            seen.add(title)
            out.append(title)
    return out


def page_section_slugs(page_text: str) -> set[str]:
    """成品 page.md 中所有标题的 slug 集合（含 H1–H6 / wiki ==）。"""
    slugs: set[str] = set()
    for line in (page_text or "").splitlines():
        heading = match_heading(line)
        if heading is not None:
            slugs.add(slugify_section(heading[1]))
    return slugs


def _zh_slug_variants(slug: str) -> set[str]:
    """简繁/异体 slug 变体，用于 outline 覆盖等价匹配。"""
    variants = {slug}
    pairs = (("關", "关"), ("蹟", "迹"), ("際", "际"), ("體", "体"), ("國", "国"))
    for src, dst in pairs:
        if src in slug:
            variants.add(slug.replace(src, dst))
        if dst in slug:
            variants.add(slug.replace(dst, src))
    return variants


def _slug_matches(required_slug: str, page_slug: str) -> bool:
    """章节 slug 等价：完全相等、互为前缀，或简繁变体一致。"""
    if not required_slug or not page_slug:
        return False
    req_vars = _zh_slug_variants(required_slug)
    page_vars = _zh_slug_variants(page_slug)
    for req in req_vars:
        for pg in page_vars:
            if req == pg:
                return True
            if req.startswith(pg) or pg.startswith(req):
                return True
    return False


def outline_coverage_issues(
    required_titles: Sequence[str],
    page_text: str,
    *,
    label: str = "",
) -> list[str]:
    """校验来源关键章节是否在成品 page.md 中保留为同义小标题。

    required_titles: 来源 outline 关键节标题（如「技术变革」「相关古迹」）。
    page_text: 成品 page.md 全文。
    返回 issue 列表；空列表表示通过。
    """
    page_slugs = page_section_slugs(page_text)
    issues: list[str] = []
    prefix = f"{label}: " if label else ""
    for title in required_titles or []:
        req_slug = slugify_section(str(title))
        if not req_slug:
            continue
        if any(_slug_matches(req_slug, ps) for ps in page_slugs):
            continue
        issues.append(f"{prefix}关键章节「{title}」在 page.md 中缺失或未保留为同级小标题")
    return issues
