"""Subagent handoff packet 与出口门（single ref gate + batch reducer gate）。

把"主 Agent 调度 ↔ Subagent 单篇创作"的交接结构化（整改计划第一阶段补充）：
- author_job_packet：发给 Subagent 的单 ref 输入包（意图/底稿/图片槽位/禁用语域/出口门）。
- ref_review_gate：单篇出口门（Subagent 不能只说"我完成了"，必须有文件 + self-check + review 决策）。
- execution_reducer_gate：批次级归并门（跨篇骨架相似度、baseSourceRef 复用、writingIntent 分布、图文分布）。

reducer 复用单一门库 core/quality_gates，不另写一套相似度。
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core import public_contacts as pc
from core import quality_gates as qg
from core.io import write_json
from core.paths import execution_root
from core.runtime_policy import active_runtime_policy
from governance.creators.assignment import creator_from_payload

from content.execution.model_contract import execution_model_pair_for_execution

# ---------------------------------------------------------------------------
# 执行合约（harness execution contract）：把模糊 LLM 调用收成有界 agent 调用。
# 5 要素：required inputs / budgets / permissions / completion conditions / output paths。
# ---------------------------------------------------------------------------
EXECUTION_CONTRACT_KEYS: tuple[str, ...] = (
    "inputs",
    "budget",
    "permissions",
    "completionConditions",
    "outputPaths",
)

DEFAULT_AUTHOR_PERMISSIONS: tuple[str, ...] = (
    "read_ref_packet",
    "search_web",
    "write_draft",
    "run_review_gate",
)


def build_execution_contract(
    *,
    inputs: list[str] | None = None,
    permissions: list[str] | None = None,
    completion_conditions: list[str] | None = None,
    output_paths: list[str] | None = None,
) -> dict[str, Any]:
    policy = active_runtime_policy()
    return {
        "inputs": inputs
        or ["4.draft/author_job_packet.json", "3.compose/writing_pack.json", "2.quality/*", "5.review/repair_report.json"],
        "budget": {
            "maxWallClockSeconds": policy.queue_max_wall_clock_seconds,
            "maxAttempts": policy.queue_max_attempts,
            "stuckThreshold": policy.queue_stuck_threshold,
        },
        "permissions": list(permissions) if permissions is not None else list(DEFAULT_AUTHOR_PERMISSIONS),
        "completionConditions": list(completion_conditions) if completion_conditions is not None else [
            "4.draft/draft.article.md 已写且非占位",
            "4.draft/author_self_check.json 存在",
            "ref_review_gate.passed == true (reviewDecision == approved)",
        ],
        "outputPaths": list(output_paths) if output_paths is not None else [
            "4.draft/draft.article.md",
            "4.draft/author_self_check.json",
            "5.review/ref_review_gate.json",
        ],
    }


def execution_contract_issues(contract: Mapping[str, Any] | None) -> list[str]:
    """校验执行合约 5 要素齐全且非空；permissions 必须为最小工具集 allow-list（非空）。"""
    if not contract:
        return ["executionContract: missing"]
    issues: list[str] = []
    for key in EXECUTION_CONTRACT_KEYS:
        if not contract.get(key):
            issues.append(f"executionContract: missing/empty `{key}`")
    budget = contract.get("budget") or {}
    if isinstance(budget, Mapping) and not budget.get("maxWallClockSeconds"):
        issues.append("executionContract.budget: maxWallClockSeconds required (Ralph per-iteration cap)")
    return issues


# ---------------------------------------------------------------------------
# author_job_packet：单 ref 输入包
# ---------------------------------------------------------------------------
def build_author_job_packet(
    *,
    execution_id: str,
    ref: str,
    brief: Mapping[str, Any],
    writing_pack: Mapping[str, Any],
    prompt_rel: str,
    content_object_rel: str | None = None,
) -> dict[str, Any]:
    from content.execution.runtime_contract import (
        canonical_sha256,
        stage_execution_context,
    )

    carrier = writing_pack.get("carrier") or brief.get("carrier")
    is_image = str(carrier or "") == "image"
    is_video = str(carrier or "") == "video"
    execution = stage_execution_context(execution_id)
    author_model = execution_model_pair_for_execution(execution_id).author
    run_id = "author_" + canonical_sha256(
        {"executionId": execution["executionId"], "objectRef": ref}
    ).removeprefix("sha256:")[:20]
    output_refs = (
        [
            "4.draft/draft_meta.json",
            "4.draft/author_self_check.json",
            "4.draft/agent_result_envelope.json",
        ]
        if is_image
        else [
            "4.draft/video_script.json",
            "4.draft/draft_meta.json",
            "4.draft/author_self_check.json",
            "4.draft/agent_result_envelope.json",
        ]
        if is_video
        else [
            "4.draft/draft.article.md",
            "4.draft/draft_meta.json",
            "4.draft/author_self_check.json",
            "4.draft/agent_result_envelope.json",
        ]
    )
    creator_assignment = creator_from_payload(writing_pack) or creator_from_payload(brief)
    assets = [
        {
            "assetId": a.get("assetId"),
            "entityName": a.get("entityName"),
            "imageLayout": a.get("imageLayout"),
            "caption": a.get("caption"),
            "sourceCollectionId": a.get("sourceCollectionId"),
            "creator": a.get("creator"),
            "license": a.get("license"),
        }
        for a in (writing_pack.get("assets") or [])
        if a.get("assetId")
    ]
    article_source_unit_freeze = (
        writing_pack.get("articleSourceUnitFreeze")
        or brief.get("articleSourceUnitFreeze")
    )
    return {
        "schema": "quwoquan_data.author_job_packet",
        "stage": "4.draft",
        **execution,
        "objectRef": ref,
        "composePacketRef": "3.compose/writing_pack.json",
        "promptSnapshotRef": "4.draft/prompt_snapshot.json",
        "provider": author_model.provider.value,
        "model": author_model.model_id,
        "runId": run_id,
        "outputRefs": output_refs,
        "ref": ref,
        "writingIntent": writing_pack.get("writingIntent") or brief.get("writingIntent"),
        "baseSourceRef": writing_pack.get("baseSourceRef") or brief.get("baseSourceRef"),
        "title": writing_pack.get("title") or brief.get("titleHint"),
        "caption": writing_pack.get("caption") or brief.get("caption") or "",
        "carrier": carrier,
        "contentObjectDir": content_object_rel,
        "promptRef": prompt_rel,
        "writingPackRef": "3.compose/writing_pack.json",
        "sourcePaths": list(writing_pack.get("sourcePaths") or []),
        "sourceUrls": list(writing_pack.get("sourceUrls") or []),
        "mustIncludeFacts": list(writing_pack.get("mustIncludeFacts") or []),
        "bannedRegisterTerms": list(writing_pack.get("bannedRegisterTerms") or []),
        "creativeBrief": writing_pack.get("creativeBrief") or {},
        "creatorAssignment": creator_assignment,
        "captionPolicy": writing_pack.get("captionPolicy") or ({"titleMaxChars": 80, "captionMaxChars": 300} if is_image else {}),
        "assets": assets,
        "articleSourceUnitFreeze": article_source_unit_freeze,
        "sourceVideo": (
            writing_pack.get("sourceVideo") if is_video else None
        ),
        "exitGates": [
            *(
                [
                    "imageCarrierContract",
                    "imageSourceScope",
                    "imageGate",
                    "galleryCaption",
                ]
                if is_image
                else ["videoScriptContract", "videoSourceRights", "videoDeliveryContract"]
                if is_video
                else [
                    "writingIntentConsistency",
                    "imageReferenceClosure",
                    "skeletonSimilarity",
                    "registerMismatch",
                    "sourceRejectBlock",
                    "contactInfo",
                    "mechanicalHeading",
                    "creativeGovernance",
                ]
            ),
        ],
        "executionContract": build_execution_contract(
            inputs=(
                ["4.draft/author_job_packet.json", "4.draft/prompt.md", "5.review/repair_report.json"]
                if is_image
                else ["4.draft/author_job_packet.json", "4.draft/prompt.md", "3.compose/writing_pack.json"]
                if is_video
                else None
            ),
            completion_conditions=(
                [
                    "4.draft/draft.article.md 不存在",
                    "4.draft/draft_meta.json.generator == image_evidence_pack",
                    "ref_review_gate.passed == true (reviewDecision == approved)",
                ]
                if is_image
                else [
                    "4.draft/video_script.json 通过 video_script schema",
                    "4.draft/draft_meta.json.generator == agent",
                    "ref_review_gate.passed == true (reviewDecision == approved)",
                ]
                if is_video
                else None
            ),
            output_paths=(
                ["4.draft/draft_meta.json", "5.review/ref_review_gate.json"]
                if is_image
                else [
                    "4.draft/video_script.json",
                    "4.draft/draft_meta.json",
                    "4.draft/author_self_check.json",
                    "5.review/ref_review_gate.json",
                ]
                if is_video
                else None
            ),
        ),
        "isolation": "single-ref: 只读本 ref 的 packet/template/source，禁止读取同批其它文章正文作为底稿",
    }


# ---------------------------------------------------------------------------
# ref_review_gate：单篇出口门
# ---------------------------------------------------------------------------
def build_ref_review_gate(
    *,
    ref: str,
    article: str,
    writing_intent: Any,
    assets: list[Mapping[str, Any]],
    carrier: str,
    route_node_count: int,
    banned_register_terms: list[str],
    cited_source_refs: list[str],
    reject_source_refs: list[str],
    self_check_present: bool,
    review_decision: str | None,
    allowed_contact_numbers: list[str] | None = None,
    mechanical_heading_extra: list[str] | None = None,
) -> dict[str, Any]:
    gate_issues: list[str] = []
    gate_issues += qg.writing_intent_consistency_issues(article, writing_intent)
    gate_issues += qg.image_reference_closure_issues(article, assets, carrier=carrier, route_node_count=route_node_count)
    gate_issues += qg.register_lexicon_issues(article, banned_register_terms)
    gate_issues += qg.source_reject_block_issues(cited_source_refs, reject_source_refs)
    gate_issues += qg.contact_info_issues(article, allowed_numbers=pc.allowed_numbers(allowed_contact_numbers or []))
    gate_issues += qg.mechanical_heading_issues(article, extra_terms=mechanical_heading_extra or [])
    if not self_check_present:
        gate_issues.append("exitGate: author_self_check.json missing (subagent must self-check, not just declare done)")
    passed = not gate_issues and review_decision == "approved"
    return {
        "schema": "quwoquan_data.ref_review_gate",
        "ref": ref,
        "passed": passed,
        "reviewDecision": review_decision,
        "issues": gate_issues,
    }


# ---------------------------------------------------------------------------
# execution_reducer_gate：批次级归并门
# ---------------------------------------------------------------------------
def build_execution_reducer_gate(refs_payload: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Reduce reviewed article objects, including the typed media closure.

    ``articleMediaMode`` is projected only by ``read_article_media_closure``;
    this reducer never infers illustration state from markdown or asset counts.
    返回跨篇归并结果：骨架相似度、baseSourceRef 复用、writingIntent 分布、图文分布。
    affectedRefs 用于只回退受影响 ref（不全批重写）。
    """
    issues: list[str] = []
    affected: set[str] = set()
    articles = {str(p.get("ref")): str(p.get("article") or "") for p in refs_payload}

    # 跨篇骨架相似度
    for ref, art in articles.items():
        peers = [a for r, a in articles.items() if r != ref]
        sk = qg.skeleton_similarity_issues(art, peers)
        if sk:
            issues.append(f"{ref}: {sk[0]}")
            affected.add(ref)

    # baseSourceRef 复用
    source_users: dict[str, list[str]] = {}
    for p in refs_payload:
        base = str(p.get("baseSourceRef") or "")
        if base:
            source_users.setdefault(base, []).append(str(p.get("ref")))
    source_reuse = {k: v for k, v in source_users.items() if len(v) > 1}
    # 底稿中心 1:1：一源只能一篇，任何 baseSourceRef 复用都判风险，
    # 不再因 multi_intent_source_bundle 声明而豁免。
    for base, users in source_reuse.items():
        issues.append(f"source_reuse_risk: baseSourceRef {base} reused by {users} (需人工确认或重选底稿)")
        affected.update(users)

    # writingIntent 分布 + typed article media closure distribution.
    intent_dist: dict[str, int] = {}
    media_modes: dict[str, str] = {}
    for p in refs_payload:
        ref = str(p.get("ref") or "")
        intent = qg.normalize_writing_intent(p.get("writingIntent")) or "unknown"
        intent_dist[intent] = intent_dist.get(intent, 0) + 1
        media_mode = str(p.get("articleMediaMode") or "")
        media_issue = str(p.get("articleMediaIssue") or "").strip()
        if media_issue or media_mode not in {"illustrated", "text_only"}:
            detail = media_issue or "typed article media closure mode is missing"
            issues.append(f"{ref}: article_media_closure: {detail}")
            affected.add(ref)
            media_modes[ref] = "invalid"
        else:
            media_modes[ref] = media_mode

    valid_modes = {
        ref: mode for ref, mode in media_modes.items() if mode != "invalid"
    }
    illustrated_refs = sorted(
        ref for ref, mode in valid_modes.items() if mode == "illustrated"
    )
    text_only_refs = sorted(
        ref for ref, mode in valid_modes.items() if mode == "text_only"
    )
    valid_count = len(valid_modes)
    allowed_text_only = valid_count // 10
    excess_text_only = max(0, len(text_only_refs) - allowed_text_only)
    if excess_text_only:
        rejected_text_only = text_only_refs[-excess_text_only:]
        issues.append(
            "article_media_coverage: illustrated must be >=90% and text_only "
            f"<=10% (illustrated={len(illustrated_refs)}/{valid_count}, "
            f"textOnly={len(text_only_refs)}/{valid_count})"
        )
        affected.update(rejected_text_only)
    illustrated_rate = (
        round(len(illustrated_refs) / valid_count, 6) if valid_count else 0.0
    )
    text_only_rate = (
        round(len(text_only_refs) / valid_count, 6) if valid_count else 0.0
    )
    image_coverage: dict[str, Any] = {
        "articleCount": valid_count,
        "illustratedCount": len(illustrated_refs),
        "textOnlyCount": len(text_only_refs),
        "illustratedRate": illustrated_rate,
        "textOnlyRate": text_only_rate,
        "modesByRef": dict(sorted(media_modes.items())),
    }

    return {
        "schema": "quwoquan_data.execution_reducer_gate",
        "passed": not issues,
        "issues": issues,
        "affectedRefs": sorted(affected),
        "sourceReuse": source_reuse,
        "intentDistribution": intent_dist,
        "imageCoverage": image_coverage,
    }


def write_execution_reducer_gate(execution_id: str, gate: Mapping[str, Any]) -> str:
    path = execution_root(execution_id) / "_shared" / "execution_reducer_gate.json"
    write_json(path, dict(gate))
    return str(path)
