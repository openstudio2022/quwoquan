"""实体聚焦度：底稿/来源是否"明确指代某个实体"的单一真相源。

为什么需要：放量时长篇多目的地游记（如「成都-重庆-三峡攻略」「沈阳自驾西藏」）
会顺带提到某个景点，但通篇并不指代该实体。若把这类源当成单实体文章底稿，
会让 baseDraftFidelity 门陷入反向激励：照抄跑题底稿 → 假通过（发出跑题内容）；
照实体重写 → fidelity 低 → 假失败。因此「从实体角度挖掘的文章/图片，标题与
正文必须明确指代此实体，否则弃稿；多地点环线内容改走网站角度（kind=route）」。

本模块同时被 download（来源单元落盘 meta.json）、workflow services（确定性选源）、
content_plan（篇目规划门）、scale_readiness（准出口径）消费，确保口径单一。
"""
from __future__ import annotations

import re
from typing import Any, Mapping

# 实体通名后缀：用于派生别名（去通名 + 前/后二字），度量底稿对该实体的聚焦度。
ENTITY_NAME_SUFFIXES: tuple[str, ...] = (
    "山", "沟", "寺", "佛", "湖", "江", "河", "峰", "镇", "村",
    "岛", "园", "宫", "阁", "陵", "祠",
)

# 聚焦度阈值（信号行中提及该实体的字符占比 0..1）。
# 标定依据：单实体游记/攻略通常 >=0.20；跨城/环线长游记对单实体 <=0.15。
ENTITY_FOCUS_STRONG_FLOOR: float = 0.20
ENTITY_FOCUS_WEAK_FLOOR: float = 0.08

# 环线判定：除当前实体外，正文+标题还突出提及的"其它覆盖目标"数量阈值。
# >= 该值即视为多地点环线（当前实体 + >=2 个兄弟目标 = >=3 个地点），
# 即使对当前实体聚焦度高，也不得作单实体底稿，应走网站角度 kind=route。
ROUTE_SIBLING_FLOOR: int = 2

# verdict 取值（与 content_plan/scale_readiness 既有消费口径对齐）。
VERDICT_STRONG = "strong"
VERDICT_SUPPORTING = "supporting_only"
VERDICT_OFF_ENTITY = "off_entity"

# content_plan / scale_readiness 视为"不可作主/底稿、只能当辅助证据"的 verdict。
BLOCKED_PRIMARY_VERDICTS = frozenset(
    {"weak", "supporting_only", "mismatch", "off_entity"}
)


def entity_focus_aliases(name: str) -> tuple[str, ...]:
    """实体名聚焦别名：全名 + 去通名后缀 + 前/后二字。

    用于度量"正文对该实体的聚焦度"（宁可多召回该实体的提及），
    跨实体/环线匹配请用更保守的 entity_match_aliases，避免通名二字误命中。
    """
    name = (name or "").strip()
    if not name:
        return ()
    aliases = {name}
    for suffix in ENTITY_NAME_SUFFIXES:
        if len(name) > 2 and name.endswith(suffix):
            aliases.add(name[:-1])
    if len(name) >= 4:
        aliases.add(name[:2])
        aliases.add(name[-2:])
    return tuple(alias for alias in aliases if len(alias) >= 2)


def entity_match_aliases(name: str) -> tuple[str, ...]:
    """跨实体匹配别名（保守）：全名 + 去通名后缀，不含通名二字切分。

    环线/覆盖目标命中统计用此函数，避免「杜甫草堂」的「草堂」「巷子」这类
    通名二字误把无关来源判成多地点环线（会导致过度弃稿）。
    """
    name = (name or "").strip()
    if len(name) < 2:
        return ()
    aliases = {name}
    for suffix in ENTITY_NAME_SUFFIXES:
        if len(name) > 2 and name.endswith(suffix):
            aliases.add(name[:-1])
    return tuple(alias for alias in aliases if len(alias) >= 2)


def _entity_mentioned(text: str, name: str) -> bool:
    """text 是否以保守别名命中实体 name。"""
    if not text or not name:
        return False
    return any(alias in text for alias in entity_match_aliases(name))


def _sibling_locations_mentioned(
    body: str,
    title: str,
    entity_name: str,
    sibling_names: tuple[str, ...] | list[str] | None,
) -> list[str]:
    """正文+标题突出提及的"其它覆盖目标"（用于环线判定）。"""
    if not sibling_names:
        return []
    text = f"{title or ''}\n{body or ''}"
    current = (entity_name or "").strip()
    hits: list[str] = []
    seen: set[str] = set()
    for sibling in sibling_names:
        name = str(sibling or "").strip()
        if not name or name == current or name in seen:
            continue
        if _entity_mentioned(text, name):
            hits.append(name)
            seen.add(name)
    return hits


