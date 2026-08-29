"""Resolve homepage quality limits from the owning reusable vertical policy."""
from __future__ import annotations

from content.execution.identity import parse_execution_id
from governance.content_supply_policy import load_content_supply_policy


def homepage_source_fidelity_limit(execution_id: str) -> float:
    identity = parse_execution_id(execution_id)
    return load_content_supply_policy(identity.vertical).homepage_max_source_fidelity


def homepage_body_char_minimum(execution_id: str) -> int:
    identity = parse_execution_id(execution_id)
    return load_content_supply_policy(identity.vertical).homepage_minimum_body_chars


def homepage_fact_count_minimum(execution_id: str) -> int:
    identity = parse_execution_id(execution_id)
    return load_content_supply_policy(identity.vertical).homepage_minimum_fact_count


def homepage_fact_char_minimum(execution_id: str) -> int:
    identity = parse_execution_id(execution_id)
    return load_content_supply_policy(identity.vertical).homepage_minimum_fact_chars


def homepage_section_char_minimum(execution_id: str) -> int:
    """成品页每个 `##` 章节的最小去空白字数（商用硬门 + 下发给 Agent 的同一数字）。"""
    identity = parse_execution_id(execution_id)
    return load_content_supply_policy(identity.vertical).homepage_minimum_section_chars


def homepage_source_outline_section_minimum(execution_id: str) -> int:
    """来源章节被认定为「有实质内容、必须保留」的最小去空白字数（选材口径，非成品门）。"""
    identity = parse_execution_id(execution_id)
    return load_content_supply_policy(
        identity.vertical
    ).homepage_source_outline_section_chars


def homepage_source_paragraph_overlap_limit(execution_id: str) -> float:
    """单个正文段落相对底稿允许的最大逐字重合度（复述原文判否线）。

    与 `homepage_source_fidelity_limit` 的整篇口径互不替代：整篇口径按全文平均，
    一段照抄会被其余重写段落稀释到线下，因此段落口径必须独立声明。
    """
    identity = parse_execution_id(execution_id)
    return load_content_supply_policy(
        identity.vertical
    ).homepage_max_source_paragraph_overlap


def homepage_intra_body_similarity_limit(execution_id: str) -> float:
    """正文任意两段之间允许的最大相似度（自我重复判否线）。"""
    identity = parse_execution_id(execution_id)
    return load_content_supply_policy(
        identity.vertical
    ).homepage_max_intra_body_paragraph_similarity


def homepage_derivation_paragraph_char_minimum(execution_id: str) -> int:
    """参与派生度判定的正文段落最小去空白字数（判定量纲，不是质量门）。

    低于该长度的段落其 n-gram 样本过小，逐字命中与共享专有名词无法区分；把它们
    纳入判定只会产出无法据以改稿的噪声。
    """
    identity = parse_execution_id(execution_id)
    return load_content_supply_policy(
        identity.vertical
    ).homepage_derivation_paragraph_minimum_chars


__all__ = [
    "homepage_body_char_minimum",
    "homepage_derivation_paragraph_char_minimum",
    "homepage_fact_count_minimum",
    "homepage_fact_char_minimum",
    "homepage_intra_body_similarity_limit",
    "homepage_section_char_minimum",
    "homepage_source_outline_section_minimum",
    "homepage_source_fidelity_limit",
    "homepage_source_paragraph_overlap_limit",
]
