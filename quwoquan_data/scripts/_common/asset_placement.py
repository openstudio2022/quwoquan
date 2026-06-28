"""确定性配图注入：把 manifest 资产按章节 / 段落锚点放进正文 figure 块。

与文章成品同构（App `qwq-rich-md/1` 真相源 `quwoquan_app/.../qwq_markdown_parser.dart`）：

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
from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.section_outline import match_heading, slugify_section

# 同时识别正文内联指令 {asset://id|...} 与 figure 块内 asset://id；取末段 id 作幂等键。
_ASSET_REF_RE = re.compile(r"asset://([^\s|}\)\]]+)")
_WRAP_CYCLE = ("wrapRight", "wrapLeft")
_GALLERY_HEADING = "## 图集"
# 章节内左右环绕的最小段落字数：太短的段落环绕会拥挤，降级 fullWidth。
_MIN_WRAP_PARAGRAPH_CHARS = 80
# 退化 caption 模式：纯数字-文件名（如 36661-Dujiangyan）或 upload 文件名 stem。
_CAPTION_FILENAME_RE = re.compile(r"^\d{2,}[-_]")


def referenced_asset_ids(text: str) -> set[str]:
    """正文已引用的 assetId（按 asset:// 末段归一），用于幂等去重。"""
    return {ref.split("/")[-1] for ref in _ASSET_REF_RE.findall(text or "")}


def _sanitize_caption(caption: str) -> str:
    """figure caption 属性内不能含双引号 / 换行，否则破坏 App 属性解析。"""
    cleaned = re.sub(r'["\r\n]+', " ", str(caption or "")).strip()
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

    new_content = "\n".join(out_lines)
    new_content = re.sub(r"\n{3,}", "\n\n", new_content)
    if not new_content.endswith("\n"):
        new_content += "\n"
    return frontmatter + new_content


def _caption_is_degraded(caption: str, *, file_name: str = "") -> bool:
    """caption 是否退化为文件名占位（无中文语义）。"""
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
    # 无 CJK 且长度很短 → 大概率文件名碎片。
    if len(text) < 12 and not re.search(r"[\u4e00-\u9fff]", text):
        return True
    return False


def caption_semantic_issues(
    assets: Sequence[Mapping[str, Any]],
    *,
    label: str = "",
) -> list[str]:
    """manifest.assets caption 语义门：禁止空/纯文件名/等于 fileName stem。"""
    issues: list[str] = []
    prefix = f"{label}: " if label else ""
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("assetId") or asset.get("id") or "").strip()
        caption = str(asset.get("caption") or "").strip()
        file_name = str(asset.get("fileName") or "").strip()
        if _caption_is_degraded(caption, file_name=file_name):
            issues.append(
                f"{prefix}asset {asset_id or file_name or '<unknown>'} caption 退化为文件名或无语义: {caption!r}"
            )
    return issues
