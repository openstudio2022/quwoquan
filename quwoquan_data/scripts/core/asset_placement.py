"""确定性配图注入：把 manifest 资产按章节 / 段落锚点放进正文 figure 块。

与文章成品同构（App `qwq-rich-md` 真相源 `quwoquan_app/.../qwq_markdown_parser.dart`）：

    :::figure id="..." layout="wrapLeft|wrapRight|fullWidth" caption="..."
    asset://<assetId>
    :::

定位优先级（用户契约：优先段落左右/上下，再章节，再图集兜底）：

1. 封面（role=cover 或首图）→ H1 之后、首段之前，fullWidth。
2. 段落锚点（placement.paragraphIndex）→ 命中自然段后，左右环绕（wrapRight/wrapLeft 交替）。
3. 章节锚点（placement.sectionSlug，或无 placement 时顺序分配）→ 对应 `##`/`###` 标题下。
4. 兜底 → 文末「## 图集」，每张 fullWidth，保证全部真实图仍可见且图文闭环。

幂等：正文已内联的 `asset://` 不重复注入（Agent 已自行配图时只补未引用图）。
仅在正文区插入，不改写 frontmatter。实体主页与文章 finalize 共用本模块（R24/R25）。
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.localization import latin_dominant
from core.page_media import HomepageAssetDisposition
from core.section_outline import match_heading, slugify_section

# 同时识别正文内联指令 {asset://id|...} 与 figure 块内 asset://id；取末段 id 作幂等键。
_ASSET_REF_RE = re.compile(r"asset://([^\s|}\)\]]+)")
_WRAP_CYCLE = ("wrapRight", "wrapLeft")
_GALLERY_HEADING = "## 图集"
# 章节内左右环绕的最小段落字数：太短的段落环绕会拥挤，降级 fullWidth。
_MIN_WRAP_PARAGRAPH_CHARS = 80
# 退化 caption 模式：纯数字-文件名（如 36661-Dujiangyan）或 upload 文件名 stem。
_CAPTION_FILENAME_RE = re.compile(r"^\d{2,}[-_]")
_CAPTION_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
# 原文图片标记残留（wiki/file 语法、像素标注、图片扩展名）→ 非语义 caption。
_CAPTION_RAW_MARKUP_RE = re.compile(
    r"(\[\[|\]\]|\bfile:|\bimage:|文件:|圖像:|图像:|\bthumb\b|\d+\s*px\b|\.(?:jpe?g|png|gif|svg|webp)\b)",
    re.IGNORECASE,
)


def referenced_asset_ids(text: str) -> set[str]:
    """正文已引用的 assetId（按 asset:// 末段归一），用于幂等去重。"""
    return {ref.split("/")[-1] for ref in _ASSET_REF_RE.findall(text or "")}


def _sanitize_caption(caption: str) -> str:
    """figure caption 属性内不能含双引号 / 换行，否则破坏 App 属性解析。"""
    cleaned = "".join(
        ch for ch in str(caption or "") if unicodedata.category(ch) != "Cf"
    )
    cleaned = re.sub(r'["\r\n]+', " ", cleaned).strip()
    return re.sub(r"\s+", " ", cleaned)


def _figure_id(role: str, seq: int) -> str:
    role = str(role or "").strip()
    if role == "cover":
        return "cover"
    if role == "closing":
        return "closing"
    return f"fig{seq}"


def _figure_block(asset_id: str, *, layout: str, caption: str, fig_id: str) -> list[str]:
    """渲染一个 figure 块（不含外围空行，由调用方按需补空行）。"""
    safe_caption = _sanitize_caption(caption)
    attrs = f'id="{fig_id}" layout="{layout}"'
    if safe_caption:
        attrs += f' caption="{safe_caption}"'
    return [f":::figure {attrs}", f"asset://{asset_id}", ":::"]


def _split_frontmatter(text: str) -> tuple[str, str]:
    """分离 YAML frontmatter（若有），只对正文做插入。返回 (frontmatter, body)。"""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            cut = end + len("\n---\n")
            return text[:cut], text[cut:]
    return "", text


