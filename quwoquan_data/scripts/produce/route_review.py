"""Review gates and human-review ledger persistence for route production."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from _common.content_evidence import gate_route_evidence_bundle
from _common.content_review import (
    check_narrative_quality,
    check_provenance,
    fact_traceability_issues,
    generator_provenance_issues,
)
from _common.creative_brief import creative_governance_issues
from _common.draft_io import (
    PLACEHOLDER_MARKER,
    draft_asset_reference_issues,
    iter_draft_articles,
    is_placeholder,
    read_draft_article,
    read_draft_meta,
    read_writing_pack,
)
from _common.entity_extract import build_entities_sidecar
from _common.image_safety import assess_asset_sources
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
from produce import route_bridge
from produce.route_compose import (
    _compose_payload_from_pack,
    _image_source_paths_from_assets,
    _source_ref_from_asset_path,
)
from produce.route_core import (
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
    carrier_hint = str(pack.get("carrier") or brief.get("carrier") or "article")
    is_image_carrier = carrier_hint in ("image", "gallery")

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
    from _common.base_draft import (
        base_draft_fidelity_issues,
        base_source_use_mode,
        load_intent_aligned_base_draft_text,
    )

    if carrier in ("image", "gallery"):
        fidelity = []
    else:
        # 门侧分母与 prompt 侧 baseDraftText 同源：同一份 writingIntent 主线对齐底稿，
        # 否则整篇多主题游记作分母会误杀聚焦文章（R-CS01 单一真相源）。
        from _common.writing_pack import primary_entity_name

        base_text = load_intent_aligned_base_draft_text(
            task_id,
            batch_id,
            brief.get("baseSourceRef"),
            writing_intent=brief.get("writingIntent"),
            entity_name=primary_entity_name(brief),
        )
        source_use_mode = base_source_use_mode(task_id, batch_id, brief.get("baseSourceRef"))
        fidelity = base_draft_fidelity_issues(
            body,
            base_text,
            carrier=carrier,
            source_use_mode=source_use_mode,
        )
    route_checks["baseDraftFidelity"] = {
        "passed": not fidelity,
        "issues": fidelity,
        "suggestions": ["以底稿为基础适度加工：相似度过低则贴回底稿叙事；过高则进一步改写表达、去版权痕迹。"] if fidelity else [],
    }
    from _common import quality_gates as qg

    wi_issues = [] if carrier in ("image", "gallery") else qg.writing_intent_consistency_issues(body, brief.get("writingIntent"))
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
    creative_issues = [] if carrier in ("image", "gallery") else creative_governance_issues(body, pack, draft_meta)
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
        report = route_bridge.call("assess_asset_sources", assess_asset_sources, assets)
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
    if carrier in ("image", "gallery"):
        # 画报载体以图为主、配小字：只校验体裁/图片/资源，不套长文叙事门。
        return {
            "carrierConsistency": _check_carrier_consistency(compose_payload),
            "imageGate": _check_image_gate(compose_payload),
            "galleryCaption": _check_gallery_caption(article, brief, quality_payload),
            "imageSourceScope": _check_image_source_scope(compose_payload),
        }
    style_family, opening_strategy = _resolve_style_opening(brief, draft_meta)
    checks = {
        "routeCoverage": _check_route_coverage(article, brief, evidence_bundle),
        "narrativeContinuity": _check_narrative_continuity(article, brief, evidence_bundle),
        "provenanceRewrite": _check_provenance_rewrite(article, brief, quality_payload, compose_payload),
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
    """Image-work caption is optional, separate from assets, and at most 300 chars."""
    issues: list[str] = []
    compact = re.sub(r"\s+", "", article)
    if len(compact) > 300:
        issues.append(f"caption too long ({len(compact)} > 300)")
    if len(str(brief.get("titleHint") or "")) > 80:
        issues.append("title too long (>80)")
    if any(term in article for term in PROVENANCE_TERMS):
        issues.append("contains provenance/platform wording")
    # 画报配文只约束长度与平台/来源痕迹；图片权利由资产门和 sourceCollection 合同兜底。
    return {
        "passed": not issues,
        "issues": issues,
        "suggestions": ["画报配文保持简短，去除平台口吻与来源痕迹。"] if issues else [],
    }


def _check_carrier_consistency(compose_payload: Mapping[str, Any]) -> dict[str, Any]:
    """体裁一致性：article 是长文；image/gallery 是结构化图片集合 + 可选短配文。"""
    carrier = str(compose_payload.get("carrier") or "article")
    article = str(compose_payload.get("articleMarkdown") or "")
    issues: list[str] = []
    if carrier in ("image", "gallery"):
        assets = [a for a in (compose_payload.get("assets") or []) if a.get("assetId")]
        if not (1 <= len(assets) <= 20):
            issues.append(f"image carrier needs 1..20 assets, got {len(assets)}")
        collection_ids = {
            str(asset.get("sourceCollectionId") or "")
            for asset in assets
            if str(asset.get("sourceCollectionId") or "")
        }
        if len(collection_ids) != 1:
            issues.append(
                f"image carrier must use one sourceCollectionId, got {sorted(collection_ids)}"
            )
        if len(str(compose_payload.get("title") or "")) > 80:
            issues.append("image title exceeds 80 characters")
        caption_text = str(compose_payload.get("caption") or "").strip()
        if not caption_text:
            caption_text = _image_visible_caption(article)
        if len(re.sub(r"\s+", "", caption_text)) > 300:
            issues.append("image caption exceeds 300 characters")
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


def _check_image_source_scope(compose_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Image works may cite only the source unit that owns their selected assets."""
    carrier = str(compose_payload.get("carrier") or "article")
    if carrier not in ("image", "gallery"):
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


