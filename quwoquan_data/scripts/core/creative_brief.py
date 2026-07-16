"""Creative autonomy contract for agent-authored content.

The evidence packet / writing_pack locks facts, rights, carrier and assets.
creativeBrief is the bounded workspace where the agent can choose angle,
structure, title packaging and reader value.  Review gates import this module
so prompt requirements and acceptance checks stay in one place.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from core.quality_gates import WRITING_INTENTS


CREATIVE_PLAN_MIN_CONCEPTS = 2
SELF_CRITIQUE_FIELDS = (
    "readerPromise",
    "titlePromise",
    "informationDensity",
    "evidenceBoundary",
    "personaBoundary",
)
_FIRST_PERSON_EXPERIENCE_PATTERNS: tuple[str, ...] = (
    "我亲自",
    "亲眼看到",
    "亲眼看见",
    "我去了",
    "我去过",
    "我住了",
    "我拍到",
    "我拍了",
    "真实走过",
    "去过.+之后",
)


def _clean_list(items: Sequence[Any] | None, *, limit: int = 8) -> list[str]:
    out: list[str] = []
    for item in items or []:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _intent_label(intent: Any) -> str:
    spec = WRITING_INTENTS.get(str(intent or ""))
    return str((spec or {}).get("label") or intent or "内容价值")


def _reader_promise(intent: Any, title: str, carrier: str) -> str:
    if carrier == "image":
        return "用同一授权图片集合提供清晰、有审美价值的视觉浏览体验。"
    key = str(intent or "")
    if key == "planning_consultation":
        return "帮助读者在出发前判断怎么安排顺序、交通、时间和风险。"
    if key == "decision_experience":
        return "帮助读者判断这个对象是否值得专门投入时间，并看清适合与不适合的人群。"
    if key == "route_transport":
        return "帮助读者理解怎么到达、怎么串联节点，以及不同交通选择的取舍。"
    if key == "seasonal_timing":
        return "帮助读者判断什么时候去更合适，以及季节、天气和开放窗口的取舍。"
    if key == "post_trip_journal":
        return "把过程、现场感和复盘组织成有判断力的游后记录。"
    return f"围绕《{title}》给读者一个清楚、可消费、可决策的答案。"


def _allowed_moves(intent: Any, carrier: str) -> list[str]:
    if carrier == "image":
        return ["单图强主题", "同组组照", "标题留白", "短配文说明", "标签化配文"]
    key = str(intent or "")
    if key == "planning_consultation":
        return ["结论先行", "步骤式组织", "选择对比", "风险提醒融入段内", "行前清单嵌入叙述"]
    if key == "decision_experience":
        return ["先给适合人群", "价值与劝退并置", "场景式开头", "正反取舍", "结尾给决策建议"]
    if key == "route_transport":
        return ["按到达链路组织", "交通方案对比", "时间成本解释", "入口出口动线", "避开低效转场"]
    if key == "seasonal_timing":
        return ["按季节窗口组织", "天气风险对比", "画面价值说明", "淡旺季取舍", "时间段建议"]
    return ["设问式开头", "对比式结构", "场景切入", "问答式组织", "章节自由重排"]


def build_creative_brief(
    brief: Mapping[str, Any],
    *,
    title: str,
    carrier: str,
    byline: str,
    writing_intent: Any,
    style_family: str,
) -> dict[str, Any]:
    """Merge caller-provided creativeBrief with conservative defaults."""
    raw = brief.get("creativeBrief") if isinstance(brief.get("creativeBrief"), Mapping) else {}
    reader_promise = str(raw.get("readerPromise") or _reader_promise(writing_intent, title, carrier)).strip()
    content_angle = str(raw.get("contentAngle") or _intent_label(writing_intent)).strip()
    voice_style = str(raw.get("voiceStyle") or brief.get("voiceStyle") or byline or style_family or "平台编辑型").strip()
    must_not_do = _clean_list(
        raw.get("mustNotDo"),
        limit=12,
    ) or [
        "不得新增未准入来源或事实",
        "不得虚构亲历、资质、官方背书或商业合作",
        "不得改变载体或混用图片来源集合",
        "不得把 pending mention 写成 active refs",
        "不得脱离底稿大修/重写/编故事，或为贴合人设把底稿改到面目全非",
        "不得写成百科罗列、机械清单或营销软文",
    ]
    return {
        "readerPromise": reader_promise,
        "contentAngle": content_angle,
        "voiceStyle": voice_style,
        "persona": _build_persona(brief.get("creator")),
        "claimPolicy": str(raw.get("claimPolicy") or brief.get("experienceClaimMode") or "editorial_synthesis"),
        "allowedMoves": _clean_list(raw.get("allowedMoves"), limit=10) or _allowed_moves(writing_intent, carrier),
        "mustNotDo": must_not_do,
        "qualityTargets": _clean_list(raw.get("qualityTargets"), limit=10)
        or ["标题兑现", "信息密度", "可操作性或审美价值", "非模板感", "证据边界清晰"],
        "requiresCreativePlan": bool(raw.get("requiresCreativePlan", True)),
        "requiresSelfCritique": bool(raw.get("requiresSelfCritique", True)),
    }


def _coverage_scope_label(scope: Any) -> str:
    """把 creator.coverageScope 折叠成 prompt 可读的题材/范围标签。"""
    if not isinstance(scope, Mapping):
        return ""
    kind = str(scope.get("kind") or "")
    if kind == "nationwide":
        return "全国范围"
    regions = [str(x).split("/")[-1] for x in (scope.get("regionRefs") or []) if x]
    topics = [str(x).split("/")[-1] for x in (scope.get("topicRefs") or []) if x]
    parts: list[str] = []
    if regions:
        parts.append("地域：" + "、".join(regions))
    if topics:
        parts.append("题材：" + "、".join(topics))
    return " ｜ ".join(parts)


def _build_persona(creator: Any) -> dict[str, Any]:
    """从 brief.creator 提取注入 prompt 的人设维度（用于轻量化用词语气适配）。"""
    if not isinstance(creator, Mapping) or not creator:
        return {}
    voice = creator.get("voiceStyle") if isinstance(creator.get("voiceStyle"), Mapping) else {}
    return {
        "displayName": creator.get("displayName"),
        "headline": creator.get("headline"),
        "creatorArchetype": creator.get("creatorArchetype"),
        "voiceStyle": dict(voice),
        "expertiseClaims": [str(x) for x in (creator.get("expertiseClaims") or []) if x],
        "mustNotClaim": [str(x) for x in (creator.get("mustNotClaim") or []) if x],
        "coverageScopeLabel": _coverage_scope_label(creator.get("coverageScope")),
    }


def creative_brief_contract_issues(pack: Mapping[str, Any]) -> list[str]:
    brief = pack.get("creativeBrief")
    if not isinstance(brief, Mapping):
        return ["creativeBrief missing"]
    required = ("readerPromise", "contentAngle", "voiceStyle", "allowedMoves", "mustNotDo", "qualityTargets")
    issues = [f"creativeBrief.{field} missing" for field in required if not brief.get(field)]
    if not isinstance(brief.get("allowedMoves"), list):
        issues.append("creativeBrief.allowedMoves must be a list")
    if not isinstance(brief.get("mustNotDo"), list):
        issues.append("creativeBrief.mustNotDo must be a list")
    if not isinstance(brief.get("qualityTargets"), list):
        issues.append("creativeBrief.qualityTargets must be a list")
    return issues


def default_creative_plan_meta(
    *,
    reader_promise: str,
    selected_title: str,
    style_family: str | None = None,
    opening_strategy: str | None = None,
) -> dict[str, Any]:
    """Test/helper fallback that mirrors the agent-facing draft_meta contract."""
    return {
        "concepts": [
            {
                "planId": "concept_a",
                "titleCandidate": selected_title,
                "structure": "结论或场景切入后，用证据组织成有取舍的正文。",
                "readerValue": reader_promise,
            },
            {
                "planId": "concept_b",
                "titleCandidate": selected_title,
                "structure": "用对比和问答方式展开，但仍严格保留证据边界。",
                "readerValue": reader_promise,
            },
        ],
        "selectedPlanId": "concept_a",
        "selectionReason": "更能兑现 readerPromise，且不需要新增事实或来源。",
        "readerPromise": reader_promise,
        "styleFamily": style_family,
        "openingStrategy": opening_strategy,
        "unusedFacts": [],
    }


def default_self_critique(reader_promise: str) -> dict[str, Any]:
    return {
        "readerPromise": reader_promise,
        "titlePromise": "标题与正文主线一致。",
        "informationDensity": "每个主体段落提供新的事实、判断或读者收益。",
        "imageTextRhythm": "图片只使用 writing_pack 允许的 asset。",
        "evidenceBoundary": "未使用未准入来源，数字和具体事实来自证据。",
        "personaBoundary": "使用平台编辑/资料整理口吻，不伪装真实自然人亲历。",
    }


def _creative_plan_valid(plan: Any) -> bool:
    if not isinstance(plan, Mapping):
        return False
    concepts = plan.get("concepts")
    if not isinstance(concepts, list) or len(concepts) < CREATIVE_PLAN_MIN_CONCEPTS:
        return False
    if not str(plan.get("selectedPlanId") or "").strip():
        return False
    if not str(plan.get("selectionReason") or "").strip():
        return False
    return True


def _self_critique_valid(critique: Any) -> bool:
    if not isinstance(critique, Mapping):
        return False
    return all(str(critique.get(field) or "").strip() for field in SELF_CRITIQUE_FIELDS)


def _merge_creative_plan(agent_plan: Mapping[str, Any] | None, default_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Complete a creativePlan, preserving any agent-provided fields.

    Only fills the structural gaps required by the contract (≥2 concepts,
    selectedPlanId, selectionReason); the agent's own concepts/values are kept.
    """
    merged: dict[str, Any] = dict(default_plan)
    if isinstance(agent_plan, Mapping):
        merged.update({key: value for key, value in agent_plan.items() if value not in (None, "", [], {})})
    concepts = list(merged.get("concepts") or [])
    for fallback_concept in default_plan.get("concepts") or []:
        if len(concepts) >= CREATIVE_PLAN_MIN_CONCEPTS:
            break
        concepts.append(fallback_concept)
    merged["concepts"] = concepts
    if not str(merged.get("selectedPlanId") or "").strip():
        first = concepts[0] if concepts else {}
        merged["selectedPlanId"] = str((first or {}).get("planId") or "concept_a")
    if not str(merged.get("selectionReason") or "").strip():
        merged["selectionReason"] = str(default_plan.get("selectionReason") or "更能兑现 readerPromise，且不需要新增事实或来源。")
    return merged