def _prune_empty_heading_sections(content: str) -> str:
    """Drop headings that do not own content before their next sibling/end.

    The author must preserve source structure, yet a source-only gallery heading
    becomes empty after gallery members are deterministically materialized in
    the single final ``## 相关图片`` section. Leaving the heading produces a
    visibly broken page, so finalization removes only headings with no text and
    no child subsection.
    """

    lines = content.split("\n")
    remove: set[int] = set()
    for index, line in enumerate(lines):
        heading = match_heading(line)
        if heading is None:
            continue
        level, _title = heading
        if level < 2:
            continue
        next_index = index + 1
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1
        if next_index >= len(lines):
            remove.add(index)
            continue
        next_heading = match_heading(lines[next_index])
        if next_heading is not None and next_heading[0] <= level:
            remove.add(index)
    if not remove:
        return content
    return "\n".join(line for index, line in enumerate(lines) if index not in remove)


def _asset_layout(asset: Mapping[str, Any], *, wrap_index: int, force_full: bool) -> str:
    explicit = str(asset.get("imageLayout") or "").strip()
    if explicit in ("wrapLeft", "wrapRight", "fullWidth"):
        return explicit
    if force_full:
        return "fullWidth"
    return _WRAP_CYCLE[wrap_index % len(_WRAP_CYCLE)]


def _asset_id(asset: Mapping[str, Any]) -> str:
    return str(asset.get("assetId") or asset.get("id") or "").strip()


