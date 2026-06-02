"""通用实体类（非线路）evidence / writing-pack / review workflow（Agent 创作版）。

覆盖博物馆/景区/餐厅/古镇等单实体内容（体验/攻略/探店/科普/叙事 等角度）。
复用 route_workflow 的资产挑选、载体路由、图片门、来源痕迹清洗与 review 检查；
仅在「章节意图」上改为单实体框架（初见/最打动/不足/去之前/适合谁），正文一律由会话模型创作。
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from _common.content_evidence import gate_route_evidence_bundle, public_byline_label
from _common.entity_extract import normalize_entity_refs
from _common.entity_annotation import merge_entity_refs
from _common.content_review import fact_traceability_issues, generator_provenance_issues
from _common.draft_io import (
    GENERATOR_AGENT,
    is_placeholder,
    read_draft_article,
    read_draft_meta,
    read_writing_pack,
    write_placeholder_draft,
    write_prompt,
    write_writing_pack,
)
from _common.io import read_json
from _common.paths import batch_inputs_dir
from _common.stage_reports import write_gate_report, write_repair_report, write_stage_result
from _common.template_fingerprints import template_fingerprint_issues
from _common.writing_pack import build_writing_pack, render_prompt_md
from produce.route_workflow import (
    analyze_route_ref,
    is_route_brief,
    resolve_carrier,
    _build_route_assets,
    _build_summary,
    _check_carrier_consistency,
    _check_cross_article_similarity,
    _check_evidence_quality,
    _check_image_gate,
    _check_provenance_rewrite,
    _check_travelogue_density,
    _jaccard,
    _load_source_texts,
    _publish_angle,
    _resolve_style_opening,
    _section_bodies,
    _unique_strings,
)


def is_entity_brief(brief: Mapping[str, Any]) -> bool:
    """非线路、且有 entityRefs 的内容（单实体或实体合集），归入实体 composer。"""
    if is_route_brief(brief):
        return False
    return bool(brief.get("entityRefs"))


def iter_entity_briefs(task_id: str, batch_id: str, refs: Sequence[str] | None = None) -> list[tuple[str, dict[str, Any]]]:
    wanted = {ref for ref in (refs or []) if ref}
    input_dir = batch_inputs_dir(task_id, batch_id, "produce", "compose")
    rows: list[tuple[str, dict[str, Any]]] = []
    if not input_dir.exists():
        return rows
    for brief_file in sorted(input_dir.glob("*.json")):
        ref = brief_file.stem
        if wanted and ref not in wanted:
            continue
        brief = read_json(brief_file)
        if is_entity_brief(brief):
            rows.append((ref, brief))
    return rows


def _entity_name(evidence_bundle: Mapping[str, Any], brief: Mapping[str, Any]) -> str:
    nodes = [n for n in (evidence_bundle.get("routeNodes") or []) if n.get("entityName")]
    if nodes:
        return str(nodes[0]["entityName"])
    refs = [str(x) for x in (brief.get("entityRefs") or []) if x]
    return refs[0].split("/")[-1] if refs else str(brief.get("titleHint") or "")


# 实体类别名词：用于 prompt 指代，避免线路话术（这条线/长线/转场/节点）。
_KIND_WORDS = {
    "博物馆": "这座博物馆",
    "古城": "这处古城",
    "古镇": "这座古镇",
    "景区": "这处景区",
    "公园": "这片园子",
    "寺": "这座寺院",
    "山": "这座山",
    "湖": "这片湖",
    "餐厅": "这家店",
    "店": "这家店",
}


def _kind_word(brief: Mapping[str, Any]) -> str:
    etype = str((brief.get("subject") or {}).get("type") or "")
    tail = etype.split("/")[-1] if etype else ""
    for key, word in _KIND_WORDS.items():
        if key in tail or key in etype:
            return word
    return "这个地方"


# ---------------------------------------------------------------------------
# prepare（compose-brief）
# ---------------------------------------------------------------------------


def _entity_section_intents(brief: Mapping[str, Any], name: str) -> list[str]:
    kind = _kind_word(brief)
    return [
        f"开篇：写为什么想去 {name}、出发前的犹豫或期待（{kind} 是否值得专门跑一趟），别先罗列信息。",
        f"初见 {name}：第一眼的真实感受与节奏，而不是名气介绍。",
        f"最打动我的：具体写一处让你愿意为 {name} 慢下来的细节（来自素材）。",
        f"也得说说不足：诚实写一处劝退/扫兴点（来自素材），并给出心理准备建议。",
        "去之前要知道的：把开放/门票/到达/时段等关键事实就地融入叙述，禁止另起清单块。",
        f"{name} 适合谁：用取舍收尾，给出时间有限时的优先建议。",
    ]


def build_entity_writing_pack(
    task_id: str,
    batch_id: str,
    ref: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_bundle = quality_payload.get("evidenceBundle") or {}
    name = _entity_name(evidence_bundle, brief)
    assets = _build_route_assets(task_id, batch_id, ref, brief, evidence_bundle)
    carrier = resolve_carrier(brief, evidence_bundle, assets)
    publish_layout = "gallery" if carrier == "gallery" else "entity"
    byline = public_byline_label(str(brief.get("templateId") or ""), brief.get("creator") or {})
    pack = build_writing_pack(
        ref=ref,
        kind="entity",
        brief=brief,
        evidence_bundle=evidence_bundle,
        assets=assets,
        carrier=carrier,
        byline=byline,
        publish_layout=publish_layout,
        section_intents=_entity_section_intents(brief, name),
        source_urls=quality_payload.get("sourceUrls") or [],
        source_paths=quality_payload.get("sourcePaths") or [],
    )
    pack["primaryEntity"] = name
    write_writing_pack(task_id, batch_id, ref, pack)
    write_prompt(task_id, batch_id, ref, render_prompt_md(pack))
    existing = read_draft_meta(task_id, batch_id, ref)
    if not existing or str(existing.get("generator")) != GENERATOR_AGENT:
        write_placeholder_draft(task_id, batch_id, ref)

    issues = list(gate_route_evidence_bundle(brief, evidence_bundle))
    if not assets:
        issues.append("writing pack has no verifiable image assets")
    write_stage_result(task_id, batch_id, "produce", "compose_brief", ref, pack)
    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="produce",
        step="compose_brief",
        ref=ref,
        passed=not issues,
        issues=issues,
        evidence_summary={"assetCount": len(assets), "carrier": carrier, "entity": name},
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
    story_spine = quality_payload.get("storySpine") or {}
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
        "publishLayout": pack.get("publishLayout") or ("gallery" if carrier == "gallery" else "entity"),
        "publishAngle": _publish_angle(brief),
        "publishTitle": brief.get("titleHint") or ref,
        "publishSeq": 1,
        "conditionContext": brief.get("conditionContext"),
        "recommendation": brief.get("recommendation"),
        "composeBriefRef": ref,
        "sourceQuality": story_spine.get("sourceQuality", []),
        "storySpine": story_spine,
        "relatedSearchPlan": quality_payload.get("relatedSearchPlan"),
        "evidenceBundle": evidence_bundle,
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


def review_entity_draft(
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

    authenticity_issues: list[str] = []
    if is_placeholder(article):
        authenticity_issues.append("draft not composed yet (placeholder); awaiting agent article")
    authenticity_issues.extend(generator_provenance_issues(draft_meta))
    body = "" if is_placeholder(article) else str(article)
    authenticity_issues.extend(template_fingerprint_issues(body))
    source_texts = _load_source_texts(quality_payload.get("sourcePaths") or [])
    traceability = fact_traceability_issues(body, dict(brief), source_texts)

    compose_payload = _compose_payload_from_pack(ref, brief, quality_payload, pack, body, draft_meta)
    write_stage_result(task_id, batch_id, "produce", "compose", ref, compose_payload)

    checks = _entity_review_checks(
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
    checks["generatorProvenance"] = {
        "passed": not authenticity_issues,
        "issues": authenticity_issues,
        "suggestions": ["按 prompt.md 由会话模型创作正文并写回 drafts/{ref}.article.md（generator=agent）。"] if authenticity_issues else [],
    }
    checks["factTraceability"] = {
        "passed": not traceability,
        "issues": traceability,
        "suggestions": ["补齐 mustIncludeFacts，并确保门票/开放时间/海拔等数字能在 source 证据中找到。"] if traceability else [],
    }

    blocking: list[str] = []
    suggestions: list[str] = []
    for cname, result in checks.items():
        if not result["passed"]:
            blocking.extend(f"{cname}: {issue}" for issue in result["issues"])
            suggestions.extend(result.get("suggestions") or [])
    human_review_required = bool(checks.get("imageGate", {}).get("humanReview"))
    decision = "approved" if not blocking else "revision_needed"
    quality_score = max(0.0, 92.0 - len(blocking) * 8.0)
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
    write_stage_result(task_id, batch_id, "produce", "review", ref, payload)
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
        fallback_stage=_entity_fallback_stage(checks) if decision != "approved" else None,
    )
    if decision != "approved":
        fallback = _entity_fallback_stage(checks)
        if fallback == "download":
            rerun_chain = ["download", "quality_analysis", "compose-brief", "review", "materialize"]
        elif fallback == "manual":
            rerun_chain = ["manual_image_review", "review", "materialize"]
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


def _entity_review_checks(
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
    checks = {
        "entityCoverage": _check_entity_coverage(article, brief, evidence_bundle),
        "provenanceRewrite": _check_provenance_rewrite(article, brief, quality_payload),
        "evidenceQuality": _check_evidence_quality(article, brief, quality_payload, compose_payload),
        "carrierConsistency": _check_carrier_consistency(compose_payload),
        "imageGate": _check_image_gate(compose_payload),
    }
    if str(compose_payload.get("carrier") or "article") != "gallery":
        style_family, opening_strategy = _resolve_style_opening(brief, draft_meta)
        checks["travelogueDensity"] = _check_travelogue_density(
            article, brief, style_family=style_family, opening_strategy=opening_strategy
        )
        checks["crossArticleSimilarity"] = _check_cross_article_similarity(task_id, batch_id, ref, article)
    return checks


def _check_entity_coverage(article: str, brief: Mapping[str, Any], evidence_bundle: Mapping[str, Any]) -> dict[str, Any]:
    name = _entity_name(evidence_bundle, brief)
    issues: list[str] = []
    if name and name not in article:
        issues.append(f"entity '{name}' not mentioned in article")
    headings = re.findall(r"(?m)^##\s", article)
    if len(headings) < 3:
        issues.append(f"too few sections ({len(headings)} < 3)")
    bodies = _section_bodies(article)
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            if _jaccard(bodies[i], bodies[j]) > 0.72:
                issues.append(f"sections {i+1} and {j+1} too similar")
                break
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["围绕单实体补足初见/亮点/不足/实用提醒等差异化分节。"] if issues else [],
    }


def _entity_fallback_stage(checks: Mapping[str, Mapping[str, Any]]) -> str:
    if not checks.get("generatorProvenance", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks["evidenceQuality"]["passed"]:
        return "download"
    if not checks.get("factTraceability", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks["provenanceRewrite"]["passed"]:
        return "agent_compose"
    if not checks["entityCoverage"]["passed"]:
        return "agent_compose"
    if not checks.get("travelogueDensity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("crossArticleSimilarity", {"passed": True})["passed"]:
        return "agent_compose"
    image_gate = checks.get("imageGate", {"passed": True})
    if not image_gate["passed"]:
        return "manual" if image_gate.get("humanReview") and len(image_gate.get("issues") or []) == 1 else "agent_compose"
    if not checks.get("carrierConsistency", {"passed": True})["passed"]:
        return "agent_compose"
    return "review"


__all__ = [
    "build_entity_writing_pack",
    "is_entity_brief",
    "iter_entity_briefs",
    "review_entity_draft",
]
