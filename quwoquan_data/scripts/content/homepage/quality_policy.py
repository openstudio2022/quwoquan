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


__all__ = [
    "homepage_body_char_minimum",
    "homepage_fact_count_minimum",
    "homepage_fact_char_minimum",
    "homepage_section_char_minimum",
    "homepage_source_outline_section_minimum",
    "homepage_source_fidelity_limit",
]
