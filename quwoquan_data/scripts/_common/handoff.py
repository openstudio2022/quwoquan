"""Subagent handoff packet 与出口门（single ref gate + batch reducer gate）。

把"主 Agent 调度 ↔ Subagent 单篇创作"的交接结构化（整改计划第一阶段补充）：
- author_job_packet：发给 Subagent 的单 ref 输入包（意图/底稿/图片槽位/禁用语域/出口门）。
- ref_review_gate：单篇出口门（Subagent 不能只说"我完成了"，必须有文件 + self-check + review 决策）。
- batch_reducer_gate：批次级归并门（跨篇骨架相似度、baseSourceRef 复用、writingIntent 分布、图文分布）。

reducer 复用单一门库 _common/quality_gates，不另写一套相似度。
"""
from __future__ import annotations

from typing import Any, Mapping

from _common import public_contacts as pc
from _common import quality_gates as qg
from _common.io import write_json
from _common.paths import batch_root


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
    max_wall_clock_seconds: int = 1200,
    max_attempts: int = 2,
    stuck_threshold: int = 3,
) -> dict[str, Any]:
    return {
        "inputs": inputs
        or ["4.draft/author_job_packet.json", "3.compose/writing_pack.json", "2.quality/*"],
        "budget": {
            "maxWallClockSeconds": int(max_wall_clock_seconds),
            "maxAttempts": int(max_attempts),
            "stuckThreshold": int(stuck_threshold),
        },
        "permissions": list(permissions) if permissions is not None else list(DEFAULT_AUTHOR_PERMISSIONS),
        "completionConditions": [
            "4.draft/draft.article.md 已写且非占位",
            "4.draft/author_self_check.json 存在",
            "ref_review_gate.passed == true (reviewDecision == approved)",
        ],
        "outputPaths": [
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
    ref: str,
    brief: Mapping[str, Any],
    writing_pack: Mapping[str, Any],
    prompt_rel: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": "quwoquan_data.author_job_packet/1",
        "ref": ref,
        "writingIntent": writing_pack.get("writingIntent") or brief.get("writingIntent"),
        "baseSourceRef": writing_pack.get("baseSourceRef") or brief.get("baseSourceRef"),
        "title": writing_pack.get("title") or brief.get("titleHint"),
        "carrier": writing_pack.get("carrier") or brief.get("carrier"),
        "promptRef": prompt_rel,
        "writingPackRef": "3.compose/writing_pack.json",
        "mustIncludeFacts": list(writing_pack.get("mustIncludeFacts") or []),
        "bannedRegisterTerms": list(writing_pack.get("bannedRegisterTerms") or []),
        "assets": [
            {"assetId": a.get("assetId"), "entityName": a.get("entityName"), "imageLayout": a.get("imageLayout")}
            for a in (writing_pack.get("assets") or [])
            if a.get("assetId")
        ],
        "exitGates": [
            "writingIntentConsistency",
            "imageReferenceClosure",
            "skeletonSimilarity",
            "registerMismatch",
            "sourceRejectBlock",
            "contactInfo",
            "mechanicalHeading",
        ],
        "executionContract": build_execution_contract(),
        "isolation": "single-ref: 只读本 ref 的 packet/SOP/source，禁止读取同批其它文章正文作为底稿",
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
        "schemaVersion": "quwoquan_data.ref_review_gate/1",
        "ref": ref,
        "passed": passed,
        "reviewDecision": review_decision,
        "issues": gate_issues,
    }


# ---------------------------------------------------------------------------
# batch_reducer_gate：批次级归并门
# ---------------------------------------------------------------------------
def build_batch_reducer_gate(refs_payload: list[Mapping[str, Any]]) -> dict[str, Any]:
    """refs_payload: 每条 {ref, article, writingIntent, baseSourceRef}。

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
    for base, users in source_reuse.items():
        issues.append(f"source_reuse_risk: baseSourceRef {base} reused by {users} (需人工确认或重选底稿)")
        affected.update(users)

    # writingIntent 分布 + 图文分布
    intent_dist: dict[str, int] = {}
    image_coverage: dict[str, int] = {}
    for p in refs_payload:
        intent = qg.normalize_writing_intent(p.get("writingIntent")) or "unknown"
        intent_dist[intent] = intent_dist.get(intent, 0) + 1
        image_coverage[str(p.get("ref"))] = len(qg._ASSET_REF_RE.findall(str(p.get("article") or "")))

    return {
        "schemaVersion": "quwoquan_data.batch_reducer_gate/1",
        "passed": not issues,
        "issues": issues,
        "affectedRefs": sorted(affected),
        "sourceReuse": source_reuse,
        "intentDistribution": intent_dist,
        "imageCoverage": image_coverage,
    }


def write_batch_reducer_gate(task_id: str, batch_id: str, gate: Mapping[str, Any]) -> str:
    path = batch_root(task_id, batch_id) / "_shared" / "batch_reducer_gate.json"
    write_json(path, dict(gate))
    return str(path)
