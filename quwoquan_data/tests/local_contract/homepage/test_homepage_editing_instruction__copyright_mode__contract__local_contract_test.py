"""创作指令必须与 copyright_mode_issues 硬门同源。

历史失败形态：`editingInstruction` 对两种 sourceUseMode 下发同一条「保留三分之二
原句骨架、恢复全部正文段落、禁止摘要」指令，而 `factual_reference_only` 的准出门
要求 fidelity <= 0.55 且 page/source <= 0.65。遵循指令必然撞门，无人值守放量下
通过率恒为 0。本测试把两侧钉在同一组常量上，防止再次漂移。
"""
from __future__ import annotations

import pytest

from content.homepage.commercial_gate import (
    FACTUAL_COMPRESSION_TIERS,
    FACTUAL_REFERENCE_MAX_FIDELITY,
    copyright_mode_issues,
)
from content.homepage.homepage_prepare import homepage_editing_instruction

_SKELETON_PHRASES = (
    "保留三分之二原句骨架",
    "禁止摘要",
    "恢复完整底稿",
)


def test_licensed_adaptation_keeps_the_skeleton_preserving_instruction() -> None:
    instruction = homepage_editing_instruction("licensed_adaptation")
    assert "保留三分之二原句骨架" in instruction
    assert "禁止摘要、合并或省略后半部分" in instruction


def test_factual_reference_only_never_asks_for_skeleton_preservation() -> None:
    """否则指令与 fidelity/压缩门正面冲突。"""
    instruction = homepage_editing_instruction("factual_reference_only")
    for phrase in _SKELETON_PHRASES:
        assert phrase not in instruction, f"与压缩门冲突的措辞仍在场: {phrase}"


def test_factual_reference_only_states_the_governed_thresholds() -> None:
    """指令必须原样带出门禁数值，避免两侧各写一个数字。"""
    instruction = homepage_editing_instruction("factual_reference_only")
    max_ratio = FACTUAL_COMPRESSION_TIERS[0][1]
    assert str(FACTUAL_REFERENCE_MAX_FIDELITY) in instruction
    assert str(max_ratio) in instruction


def test_factual_reference_only_requires_fact_extraction_rewrite() -> None:
    instruction = homepage_editing_instruction("factual_reference_only")
    assert "事实抽取" in instruction
    assert "重写" in instruction


def test_both_modes_keep_the_shared_structural_requirements() -> None:
    """章节/多级标题/时间线归并是载体级要求，与版权模式无关。"""
    for mode in ("licensed_adaptation", "factual_reference_only"):
        instruction = homepage_editing_instruction(mode)
        assert "清单内标题必须原文、原层级保留" in instruction
        assert "章节均衡硬要求" in instruction
        assert "时间线归并硬要求" in instruction


def test_unknown_mode_fails_closed() -> None:
    with pytest.raises(ValueError, match="sourceUseMode"):
        homepage_editing_instruction("public_domain")


def test_a_draft_following_the_factual_instruction_passes_the_gate() -> None:
    """指令的字面目标必须落在门内：压缩到 0.5、无长串原文沿用即通过。"""
    source = "".join(f"乐山大佛第{index}段记载了开凿与维修的具体年份和尺度。" for index in range(1, 61))
    rewritten = "".join(f"该处第{index}项事实经改写后只保留年份与尺度要点。" for index in range(1, 26))
    assert copyright_mode_issues(rewritten, source, "factual_reference_only") == []


def _rendered_draft_prompt(source_use_mode: str) -> str:
    from content.homepage.homepage_prompt import _render_entity_page_prompt

    return _render_entity_page_prompt(
        {
            "name": "乐山大佛",
            "etype": "景区",
            "minChars": 350,
            "minSectionChars": 80,
            "baseDraft": {
                "sourceRef": "1.source/baike/source.clean.md",
                "sourceUseMode": source_use_mode,
                "markdown": "乐山大佛开凿于唐代，历时约九十年建成。",
            },
        }
    )


def test_rendered_draft_prompt_carries_the_mode_specific_instruction() -> None:
    """真正下发给创作方的是 4.draft/prompt.md：它必须消费同一条指令，而非另写一套。"""
    factual = _rendered_draft_prompt("factual_reference_only")
    assert "sourceUseMode=factual_reference_only" in factual
    assert "事实抽取" in factual
    for phrase in _SKELETON_PHRASES:
        assert phrase not in factual, f"prompt 仍下发与压缩门冲突的措辞: {phrase}"

    licensed = _rendered_draft_prompt("licensed_adaptation")
    assert "sourceUseMode=licensed_adaptation" in licensed
    assert "保留三分之二原句骨架" in licensed


def test_rendered_draft_prompt_states_no_second_fidelity_target() -> None:
    """system 段曾硬编码 65%-85% 留存目标，与 factual 模式的 0.55 上限直接冲突。"""
    for mode in ("licensed_adaptation", "factual_reference_only"):
        prompt = _rendered_draft_prompt(mode)
        assert "65%-85%" not in prompt
        assert "留存率目标" not in prompt
