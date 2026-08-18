"""Canonical projection of an upstream ``distributionDecision`` into a row.

缺席与阻止是两种结果，必须分开投影。多个上游把「上游还没有做出决策」写成
``""``，那是穿了空串外衣的缺席，不是拒绝授权；保留成空串会让下游把上游契约
缺口报成权利拒绝，掩盖真正该修的写入方。所以缺席在这里只有一个动作：不写这
个键。已在场的决策一律原样透传，包括无法识别的取值——识别与拒绝是下游分级
的职责，投影层擦掉它等于把「取值非法」伪装成「键缺席」。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DISTRIBUTION_DECISION_KEY = "distributionDecision"


def projected_distribution_decision(source: Mapping[str, Any]) -> dict[str, Any]:
    """在场则返回单键映射，缺席则返回空映射（调用方用 ``**`` 展开）。"""
    if DISTRIBUTION_DECISION_KEY not in source:
        return {}
    raw = source[DISTRIBUTION_DECISION_KEY]
    if raw is None:
        return {}
    if isinstance(raw, str):
        decision = raw.strip()
        return {DISTRIBUTION_DECISION_KEY: decision} if decision else {}
    return {DISTRIBUTION_DECISION_KEY: raw}


__all__ = ["DISTRIBUTION_DECISION_KEY", "projected_distribution_decision"]