def entity_focus_score(body: str, entity_name: str) -> float:
    """底稿对目标实体的聚焦度：提及该实体（含别名）的信号行字符占比（0..1）。"""
    aliases = entity_focus_aliases(entity_name)
    if not body or not aliases:
        return 0.0
    lines = [line for line in body.splitlines() if line.strip()]
    total = sum(len(re.sub(r"\s+", "", line)) for line in lines)
    if total <= 0:
        return 0.0
    hit = sum(
        len(re.sub(r"\s+", "", line))
        for line in lines
        if any(alias in line for alias in aliases)
    )
    return hit / total


def _title_refers_entity(title: str, entity_name: str) -> bool:
    aliases = entity_focus_aliases(entity_name)
    title = (title or "").strip()
    if not title or not aliases:
        return False
    return any(alias in title for alias in aliases)


def classify_entity_focus(
    body: str,
    entity_name: str,
    *,
    title: str = "",
    sibling_names: tuple[str, ...] | list[str] | None = None,
) -> tuple[float, str]:
    """返回 (focusScore, verdict)。

    verdict 语义（"标题和文字是否明确指代此实体"）：
    - strong：正文聚焦达标且非多地点环线，可作单实体文章/底稿主源；
    - supporting_only：只顺带提及，只能作辅助证据；
    - off_entity：通篇不指代该实体（多地点环线 / 只有图无正文 / 跑题）。

    环线优先级最高：标题+正文还突出提及 >=ROUTE_SIBLING_FLOOR 个其它覆盖目标，
    即视为多地点环线，无论对当前实体聚焦多高都判 off_entity（应走网站角度 route）。
    这样实现"实体可能不止说一个实体，比如环线 → 弃稿"。

    非环线时：标题明确指代该实体可把 strong 边界略放宽（标题+正文双指代信号）；
    标题不指代且正文聚焦不足则维持 supporting/off_entity。
    """
    score = round(entity_focus_score(body, entity_name), 4)
    sibling_hits = _sibling_locations_mentioned(body, title, entity_name, sibling_names)
    if len(sibling_hits) >= ROUTE_SIBLING_FLOOR:
        # 多地点环线：当前实体 + >=2 兄弟目标 = >=3 地点 → 单实体角度弃稿。
        return score, VERDICT_OFF_ENTITY
    title_hit = _title_refers_entity(title, entity_name)
    strong_floor = ENTITY_FOCUS_STRONG_FLOOR
    if title_hit:
        # 标题明确点名该实体时，正文聚焦门略放宽（仍需正文有实体落地）。
        strong_floor = max(ENTITY_FOCUS_WEAK_FLOOR, ENTITY_FOCUS_STRONG_FLOOR - 0.05)
    if score >= strong_floor:
        return score, VERDICT_STRONG
    if score >= ENTITY_FOCUS_WEAK_FLOOR:
        return score, VERDICT_SUPPORTING
    return score, VERDICT_OFF_ENTITY


def verdict_is_primary_eligible(verdict: str) -> bool:
    """该 verdict 是否可作实体文章/底稿主源（strong / 空均视为放行，弱/跑题拒绝）。"""
    v = str(verdict or "").strip().lower()
    return v not in BLOCKED_PRIMARY_VERDICTS


def coverage_targets_mentioned(
    body: str,
    title: str,
    target_names: Mapping[str, Any] | list[str] | tuple[str, ...],
) -> list[str]:
    """统计该来源（标题+正文）明确提及了给定覆盖目标集中的哪些实体。

    1:1 底稿中心模型下用于多标签覆盖：一篇底稿明确提及的覆盖目标都登记为 entityTags，
    底稿仍只认领单一 base。使用保守的 entity_match_aliases，避免通名二字误命中拉高覆盖数。
    """
    names = list(target_names.keys()) if isinstance(target_names, Mapping) else list(target_names)
    text = f"{title or ''}\n{body or ''}"
    hit: list[str] = []
    seen: set[str] = set()
    for name in names:
        canonical = str(name).strip()
        if not canonical or canonical in seen:
            continue
        if _entity_mentioned(text, canonical):
            hit.append(canonical)
            seen.add(canonical)
    return hit
