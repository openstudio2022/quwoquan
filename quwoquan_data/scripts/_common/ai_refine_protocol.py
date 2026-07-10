"""AI 加工最小干扰协议（plan §11）。

模型侧只见「纯文字 + 极简图片占位符」：占位符整行形如 `[[IMG:fig_02]]`（**不含图注**），
不暴露 `:::figure` 语法、asset://、URL、license、图注等任何元数据；封面裁决与相关图片区
完全不进 prompt。模型禁止新增/删除/移动/复制占位符、禁止改 id、禁止在占位符行追加文字。

图注不再要求模型逐字复述（旧协议 `[[IMG:fig_NN]] 原图注` 常因模型微调图注被整篇
reject，失败面大且无价值）；图注唯一真相源是 bindings，finalize 展开时注入。

代码侧承担全部结构职责：
- `placeholder_consistency_issues`：写回文本与下发底稿的占位符集合必须完全一致
  （缺失/新增/重复/行尾追加文字任一发生 → 结构化 reject，重跑该实体，禁止静默修复）。
- `expand_image_placeholders`：按 bindings 把占位符行展开为块级 fullWidth
  `:::figure`（caption 只用 bindings 原图注），asset:// 指向 source 阶段
  sourceAssetId，由 finalize 既有机制映射为发布态 assetId。
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

# 占位符必须独占一行；捕获行尾残留文字用于校验（新协议应为空）。
IMAGE_PLACEHOLDER_LINE_RE = re.compile(r"^\[\[IMG:([A-Za-z0-9_\-]+)\]\][ \t]*(.*?)[ \t]*$", re.M)
# 行内出现（未独占一行）的占位符也要能识别为异常。
IMAGE_PLACEHOLDER_ANY_RE = re.compile(r"\[\[IMG:([A-Za-z0-9_\-]+)\]\]")


def image_placeholder_line(fig_id: str) -> str:
    """极简占位符行：只有 id，无图注（图注真相源在 bindings）。"""
    return f"[[IMG:{fig_id}]]"


def extract_image_placeholders(text: str) -> list[tuple[str, str]]:
    """按出现顺序提取 (figId, 行尾图注)；只认独占一行的占位符。"""
    return [
        (match.group(1), match.group(2).strip())
        for match in IMAGE_PLACEHOLDER_LINE_RE.finditer(str(text or ""))
    ]


def placeholder_consistency_issues(
    draft_text: str,
    bindings: Sequence[Mapping[str, Any]],
    *,
    label: str = "",
) -> list[str]:
    """占位符一致性校验：任何漂移都结构化 reject，禁止静默修复。

    新协议下占位符行只有 `[[IMG:fig_NN]]`；行尾出现任何文字（模型自拟图注/
    复述旧图注）都视为协议违例——图注唯一真相源在 bindings，不接受模型改写面。
    """
    prefix = f"{label}: " if label else ""
    expected_ids: set[str] = set()
    for row in bindings or []:
        fig_id = str(row.get("figId") or "").strip()
        if fig_id:
            expected_ids.add(fig_id)

    found = extract_image_placeholders(draft_text)
    found_ids = [fig_id for fig_id, _ in found]
    issues: list[str] = []

    for fig_id in sorted(expected_ids - set(found_ids)):
        issues.append(f"{prefix}AI 协议 reject：占位符 [[IMG:{fig_id}]] 缺失（禁止删除/改写占位符）")
    for fig_id in sorted(set(found_ids) - expected_ids):
        issues.append(f"{prefix}AI 协议 reject：出现未下发的占位符 [[IMG:{fig_id}]]（禁止新增/改 id）")
    duplicated = sorted({fig_id for fig_id in found_ids if found_ids.count(fig_id) > 1})
    for fig_id in duplicated:
        issues.append(f"{prefix}AI 协议 reject：占位符 [[IMG:{fig_id}]] 重复出现（禁止复制占位符）")
    for fig_id, trailing in found:
        if fig_id in expected_ids and trailing:
            issues.append(
                f"{prefix}AI 协议 reject：占位符 [[IMG:{fig_id}]] 行尾出现多余文字"
                f"（应只保留 [[IMG:{fig_id}]]，实为「{trailing[:60]}」）"
            )
    # 占位符必须独占一行：行内混排（如句中出现）视为被移动/改写。
    inline_ids = [m.group(1) for m in IMAGE_PLACEHOLDER_ANY_RE.finditer(str(draft_text or ""))]
    for fig_id in sorted(set(inline_ids) - set(found_ids)):
        issues.append(f"{prefix}AI 协议 reject：占位符 [[IMG:{fig_id}]] 未独占一行（禁止混入句中）")
    return issues


def expand_image_placeholders(
    text: str,
    bindings: Sequence[Mapping[str, Any]],
) -> str:
    """把 `[[IMG:figId]]` 行展开为块级 fullWidth figure（caption 只用 bindings 原图注）。

    展开必须发生在 placeholder_consistency_issues 通过之后；未知占位符原样保留，
    交由主页结构门（零占位符残留）阻断。
    """
    by_id: dict[str, Mapping[str, Any]] = {}
    for row in bindings or []:
        fig_id = str(row.get("figId") or "").strip()
        if fig_id:
            by_id[fig_id] = row

    def _replace(match: re.Match[str]) -> str:
        fig_id = match.group(1)
        row = by_id.get(fig_id)
        if row is None:
            return match.group(0)
        source_asset_id = str(row.get("sourceAssetId") or "").strip()
        if not source_asset_id:
            return match.group(0)
        caption = re.sub(r'["\r\n]+', " ", str(row.get("caption") or "")).strip()
        return (
            f':::figure id="{fig_id}" layout="fullWidth" caption="{caption}"\n'
            f"asset://{source_asset_id}\n"
            ":::"
        )

    return IMAGE_PLACEHOLDER_LINE_RE.sub(_replace, str(text or ""))