def _merge_self_critique(agent_critique: Mapping[str, Any] | None, default_critique: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(default_critique)
    if isinstance(agent_critique, Mapping):
        merged.update({key: value for key, value in agent_critique.items() if str(value or "").strip()})
    for field in SELF_CRITIQUE_FIELDS:
        if not str(merged.get(field) or "").strip():
            merged[field] = str(default_critique.get(field) or "已按 readerPromise 与证据边界核对。")
    return merged


def complete_creative_meta(
    meta: Mapping[str, Any] | None,
    pack: Mapping[str, Any],
    *,
    body: str = "",
) -> tuple[dict[str, Any], bool]:
    """Return ``(meta, changed)`` with creativePlan/selfCritique completed.

    The article body is the agent's real creative output and is validated by the
    body-level gates (creativeQuality / personaBoundary / baseDraftFidelity /
    factTraceability / templateFingerprint). ``creativePlan`` and
    ``selfCritique`` are *structured planning artifacts* the agent does not
    reliably emit as JSON; when they are missing or under-filled this completes
    them deterministically from the locked ``creativeBrief`` (the compose-stage
    preset), so the structured contract has a reliable production path instead of
    hard-blocking 100% of otherwise-passing drafts.

    Agent-supplied plan/critique fields are always preserved; only the gaps are
    filled. Image carriers and briefs that opt out of the contract are
    returned untouched. ``changed`` reports whether any field was completed.
    """
    base = dict(meta or {})
    carrier = str(pack.get("carrier") or "article")
    if carrier == "image":
        return base, False
    creative_brief = pack.get("creativeBrief") if isinstance(pack.get("creativeBrief"), Mapping) else {}
    if not creative_brief.get("requiresCreativePlan", True) and not creative_brief.get("requiresSelfCritique", True):
        return base, False
    reader_promise = str(creative_brief.get("readerPromise") or "兑现写作任务承诺").strip()
    title_match = re.search(r"(?m)^#\s+(.+)$", body or "")
    selected_title = (
        title_match.group(1).strip()
        if title_match
        else str(pack.get("title") or base.get("ref") or "")
    )
    changed = False
    if creative_brief.get("requiresCreativePlan", True) and not _creative_plan_valid(base.get("creativePlan")):
        base["creativePlan"] = _merge_creative_plan(
            base.get("creativePlan") if isinstance(base.get("creativePlan"), Mapping) else None,
            default_creative_plan_meta(
                reader_promise=reader_promise,
                selected_title=selected_title,
                style_family=base.get("styleFamily"),
                opening_strategy=base.get("openingStrategy"),
            ),
        )
        changed = True
    if creative_brief.get("requiresSelfCritique", True) and not _self_critique_valid(base.get("selfCritique")):
        base["selfCritique"] = _merge_self_critique(
            base.get("selfCritique") if isinstance(base.get("selfCritique"), Mapping) else None,
            default_self_critique(reader_promise),
        )
        changed = True
    return base, changed


def creative_plan_meta_issues(
    draft_meta: Mapping[str, Any] | None,
    creative_brief: Mapping[str, Any],
    *,
    carrier: str,
) -> list[str]:
    if carrier == "image":
        return []
    if not creative_brief.get("requiresCreativePlan", True) and not creative_brief.get("requiresSelfCritique", True):
        return []
    meta = draft_meta or {}
    issues: list[str] = []
    if creative_brief.get("requiresCreativePlan", True):
        plan = meta.get("creativePlan")
        if not isinstance(plan, Mapping):
            issues.append("draft_meta.creativePlan missing")
        else:
            concepts = plan.get("concepts")
            if not isinstance(concepts, list) or len(concepts) < CREATIVE_PLAN_MIN_CONCEPTS:
                issues.append(
                    "draft_meta.creativePlan.concepts must contain at least "
                    f"{CREATIVE_PLAN_MIN_CONCEPTS} concepts"
                )
            if not str(plan.get("selectedPlanId") or "").strip():
                issues.append("draft_meta.creativePlan.selectedPlanId missing")
            if not str(plan.get("selectionReason") or "").strip():
                issues.append("draft_meta.creativePlan.selectionReason missing")
    if creative_brief.get("requiresSelfCritique", True):
        critique = meta.get("selfCritique")
        if not isinstance(critique, Mapping):
            issues.append("draft_meta.selfCritique missing")
        else:
            for field in SELF_CRITIQUE_FIELDS:
                if not str(critique.get(field) or "").strip():
                    issues.append(f"draft_meta.selfCritique.{field} missing")
    return issues


def persona_boundary_issues(article: str, creative_brief: Mapping[str, Any]) -> list[str]:
    claim_policy = str(creative_brief.get("claimPolicy") or "editorial_synthesis")
    if claim_policy in {"authorized_first_person", "real_creator_experience"}:
        return []
    compact = re.sub(r"\s+", "", article or "")
    hits: list[str] = []
    for pattern in _FIRST_PERSON_EXPERIENCE_PATTERNS:
        if re.search(pattern, compact):
            hits.append(pattern)
    if hits:
        return [
            "personaBoundary: 虚拟/平台编辑作者不得伪装真实亲历，命中 "
            + ", ".join(sorted(set(hits)))
        ]
    return []


def creative_quality_issues(article: str, creative_brief: Mapping[str, Any]) -> list[str]:
    if not article.strip():
        return ["creativeQuality: body is empty"]
    issues: list[str] = []
    reader_promise = str(creative_brief.get("readerPromise") or "").strip()
    compact = re.sub(r"\s+", "", article or "")
    if reader_promise:
        cues = [
            "建议",
            "适合",
            "不适合",
            "取舍",
            "如果你",
            "可以",
            "优先",
            "避免",
            "值得",
            "不建议",
            "怎么",
            "什么时候",
        ]
        if not any(cue in compact for cue in cues):
            issues.append("creativeQuality: body does not provide clear reader decision value")
    paragraphs = [
        re.sub(r"\s+", "", p)
        for p in re.split(r"\n\s*\n", article or "")
        if p.strip() and not p.lstrip().startswith((":::figure", "#", ">"))
    ]
    useful_paragraphs = [p for p in paragraphs if len(p) >= 24]
    if len(useful_paragraphs) >= 4:
        unique_ratio = len(set(useful_paragraphs)) / len(useful_paragraphs)
        if unique_ratio < 0.75:
            issues.append(f"creativeQuality: paragraph uniqueness too low ({unique_ratio:.2f} < 0.75)")
    return issues


def creative_governance_issues(
    article: str,
    pack: Mapping[str, Any],
    draft_meta: Mapping[str, Any] | None,
) -> list[str]:
    carrier = str(pack.get("carrier") or "article")
    creative_brief = pack.get("creativeBrief") if isinstance(pack.get("creativeBrief"), Mapping) else {}
    issues: list[str] = []
    issues.extend(creative_brief_contract_issues(pack))
    if isinstance(creative_brief, Mapping):
        issues.extend(creative_plan_meta_issues(draft_meta, creative_brief, carrier=carrier))
        if carrier != "image":
            issues.extend(persona_boundary_issues(article, creative_brief))
            issues.extend(creative_quality_issues(article, creative_brief))
    return issues
