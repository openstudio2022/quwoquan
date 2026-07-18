"""Review gates and human-review ledger persistence for route production."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from core.data_issue import DataIssueCode, DataIssueStage, DataRecoveryAction, data_issues
from content.post.article.evidence_bundle import gate_route_evidence_bundle
from content.post.content_review import (
    check_narrative_quality,
    check_provenance,
    fact_traceability_issues,
    generator_provenance_issues,
)
from core.creative_brief import creative_governance_issues
from content.post.article.draft_io import (
    PLACEHOLDER_MARKER,
    draft_asset_reference_issues,
    iter_draft_articles,
    is_placeholder,
    read_draft_article,
    read_draft_meta,
    read_writing_pack,
    repair_creative_meta,
)
from governance.coverage.entity_extract import build_entities_sidecar
from core.image_safety import assess_asset_sources
from content.review.ledger import (
    ReviewItem,
    ReviewLedger,
    agent_article_item,
    agent_fact_item,
    agent_image_item,
    load_policy,
    save_ledger,
)
from content.execution.stage_reports import write_gate_report, write_repair_report, write_stage_result
from core.style_catalog import detect_opening_strategy, family_allowed_openings
from core.template_fingerprints import template_fingerprint_issues
from content.post.article.route_compose import (
    _compose_payload_from_pack,
    _image_source_paths_from_assets,
    _source_ref_from_asset_path,
)
from content.post.article.route_core import (
    DECISION_MARKERS,
    DISLIKE_FEELING_MARKERS,
    LIKE_FEELING_MARKERS,
    PROVENANCE_TERMS,
    STANDALONE_TIPS_MARKERS,
    TRANSITION_TERMS,
    aggregate_checks,
    _build_summary,
    _compact_public_text,
    _fact_in_article,
    _image_caption_from_article,
    _jaccard,
    _section_bodies,
    _unique_strings,
)
from content.post.article.route_review_checks import (
    _review_fallback_stage,
    _route_review_checks,
)

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
    execution_id: str,
    ref: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_bundle = quality_payload.get("evidenceBundle") or {}
    pack = read_writing_pack(execution_id, ref) or {}
    article = read_draft_article(execution_id, ref)
    # 创作后校验补全（fix A）：creativePlan/selfCritique 结构化字段按 creativeBrief 预置补全，
    # 让正文已达标的稿件有可靠成稿路径，不再被 creativeGovernance 硬拦。仅补元数据，不动正文。
    draft_meta = repair_creative_meta(execution_id, ref) or read_draft_meta(execution_id, ref)
    carrier_hint = str(pack.get("carrier") or brief.get("carrier") or "article")
    is_image_carrier = carrier_hint == "image"

    # 出处 + 占位门：文章未由 agent 创作直接判 revision_needed。图片作品是结构化
    # sourceCollection/assets/caption，不生成正文，不走 draft.article.md 门。
    authenticity_issues: list[str] = []
    if not is_image_carrier and is_placeholder(article):
        authenticity_issues.append("draft not composed yet (placeholder); awaiting agent article")
    if not is_image_carrier:
        authenticity_issues.extend(generator_provenance_issues(draft_meta))
    body = "" if is_image_carrier or is_placeholder(article) else str(article)
    if not is_image_carrier:
        authenticity_issues.extend(template_fingerprint_issues(body))
        authenticity_issues.extend(draft_asset_reference_issues(body, pack))
    source_texts = _load_source_texts(quality_payload.get("sourcePaths") or [])
    traceability = [] if is_image_carrier else fact_traceability_issues(body, dict(brief), source_texts)

    compose_payload = _compose_payload_from_pack(ref, brief, quality_payload, pack, body, draft_meta)
    carrier = str(compose_payload.get("carrier") or brief.get("carrier") or "article")
    write_stage_result(execution_id, "post", "compose", ref, compose_payload)

    route_checks = _route_review_checks(
        body,
        brief,
        evidence_bundle,
        quality_payload,
        compose_payload,
        execution_id=execution_id,
        ref=ref,
        draft_meta=draft_meta,
    )
    route_checks["generatorProvenance"] = {
        "passed": not authenticity_issues,
        "issues": authenticity_issues,
        "suggestions": ["按 prompt.md 由创作 agent创作正文并写回对象 `4.draft/draft.article.md`（generator=agent）。"] if authenticity_issues else [],
    }
    route_checks["factTraceability"] = {
        "passed": not traceability,
        "issues": traceability,
        "suggestions": ["补齐 mustIncludeFacts，并确保票价/海拔/时长等数字能在 source 证据中找到。"] if traceability else [],
    }
    from content.post.article.base_draft import (
        load_base_draft_text,
    )
    from content.post.article.base_draft_source import base_source_use_mode
    from content.post.fidelity import base_draft_fidelity_issues

    if carrier == "image":
        fidelity = []
    else:
        # 底稿中心 1:1：门侧分母 = 整篇单一底稿（与 prompt 侧 baseDraftText 同源）。
        # 不再按 writingIntent 收窄分母——成品本就只来自这一篇底稿，整篇度量才能既防误杀
        # （多主题游记不再因离题段落拉低 fidelity）又防逐字照搬（高相似仍触顶）。
        base_text = load_base_draft_text(execution_id, brief.get("baseSourceRef"))
        source_use_mode = base_source_use_mode(execution_id, brief.get("baseSourceRef"))
        fidelity = base_draft_fidelity_issues(
            body,
            base_text,
            carrier=carrier,
            source_use_mode=source_use_mode,
        )
    if carrier == "image":
        figure_group_issues: list[str] = []
    else:
        from core.figure_groups import figure_group_integrity_issues

        # 连续图组带回完整性（P2 / R-CS10）：底稿里出现的 figuregroup，创作 agent 成稿必须按原
        # id/张数原样带回，禁止丢图/拆成多个单图/篡改组内 assetId（图文混排丢失直接回归防线）。
        # 必须对【原始 body】判（含 figuregroup 占位），不能对剥图后的文本判；底稿与 fidelity 同源。
        figure_group_issues = figure_group_integrity_issues(body, base_text)
    route_checks["figureGroupIntegrity"] = {
        "passed": not figure_group_issues,
        "issues": figure_group_issues,
        "suggestions": ["把底稿里的 :::figuregroup 连续图组占位按原 id 与组内 assetId 原样带回，勿丢图/拆图。"]
        if figure_group_issues
        else [],
    }
    route_checks["baseDraftFidelity"] = {
        "passed": not fidelity,
        "issues": fidelity,
        "suggestions": ["以底稿为基础适度加工：相似度过低则贴回底稿叙事；过高则进一步改写表达、去版权痕迹。"] if fidelity else [],
    }
    from core import quality_gates as qg

    # 结构形态硬门（与来源数量无关，低误报）：单章节过半失衡 + 平行时间线拼接未归并。
    sb_issues = [] if carrier == "image" else qg.section_balance_issues(
        body, max_ratio=qg.SECTION_BALANCE_MAX_RATIO_ARTICLE
    )
    route_checks["sectionBalance"] = {
        "passed": not sb_issues,
        "issues": sb_issues,
        "suggestions": ["压缩或拆分过长章节，避免一段吞并其余应有章节；按 writingIntent 均衡分配篇幅。"] if sb_issues else [],
    }
    tl_issues = [] if carrier == "image" else qg.timeline_monotonicity_issues(body)
    route_checks["timelineOrder"] = {
        "passed": not tl_issues,
        "issues": tl_issues,
        "suggestions": ["把同章节内并列时间线按真实时间顺序归并为单一连贯叙事，禁止首尾拼接造成时间倒错。"] if tl_issues else [],
    }
    wi_issues = [] if carrier == "image" else qg.writing_intent_consistency_issues(body, brief.get("writingIntent"))
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
        "suggestions": ["改用该垂类合适的语域（如户外景区禁'看展/展厅/展陈'），由垂类规则词表约束。"] if reg_issues else [],
    }
    from core import public_contacts as pc

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
    creative_issues = [] if carrier == "image" else creative_governance_issues(body, pack, draft_meta)
    route_checks["creativeGovernance"] = {
        "passed": not creative_issues,
        "issues": creative_issues,
        "suggestions": [
            "按 creativeBrief 先形成 2-3 个构思，选择最能兑现 readerPromise 的结构；"
            "修正文案时只在 evidence 边界内发挥，不伪装真实亲历，并把 creativePlan/selfCritique 写入 draft_meta。"
        ] if creative_issues else [],
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
    write_stage_result(execution_id, "post", "review", ref, _persisted_review_payload(payload))
    _persist_review_ledger(
        execution_id, ref, brief, compose_payload, route_checks, traceability, draft_meta, quality_score
    )
    fallback = _review_fallback_stage(route_checks) if decision != "approved" else None
    issue_code = DataIssueCode.SOURCE_MISSING if fallback == "download" else DataIssueCode.QUALITY_FAILED
    recovery = (
        DataRecoveryAction.REWIND_DOWNLOAD
        if fallback == "download"
        else DataRecoveryAction.REWIND_COMPOSE
    )
    typed_blocking = data_issues(
        issue_code,
        stage=DataIssueStage.REVIEW,
        ref=ref,
        messages=blocking,
        recovery=recovery,
    )
    write_gate_report(
        execution_id=execution_id,
        command="post",
        step="review",
        ref=ref,
        passed=decision == "approved",
        issues=typed_blocking,
        evidence_summary={"qualityScore": quality_score, "generator": compose_payload.get("generator")},
        next_step="materialize" if decision == "approved" else None,
    )
    if decision != "approved":
        assert fallback is not None
        if fallback == "download":
            rerun_chain = ["download", "quality_analysis", "compose-brief", "review", "materialize"]
        elif fallback == "agent_compose":
            rerun_chain = ["agent_compose", "review", "materialize"]
        else:
            rerun_chain = [fallback, "review", "materialize"]
        write_repair_report(
            execution_id=execution_id,
            command="post",
            ref=ref,
            failed_stage=DataIssueStage.REVIEW,
            failed_gate="contentReview",
            issues=typed_blocking,
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
    execution_id: str,
    ref: str,
    brief: Mapping[str, Any],
    compose_payload: Mapping[str, Any],
    route_checks: Mapping[str, Mapping[str, Any]],
    traceability: Sequence[str],
    draft_meta: Mapping[str, Any] | None,
    quality_score: float,
) -> None:
    """构建并落 human-in-loop 账本 + 实体 sidecar（agent 判定来源）。"""
    policy = load_policy(execution_id)

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
        executionId=execution_id,
        ref=ref,
        policy=policy,
        article=article_item,
        images=image_items,
        facts=fact_items,
    )
    # 合并已存在的人判定（annotate 写过的 human* 不被 review 覆盖）。
    _merge_human_decisions(execution_id, ref, ledger)
    save_ledger(ledger)

    build_entities_sidecar(execution_id, ref, draft_meta)


def _merge_human_decisions(execution_id: str, ref: str, ledger: ReviewLedger) -> None:
    from content.review.ledger import load_ledger

    prev = load_ledger(execution_id, ref)
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
