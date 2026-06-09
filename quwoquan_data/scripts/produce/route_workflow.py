"""通用线路类 evidence / writing-pack / review workflow（Agent 创作版）。

正文不再由脚本拼接：
  - prepare 阶段（build_route_writing_pack）只准备证据/选图/写作契约 + prompt.md，并写占位草稿。
  - 会话模型据 prompt.md 创作正文写回对象 `4.draft/draft.article.md`（generator=agent）。
  - review 阶段（review_route_draft）读取 agent 草稿，过模板指纹/事实可回溯/出处三道门 + 既有质量门。
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from _common.batch_asset_registry import BatchAssetRegistry, allocate_post_asset_id, load_batch_asset_registry
from _common.batch_manifest import load_batch_manifest
from _common.content_evidence import (
    build_related_search_plan,
    build_route_evidence_bundle,
    entity_names_from_refs,
    gate_route_evidence_bundle,
    load_source_records,
    public_byline_label,
)
from _common.evidence_contract import quality_payload_contract_issues
from _common.content_review import (
    check_narrative_quality,
    check_provenance,
    fact_traceability_issues,
    generator_provenance_issues,
    _long_phrase_hits,
)
from _common.draft_io import (
    GENERATOR_AGENT,
    PLACEHOLDER_MARKER,
    draft_asset_reference_issues,
    iter_draft_articles,
    is_placeholder,
    read_draft_article,
    read_draft_meta,
    read_writing_pack,
    write_placeholder_draft,
    write_prompt,
    write_writing_pack,
)
from _common.entity_extract import build_entities_sidecar, normalize_entity_refs
from _common.entity_annotation import merge_entity_refs
from _common.fact_coverage import fact_covered
from _common.image_safety import assess_image, assess_asset_sources, is_near_duplicate, STATUS_UNSAFE
from _common.review_ledger import (
    ReviewItem,
    ReviewLedger,
    agent_article_item,
    agent_fact_item,
    agent_image_item,
    load_policy,
    save_ledger,
)
from _common.stage_reports import write_gate_report, write_repair_report, write_stage_result
from _common.style_catalog import detect_opening_strategy, family_allowed_openings
from _common.template_fingerprints import template_fingerprint_issues
from _common.writing_pack import build_writing_pack, render_prompt_md


ROUTE_TEMPLATE_IDS = {
    "线路_跟团攻略",
    "线路_环线攻略",
    "线路_自驾路书",
    "线路_枢纽到达",
    "线路_深度探险",
    "线路_周末短途",
    "线路_省钱攻略",
    "线路_银发慢游",
    "线路_补给避险",
}
PROVENANCE_TERMS = ("马蜂窝", "携程", "小红书", "知乎", "大众点评", "来源平台", "游记里还提到")
TRANSITION_TERMS = ("先", "再", "随后", "最后", "一路", "转场", "返程")
LIKE_FEELING_MARKERS = ("愿意", "放松", "松弛", "值得慢", "喜欢", "心动", "治愈", "踏实", "舍不得")
DISLIKE_FEELING_MARKERS = ("怕", "劝退", "累", "疲惫", "拖", "后悔", "别硬撑", "受不了", "难受", "硬撑")
DECISION_MARKERS = ("我会", "我更愿意", "建议把", "如果你", "可以跟团", "宁可", "就该", "值不值得", "优先看", "我不会")
STANDALONE_TIPS_MARKERS = ("实用信息", "实用攻略信息", "来源平台", "信息卡", "小贴士：", "tips：", "贴士：")

# 修辞/结构骨架门：仅出建议与降分，不阻断（底稿轻改范式：结构跟随底稿，不强套骨架）。
# 硬门保留：真实性(generatorProvenance/factTraceability/baseDraftFidelity)、反抄袭/去版权
# (provenanceRewrite)、反雷同(crossArticleSimilarity)、证据/图片/联系方式/语域/载体/路线覆盖。
SOFT_CHECKS = {
    "travelogueDensity",
    "mechanicalHeading",
    "proseStyle",
    "narrativeContinuity",
    "sectionShape",
}


def aggregate_checks(
    checks: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], list[str], int]:
    """聚合评审 checks：HARD 失败计入 blocking；SOFT 失败仅出建议+降分。

    返回 (blocking, suggestions, soft_failed_count)。
    """
    blocking: list[str] = []
    suggestions: list[str] = []
    soft_failed = 0
    for name, result in checks.items():
        if result.get("passed", True):
            continue
        issues = list(result.get("issues") or [])
        if name in SOFT_CHECKS:
            soft_failed += 1
            suggestions.extend(f"[建议] {name}: {issue}" for issue in issues)
        else:
            blocking.extend(f"{name}: {issue}" for issue in issues)
        suggestions.extend(result.get("suggestions") or [])
    return blocking, suggestions, soft_failed


def is_route_brief(brief: Mapping[str, Any]) -> bool:
    subject = brief.get("subject") or {}
    return (
        isinstance(subject, Mapping)
        and subject.get("kind") == "topic"
        and subject.get("type") == "旅行/线路"
        and str(brief.get("templateId") or "") in ROUTE_TEMPLATE_IDS
    )


def load_compose_brief(task_id: str, batch_id: str, ref: str) -> dict[str, Any]:
    from _common.content_object import read_brief_object

    return read_brief_object(task_id, batch_id, ref) or {}


def iter_route_briefs(task_id: str, batch_id: str, refs: Sequence[str] | None = None) -> list[tuple[str, dict[str, Any]]]:
    from _common.content_object import iter_briefs

    wanted = {ref for ref in (refs or []) if ref}
    return [
        (ref, brief)
        for ref, brief in iter_briefs(task_id, batch_id)
        if (not wanted or ref in wanted) and is_route_brief(brief)
    ]


def analyze_route_ref(task_id: str, batch_id: str, ref: str, brief: Mapping[str, Any]) -> dict[str, Any]:
    from _common.content_object import register_from_brief

    register_from_brief(task_id, batch_id, ref, brief, content_type="article")
    entity_refs = [str(item) for item in brief.get("entityRefs") or [] if item]
    entity_names = entity_names_from_refs(entity_refs)
    source_records = load_source_records(task_id, batch_id, entity_names)
    evidence_bundle = build_route_evidence_bundle(
        ref,
        brief,
        source_records,
        entity_refs=entity_refs,
        title=str(brief.get("titleHint") or ref),
    )
    source_quality = evidence_bundle.get("storySpine", {}).get("sourceQuality", [])
    issues = gate_route_evidence_bundle(brief, evidence_bundle)
    related_search_plan = (
        build_related_search_plan({"ref": ref, "entityRefs": entity_refs}, evidence_bundle["storySpine"])
        if issues
        else None
    )
    retained_scores = [int(row.get("score") or 0) for row in source_quality if row.get("quality") != "Reject"]
    retained_avg = sum(retained_scores) / max(len(retained_scores), 1) if retained_scores else 0
    coverage = evidence_bundle.get("coverage") or {}
    coverage_ratio = 0.0
    expected = int(coverage.get("expectedEntityCount") or 0)
    if expected:
        coverage_ratio = float(coverage.get("coveredEntityCount") or 0) / expected
    quality_score = round(min(100.0, retained_avg * 12 + coverage_ratio * 28))
    recommendation = "proceed" if not issues else ("skip" if coverage_ratio == 0 else "needs_improvement")
    payload = {
        "topicId": ref,
        "qualityScore": quality_score,
        "breakdown": {
            "depth": round(min(25.0, retained_avg * 4), 1),
            "originality": 22.0,
            "practicality": round(min(30.0, coverage_ratio * 30), 1),
            "readability": 20.0,
        },
        "recommendation": recommendation,
        "templateId": brief.get("templateId"),
        "title": brief.get("titleHint") or ref,
        "evidenceBundle": evidence_bundle,
        "sourceUrls": _unique_strings(str(row.get("url") or "") for row in source_records),
        "sourcePaths": _unique_strings(str(row.get("sourcePath") or "") for row in source_records),
    }
    contract_issues = quality_payload_contract_issues(payload)
    if contract_issues:
        issues = [*issues, *contract_issues]
        recommendation = "skip" if coverage_ratio == 0 else "needs_improvement"
        payload["recommendation"] = recommendation
    write_stage_result(task_id, batch_id, "produce", "quality_analysis", ref, payload)
    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="produce",
        step="quality_analysis",
        ref=ref,
        passed=not issues,
        issues=issues,
        evidence_summary={
            "coveredEntityCount": coverage.get("coveredEntityCount"),
            "expectedEntityCount": coverage.get("expectedEntityCount"),
            "retainedSourceCount": len(retained_scores),
            "relatedSearchPlan": related_search_plan,
        },
        next_step="compose-brief",
        fallback_stage="download" if issues else None,
    )
    if issues:
        write_repair_report(
            task_id=task_id,
            batch_id=batch_id,
            command="produce",
            ref=ref,
            failed_stage="quality_analysis",
            failed_gate="routeEvidence",
            issues=issues,
            evidence_summary={"relatedSearchPlan": related_search_plan},
            fallback_stage="download",
            rerun_chain=["download", "quality_analysis", "compose-brief", "review", "materialize"],
        )
    return payload


# ---------------------------------------------------------------------------
# prepare（compose-brief）：准备写作契约，不写正文
# ---------------------------------------------------------------------------


def _route_section_intents(brief: Mapping[str, Any], evidence_bundle: Mapping[str, Any]) -> list[str]:
    """章节意图：跟随底稿自身结构，仅给最小推进建议（不再下发固定骨架）。"""
    nodes = [str(n.get("entityName") or "") for n in (evidence_bundle.get("routeNodes") or []) if n.get("entityName")]
    order = "、".join(nodes) if nodes else "线路各节点"
    return [
        "结构跟随底稿：保留底稿自身的小标题与叙述顺序，只做轻量编辑（去语病/补证据/去平台痕迹）。",
        f"若底稿未按主线推进，可按 {order} 的真实顺序理顺，但不要套用固定模板小标题。",
    ]


def build_route_writing_pack(
    task_id: str,
    batch_id: str,
    ref: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
) -> dict[str, Any]:
    from _common.content_object import register_from_brief

    register_from_brief(task_id, batch_id, ref, brief, content_type="article")
    evidence_bundle = quality_payload.get("evidenceBundle") or {}
    assets = _build_route_assets(task_id, batch_id, ref, brief, evidence_bundle)
    carrier = resolve_carrier(brief, evidence_bundle, assets)
    publish_layout = "gallery" if carrier == "gallery" else "travel"
    byline = public_byline_label(str(brief.get("templateId") or ""), brief.get("creator") or {})
    pack = build_writing_pack(
        ref=ref,
        kind="route",
        brief=brief,
        evidence_bundle=evidence_bundle,
        assets=assets,
        carrier=carrier,
        byline=byline,
        publish_layout=publish_layout,
        section_intents=_route_section_intents(brief, evidence_bundle),
        source_urls=quality_payload.get("sourceUrls") or [],
        source_paths=quality_payload.get("sourcePaths") or [],
    )
    _attach_base_draft_text(task_id, batch_id, pack)
    write_writing_pack(task_id, batch_id, ref, pack)
    write_prompt(task_id, batch_id, ref, render_prompt_md(pack))
    # 仅当尚无 agent 草稿时写占位，避免覆盖会话模型已创作的正文。
    existing = read_draft_meta(task_id, batch_id, ref)
    if not existing or str(existing.get("generator")) != GENERATOR_AGENT:
        write_placeholder_draft(task_id, batch_id, ref)

    issues = _writing_pack_readiness_issues(brief, evidence_bundle, assets)
    write_stage_result(task_id, batch_id, "produce", "compose_brief", ref, pack)
    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="produce",
        step="compose_brief",
        ref=ref,
        passed=not issues,
        issues=issues,
        evidence_summary={"assetCount": len(assets), "carrier": carrier, "routeNodeCount": len(evidence_bundle.get("routeNodes") or [])},
        next_step="agent_compose",
        fallback_stage="download" if issues else None,
    )
    if issues:
        write_repair_report(
            task_id=task_id,
            batch_id=batch_id,
            command="produce",
            ref=ref,
            failed_stage="compose_brief",
            failed_gate="writingPackReadiness",
            issues=issues,
            fallback_stage="download",
            rerun_chain=["download", "quality_analysis", "compose-brief", "review", "materialize"],
        )
    return pack


def _writing_pack_readiness_issues(
    brief: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
    assets: Sequence[Mapping[str, Any]],
) -> list[str]:
    issues = list(gate_route_evidence_bundle(brief, evidence_bundle))
    if not assets:
        issues.append("writing pack has no verifiable image assets")
    return issues


# ---------------------------------------------------------------------------
# review：读 agent 草稿 + 三道门 + 既有质量门
# ---------------------------------------------------------------------------


def _compose_payload_from_pack(
    ref: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
    pack: Mapping[str, Any],
    article: str,
    draft_meta: Mapping[str, Any] | None,
) -> dict[str, Any]:
    evidence_bundle = quality_payload.get("evidenceBundle") or {}
    story_spine = (evidence_bundle.get("storySpine") or {}) if isinstance(evidence_bundle, Mapping) else {}
    carrier = str(pack.get("carrier") or "article")
    template = (brief.get("render") or {}).get("articleTemplate") or "journal"
    meta = draft_meta or {}
    payload = {
        "topicId": ref,
        "title": brief.get("titleHint") or ref,
        "summary": _build_summary(article),
        "articleMarkdown": article,
        "carrier": carrier,
        "entityRefs": merge_entity_refs(brief, draft_meta),
        "tagRefs": list(brief.get("tagRefs") or []),
        "sourceUrls": list(quality_payload.get("sourceUrls") or []),
        "sourcePaths": list(quality_payload.get("sourcePaths") or []),
        "template": template,
        "assets": list(pack.get("assets") or []),
        "publishLayout": "gallery" if carrier == "gallery" else "travel",
        "publishAngle": _publish_angle(brief),
        "publishTitle": brief.get("titleHint") or ref,
        "publishSeq": 1,
        "conditionContext": brief.get("conditionContext"),
        "composeBriefRef": ref,
        "storySpine": story_spine,
        "generator": str(meta.get("generator") or "pending"),
        "generatorModel": meta.get("model"),
        "citedSourceRefs": list(meta.get("citedSourcePaths") or []),
        "articleRenderProfile": {
            "template": template,
            "fontPreset": (brief.get("render") or {}).get("fontPreset", "clean"),
        },
    }
    if carrier == "gallery":
        payload["galleryMarkdown"] = article
    return payload


def _attach_base_draft_text(task_id: str, batch_id: str, pack: dict[str, Any]) -> None:
    """把底稿正文内联进 writing pack，供 prompt 渲染「在此基础上适度加工」。"""
    from _common.base_draft import load_base_draft_text

    base_ref = str(pack.get("baseSourceRef") or "")
    if not base_ref:
        return
    text = load_base_draft_text(task_id, batch_id, base_ref).strip()
    if text:
        pack["baseDraftText"] = text[:4000]


def _load_source_texts(source_paths: Sequence[str]) -> list[str]:
    texts: list[str] = []
    for path in source_paths or []:
        candidate = Path(path)
        if candidate.is_file():
            try:
                texts.append(candidate.read_text(encoding="utf-8"))
            except OSError:
                continue
    return texts


def review_route_draft(
    task_id: str,
    batch_id: str,
    ref: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_bundle = quality_payload.get("evidenceBundle") or {}
    pack = read_writing_pack(task_id, batch_id, ref) or {}
    article = read_draft_article(task_id, batch_id, ref)
    draft_meta = read_draft_meta(task_id, batch_id, ref)

    # 出处 + 占位门：未由 agent 创作的正文直接判 revision_needed。
    authenticity_issues: list[str] = []
    if is_placeholder(article):
        authenticity_issues.append("draft not composed yet (placeholder); awaiting agent article")
    authenticity_issues.extend(generator_provenance_issues(draft_meta))
    body = "" if is_placeholder(article) else str(article)
    authenticity_issues.extend(template_fingerprint_issues(body))
    authenticity_issues.extend(draft_asset_reference_issues(body, pack))
    source_texts = _load_source_texts(quality_payload.get("sourcePaths") or [])
    traceability = fact_traceability_issues(body, dict(brief), source_texts)

    compose_payload = _compose_payload_from_pack(ref, brief, quality_payload, pack, body, draft_meta)
    write_stage_result(task_id, batch_id, "produce", "compose", ref, compose_payload)

    route_checks = _route_review_checks(
        body,
        brief,
        evidence_bundle,
        quality_payload,
        compose_payload,
        task_id=task_id,
        batch_id=batch_id,
        ref=ref,
        draft_meta=draft_meta,
    )
    route_checks["generatorProvenance"] = {
        "passed": not authenticity_issues,
        "issues": authenticity_issues,
        "suggestions": ["按 prompt.md 由会话模型创作正文并写回对象 `4.draft/draft.article.md`（generator=agent）。"] if authenticity_issues else [],
    }
    route_checks["factTraceability"] = {
        "passed": not traceability,
        "issues": traceability,
        "suggestions": ["补齐 mustIncludeFacts，并确保票价/海拔/时长等数字能在 source 证据中找到。"] if traceability else [],
    }
    from _common.base_draft import base_draft_fidelity_issues, load_base_draft_text

    base_text = load_base_draft_text(task_id, batch_id, brief.get("baseSourceRef"))
    fidelity = base_draft_fidelity_issues(body, base_text)
    route_checks["baseDraftFidelity"] = {
        "passed": not fidelity,
        "issues": fidelity,
        "suggestions": ["以底稿为基础适度加工：相似度过低则贴回底稿叙事；过高则进一步改写表达、去版权痕迹。"] if fidelity else [],
    }
    from _common import quality_gates as qg

    wi_issues = qg.writing_intent_consistency_issues(body, brief.get("writingIntent"))
    route_checks["writingIntentConsistency"] = {
        "passed": not wi_issues,
        "issues": wi_issues,
        "suggestions": ["按 writingIntent 主线补齐结构（路线攻略=节点顺序/转场/票务/取舍；体验=过程/取舍；游记=时间线/复盘）。"] if wi_issues else [],
    }
    banned_terms = [str(b) for b in (pack.get("bannedRegisterTerms") or brief.get("bannedRegisterTerms") or [])]
    reg_issues = qg.register_lexicon_issues(body, banned_terms)
    route_checks["registerMismatch"] = {
        "passed": not reg_issues,
        "issues": reg_issues,
        "suggestions": ["改用该垂类合适的语域（如户外景区禁'看展/展厅/展陈'），由 SOP 词表约束。"] if reg_issues else [],
    }
    from _common import public_contacts as pc

    allowed_contacts = [str(n) for n in (pack.get("allowedContactNumbers") or brief.get("allowedContactNumbers") or [])]
    contact_issues = qg.contact_info_issues(body, allowed_numbers=pc.allowed_numbers(allowed_contacts))
    route_checks["contactInfo"] = {
        "passed": not contact_issues,
        "issues": contact_issues,
        "suggestions": ["删除私人电话/微信/QQ；仅保留紧急/公共服务短号或 source 核实的景区官方接待电话。"] if contact_issues else [],
    }
    heading_extra = [str(t) for t in (pack.get("mechanicalHeadingTerms") or brief.get("mechanicalHeadingTerms") or [])]
    heading_issues = qg.mechanical_heading_issues(body, extra_terms=heading_extra)
    route_checks["mechanicalHeading"] = {
        "passed": not heading_issues,
        "issues": heading_issues,
        "suggestions": ["把纯清单式小标题改写得自然、有视角；优先沿用底稿已有小标题，不要套统一模板。"] if heading_issues else [],
    }

    blocking, suggestions, soft_failed = aggregate_checks(route_checks)
    human_review_required = bool(route_checks.get("imageGate", {}).get("humanReview"))
    decision = "approved" if not blocking else "revision_needed"
    quality_score = max(0.0, 92.0 - len(blocking) * 8.0 - soft_failed * 3.0)
    payload = {
        "topicId": ref,
        "decision": decision,
        "qualityScore": quality_score,
        "issues": blocking,
        "suggestions": _unique_strings(suggestions),
        "checks": route_checks,
        "humanReviewRequired": human_review_required,
        "generator": compose_payload.get("generator"),
    }
    write_stage_result(task_id, batch_id, "produce", "review", ref, _persisted_review_payload(payload))
    _persist_review_ledger(
        task_id, batch_id, ref, brief, compose_payload, route_checks, traceability, draft_meta, quality_score
    )
    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="produce",
        step="review",
        ref=ref,
        passed=decision == "approved",
        issues=blocking,
        evidence_summary={"qualityScore": quality_score, "generator": compose_payload.get("generator")},
        next_step="materialize" if decision == "approved" else None,
        fallback_stage=_review_fallback_stage(route_checks) if decision != "approved" else None,
    )
    if decision != "approved":
        fallback = _review_fallback_stage(route_checks)
        if fallback == "download":
            rerun_chain = ["download", "quality_analysis", "compose-brief", "review", "materialize"]
        elif fallback == "agent_compose":
            rerun_chain = ["agent_compose", "review", "materialize"]
        else:
            rerun_chain = [fallback, "review", "materialize"]
        write_repair_report(
            task_id=task_id,
            batch_id=batch_id,
            command="produce",
            ref=ref,
            failed_stage="review",
            failed_gate="contentReview",
            issues=blocking,
            fallback_stage=fallback,
            rerun_chain=rerun_chain,
        )
    return payload


def _persisted_review_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks") or {}
    return {
        "topicId": payload.get("topicId"),
        "decision": payload.get("decision"),
        "issues": list(payload.get("issues") or []),
        "humanReviewRequired": bool(payload.get("humanReviewRequired")),
        "generator": payload.get("generator"),
        "checks": {name: {"passed": bool(result.get("passed"))} for name, result in checks.items()},
    }


def _score_from_quality(quality_score: float) -> int:
    if quality_score >= 85:
        return 5
    if quality_score >= 75:
        return 4
    if quality_score >= 60:
        return 3
    return 2


def _persist_review_ledger(
    task_id: str,
    batch_id: str,
    ref: str,
    brief: Mapping[str, Any],
    compose_payload: Mapping[str, Any],
    route_checks: Mapping[str, Mapping[str, Any]],
    traceability: Sequence[str],
    draft_meta: Mapping[str, Any] | None,
    quality_score: float,
) -> None:
    """构建并落 human-in-loop 账本 + 实体 sidecar（agent 判定来源）。"""
    policy = load_policy(task_id, batch_id)

    # 文章项：非图片质量门是否全过（图片/事实另列项）。
    narrative_passed = all(
        v.get("passed", True)
        for k, v in route_checks.items()
        if k not in ("imageGate", "factTraceability")
    )
    article_item = agent_article_item(ref, passed=narrative_passed, score=_score_from_quality(quality_score))

    # 图片项：逐图 image_safety verdict → agent 判定/打分。
    image_items: list[ReviewItem] = []
    assets = [a for a in (compose_payload.get("assets") or []) if a.get("sourcePath")]
    if assets:
        report = assess_asset_sources(assets)
        for v in report.get("verdicts", []):
            asset_id = str(v.get("assetId") or "")
            if asset_id:
                image_items.append(agent_image_item(asset_id, v))

    # 事实项：mustIncludeFacts 是否可回溯（traceability 中命中即存疑）。
    fact_items: list[ReviewItem] = []
    must_facts = []
    spine = compose_payload.get("storySpine") or {}
    if isinstance(spine, Mapping):
        must_facts = list(spine.get("mustIncludeFacts") or [])
    trace_blob = " ".join(traceability)
    for fact in must_facts:
        fact_items.append(agent_fact_item(str(fact), traceable=str(fact) not in trace_blob))

    ledger = ReviewLedger(
        taskId=task_id,
        batchId=batch_id,
        ref=ref,
        policy=policy,
        article=article_item,
        images=image_items,
        facts=fact_items,
    )
    # 合并已存在的人判定（annotate 写过的 human* 不被 review 覆盖）。
    _merge_human_decisions(task_id, batch_id, ref, ledger)
    save_ledger(ledger)

    build_entities_sidecar(task_id, batch_id, ref, draft_meta)


def _merge_human_decisions(task_id: str, batch_id: str, ref: str, ledger: ReviewLedger) -> None:
    from _common.review_ledger import load_ledger

    prev = load_ledger(task_id, batch_id, ref)
    if prev is None:
        return
    for item in ledger.all_items():
        old = prev.find_item(item.kind, item.target)
        if old is None:
            continue
        item.humanJudgment = old.humanJudgment
        item.humanScore = old.humanScore
        item.humanOverride = old.humanOverride
        item.reprocessCount = old.reprocessCount


def _route_review_checks(
    article: str,
    brief: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
    compose_payload: Mapping[str, Any],
    *,
    task_id: str = "",
    batch_id: str = "",
    ref: str = "",
    draft_meta: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    carrier = str(compose_payload.get("carrier") or "article")
    if carrier == "gallery":
        # 画报载体以图为主、配小字：只校验体裁/图片/资源，不套长文叙事门。
        return {
            "carrierConsistency": _check_carrier_consistency(compose_payload),
            "imageGate": _check_image_gate(compose_payload),
            "galleryCaption": _check_gallery_caption(article, brief, quality_payload),
        }
    style_family, opening_strategy = _resolve_style_opening(brief, draft_meta)
    checks = {
        "routeCoverage": _check_route_coverage(article, brief, evidence_bundle),
        "narrativeContinuity": _check_narrative_continuity(article, brief, evidence_bundle),
        "provenanceRewrite": _check_provenance_rewrite(article, brief, quality_payload),
        "evidenceQuality": _check_evidence_quality(article, brief, quality_payload, compose_payload),
        "travelogueDensity": _check_travelogue_density(
            article, brief, style_family=style_family, opening_strategy=opening_strategy
        ),
        "crossArticleSimilarity": _check_cross_article_similarity(task_id, batch_id, ref, article),
        "carrierConsistency": _check_carrier_consistency(compose_payload),
        "mixedLayout": _check_mixed_layout(article),
        "proseStyle": _check_prose_style(article),
        "imageGate": _check_image_gate(compose_payload),
    }
    return checks


def _check_prose_style(article: str) -> dict[str, Any]:
    """文风门：禁止机械化固定收尾小标题（它到底适合谁 等）。"""
    from _common.prose_style import mechanical_ending_title_issues

    issues = mechanical_ending_title_issues(article)
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["把取舍判断自然融入叙述收尾，删除『适合谁』之类固定小标题。"] if issues else [],
    }


def _check_mixed_layout(article: str) -> dict[str, Any]:
    """图文混合编排门（仅当正文内嵌 >=2 个 :::figure 时生效）：

    - 禁止空 figure 块；
    - 图片需跨小节分布（不得全部挤在正文前 40%）；
    - 图片之间/前后不得有过大纯文字空档（> 1200 字无配图，提示拆图或转 gallery）。
    单图或无内嵌图的文章（仅封面）不受约束。
    """
    blocks = list(re.finditer(r"(?ms)^:::figure\n(.*?)\n:::", article))
    issues: list[str] = []
    if len(blocks) < 2:
        return {"passed": True, "issues": [], "suggestions": []}

    for b in blocks:
        inner = b.group(1)
        if not re.search(r"!\[[^\]]*\]\(asset://[^)]+\)", inner):
            issues.append("empty/invalid figure block")

    total = len(article)
    positions = [b.start() / total for b in blocks if total]
    if positions and all(p < 0.4 for p in positions):
        issues.append("figures all clustered in first 40% (intersperse across sections)")

    # 过大纯文字空档：相邻图片（含首尾）之间正文字数 > 1200
    anchors = [0] + [b.end() for b in blocks] + [total]
    starts = [0] + [b.start() for b in blocks]
    for s, e in zip(anchors[:-1], starts[1:] + [total]):
        gap = re.sub(r"\s+", "", article[s:e])
        if len(gap) > 1200:
            issues.append(f"large text gap without figure ({len(gap)} chars)")
            break

    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["图文混合：figure 跨小节穿插、避免大段无图空档、去掉空图块；图多则转 gallery 配小字。"]
        if issues
        else [],
    }


def _check_gallery_caption(
    article: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """画报小字门：每个 figure 配文不超长、无平台来源口吻、无整句搬运。"""
    issues: list[str] = []
    caption_max = int((brief.get("imagePolicy") or {}).get("captionMaxChars") or 24)
    # 配文 = figure 块内既非围栏、又非图片标记的正文行。
    texts: list[str] = []
    for block in re.findall(r"(?ms)^:::figure\n(.*?)\n:::", article):
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("!", "#", ">", ":::")):
                continue
            texts.append(stripped)
    for cap in texts:
        compact = re.sub(r"\s+", "", cap)
        if len(compact) > caption_max:
            issues.append(f"caption too long ({len(compact)} > {caption_max}): {cap[:20]}")
    if any(term in article for term in PROVENANCE_TERMS):
        issues.append("contains provenance/platform wording")
    source_texts = _load_source_texts(quality_payload.get("sourcePaths") or [])
    for hit in _long_phrase_hits(article, source_texts):
        issues.append(f"too similar to source phrase '{hit}'")
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["画报配文保持简短，避免平台口吻与整句搬运。"] if issues else [],
    }


def _check_carrier_consistency(compose_payload: Mapping[str, Any]) -> dict[str, Any]:
    """体裁一致性：article 必须像长文（多小节正文），gallery 必须像图集（多图块）。"""
    carrier = str(compose_payload.get("carrier") or "article")
    article = str(compose_payload.get("articleMarkdown") or "")
    issues: list[str] = []
    if carrier == "gallery":
        if article.count(":::figure") < 3:
            issues.append("gallery carrier lacks figure blocks")
    else:
        if len(re.findall(r"(?m)^##\s", article)) < 3:
            issues.append("article carrier lacks prose sections (looks like a gallery)")
        if article.count(":::figure") and len(re.sub(r"\s+", "", article)) < 600:
            issues.append("article carrier is image-only; route to gallery instead")
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["按载体定位组织内容：长文走分节叙事，图集走画报配小字。"] if issues else [],
    }


def _check_image_gate(compose_payload: Mapping[str, Any]) -> dict[str, Any]:
    """图片门并入裁决：unsafe/重复 -> 阻断改稿；含人脸/后端缺失 -> 标记人工复核。"""
    from _common.image_safety import assess_asset_sources

    assets = [a for a in (compose_payload.get("assets") or []) if a.get("sourcePath")]
    if not assets:
        return {"passed": False, "issues": ["no verifiable image assets"], "humanReview": False, "suggestions": ["补充可校验的图片资源。"]}
    report = assess_asset_sources(assets)
    issues: list[str] = []
    for asset_id in report["unsafe"]:
        issues.append(f"unsafe image (watermark/platform/copyright): {asset_id}")
    if report["duplicateGroups"]:
        issues.append(f"{len(report['duplicateGroups'])} duplicate image group(s)")
    # 含人脸/后端缺失 → 记账本存疑、转 human-in-loop（不硬阻断 review，留待发布门 + annotate）。
    human_review = bool(report["needsReview"])
    notes = [f"image needs human review (face/backend): {a}" for a in report["needsReview"]]
    return {
        "passed": not issues,
        "issues": issues,
        "humanReview": human_review,
        "humanReviewTargets": list(report["needsReview"]),
        "notes": notes,
        "suggestions": ["替换带水印/平台文字的图片；含人脸的图片转人工复核（写入账本）。"]
        if (issues or human_review)
        else [],
    }


def _opening_paragraph(article: str) -> str:
    body = re.split(r"(?m)^##\s", article, maxsplit=1)[0]
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip() and not p.lstrip().startswith(("#", ">", ":::"))]
    return paragraphs[0] if paragraphs else ""


def _check_travelogue_density(
    article: str,
    brief: Mapping[str, Any],
    *,
    style_family: str = "",
    opening_strategy: str = "",
) -> dict[str, Any]:
    """游记感密度门：开篇钩子（按所选体裁多策略，破"千篇一律"）+ 显式喜欢/不喜欢 + 取舍判断 + 注意事项就地融入。

    开篇不再强制单一"出发动机"：按 styleFamily 的 allowedOpenings 用 detect_opening_strategy 语义化校验，
    开篇须真正落地该体裁允许的任一开篇策略；若 draft_meta 声明了 openingStrategy，正文开篇须与之一致（诚信）。
    无 styleFamily 时使用默认 allowedOpenings 规则。
    """
    issues: list[str] = []
    opening_required = bool((brief.get("openingTension") or {}).get("required", True))
    feelings = brief.get("explicitFeelings") or {"requireLike": True, "requireDislike": True}
    decision = brief.get("decisionPoints") or {"required": True, "minPoints": 2}
    tips_policy = brief.get("tipsEmbeddingPolicy") or {"forbidStandaloneBlock": True}

    opening = _opening_paragraph(article)
    if opening_required:
        detected = detect_opening_strategy(opening, style_family)
        if detected is None:
            allowed = family_allowed_openings(style_family)
            issues.append(
                f"opening lacks a real hook for styleFamily '{style_family or 'default'}'; "
                f"adopt one of {allowed} (现为套路化/千篇一律开头)"
            )
        elif opening_strategy and opening_strategy != detected:
            issues.append(
                f"declared openingStrategy '{opening_strategy}' not reflected in opening (detected '{detected}')"
            )
    if feelings.get("requireLike", True) and not any(m in article for m in LIKE_FEELING_MARKERS):
        issues.append("missing explicit positive feeling (like)")
    if feelings.get("requireDislike", True) and not any(m in article for m in DISLIKE_FEELING_MARKERS):
        issues.append("missing explicit negative feeling (dislike)")
    min_points = int(decision.get("minPoints", 2))
    decision_hits = sum(article.count(m) for m in DECISION_MARKERS)
    if decision.get("required", True) and decision_hits < min_points:
        issues.append(f"too few decision points ({decision_hits} < {min_points})")
    if tips_policy.get("forbidStandaloneBlock", True):
        for marker in STANDALONE_TIPS_MARKERS:
            if marker in article:
                issues.append(f"tips dumped as standalone block ('{marker}'), embed inline instead")
                break
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["开篇换用所选体裁的真实钩子，正文写清喜欢与不喜欢，注意事项就地融入而非另起清单。"] if issues else [],
    }


def _resolve_style_opening(brief: Mapping[str, Any], draft_meta: Mapping[str, Any] | None) -> tuple[str, str]:
    """最终 styleFamily（agent 自选优先于 blueprint 默认）与所声明的 openingStrategy。"""
    meta = draft_meta or {}
    style_family = str(meta.get("styleFamily") or brief.get("styleFamily") or "")
    opening_strategy = str(meta.get("openingStrategy") or "")
    return style_family, opening_strategy


def _check_cross_article_similarity(
    task_id: str,
    batch_id: str,
    ref: str,
    article: str,
    *,
    threshold: float = 0.65,
) -> dict[str, Any]:
    """跨篇相似度门（破量产"千篇一律"）：本篇开篇若与同批其他文章开篇字符级 jaccard 过高则判 revision。

    专治"X 的水/风景，我在屏幕上看了无数遍，总怕亲眼一看会不过如此"这类换实体名不换句式的批量套路开头。
    """
    opening = _opening_paragraph(article)
    if not opening:
        return {"passed": True, "issues": [], "suggestions": []}
    issues: list[str] = []
    for other_ref, other in iter_draft_articles(task_id, batch_id):
        if other_ref == ref:
            continue
        try:
            other_text = other.read_text(encoding="utf-8")
        except OSError:
            continue
        if PLACEHOLDER_MARKER in other_text:
            continue
        other_opening = _opening_paragraph(other_text)
        if not other_opening:
            continue
        sim = _jaccard(opening, other_opening)
        if sim > threshold:
            issues.append(f"opening too similar to sibling '{other_ref}' (jaccard={sim:.2f})")
            break
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["换一种开篇策略/切入角度，避免与同批文章雷同（同质开头会被批量识别）。"] if issues else [],
    }


def _check_route_coverage(
    article: str,
    brief: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    route_nodes = evidence_bundle.get("routeNodes") or []
    min_covered = int((brief.get("routeCoverageExpectations") or {}).get("minCoveredEntityRefs") or max(1, min(len(route_nodes), 2)))
    mentioned = [node["entityName"] for node in route_nodes if node.get("entityName") and node["entityName"] in article]
    issues: list[str] = []
    if len(mentioned) < min_covered:
        issues.append(f"only mentions {len(mentioned)} route nodes (need >= {min_covered})")
    progression = [node["entityName"] for node in route_nodes if node.get("entityName")]
    if progression:
        positions = [article.find(name) for name in progression if name in article]
        if positions and positions != sorted(positions):
            issues.append("route node order is out of progression")
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["按主线顺序补足缺失节点，避免只写首实体。"] if issues else [],
    }


def _check_narrative_continuity(
    article: str,
    brief: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []
    headings = re.findall(r"(?m)^##\s+(.+)$", article)
    required_headings = [str(item) for item in (brief.get("structure") or {}).get("required") or []]
    same_required = sum(1 for heading in headings if heading in required_headings)
    if required_headings and same_required >= max(3, len(required_headings) - 1):
        issues.append("headings still mirror structure.required slots")
    if sum(article.count(term) for term in TRANSITION_TERMS) < 2:
        issues.append("missing route progression transitions")
    paragraphs = [p.strip() for p in article.split("\n\n") if p.strip()]
    min_paragraphs = int((brief.get("continuityExpectations") or {}).get("minNarrativeParagraphs") or 4)
    if len(paragraphs) < min_paragraphs:
        issues.append(f"too few narrative paragraphs ({len(paragraphs)} < {min_paragraphs})")
    bodies = _section_bodies(article)
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            if _jaccard(bodies[i], bodies[j]) > 0.72:
                issues.append(f"sections {i+1} and {j+1} too similar")
                break
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["改用主线推进和转场过渡组织正文，不要按固定槽位平铺。"] if issues else [],
    }


def _check_provenance_rewrite(
    article: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
) -> dict[str, Any]:
    issues = check_narrative_quality(article, {"template": brief.get("templateId")})
    if any(term in article for term in PROVENANCE_TERMS):
        issues.append("contains provenance/platform wording")
    source_texts: list[str] = []
    for path in quality_payload.get("sourcePaths") or []:
        candidate = Path(path)
        if candidate.is_file():
            source_texts.append(candidate.read_text(encoding="utf-8"))
    hits = _long_phrase_hits(article, source_texts)
    for hit in hits:
        issues.append(f"too similar to source phrase '{hit}'")
    temp_dir = Path("/tmp") / "qwq_route_review"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_article = temp_dir / f"{quality_payload.get('topicId', 'route')}.md"
    temp_article.write_text(article, encoding="utf-8")
    for issue in check_provenance(temp_article):
        if issue not in issues:
            issues.append(issue)
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["继续改写来源痕迹明显的句子，避免平台口吻和整句搬运。"] if issues else [],
    }


def _check_evidence_quality(
    article: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
    compose_payload: Mapping[str, Any],
) -> dict[str, Any]:
    issues = list(gate_route_evidence_bundle(brief, quality_payload.get("evidenceBundle") or {}))
    recommendation = str(quality_payload.get("recommendation") or "")
    if recommendation == "skip":
        issues.append("quality analysis marked this route as skip")
    if not compose_payload.get("assets"):
        issues.append("compose payload missing assets")
    for fact in [str(item) for item in brief.get("mustIncludeFacts") or [] if item]:
        if not _fact_in_article(article, fact):
            issues.append(f"mustIncludeFact missing in article: {fact}")
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["返回 download/source_screen 补强线路证据，再重新创作。"] if issues else [],
    }


def _review_fallback_stage(checks: Mapping[str, Mapping[str, Any]]) -> str:
    if not checks.get("generatorProvenance", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks["evidenceQuality"]["passed"]:
        return "download"
    if not checks.get("factTraceability", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("baseDraftFidelity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks["provenanceRewrite"]["passed"]:
        return "agent_compose"
    if not checks["routeCoverage"]["passed"]:
        return "agent_compose"
    if not checks.get("travelogueDensity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("crossArticleSimilarity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("mixedLayout", {"passed": True})["passed"]:
        return "agent_compose"
    image_gate = checks.get("imageGate", {"passed": True})
    if not image_gate["passed"]:
        return "agent_compose"
    if not checks.get("carrierConsistency", {"passed": True})["passed"]:
        return "agent_compose"
    return "review"


def _publish_angle(brief: Mapping[str, Any]) -> str:
    """由 templateId 确定性映射 publish 目录 angle（与 tagRefs Format/内容角度 对齐）。"""
    template_id = str(brief.get("templateId") or "")
    if "跟团" in template_id:
        return "跟团攻略"
    if "自驾" in template_id:
        return "自驾路书"
    if "深度" in template_id:
        return "深度探险"
    if "枢纽" in template_id:
        return "枢纽到达"
    if "省钱" in template_id:
        return "省钱攻略"
    if "周末短途" in template_id or "银发" in template_id or "补给" in template_id:
        # 一日游/周边/短线：落「攻略」层（见 test_post_dir_layout 都江堰一日游）
        return "攻略"
    if "环线" in template_id:
        return "环线攻略"
    return "攻略"


def _entity_image_candidates(
    task_id: str, batch_id: str, name: str, entity_ref: str = ""
) -> list[dict[str, Any]]:
    """实体可选图候选（新布局：来源单元 assets/）。

    每项 {path, sourceRef, sourceAssetRef}（后两者为相对 batch 根路径，构成证据链）。
    """
    from _common.source_unit import (
        find_entity_object_dirs,
        object_image_candidates,
        resolve_entity_object_dir,
    )

    cands: list[dict[str, Any]] = []
    if entity_ref:
        cands = object_image_candidates(
            resolve_entity_object_dir(task_id, batch_id, entity_ref), task_id, batch_id
        )
    if not cands:
        for obj in find_entity_object_dirs(task_id, batch_id, name):
            cands.extend(object_image_candidates(obj, task_id, batch_id))
    if cands:
        return cands
    return []


def _pick_safe_image(candidates: Sequence[Mapping[str, Any]], chosen: Sequence[Path]):
    """挑出 safe（非 unsafe）且与已选不近重复的第一张，杜绝同源复用。返回 (candidate, verdict)。"""
    fallback = None
    for cand in candidates:
        path = cand["path"]
        if any(is_near_duplicate(path, picked) for picked in chosen):
            continue
        verdict = assess_image(path)
        if verdict.status == STATUS_UNSAFE:
            continue
        if fallback is None:
            fallback = (cand, verdict)
        if verdict.status != "needs_review":
            return cand, verdict
    return fallback


def _image_plan_layouts(image_plan: Sequence[Mapping[str, Any]]) -> list[str]:
    layouts: list[str] = []
    for slot in image_plan:
        if slot.get("gallery"):
            layouts.append("gallery")
        else:
            layouts.append(str(slot.get("imageLayout") or "wrapRight"))
    return layouts


def _node_layout(layouts: Sequence[str], position: int) -> str:
    """节点版面职责：优先取 imagePlan 非首槽，缺失时 wrapRight/wrapLeft/gallery 交替，避免统一降级。"""
    non_cover = layouts[1:] if len(layouts) > 1 else []
    if non_cover:
        return non_cover[position % len(non_cover)]
    return ("wrapRight", "wrapLeft", "gallery")[position % 3]


def _make_asset(
    ref: str,
    *,
    role: str,
    candidate: Mapping[str, Any],
    layout: str,
    caption: str,
    entity_name: str,
    global_batch_seq: int,
    asset_registry: BatchAssetRegistry,
    verdict=None,
) -> dict[str, Any]:
    path = candidate["path"]
    # 成品资产文件名即 assetId（可由 article.md 的 asset:// 直查文件，无需翻 manifest）。
    asset_id = allocate_post_asset_id(
        entity_name=entity_name,
        role=role,
        ref=ref,
        global_batch_seq=global_batch_seq,
        registry=asset_registry,
    )
    ext = path.suffix.lower() or ".jpg"
    asset = {
        "assetId": asset_id,
        "fileName": f"{asset_id}{ext}",
        "caption": caption,
        "kind": "image",
        "scope": "cold_start",
        "role": role,
        "entityName": entity_name,
        "objectKey": "",
        "sourcePath": str(path),
        # 证据链：source 原图 + 原文（相对 batch 根；materialize 直接写入 manifest）。
        "sourceAssetRef": str(candidate.get("sourceAssetRef") or ""),
        "sourceRef": str(candidate.get("sourceRef") or ""),
        "imageLayout": layout,
    }
    if verdict is not None:
        asset["imageStatus"] = verdict.status
        asset["textAreaRatio"] = round(verdict.text_area_ratio, 4)
        asset["isTextHeavy"] = bool(verdict.is_text_heavy)
    return asset


def _build_route_assets(
    task_id: str,
    batch_id: str,
    ref: str,
    brief: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """选图：cover/node/closing 三类职责，节点图绑定各自实体，跨实体感知去重，跳过 unsafe。"""
    image_plan = list(brief.get("imagePlan") or [])
    manifest = load_batch_manifest(task_id, batch_id)
    global_batch_seq = int(brief.get("globalBatchSeq") or manifest.get("globalBatchSeq") or 0)
    if global_batch_seq <= 0:
        raise RuntimeError(f"missing globalBatchSeq for task={task_id} batch={batch_id}")
    asset_registry = load_batch_asset_registry(task_id, batch_id, global_batch_seq)
    layouts = _image_plan_layouts(image_plan)
    route_nodes = [node for node in (evidence_bundle.get("routeNodes") or []) if node.get("entityName")]
    entity_names = [str(node["entityName"]) for node in route_nodes]
    if not entity_names:
        return []
    ref_by_name = {str(node["entityName"]): str(node.get("entityRef") or "") for node in route_nodes}

    per_entity = {
        name: _entity_image_candidates(task_id, batch_id, name, ref_by_name.get(name, ""))
        for name in dict.fromkeys(entity_names)
    }

    assets: list[dict[str, Any]] = []
    chosen: list[Path] = []

    cover_layout = layouts[0] if layouts else "fullWidth"
    cover_pool = per_entity.get(entity_names[0]) or []
    cover = _pick_safe_image(cover_pool, chosen)
    if cover is not None:
        chosen.append(cover[0]["path"])
        assets.append(
            _make_asset(
                ref,
                role="cover",
                candidate=cover[0],
                layout=cover_layout,
                caption=entity_names[0],
                entity_name=entity_names[0],
                global_batch_seq=global_batch_seq,
                asset_registry=asset_registry,
                verdict=cover[1],
            )
        )

    for position, name in enumerate(entity_names):
        node_image = _pick_safe_image(per_entity.get(name) or [], chosen)
        if node_image is None:
            continue
        chosen.append(node_image[0]["path"])
        assets.append(
            _make_asset(
                ref,
                role="node",
                candidate=node_image[0],
                layout=_node_layout(layouts, position),
                caption=name,
                entity_name=name,
                global_batch_seq=global_batch_seq,
                asset_registry=asset_registry,
                verdict=node_image[1],
            )
        )

    closing_pool = per_entity.get(entity_names[-1]) or []
    closing = _pick_safe_image(closing_pool, chosen)
    if closing is not None:
        chosen.append(closing[0]["path"])
        assets.append(
            _make_asset(
                ref,
                role="closing",
                candidate=closing[0],
                layout="fullWidth",
                caption=f"{entity_names[-1]}·回望",
                entity_name=entity_names[-1],
                global_batch_seq=global_batch_seq,
                asset_registry=asset_registry,
                verdict=closing[1],
            )
        )

    return assets


GALLERY_MIN_IMAGES = 4
LOW_NARRATIVE_SIGNALS = 6


def _narrative_volume(evidence_bundle: Mapping[str, Any]) -> int:
    nodes = evidence_bundle.get("routeNodes") or []
    total = 0
    for node in nodes:
        total += len([x for x in (node.get("mainlineEvidence") or []) if x])
        emotion = node.get("emotionEvidence") or {}
        total += len(emotion.get("likes") or []) + len(emotion.get("painPoints") or [])
    return total


def resolve_carrier(brief: Mapping[str, Any], evidence_bundle: Mapping[str, Any], assets: Sequence[Mapping[str, Any]]) -> str:
    """载体路由：图带交叠文字 -> article；显式 gallery 或图多文少 -> gallery；否则 article。"""
    if any(asset.get("isTextHeavy") for asset in assets):
        return "article"
    declared = str(brief.get("carrier") or "").lower()
    if declared == "gallery":
        return "gallery"
    if declared and declared != "gallery":
        return "article"
    policy = brief.get("imagePolicy") or {}
    min_images = int(policy.get("minImages") or GALLERY_MIN_IMAGES)
    safe_imgs = [a for a in assets if a.get("imageStatus", "safe") in ("safe", "text_heavy")]
    if len(safe_imgs) >= min_images and _narrative_volume(evidence_bundle) <= LOW_NARRATIVE_SIGNALS:
        return "gallery"
    return "article"


def _build_summary(article: str) -> str:
    compact = re.sub(r"\s+", " ", article).strip()
    return compact[:160]


def _section_bodies(article: str) -> list[str]:
    parts = re.split(r"\n## ", article)
    bodies: list[str] = []
    for part in parts[1:]:
        lines = part.split("\n", 1)
        body = lines[1] if len(lines) > 1 else ""
        body = re.sub(r":::figure[\s\S]*?:::", "", body)
        body = re.sub(r"\s+", " ", body).strip()
        if len(body) > 40:
            bodies.append(body)
    return bodies


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _fact_in_article(article: str, fact: str) -> bool:
    if fact in article:
        return True
    return fact_covered(fact, article)


def _unique_strings(values: Sequence[str] | Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


__all__ = [
    "ROUTE_TEMPLATE_IDS",
    "analyze_route_ref",
    "build_route_writing_pack",
    "is_route_brief",
    "iter_route_briefs",
    "load_compose_brief",
    "resolve_carrier",
    "review_route_draft",
]
