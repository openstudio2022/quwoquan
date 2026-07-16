"""P2 连续图组（figuregroup）回填契约：

唯一真相源 `core/figure_groups.py`。覆盖：
- expand（回填）：AI 原样带回的 :::figuregroup 占位展开为 N 个同源 :::figure 单图块；
- integrity（带回完整性）：底稿组被丢弃/拆图/改 assetId 时如实报问题，正确带回不误报；
- prune（绑定后清理）：组内未同源下载的 source-inline 占位剔除并重算 count，全未绑定整块删除；
- 计数：figure_image_count 把组内逐张计入；
- 净化保结构：clean_source_markdown 不打散 :::figure/:::figuregroup 围栏与 asset 引用。

可直接运行：python3 quwoquan_data/tests/local_contract/core/test_figure_group_backfill__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.figure_groups import (  # noqa: E402
    build_figure_group_block,
    expand_figure_groups,
    figure_group_integrity_issues,
    figure_image_count,
    iter_figure_groups,
    prune_unbound_group_images,
)

_GROUP_DRAFT = (
    "## 五花海\n"
    "清晨抵达。\n"
    ':::figuregroup id="grp-001" count="3"\n'
    "![湖景一](asset://asset_001)\n"
    "![湖景二](asset://asset_002)\n"
    "![湖景三](asset://asset_003)\n"
    ":::\n"
    "随后离开。\n"
)


def test_expand_backfills_group_into_n_same_source_single_figures():
    expanded = expand_figure_groups(_GROUP_DRAFT)
    # 组占位被展开，不再残留 figuregroup。
    assert ":::figuregroup" not in expanded
    # 展开为 3 个单图块（同序、同源 assetId）。
    assert expanded.count(":::figure") == 3
    for aid in ("asset_001", "asset_002", "asset_003"):
        assert f"asset://{aid}" in expanded
    # 正文文字保留（围栏外内容不丢）。
    assert "清晨抵达。" in expanded and "随后离开。" in expanded


def test_figure_image_count_counts_group_members():
    assert figure_image_count(_GROUP_DRAFT) == 3
    # 单图块 + 组：1 + 2 = 3。
    mixed = (
        ":::figure\n![封面](asset://cover)\n封面\n:::\n"
        + build_figure_group_block("grp-009", [("a", "x1"), ("b", "x2")])
    )
    assert figure_image_count(mixed) == 3


def test_integrity_passes_when_group_returned_verbatim():
    # AI 原样带回 -> 无问题。
    assert figure_group_integrity_issues(_GROUP_DRAFT, _GROUP_DRAFT) == []
    # 底稿无组 -> 不触发（None/空底稿安全）。
    assert figure_group_integrity_issues(_GROUP_DRAFT, "纯文字底稿") == []


def test_integrity_flags_dropped_or_split_or_tampered_group():
    base = _GROUP_DRAFT
    # 整组丢失（拆成单图/删图）。
    article_split = (
        "## 五花海\n清晨抵达。\n"
        ":::figure\n![湖景一](asset://asset_001)\n湖景一\n:::\n"
        "随后离开。\n"
    )
    issues = figure_group_integrity_issues(article_split, base)
    assert issues and "grp-001" in issues[0]

    # 组内 assetId 被篡改/丢图（count 对不上原序）。
    article_tampered = (
        "## 五花海\n清晨抵达。\n"
        ':::figuregroup id="grp-001" count="2"\n'
        "![湖景一](asset://asset_001)\n"
        "![别处图](asset://asset_999)\n"
        ":::\n随后离开。\n"
    )
    issues2 = figure_group_integrity_issues(article_tampered, base)
    assert issues2 and "grp-001" in issues2[0]


def test_prune_drops_unbound_inline_and_recounts():
    # 组内 2 张已同源绑定（asset_*），1 张仍是未下载的 source-inline 占位 -> 剔除并重算 count=2。
    draft = (
        ':::figuregroup id="grp-001" count="3"\n'
        "![一](asset://asset_001)\n"
        "![二](asset://source-inline-077)\n"
        "![三](asset://asset_003)\n"
        ":::\n"
    )
    pruned = prune_unbound_group_images(draft)
    groups = list(iter_figure_groups(pruned))
    assert len(groups) == 1
    gid, declared, imgs = groups[0]
    assert gid == "grp-001" and declared == 2
    assert [aid for _c, aid in imgs] == ["asset_001", "asset_003"]
    assert "source-inline-077" not in pruned


def test_prune_drops_entire_group_when_all_unbound():
    draft = (
        "前文\n"
        ':::figuregroup id="grp-002" count="2"\n'
        "![一](asset://source-inline-010)\n"
        "![二](asset://source-inline-011)\n"
        ":::\n"
        "后文\n"
    )
    pruned = prune_unbound_group_images(draft)
    assert ":::figuregroup" not in pruned
    assert "前文" in pruned and "后文" in pruned


def test_clean_source_markdown_preserves_figure_fences():
    """净化（去噪声）不得打散图文混排围栏：:::figure/:::figuregroup 起止行与 asset 引用必须保结构保留，
    否则 source.clean.md（AI 优先消费的底稿）里的图文块被破坏 -> 图文混排丢失。"""
    from content.post.evidence_text import clean_source_markdown

    raw = (
        "## 五花海\n"
        "正文一段，足够长以免被当作无字母噪声行处理。\n"
        ':::figuregroup id="grp-001" count="2"\n'
        "![一](asset://source-inline-001)\n"
        "![二](asset://source-inline-002)\n"
        ":::\n"
        ":::figure\n"
        "![封面](asset://source-inline-003)\n"
        "封面说明\n"
        ":::\n"
    )
    cleaned = clean_source_markdown(raw)
    # 围栏起止行都在（尤其是无字母的收尾 `:::` 不再被当噪声删）。
    assert ':::figuregroup id="grp-001" count="2"' in cleaned
    assert cleaned.count(":::") >= 4  # group 起+止 + figure 起+止
    assert "asset://source-inline-001" in cleaned
    assert "asset://source-inline-003" in cleaned
    # 展开后图片张数守恒（组 2 张 + 单图 1 张 = 3）。
    assert figure_image_count(cleaned) == 3


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"figure group backfill tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
