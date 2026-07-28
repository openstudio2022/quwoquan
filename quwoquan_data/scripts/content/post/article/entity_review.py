"""通用实体类（非线路）evidence / writing-pack / review workflow（Agent 创作版）。

覆盖博物馆/景区/餐厅/古镇等单实体内容（体验/攻略/探店/科普/叙事 等角度）。
复用线路内容的资产挑选、载体路由、图片门、来源痕迹清洗与 review 检查；
仅在「章节意图」上改为单实体框架（初见/最打动/不足/去之前/适合谁），正文一律由创作 agent创作。
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from core.data_issue import DataIssueCode, DataIssueStage, DataRecoveryAction, data_issues
from content.post.article.evidence_bundle import gate_route_evidence_bundle, public_byline_label
from core.creative_brief import creative_brief_contract_issues, creative_governance_issues
from content.post.object_index import require_title_hint
from governance.coverage.entity_extract import normalize_entity_refs
from content.review.annotation.entity_annotation import merge_entity_refs
from content.post.content_review import fact_traceability_issues, generator_provenance_issues
from content.post.article.draft_io import (
    GENERATOR_AGENT,
    draft_asset_reference_issues,
    is_placeholder,
    read_draft_article,
    read_draft_meta,
    read_writing_pack,
    repair_creative_meta,
    write_image_evidence_draft,
    write_placeholder_draft,
    write_prompt,
    write_writing_pack,
)
from core.content_tags import resolved_content_tag_refs
from content.execution.stage_reports import clear_repair_report, write_gate_report, write_repair_report, write_stage_result
from core.template_fingerprints import template_fingerprint_issues
from content.post.article.prompt_renderer import render_prompt_md
from content.post.article.writing_pack import build_writing_pack
from content.post.article.route_analysis import analyze_route_ref
from content.post.article.route_assets import _build_route_assets
from content.post.article.route_compose import _attach_base_draft_text
from content.post.article.route_core import (
    IMAGE_EVIDENCE_GENERATOR,
    aggregate_checks,
    is_route_brief,
    resolve_carrier,
    _article_without_assets_allowed,
    _build_summary,
    _compact_public_text,
    _image_caption_from_article,
    _image_caption_from_brief,
    _jaccard,
    _publish_angle,
    _section_bodies,
    _unique_strings,
    load_compose_brief,
)
from content.post.article.route_review import (
    _load_source_texts,
    _persisted_review_payload,
)
from content.post.article.route_review_checks import (
    _check_carrier_consistency,
    _check_cross_article_similarity,
    _check_evidence_quality,
    _check_image_fidelity,
    _check_image_gate,
    _check_prose_style,
    _check_provenance_rewrite,
    _check_travelogue_density,
    _resolve_style_opening,
)


from content.post.article.entity_composition import (
    _compose_payload_from_pack,
    _entity_name,
    _image_source_paths_from_assets,
    _source_ref_from_asset_path,
)

def _same_source_unit(a: str, b: str) -> bool:
    marker = "/1.download/sources/"

    def unit(ref: str) -> str:
        text = str(ref or "").replace("\\", "/")
        if "/assets/" in text:
            return text.split("/assets/", 1)[0]
        if text.endswith("/source.md") or text.endswith("/meta.json"):
            return text.rsplit("/", 1)[0]
        if marker in text:
            head, tail = text.split(marker, 1)
            return head + marker + tail.split("/", 1)[0]
        return text

    return bool(a) and bool(b) and unit(a) == unit(b)

def _single_base_asset_issues(
    compose_payload: Mapping[str, Any],
    base_source_ref: str,
    *,
    carrier: str,
) -> list[str]:
    """资产同源硬门：每张配图的 sourceRef 必须与底稿同一 source unit（单底稿零参考）。"""
    if not base_source_ref:
        return []
    issues: list[str] = []
    for asset in compose_payload.get("assets") or []:
        if not isinstance(asset, Mapping):
            continue
        asset_source_ref = str(asset.get("sourceRef") or "").strip()
        if not asset_source_ref:
            continue
        if not _same_source_unit(asset_source_ref, base_source_ref):
            issues.append(
                f"配图 {asset.get('assetId') or asset.get('fileName') or '?'} 的 sourceRef 不在底稿来源单元内"
                f"（跨 source unit 借图）：{asset_source_ref}"
            )
    return issues

def _check_image_source_scope(compose_payload: Mapping[str, Any]) -> dict[str, Any]:
    carrier = str(compose_payload.get("carrier") or "article")
    if carrier != "image":
        return {"passed": True, "issues": [], "suggestions": []}
    assets = [asset for asset in (compose_payload.get("assets") or []) if isinstance(asset, Mapping)]
    allowed = set(_image_source_paths_from_assets(assets))
    cited = set(
        _unique_strings(
            [
                _source_ref_from_asset_path(item)
                for item in [
                    *(compose_payload.get("sourcePaths") or []),
                    *(compose_payload.get("citedSourceRefs") or []),
                ]
            ]
        )
    )
    cited.discard("")
    issues: list[str] = []
    if not allowed:
        issues.append("image source scope missing asset sourceRef/sourcePath")
    extra = sorted(cited - allowed)
    if extra:
        issues.append(f"image carrier cites non-image source units: {extra[:5]}")
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["图片作品只保留所选图片集合的 source unit，不得混入 homepage/article 来源。"] if issues else [],
    }

def review_entity_draft(
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

    checks = _entity_review_checks(
        body,
        brief,
        evidence_bundle,
        quality_payload,
        compose_payload,
        execution_id=execution_id,
        ref=ref,
        draft_meta=draft_meta,
    )
    checks["generatorProvenance"] = {
        "passed": not authenticity_issues,
        "issues": authenticity_issues,
        "suggestions": ["按 prompt.md 由创作 agent创作正文并写回对象 `4.draft/draft.article.md`（generator=agent）。"] if authenticity_issues else [],
    }
    checks["factTraceability"] = {
        "passed": not traceability,
        "issues": traceability,
        "suggestions": ["补齐 mustIncludeFacts，并确保门票/开放时间/海拔等数字能在 source 证据中找到。"] if traceability else [],
    }
    from content.post.article.base_draft import (
        load_base_draft_text,
    )
    from content.post.article.base_draft_source import base_source_use_mode
    from content.post.fidelity import (
        base_draft_fidelity_issues,
        commercial_article_near_copy_gate,
    )

    if carrier == "image":
        fidelity = []
        near_copy = commercial_article_near_copy_gate(
            "",
            "",
            source_use_mode="factual_reference_only",
            carrier=carrier,
        )
    else:
        # 底稿中心 1:1：分母 = 整篇单一底稿（与 prompt 侧 baseDraftText 同源），
        # 不再按 writingIntent 收窄——成品只来自这一篇底稿，整篇度量同时防误杀与防照搬。
        base_text = load_base_draft_text(execution_id, brief.get("baseSourceRef"))
        source_use_mode = base_source_use_mode(execution_id, brief.get("baseSourceRef"))
        fidelity = base_draft_fidelity_issues(
            body,
            base_text,
            carrier=carrier,
            source_use_mode=source_use_mode,
        )
        near_copy = commercial_article_near_copy_gate(
            body,
            base_text,
            carrier=carrier,
            source_use_mode=source_use_mode,
        )
    checks["baseDraftFidelity"] = {
        "passed": not fidelity,
        "issues": fidelity,
        "suggestions": ["以底稿为基础适度加工：相似度过低则贴回底稿叙事；过高则进一步改写表达、去版权痕迹。"] if fidelity else [],
    }
    checks["commercialNearCopy"] = near_copy.to_review_check()
    # 单底稿零参考硬门（仅对声明了唯一底稿的可轻改文章生效）：
    # ① 正文不得从同实体其它来源单元长串照搬（反拼接）；② 配图必须与底稿同一 source unit。
    single_base_issues: list[str] = []
    base_source_ref = str(brief.get("baseSourceRef") or "").strip()
    if carrier != "image" and base_source_ref:
        from content.post.article.base_draft import sibling_source_texts
        from content.post.fidelity import cross_source_overlap_issues

        others = sibling_source_texts(execution_id, base_source_ref)
        single_base_issues.extend(
            cross_source_overlap_issues(body, base_text, others, carrier=carrier)
        )
    single_base_issues.extend(
        _single_base_asset_issues(compose_payload, base_source_ref, carrier=carrier)
    )
    checks["singleBaseZeroReference"] = {
        "passed": not single_base_issues,
        "issues": single_base_issues,
        "suggestions": [
            "全文与配图只能来自唯一底稿来源单元：删除从其它来源单元搬迁的段落；配图改用底稿同 source unit 内的已授权图。"
        ] if single_base_issues else [],
    }
    from core import quality_gates as qg

    # 结构形态硬门（与来源数量无关，低误报）：单章节过半失衡 + 平行时间线拼接未归并。
    sb_issues = [] if carrier == "image" else qg.section_balance_issues(
        body, max_ratio=qg.SECTION_BALANCE_MAX_RATIO_ARTICLE
    )
    checks["sectionBalance"] = {
        "passed": not sb_issues,
        "issues": sb_issues,
        "suggestions": ["压缩或拆分过长章节，避免一段吞并其余应有章节；按 writingIntent 均衡分配篇幅。"] if sb_issues else [],
    }
    tl_issues = [] if carrier == "image" else qg.timeline_monotonicity_issues(body)
    checks["timelineOrder"] = {
        "passed": not tl_issues,
        "issues": tl_issues,
        "suggestions": ["把同章节内并列时间线按真实时间顺序归并为单一连贯叙事，禁止首尾拼接造成时间倒错。"] if tl_issues else [],
    }
    if carrier == "image":
        checks["writingIntentConsistency"] = {"passed": True, "issues": [], "suggestions": []}
    else:
        wi_issues = qg.writing_intent_consistency_issues(body, brief.get("writingIntent"))
        checks["writingIntentConsistency"] = {
            "passed": not wi_issues,
            "issues": wi_issues,
            "suggestions": [
                "按 writingIntent 主线补齐结构（攻略=步骤/交通/票务/取舍；体验=适合人群/价值/取舍；游记=时间线/现场/复盘）。"
            ] if wi_issues else [],
        }
    banned_terms = [str(b) for b in (pack.get("bannedRegisterTerms") or brief.get("bannedRegisterTerms") or [])]
    reg_issues = qg.register_lexicon_issues(body, banned_terms)
    checks["registerMismatch"] = {
        "passed": not reg_issues,
        "issues": reg_issues,
        "suggestions": ["改用该垂类合适的语域（如户外景区禁'看展/展厅/展陈'），由垂类规则词表约束。"] if reg_issues else [],
    }
    from core import public_contacts as pc

    allowed_contacts = [str(n) for n in (pack.get("allowedContactNumbers") or brief.get("allowedContactNumbers") or [])]
    contact_issues = qg.contact_info_issues(body, allowed_numbers=pc.allowed_numbers(allowed_contacts))
    checks["contactInfo"] = {
        "passed": not contact_issues,
        "issues": contact_issues,
        "suggestions": ["删除私人电话/微信/QQ；仅保留紧急/公共服务短号或 source 核实的景区官方接待电话。"] if contact_issues else [],
    }
    heading_extra = [str(t) for t in (pack.get("mechanicalHeadingTerms") or brief.get("mechanicalHeadingTerms") or [])]
    heading_issues = qg.mechanical_heading_issues(body, extra_terms=heading_extra)
    checks["mechanicalHeading"] = {
        "passed": not heading_issues,
        "issues": heading_issues,
        "suggestions": ["把纯清单式小标题改写得自然、有视角；优先沿用底稿已有小标题，不要套统一模板。"] if heading_issues else [],
    }
    creative_issues = [] if carrier == "image" else creative_governance_issues(body, pack, draft_meta)
    checks["creativeGovernance"] = {
        "passed": not creative_issues,
        "issues": creative_issues,
        "suggestions": [
            "按 creativeBrief 先形成 2-3 个构思，选择最能兑现 readerPromise 的结构；"
            "修正文案时只在 evidence 边界内发挥，不伪装真实亲历，并把 creativePlan/selfCritique 写入 draft_meta。"
        ] if creative_issues else [],
    }

    blocking, suggestions, soft_failed = aggregate_checks(checks)
    human_review_required = bool(checks.get("imageGate", {}).get("humanReview"))
    decision = "approved" if not blocking else "revision_needed"
    quality_score = max(0.0, 92.0 - len(blocking) * 8.0 - soft_failed * 3.0)
    payload = {
        "topicId": ref,
        "decision": decision,
        "qualityScore": quality_score,
        "issues": blocking,
        "suggestions": _unique_strings(suggestions),
        "checks": checks,
        "humanReviewRequired": human_review_required,
        "generator": compose_payload.get("generator"),
    }
    write_stage_result(execution_id, "post", "review", ref, _persisted_review_payload(payload))
    fallback = _entity_fallback_stage(checks) if decision != "approved" else None
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
    else:
        clear_repair_report(execution_id=execution_id, command="post", ref=ref)
    return payload

def _entity_review_checks(
    article: str,
    brief: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
    compose_payload: Mapping[str, Any],
    *,
    execution_id: str = "",
    ref: str = "",
    draft_meta: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    if str(compose_payload.get("carrier") or "article") == "image":
        return {
            "carrierConsistency": _check_carrier_consistency(compose_payload),
            "imageGate": _check_image_gate(compose_payload),
            "imageFidelity": _check_image_fidelity(compose_payload),
            "imageSourceScope": _check_image_source_scope(compose_payload),
        }
    checks = {
        "entityCoverage": _check_entity_coverage(article, brief, evidence_bundle),
        "provenanceRewrite": _check_provenance_rewrite(article, brief, quality_payload, compose_payload),
        "evidenceQuality": _check_evidence_quality(article, brief, quality_payload, compose_payload),
        "carrierConsistency": _check_carrier_consistency(compose_payload),
        "proseStyle": _check_prose_style(article),
        "imageGate": _check_image_gate(compose_payload),
    }
    if str(compose_payload.get("carrier") or "article") != "image":
        style_family, opening_strategy = _resolve_style_opening(brief, draft_meta)
        checks["travelogueDensity"] = _check_travelogue_density(
            article, brief, style_family=style_family, opening_strategy=opening_strategy
        )
        checks["crossArticleSimilarity"] = _check_cross_article_similarity(execution_id, ref, article)
        checks["sectionShape"] = _check_section_shape(article)
    return checks

def _check_entity_coverage(article: str, brief: Mapping[str, Any], evidence_bundle: Mapping[str, Any]) -> dict[str, Any]:
    """HARD：实体必须在正文出现（事实完整性）。结构形态另由软门 sectionShape 评估。"""
    name = _entity_name(evidence_bundle, brief)
    issues: list[str] = []
    if name and name not in article:
        issues.append(f"entity '{name}' not mentioned in article")
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["正文须真正写到该实体，而非只在标题出现。"] if issues else [],
    }

def _check_section_shape(article: str) -> dict[str, Any]:
    """SOFT：分节形态建议（章节过少/雷同）——不阻断，结构以底稿为准。"""
    issues: list[str] = []
    headings = re.findall(r"(?m)^##\s", article)
    if len(headings) < 2:
        issues.append(f"too few sections ({len(headings)} < 2)")
    bodies = _section_bodies(article)
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            if _jaccard(bodies[i], bodies[j]) > 0.72:
                issues.append(f"sections {i+1} and {j+1} too similar")
                break
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["如底稿本身分节较细，可保留；过少或雷同时适度补足差异化分节。"] if issues else [],
    }

def _entity_fallback_stage(checks: Mapping[str, Mapping[str, Any]]) -> str:
    if not checks.get("generatorProvenance", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("evidenceQuality", {"passed": True})["passed"]:
        return "download"
    if not checks.get("factTraceability", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("baseDraftFidelity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("commercialNearCopy", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("singleBaseZeroReference", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("provenanceRewrite", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("entityCoverage", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("travelogueDensity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("crossArticleSimilarity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("creativeGovernance", {"passed": True})["passed"]:
        return "agent_compose"
    image_gate = checks.get("imageGate", {"passed": True})
    if not image_gate["passed"]:
        return "agent_compose"
    if not checks.get("imageFidelity", {"passed": True})["passed"]:
        return "compose_brief"
    if not checks.get("carrierConsistency", {"passed": True})["passed"]:
        return "agent_compose"
    return "review"