def _image_visible_caption(article: str) -> str:
    """Extract the user-visible caption text from an image-post markdown draft."""
    text = re.sub(r"(?ms)^:::figure\n.*?\n:::\s*", "", article or "")
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def _check_image_gate(compose_payload: Mapping[str, Any]) -> dict[str, Any]:
    """图片门并入裁决：unsafe/重复 -> 阻断改稿；含人脸/后端缺失 -> 标记人工复核。"""
    from _common.image_safety import assess_asset_sources

    carrier = str(compose_payload.get("carrier") or "article")
    if carrier not in ("image", "gallery") and str(compose_payload.get("publishMediaMode") or "").strip() == "text_only":
        return {
            "passed": True,
            "issues": [],
            "humanReview": False,
            "notes": ["text-only article skips image gate"],
            "suggestions": [],
        }
    assets = [a for a in (compose_payload.get("assets") or []) if a.get("sourcePath")]
    if not assets:
        return {"passed": False, "issues": ["no verifiable image assets"], "humanReview": False, "suggestions": ["补充可校验的图片资源。"]}
    report = route_bridge.call("assess_asset_sources", assess_asset_sources, assets)
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
    text = article.lstrip()
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            text = parts[1]
    text = re.sub(r"(?ms)^:::figure\b.*?^:::\s*", "", text)
    paragraphs: list[str] = []
    for paragraph in text.split("\n\n"):
        stripped = paragraph.strip()
        if not stripped:
            continue
        if stripped.lstrip().startswith(("#", ">", ":::")):
            continue
        if re.fullmatch(r"asset://[^\s]+", stripped):
            continue
        paragraphs.append(stripped)
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
    observations: list[str] = []
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
            observations.append(
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
        "observations": observations,
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
    compose_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    carrier = str(brief.get("carrier") or "article")
    issues = check_narrative_quality(article, {"template": brief.get("templateId"), "carrier": carrier})
    if any(term in article for term in PROVENANCE_TERMS):
        issues.append("contains provenance/platform wording")
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
    text_only = str(compose_payload.get("publishMediaMode") or "").strip() == "text_only"
    if not compose_payload.get("assets") and not text_only:
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
    if not checks.get("evidenceQuality", {"passed": True})["passed"]:
        return "download"
    if not checks.get("factTraceability", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("baseDraftFidelity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("provenanceRewrite", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("routeCoverage", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("travelogueDensity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("crossArticleSimilarity", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("creativeGovernance", {"passed": True})["passed"]:
        return "agent_compose"
    if not checks.get("mixedLayout", {"passed": True})["passed"]:
        return "agent_compose"
    image_gate = checks.get("imageGate", {"passed": True})
    if not image_gate["passed"]:
        return "agent_compose"
    if not checks.get("carrierConsistency", {"passed": True})["passed"]:
        return "agent_compose"
    return "review"

__all__ = [name for name in globals() if not name.startswith("__")]
