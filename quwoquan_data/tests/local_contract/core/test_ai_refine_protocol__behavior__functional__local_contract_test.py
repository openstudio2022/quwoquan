"""AI 加工最小干扰协议合约测试（plan §11）。

L1_domain_service=quwoquan_data 内容生产 / L2=实体主页生成 / L3=AI 加工协议。
验收意图 contract：占位符缺失/新增/重复/改 id/追加文字均 reject；
展开只由代码侧完成且 caption 只用原图注。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from core.ai_refine_protocol import (  # noqa: E402
    expand_image_placeholders,
    extract_image_placeholders,
    image_placeholder_line,
    placeholder_consistency_issues,
)

_BINDINGS = [
    {"figId": "fig_02", "sourceAssetId": "001_002", "caption": "大雄宝殿前的古柏", "sectionAnchor": "历史沿革"},
    {"figId": "fig_03", "sourceAssetId": "001_003", "caption": "红军长征纪念碑", "sectionAnchor": "文物保护"},
]


def _draft(*lines: str) -> str:
    return "\n".join(["# 武侯祠", "", *lines, "", "正文若干。"])


def test_placeholder_roundtrip_passes():
    draft = _draft(
        image_placeholder_line("fig_02"),
        "",
        image_placeholder_line("fig_03"),
    )
    assert placeholder_consistency_issues(draft, _BINDINGS) == []


def test_missing_placeholder_rejected():
    draft = _draft(image_placeholder_line("fig_02"))
    issues = placeholder_consistency_issues(draft, _BINDINGS, label="武侯祠")
    assert any("[[IMG:fig_03]] 缺失" in issue for issue in issues), issues


def test_unknown_placeholder_rejected():
    draft = _draft(
        image_placeholder_line("fig_02"),
        image_placeholder_line("fig_03"),
        image_placeholder_line("fig_99"),
    )
    issues = placeholder_consistency_issues(draft, _BINDINGS)
    assert any("未下发的占位符 [[IMG:fig_99]]" in issue for issue in issues), issues


def test_duplicated_placeholder_rejected():
    draft = _draft(
        image_placeholder_line("fig_02"),
        image_placeholder_line("fig_02"),
        image_placeholder_line("fig_03"),
    )
    issues = placeholder_consistency_issues(draft, _BINDINGS)
    assert any("[[IMG:fig_02]] 重复出现" in issue for issue in issues), issues


def test_trailing_caption_text_rejected():
    draft = _draft(
        image_placeholder_line("fig_02") + " 润色过的美丽古柏",
        image_placeholder_line("fig_03"),
    )
    issues = placeholder_consistency_issues(draft, _BINDINGS)
    assert any("[[IMG:fig_02]] 行尾出现多余文字" in issue for issue in issues), issues


def test_inline_embedded_placeholder_rejected():
    draft = _draft(
        "句中混入 [[IMG:fig_02]] 大雄宝殿前的古柏 不允许。",
        image_placeholder_line("fig_03"),
    )
    issues = placeholder_consistency_issues(draft, _BINDINGS)
    assert any("[[IMG:fig_02]] 缺失" in issue for issue in issues) or any(
        "未独占一行" in issue for issue in issues
    ), issues


def test_expand_produces_block_fullwidth_figure_with_original_caption_only():
    draft = _draft(
        image_placeholder_line("fig_02"),
        image_placeholder_line("fig_03"),
    )
    out = expand_image_placeholders(draft, _BINDINGS)
    assert "[[IMG:" not in out
    assert ':::figure id="fig_02" layout="fullWidth" caption="大雄宝殿前的古柏"\nasset://001_002\n:::' in out
    assert ':::figure id="fig_03" layout="fullWidth" caption="红军长征纪念碑"\nasset://001_003\n:::' in out


def test_expand_keeps_unknown_placeholder_for_structure_gate():
    draft = _draft(image_placeholder_line("fig_99"))
    out = expand_image_placeholders(draft, _BINDINGS)
    assert "[[IMG:fig_99]]" in out, "未知占位符必须留给结构门阻断，不得静默吞掉"


def test_extract_only_matches_full_lines():
    text = "\n".join([
        image_placeholder_line("fig_02"),
        "行内 [[IMG:fig_03]] 不算独占一行",
    ])
    assert extract_image_placeholders(text) == [("fig_02", "")]