def place_assets_in_markdown(
    body: str,
    assets: Sequence[Mapping[str, Any]],
    *,
    placements: Sequence[Mapping[str, Any]] | None = None,
    cover_first: bool = True,
) -> str:
    """把未内联的资产按锚点注入正文，返回新正文（幂等）。

    assets: manifest 资产列表（含 assetId/role/caption/可选 imageLayout）。
    placements: 可选 [{assetRef|assetId, sectionSlug, paragraphIndex, caption, suggestedLayout}]
      —— P1 联网 wikitext 解析产出；缺省时退化为按章节顺序分配 + 图集兜底。
    """
    frontmatter, content = _split_frontmatter(body or "")
    valid_assets = [a for a in (assets or []) if _asset_id(a)]
    if not valid_assets:
        return body or ""

    referenced = referenced_asset_ids(content)
    pending = [a for a in valid_assets if _asset_id(a) not in referenced]
    if not pending:
        return body or ""

    placement_by_id: dict[str, Mapping[str, Any]] = {}
    for placement in placements or []:
        ref = str(placement.get("assetId") or placement.get("assetRef") or "").strip()
        if ref:
            placement_by_id[ref.split("/")[-1]] = placement

    # 旧草稿可能把图集成员展开进正文。先统一剥离，再计算章节行号，避免删除块后
    # 行号漂移；新链路不会为 groupMember 生成 Agent 占位符。
    for asset in valid_assets:
        asset_id = _asset_id(asset)
        placement = placement_by_id.get(asset_id)
        placement_type = str(
            (placement or {}).get("placementType")
            or asset.get("placementType")
            or ""
        )
        if asset_id in referenced and placement_type != "inline":
            content = _strip_asset_figure_blocks(content, asset_id)
    referenced = referenced_asset_ids(content)

    lines = content.split("\n")
    # 收集插入点：line_index -> 该行后追加的块行列表（最后从后往前应用，避免行号漂移）。
    inserts: dict[int, list[str]] = {}

    def _queue(after_line: int, block: list[str]) -> None:
        inserts.setdefault(after_line, [])
        inserts[after_line].extend(["", *block])

    # H1 行 / 章节 slug -> 标题行号。
    h1_line = -1
    section_lines: list[tuple[str, int]] = []
    for idx, line in enumerate(lines):
        heading = match_heading(line)
        if heading is None:
            continue
        level, title = heading
        if level <= 1 and h1_line < 0:
            h1_line = idx
        elif level >= 2:
            section_lines.append((slugify_section(title), idx))

    wrap_index = 0
    remaining: list[Mapping[str, Any]] = []

    # 1) 封面：role=cover 优先，否则首张。注入 H1 后（无 H1 则正文最前）。
    cover_asset: Mapping[str, Any] | None = None
    if cover_first:
        for asset in pending:
            if str(asset.get("role") or "") == "cover":
                cover_asset = asset
                break
        if cover_asset is None:
            cover_asset = pending[0]
    if cover_asset is not None:
        block = _figure_block(
            _asset_id(cover_asset),
            layout="fullWidth",
            caption=str(cover_asset.get("caption") or ""),
            fig_id="cover",
        )
        anchor = h1_line if h1_line >= 0 else -1
        if anchor >= 0:
            _queue(anchor, block)
        else:
            lines = block + [""] + lines
            # 重新计算后续 section 行号（封面块插到最前，整体下移）。
            shift = len(block) + 1
            section_lines = [(slug, ln + shift) for slug, ln in section_lines]

    used_section_lines: set[int] = set()

    # 2)+3) 其余图：先按 placement 锚点，再按章节顺序分配。
    section_cursor = 0
    seq = 2
    for asset in pending:
        if asset is cover_asset:
            continue
        asset_id = _asset_id(asset)
        placement = placement_by_id.get(asset_id)
        target_line = -1
        force_full = False
        if placement is not None:
            slug = slugify_section(str(placement.get("sectionSlug") or ""))
            for s_slug, s_line in section_lines:
                if s_slug and slug and (s_slug == slug or s_slug.startswith(slug) or slug.startswith(s_slug)):
                    target_line = s_line
                    break
        if target_line < 0 and section_lines:
            # 顺序分配到尚未配图的章节。
            while section_cursor < len(section_lines) and section_lines[section_cursor][1] in used_section_lines:
                section_cursor += 1
            if section_cursor < len(section_lines):
                target_line = section_lines[section_cursor][1]
                section_cursor += 1
        if target_line < 0:
            remaining.append(asset)
            continue
        used_section_lines.add(target_line)
        layout = _asset_layout(asset, wrap_index=wrap_index, force_full=force_full)
        if layout in _WRAP_CYCLE:
            wrap_index += 1
        block = _figure_block(
            asset_id,
            layout=layout,
            caption=str(asset.get("caption") or ""),
            fig_id=_figure_id(str(asset.get("role") or ""), seq),
        )
        seq += 1
        _queue(target_line, block)

    # 应用 H1/章节插入（从后往前，保持行号稳定）。
    for after_line in sorted(inserts.keys(), reverse=True):
        block = inserts[after_line]
        insert_at = after_line + 1
        lines[insert_at:insert_at] = block

    out_lines = lines

    # 4) 兜底：仍未放置的图进文末「图集」，全部 fullWidth 保留。
    if remaining:
        gallery: list[str] = ["", _GALLERY_HEADING, ""]
        for asset in remaining:
            gallery.extend(
                _figure_block(
                    _asset_id(asset),
                    layout="fullWidth",
                    caption=str(asset.get("caption") or ""),
                    fig_id=_figure_id(str(asset.get("role") or ""), seq),
                )
            )
            gallery.append("")
            seq += 1
        out_lines = out_lines + gallery

    new_content = _prune_empty_heading_sections("\n".join(out_lines))
    new_content = re.sub(r"\n{3,}", "\n\n", new_content)
    if not new_content.endswith("\n"):
        new_content += "\n"
    return frontmatter + new_content


_RELATED_HEADING = "## 相关图片"


