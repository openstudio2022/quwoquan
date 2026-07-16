"""连续图组占位（figuregroup）契约与回填的唯一真相源（P2）。

根因（R-CS10 图文混排丢失）：抽取器对相邻连续图每张独立产 `:::figure` 占位（连续 6 张拆 6 个），
正文图文交错被打散、AI 易丢图。P2 把**相邻连续图合并为单个 `:::figuregroup` 占位**（内部 N 张
同源 assetId），契约是「AI 原样带回该组占位 → CLI 在占位内回填同源连续图」。

占位形态（source.md 基底稿 / AI 原样带回的 draft.article.md / page.md 中保持一致）：

    :::figuregroup id="grp-001" count="3"
    ![说明1](asset://<assetId-1>)
    ![说明2](asset://<assetId-2>)
    ![说明3](asset://<assetId-3>)
    :::

回填（expand_figure_groups）：发布/审稿结构校验消费前，把每个 figuregroup 展开为 N 个连续
`:::figure` 块（与既有单图内联块同形），下游所有 `:::figure` 解析器无需改造即可消费展开形态。

单一来源：禁止在别处另写 figuregroup 正则或展开逻辑；所有消费者都从本模块取。
"""
from __future__ import annotations

import re
from typing import Iterator

# figuregroup 块：起始行 `:::figuregroup ...`（可带 id/count 属性），中间 N 行图片，`:::` 收尾。
# 用 \b 确保不与单图 `:::figure` 混淆（figuregroup 以 figure 开头，匹配时必须先吃 group 形态）。
FIGURE_GROUP_RE = re.compile(r"(?ms)^:::figuregroup\b[^\n]*\n(.*?)\n:::[ \t]*$")
_GROUP_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(asset://([^)]+)\)")
_GROUP_ID_RE = re.compile(r'id="([^"]*)"')
_GROUP_COUNT_RE = re.compile(r'count="(\d+)"')


def build_figure_group_block(group_id: str, images: list[tuple[str, str]]) -> str:
    """构造 figuregroup 占位块。images: [(caption, assetId), ...]。"""
    lines = [f':::figuregroup id="{group_id}" count="{len(images)}"']
    for caption, asset_id in images:
        safe_caption = str(caption or "").replace("\n", " ").strip()
        lines.append(f"![{safe_caption}](asset://{asset_id})")
    lines.append(":::")
    return "\n".join(lines)


def build_single_figure_block(caption: str, asset_id: str) -> str:
    """构造单图内联块（与抽取器/source.md 既有单图形态一致）。"""
    safe_caption = str(caption or "").replace("\n", " ").strip()
    return f":::figure\n![{safe_caption}](asset://{asset_id})\n{safe_caption}\n:::"


def iter_figure_groups(markdown: str) -> Iterator[tuple[str, int, list[tuple[str, str]]]]:
    """枚举正文中的 figuregroup：yield (groupId, declaredCount, [(caption, assetId), ...])。"""
    for match in FIGURE_GROUP_RE.finditer(str(markdown or "")):
        header = match.group(0).splitlines()[0]
        gid_match = _GROUP_ID_RE.search(header)
        count_match = _GROUP_COUNT_RE.search(header)
        group_id = gid_match.group(1) if gid_match else ""
        declared = int(count_match.group(1)) if count_match else 0
        images = [(m.group(1), m.group(2)) for m in _GROUP_IMAGE_RE.finditer(match.group(1))]
        yield group_id, declared, images


def figure_group_ids(markdown: str) -> list[str]:
    return [gid for gid, _count, _imgs in iter_figure_groups(markdown) if gid]


def expand_figure_groups(markdown: str) -> str:
    """回填：把每个 figuregroup 展开为 N 个连续 `:::figure` 块（下游统一消费单图形态）。"""
    text = str(markdown or "")

    def _replace(match: re.Match[str]) -> str:
        images = [(m.group(1), m.group(2)) for m in _GROUP_IMAGE_RE.finditer(match.group(1))]
        if not images:
            return ""
        return "\n\n".join(build_single_figure_block(cap, aid) for cap, aid in images)

    expanded = FIGURE_GROUP_RE.sub(_replace, text)
    return re.sub(r"\n{3,}", "\n\n", expanded)


_UNBOUND_INLINE_RE = re.compile(r"^source-inline-\d+$")


def prune_unbound_group_images(markdown: str) -> str:
    """绑定后清理 figuregroup：剔除仍是 `asset://source-inline-NNN`（未成功同源下载）的图行，
    重算 count；组内全部未绑定则整块删除。保证带回的连续图组里每张都锚定真实资产。"""
    text = str(markdown or "")

    def _replace(match: re.Match[str]) -> str:
        header = match.group(0).splitlines()[0]
        gid_match = _GROUP_ID_RE.search(header)
        group_id = gid_match.group(1) if gid_match else "grp"
        kept = [
            (m.group(1), m.group(2))
            for m in _GROUP_IMAGE_RE.finditer(match.group(1))
            if not _UNBOUND_INLINE_RE.match(m.group(2))
        ]
        if not kept:
            return ""
        return build_figure_group_block(group_id, kept)

    pruned = FIGURE_GROUP_RE.sub(_replace, text)
    return re.sub(r"\n{3,}", "\n\n", pruned)


def figure_image_count(markdown: str) -> int:
    """正文实际图片张数：单图块 + figuregroup 内每张都计入（先展开再数 `:::figure`）。"""
    return expand_figure_groups(markdown).count(":::figure")


def figure_group_integrity_issues(article: str, base_draft: str) -> list[str]:
    """连续图组带回完整性：底稿基底里出现的 figuregroup，AI 成稿必须按原 id/张数带回，
    禁止拆成多个单图、丢图或篡改组内 assetId（R-CS10 回归防线）。"""
    issues: list[str] = []
    base_groups = {gid: imgs for gid, _c, imgs in iter_figure_groups(base_draft) if gid}
    if not base_groups:
        return issues
    article_groups = {gid: imgs for gid, _c, imgs in iter_figure_groups(article) if gid}
    for gid, base_imgs in base_groups.items():
        got = article_groups.get(gid)
        if got is None:
            issues.append(f"figuregroup {gid} dropped or split into singles (must return group placeholder verbatim)")
            continue
        base_ids = [aid for _cap, aid in base_imgs]
        got_ids = [aid for _cap, aid in got]
        if got_ids != base_ids:
            issues.append(f"figuregroup {gid} asset ids changed/reordered: expected {base_ids}, got {got_ids}")
    return issues


__all__ = [
    "FIGURE_GROUP_RE",
    "build_figure_group_block",
    "build_single_figure_block",
    "iter_figure_groups",
    "figure_group_ids",
    "expand_figure_groups",
    "prune_unbound_group_images",
    "figure_image_count",
    "figure_group_integrity_issues",
]
