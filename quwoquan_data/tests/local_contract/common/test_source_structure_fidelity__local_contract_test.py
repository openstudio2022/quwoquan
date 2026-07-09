"""source 结构保真 local_contract：定义列表 / 表格 GFM 保真 / cell 属性残留 / clean 豁免。

回归背书（S100 秀山岛/东沙古镇批次实测问题）：
- `;滃洲县县长` 定义列表语法漏进 source.md（分号残留）；
- 气候 wikitable 被逐行降维丢矩阵结构；
- 无引号/typo cell 属性（`valign=top|`、`avlign=top|`）残留进 source.clean.md；
- GFM 表格分隔行 `|---|---|` 被 clean 的「无字母→样板噪声」规则误删。
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common.content_evidence import clean_source_markdown  # noqa: E402
from _common.source_layout import render_source_markdown  # noqa: E402
from _common.wiki_wikitext import parse_wikitext_layout  # noqa: E402

_WIKITEXT = """== 历史 ==

;滃洲县县长
;首任县长:王某某
:县治设于岛北

== 气候 ==

{| class="wikitable"
|+ 秀山岛气候平均数据
! 月份 !! 平均高温 !! 平均低温
|-
|valign=top| 一月 || 8.6 || 2.1
|-
|avlign=top| 七月 || style="background:#eee"| 31.2 || 25.4
|-
| 全年 || 20.1 || 13.0
|}

== 景点 ==

{| class="wikitable"
! 景点 !! 海拔
|-
| 摩星山 [[File:Moxing.jpg|thumb|摩星山]] || 257米
|-
| 兰秀文化 || —
|}
"""


def _layout_and_markdown() -> tuple[dict, str]:
    layout = parse_wikitext_layout(_WIKITEXT, title="秀山岛")
    return layout, render_source_markdown(layout)


def test_definition_list_renders_as_list_items_without_semicolon_residue() -> None:
    layout, md = _layout_and_markdown()
    items = [b for b in layout["blocks"] if b.get("type") == "listItem" and b.get("origin") == "wikidefinition"]
    texts = [b["text"] for b in items]
    assert "滃洲县县长" in texts
    assert "首任县长：王某某" in texts
    assert "县治设于岛北" in texts
    # 原始 `;` / `:` 语法不得漏进 source.md。
    assert not any(line.lstrip().startswith((";", "；")) for line in md.splitlines())


def test_simple_rectangular_table_preserved_as_gfm_matrix() -> None:
    layout, md = _layout_and_markdown()
    tables = {row["tableId"]: row for row in layout["tables"]}
    decisions = sorted(row["mappingDecision"] for row in layout["tables"])
    # 气候表 → table 保真；含行图的景点表 → 逐行降维（figure 锚定链不变）。
    assert "table" in decisions and "orderedList" in decisions
    table_blocks = [b for b in layout["blocks"] if b.get("type") == "table"]
    assert len(table_blocks) == 1
    block = table_blocks[0]
    assert block["headers"] == ["月份", "平均高温", "平均低温"]
    assert block["rows"][0] == ["一月", "8.6", "2.1"]
    # source.md 渲染为 GFM 表格。
    assert "| 月份 | 平均高温 | 平均低温 |" in md
    assert "| --- | --- | --- |" in md
    assert "| 七月 | 31.2 | 25.4 |" in md
    table_meta = next(row for row in tables.values() if row["mappingDecision"] == "table")
    assert table_meta["rowCount"] == 3 and table_meta["columnCount"] == 3


def test_unquoted_and_typo_cell_attributes_stripped() -> None:
    _, md = _layout_and_markdown()
    assert "valign=" not in md
    assert "avlign=" not in md
    assert "style=" not in md


def test_clean_source_markdown_keeps_gfm_table_and_drops_attr_residue() -> None:
    raw = "\n".join(
        [
            "## 气候",
            "",
            "| 月份 | 平均高温 |",
            "| --- | --- |",
            "| 一月 | 8.6 |",
            "",
            "- avlign=top|白泉丈人坥等聚居村落",
            "valign=top|正文残留行",
            'style="color:red"|',
            "正文段落保持原样，介绍秀山岛的地理与气候概况。",
        ]
    )
    cleaned = clean_source_markdown(raw)
    # GFM 表格三类行（表头/分隔/数据）全部保留。
    assert "| 月份 | 平均高温 |" in cleaned
    assert "| --- | --- |" in cleaned
    assert "| 一月 | 8.6 |" in cleaned
    # 属性残留剥前缀保正文；纯属性行整行剔除。
    assert "avlign=" not in cleaned and "valign=" not in cleaned and "style=" not in cleaned
    assert "白泉丈人坥等聚居村落" in cleaned
    assert "正文残留行" in cleaned
    assert "正文段落保持原样" in cleaned


def _run() -> None:
    test_definition_list_renders_as_list_items_without_semicolon_residue()
    test_simple_rectangular_table_preserved_as_gfm_matrix()
    test_unquoted_and_typo_cell_attributes_stripped()
    test_clean_source_markdown_keeps_gfm_table_and_drops_attr_residue()
    print("OK: source structure fidelity contract passed")


if __name__ == "__main__":
    _run()