def _strip_asset_figure_blocks(content: str, asset_id: str) -> str:
    """剥离正文中引用指定 asset 的 figure 块与裸 asset:// 行（封面去重用）。"""
    if not asset_id:
        return content
    escaped = re.escape(asset_id)
    # 完整 figure 块。
    content = re.sub(
        rf"^:::figure[^\n]*\nasset://(?:\S*/)?{escaped}\s*\n:::\s*$",
        "",
        content,
        flags=re.M,
    )
    # 裸引用行。
    content = re.sub(rf"^asset://(?:\S*/)?{escaped}\s*$", "", content, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", content)


def place_homepage_assets_in_markdown(
    body: str,
    assets: Sequence[dict[str, Any]],
    *,
    placements: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """实体主页三段契约注入（区别于文章链路的 place_assets_in_markdown）。

    契约（百科主页结构化计划 §6/§7/§10）：
    - 封面只在 frontmatter `coverImage` 声明，正文不重复展示封面。
    - 正文内嵌图唯一形态 = 块级 `:::figure layout="fullWidth"`（禁 wrapLeft/wrapRight），
      仅原图注（一行）；只有 placementType=inline 且有可靠章节锚点时才能进入正文。
    - 其余合格图全部进文末固定 `## 相关图片` 章节的单个 `:::gallery`（grid）。
    - 就地改写 asset["role"]：cover 保持；进正文的标 inline；其余标 related。

    幂等：正文已引用的 inline asset 不重复注入；groupMember 即使被旧草稿引用，
    也会从正文移除并归入相关图片。
    """
    frontmatter, content = _split_frontmatter(body or "")
    valid_assets = [a for a in (assets or []) if _asset_id(a)]
    if not valid_assets:
        return body or ""

    # 封面只在 frontmatter：Agent/旧链路把封面 figure 内联进正文时，代码侧剥离
    # （结构真相源在代码不在模型）。
    for asset in valid_assets:
        if str(asset.get("role") or "") == HomepageAssetDisposition.COVER.value:
            content = _strip_asset_figure_blocks(content, _asset_id(asset))

    referenced = referenced_asset_ids(content)
    placement_by_id: dict[str, Mapping[str, Any]] = {}
    for placement in placements or []:
        ref = str(placement.get("assetId") or placement.get("assetRef") or "").strip()
        if ref:
            placement_by_id[ref.split("/")[-1]] = placement

    # 旧草稿可能把图集成员展开进正文。先统一剥离，再计算章节行号，避免删除块后
    # 行号漂移；新链路不会为 groupMember 生成 Agent 占位符。
    for asset in valid_assets:
        asset_id = _asset_id(asset)
        placement = placement_by_id.get(asset_id)
        placement_type = str(
            (placement or {}).get("placementType")
            or asset.get("placementType")
            or ""
        )
        if asset_id in referenced and placement_type != "inline":
            content = _strip_asset_figure_blocks(content, asset_id)
    referenced = referenced_asset_ids(content)

    lines = content.split("\n")
    section_lines: list[tuple[str, int]] = []
    for idx, line in enumerate(lines):
        heading = match_heading(line)
        if heading is None:
            continue
        level, title = heading
        if level >= 2:
            section_lines.append((slugify_section(title), idx))

    inserts: dict[int, list[str]] = {}

    def _queue(after_line: int, block: list[str]) -> None:
        inserts.setdefault(after_line, [])
        inserts[after_line].extend(["", *block])

    related: list[dict[str, Any]] = []
    seq = 2

    for asset in valid_assets:
        asset_id = _asset_id(asset)
        role = str(asset.get("role") or "")
        if role == HomepageAssetDisposition.COVER.value:
            # 封面只在 frontmatter；若正文误引用由结构门拦截。
            asset["imageLayout"] = "fullWidth"
            continue
        placement = placement_by_id.get(asset_id)
        placement_type = str(
            (placement or {}).get("placementType")
            or asset.get("placementType")
            or ""
        )
        if placement_type != "inline":
            asset["role"] = HomepageAssetDisposition.RELATED.value
            asset["imageLayout"] = "grid"
            related.append(asset)
            continue
        if asset_id in referenced:
            asset["role"] = HomepageAssetDisposition.INLINE.value
            asset["imageLayout"] = "fullWidth"
            continue
        caption = str(asset.get("caption") or "")
        # 无原图注（或退化 caption）不得作正文解释图 → 页尾相关图片。
        if not caption.strip() or _caption_is_degraded(caption, file_name=str(asset.get("fileName") or "")):
            asset["role"] = HomepageAssetDisposition.RELATED.value
            related.append(asset)
            continue
        target_line = -1
        if placement is not None:
            slug = slugify_section(str(placement.get("sectionSlug") or ""))
            for s_slug, s_line in section_lines:
                if s_slug and slug and (
                    s_slug == slug or s_slug.startswith(slug) or slug.startswith(s_slug)
                ):
                    target_line = s_line
                    break
        if target_line < 0:
            asset["role"] = HomepageAssetDisposition.RELATED.value
            related.append(asset)
            continue
        asset["role"] = HomepageAssetDisposition.INLINE.value
        asset["imageLayout"] = "fullWidth"
        _queue(
            target_line,
            _figure_block(asset_id, layout="fullWidth", caption=caption, fig_id=_figure_id("", seq)),
        )
        seq += 1

    for after_line in sorted(inserts.keys(), reverse=True):
        block = inserts[after_line]
        lines[after_line + 1 : after_line + 1] = block

    out_lines = lines
    if related:
        ids = ",".join(_asset_id(a) for a in related)
        gallery_block = ["", _RELATED_HEADING, "", f':::gallery ids="{ids}" layout="grid"', ":::"]
        for a in related:
            a["imageLayout"] = "grid"
        out_lines = out_lines + gallery_block

    new_content = _prune_empty_heading_sections("\n".join(out_lines))
    new_content = re.sub(r"\n{3,}", "\n\n", new_content)
    if not new_content.endswith("\n"):
        new_content += "\n"
    return frontmatter + new_content


def _caption_is_degraded(caption: str, *, file_name: str = "") -> bool:
    """caption 是否退化（文件名占位 / 原文标记残留 / 英文拉丁主导，缺中文语义）。

    中文内容产品里 caption 必须以原文中文语义为基础：
    - 空、纯数字文件名、等于文件名 stem → 退化；
    - 含 wiki/file 原文图片标记（``[[``/``File:``/``.jpg`` 等）→ 退化；
    - 无任何 CJK 字符（纯英文/拉丁/数字，如四姑娘山英文封面）→ 退化；
    - 拉丁字母明显多于中文（英文主导）→ 退化。
    """
    text = str(caption or "").strip()
    if not text:
        return True
    if _CAPTION_FILENAME_RE.match(text):
        return True
    stem = Path(file_name).stem if file_name else ""
    if stem and text == stem:
        return True
    if stem and text.replace(" ", "") == stem.replace("_", "").replace("-", ""):
        return True
    if _CAPTION_RAW_MARKUP_RE.search(text):
        return True
    # 无中文语义（纯拉丁/英文/数字）→ 退化（含旧的「短且无 CJK」情形）。
    if not _CAPTION_CJK_RE.search(text):
        return True
    # 英文/拉丁主导（占比规则单一真相源在 core.localization，全仓共用）。
    if latin_dominant(text):
        return True
    return False


def caption_semantic_issues(
    assets: Sequence[Mapping[str, Any]],
    *,
    label: str = "",
) -> list[str]:
    """manifest.assets caption 语义门：禁止纯文件名/无语义 caption。

    role=related（页尾相关图片）允许空 caption——契约「无原图注不加说明，禁止虚构」；
    cover/inline 必须有非退化 caption（cover 由 finalize 兜底实体名，inline 依赖原图注）。
    """
    issues: list[str] = []
    prefix = f"{label}: " if label else ""
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("assetId") or asset.get("id") or "").strip()
        caption = str(asset.get("caption") or "").strip()
        file_name = str(asset.get("fileName") or "").strip()
        role = str(asset.get("role") or "").strip()
        if not caption and role == "related":
            continue
        if _caption_is_degraded(caption, file_name=file_name):
            issues.append(
                f"{prefix}asset {asset_id or file_name or '<unknown>'} caption 退化为文件名或无语义: {caption!r}"
            )
    return issues
