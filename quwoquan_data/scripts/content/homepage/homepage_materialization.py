"""Deterministic entity-homepage materialization helpers."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from content.execution.asset_registry import load_execution_asset_registry
from core.localization import fold_to_simplified

def _homepage_outline_issues(outline_rows: list[dict[str, Any]], page_text: str, label: str) -> list[str]:
    """校验关键章节在 Agent 正文中按原 `##/###` 层级保留。"""
    if not outline_rows:
        return []
    from core.localization import fold_to_simplified
    from core.section_outline import match_heading, slugify_section
    headings: list[tuple[int, str]] = []
    for line in str(page_text or "").splitlines():
        heading = match_heading(line)
        if heading is None:
            continue
        headings.append((int(heading[0]), slugify_section(heading[1])))
    issues: list[str] = []
    for row in outline_rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        try:
            level = int(row.get("level") or 2)
        except (TypeError, ValueError):
            level = 2
        slug = slugify_section(fold_to_simplified(title))
        matched = False
        for page_level, page_slug in headings:
            if page_level != level:
                continue
            if page_slug == slug or page_slug.startswith(slug) or slug.startswith(page_slug):
                matched = True
                break
        if not matched:
            marker = "#" * min(max(level, 1), 6)
            issues.append(f"{label}: 关键章节「{title}」未按 `{marker}` 层级保留为小标题")
    return issues

def _homepage_source_figure_issues(base: dict[str, Any], draft_text: str, label: str) -> list[str]:
    """Agent 必须带回 prompt 底稿中的 source-stage asset:// 占位（landscape 兜底）。
    AI 协议主线（[[IMG:]] 占位符）由 placeholder_consistency_issues 单独校验；
    本函数只兜底旧式 asset:// 直引（base markdown 无占位符时自动为空）。
    """
    base_markdown = str(base.get("markdown") or "")
    if re.search(r"^\s*\[\[IMG:fig_\d+\]\]\s*$", base_markdown, flags=re.MULTILINE):
        return []
    from core.asset_placement import referenced_asset_ids
    expected = referenced_asset_ids(base_markdown)
    if not expected:
        return []
    actual = referenced_asset_ids(draft_text)
    missing = sorted(expected - actual)
    return [f"{label}: homepage figure placeholder missing asset://{asset_id}" for asset_id in missing]

def _replace_homepage_source_asset_refs(page_text: str, assets: list[dict[str, Any]]) -> str:
    """把 prompt 中 source 阶段 `asset://sourceAssetId` 替换为发布态 assetId。"""
    out = str(page_text or "")
    for asset in assets:
        source_asset_id = str(asset.get("sourceAssetId") or "").strip()
        final_asset_id = str(asset.get("assetId") or "").strip()
        if source_asset_id and final_asset_id:
            out = out.replace(f"asset://{source_asset_id}", f"asset://{final_asset_id}")
    return out

def _ensure_homepage_cover_frontmatter(page_text: str, cover_asset_id: str) -> str:
    """实体主页与文章一致：frontmatter 标 coverImage，供 feed/卡片封面取图。"""
    cover_asset_id = str(cover_asset_id or "").strip()
    if not cover_asset_id:
        return page_text
    cover_line = f"coverImage: asset://{cover_asset_id}"
    if page_text.startswith("---\n"):
        end = page_text.find("\n---\n", 4)
        if end != -1:
            head = page_text[:end]
            if "coverImage:" in head:
                return page_text
            return head + "\n" + cover_line + page_text[end:]
    return f"---\n{cover_line}\n---\n\n" + page_text

def _fold_homepage_manifest_assets(
    assets: list[dict[str, Any]],
    assets_dir: Path,
    *,
    execution_id: str = "",
) -> None:
    """fold_to_simplified 会折叠 page.md 内 asset:// id；manifest、磁盘文件名与
    asset_id_registry 三者须同步折叠，避免图文闭环门/目录证据链门误杀。"""
    registry = None
    if execution_id:
        registry = load_execution_asset_registry(execution_id, 0)
    for asset in assets:
        old_id = str(asset.get("assetId") or "").strip()
        if not old_id:
            continue
        new_id = fold_to_simplified(old_id)
        if new_id == old_id:
            continue
        if registry is not None:
            registry.rename_asset_id(old_id, new_id)
        old_file = str(asset.get("fileName") or "").strip()
        suffix = Path(old_file).suffix if old_file else ".jpg"
        new_file = f"{new_id}{suffix}"
        src = assets_dir / old_file if old_file else assets_dir / f"{old_id}{suffix}"
        dst = assets_dir / new_file
        if src.is_file() and src != dst:
            if dst.is_file():
                src.unlink()
            else:
                src.rename(dst)
        asset["assetId"] = new_id
        asset["fileName"] = new_file
        for field in ("caption", "relevance"):
            if asset.get(field):
                asset[field] = fold_to_simplified(str(asset[field]))

def _homepage_layout_assets(assets: list[dict[str, Any]]) -> None:
    """就地为 manifest 资产标注版面：主页三段契约下正文图一律块级 fullWidth。
    禁 wrapLeft/wrapRight 文字环绕（移动端拥挤且与主页契约冲突）；related 资产的
    grid 版面由 place_homepage_assets_in_markdown 在归入相关图片区时覆盖。
    """
    for asset in assets:
        asset["imageLayout"] = "fullWidth"
        asset.setdefault("sectionAnchor", str(asset.get("sectionAnchor") or ""))

