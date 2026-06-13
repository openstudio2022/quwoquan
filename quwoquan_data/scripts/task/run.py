"""workflow run — 无人值守任务编排器（DAG 薄编排壳，目标① 全流程自动化）。

把零散的 download/build/plan/produce/review/publish 串成固定 DAG，运营只在入口
(task.yaml) 与出口(抽检)介入，中间不再逐步手敲 10+ 条 CLI。

设计原则（与 13-coding-discipline R24 抽象克制一致）：
- 薄编排：不重写任何 stage 逻辑，只按 DAG 顺序调用既有 handler / 既有薄函数。
- 双类节点：
  * 确定性节点(deterministic)：CLI 直接跑（download fetch / build validate /
    produce review --materialize / publish）。
  * Agent checkpoint：写 assistant_tasks 清单 + 暂停，输出明确指引；Agent 物化产物
    后用 `workflow run --resume` 继续。这是「Agent 会话创作 = 自动化执行者」的接缝，
    不是人手工断点。
- 可 resume：workflow 状态落 runtime/tasks/<taskId>/batches/<batch>/task_workflow_state.json，
  记录已完成 stage、当前等待的 checkpoint、ReAct 回退指针与 baseline 冻结件。

DAG（stage 序）：
  download_plan(checkpoint:Agent 写 source_plan)
  -> download_fetch(auto)
  -> build_prepare(auto 下发主页契约) -> build_homepage(checkpoint:Agent 写 page 三件套)
  -> build_validate(auto 采纳门)
  -> content_plan(checkpoint:Agent 证据驱动篇目+注册+brief)
  -> produce_plan(auto 校验 brief 或 legacy 每实体 brief)
  -> produce_compose(auto compose-brief) -> produce_author(checkpoint:Agent 写 article)
  -> produce_annotate(auto) -> produce_review(auto review+media gate --materialize)
  -> publish(auto)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from _common.entity_extract import require_domain_etype
from _common.io import read_json, write_json
from _common.paths import (
    batch_root,
    batch_workflow_packet_path,
    task_baseline_freeze_packet_path,
    ensure_batch_layout,
)
from task import store

WORKFLOW_STATE_VERSION = "quwoquan.task.workflow_state"
PIPELINE_STATE_VERSION = WORKFLOW_STATE_VERSION

# 节点类型
AUTO = "auto"          # CLI 确定性执行
CHECKPOINT = "checkpoint"  # 等待 Agent 物化产物后 resume


@dataclass
class StageResult:
    """单 stage 执行结果。"""
    stage: str
    kind: str
    status: str           # done | waiting | failed | skipped
    message: str = ""
    checkpoint_hint: str = ""
    fallback_stage: str | None = None   # ReAct 回退目标 DAG stage（failed 时消费）
    issues: list[str] = field(default_factory=list)


# ReAct 回退：CLI gate fallbackStage(download/compose) → DAG stage
# 语义：证据不足回到检索 checkpoint；质量不达回到 compose 重组。
FALLBACK_DAG_STAGE = {
    "download": "download_plan",
    "compose": "produce_compose",
    "agent_compose": "produce_compose",
    "manual": "produce_compose",
    "produce_compose": "produce_compose",
    "download_plan": "download_plan",
}
MAX_REACT_REWINDS = 2  # 单 stage 自动回退次数上限，超出转人工，防无限自省
MAX_MANAGED_INFRA_RETRIES = 3


@dataclass
class PipelineContext:
    task_id: str
    batch_id: str
    entity_ids: list[str]
    spec: dict
    baseline_packet: dict | None = None
    baseline_packet_path: Path | None = None
    until: str | None = None
    completed: list[str] = field(default_factory=list)
    managed: bool = False
    runtime: str = "local"
    max_workers: int = 3
    model: str = "composer-2.5"
    release_only: bool = False
    agent_runner: Callable[[str], dict[str, Any]] | None = None


def _write_workflow_packet(
    ctx: PipelineContext,
    *,
    stage_name: str,
    kind: str,
    result: StageResult,
    completed: list[str],
    next_stage: str | None,
    state: dict,
) -> Path:
    from _common.command_packet import build_packet, write_packet

    packet = build_packet(
        task_id=ctx.task_id,
        command="data workflow run",
        object_kind="workflow",
        object_ref=f"{ctx.task_id}::{ctx.batch_id}",
        stage=stage_name,
        read_policy=[
            "baseline_freeze_packet.json",
            "workflow_state.json",
            "current stage inputs",
        ],
        stop_if=[f"stage {stage_name} failed", f"stage {stage_name} waiting"] if result.status != "done" else [],
        output_policy=[
            "write _shared/workflow_packets/<stage>.json",
            "write _shared/task_workflow_state.json",
            "advance only when gate is green",
        ],
        inputs={
            "baselinePacketPath": str(ctx.baseline_packet_path or ""),
            "completedStages": completed,
            "waitingCheckpoint": state.get("waitingCheckpoint"),
            "until": ctx.until or "",
        },
        outputs={
            "status": result.status,
            "message": result.message,
            "checkpointHint": result.checkpoint_hint,
            "fallbackStage": result.fallback_stage,
            "issues": list(result.issues),
            "nextStage": next_stage or "",
        },
        handoff_to=result.fallback_stage or (next_stage or stage_name),
        evidence={
            "kind": kind,
            "completed": result.status == "done",
            "issueCount": len(result.issues),
        },
        summary={
            "taskId": ctx.task_id,
            "batchId": ctx.batch_id,
            "stage": stage_name,
            "status": result.status,
            "message": result.message,
        },
    )
    return write_packet(batch_workflow_packet_path(ctx.task_id, ctx.batch_id, stage_name), packet)


def _state_path(task_id: str, batch_id: str) -> Path:
    from _common.paths import batch_workflow_state_path
    return batch_workflow_state_path(task_id, batch_id)


def load_workflow_state(task_id: str, batch_id: str) -> dict:
    p = _state_path(task_id, batch_id)
    if p.exists():
        return read_json(p)
    return {
        "schemaVersion": WORKFLOW_STATE_VERSION,
        "taskId": task_id,
        "batchId": batch_id,
        "completed": [],
        "waitingCheckpoint": None,
        "status": "queued",
        "owner": None,
        "heartbeatAt": None,
        "retryCounts": {},
        "infrastructureRetryCounts": {},
        "failedObjects": [],
        "nextAction": None,
        "updatedAt": store.now_iso(),
    }


def save_workflow_state(state: dict) -> Path:
    state["updatedAt"] = store.now_iso()
    p = _state_path(state["taskId"], state["batchId"])
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, state)
    return p


def _load_baseline_packet(task_id: str, packet_path: Path | None = None) -> tuple[Path, dict]:
    path = packet_path or task_baseline_freeze_packet_path(task_id)
    if not path.is_file():
        raise RuntimeError(
            f"missing baseline freeze packet: {path}. "
            f"Run `qwq-data data baseline --task {task_id}` first."
        )
    packet = read_json(path)
    if not isinstance(packet, dict):
        raise RuntimeError(f"baseline freeze packet unreadable: {path}")
    if str(packet.get("taskId") or "").strip() != task_id:
        raise RuntimeError(
            f"baseline freeze packet taskId mismatch: {packet.get('taskId')} != {task_id}"
        )
    if str(packet.get("command") or "").strip() != "data baseline":
        raise RuntimeError(f"baseline freeze packet command mismatch: {packet.get('command')}")
    return path, packet


# ─── coverage 实体解析（download/build 的输入）────────────────────────
def _coverage_entity_ids(spec: dict) -> list[str]:
    out: list[str] = []
    for target in (spec.get("scope") or {}).get("coverageTargets") or []:
        name = str(target.get("name") or "").strip()
        if name:
            out.append(name)
    return out


# ─── checkpoint 完成度探测（resume 判定 Agent 是否已物化产物）──────────
def _coverage_entity_type(spec: dict) -> str:
    """coverageTargets/entityTypes 的唯一类型真相源；显式任务必须给出明确类型。"""
    scope = spec.get("scope") or {}
    targets = scope.get("coverageTargets") or []
    target_types = {
        str(target.get("entityType") or "").strip()
        for target in targets
        if str(target.get("entityType") or "").strip()
    }
    if len(target_types) > 1:
        raise ValueError(
            "workflow currently requires a single entityType across coverageTargets; "
            f"got {sorted(target_types)}"
        )
    if target_types:
        only = next(iter(target_types))
        require_domain_etype(only, context="scope.coverageTargets[].entityType")
        return only
    types = [str(item).strip() for item in (scope.get("entityTypes") or []) if str(item).strip()]
    if not types:
        return ""
    require_domain_etype(types[0], context="scope.entityTypes[0]")
    return types[0]


def _source_plan_filled(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """download_plan checkpoint：来源数量、权利模式和图片计划均满足任务规模。"""
    from download.gate import download_requirements
    from download.source_inputs import (
        curated_images_for_entity,
        curated_sources_for_entity,
        source_plan_rights_issues,
    )
    from _common.image_rules import relevance_issue
    from vertical.license import validate_image_rights

    etype = _coverage_entity_type(ctx.spec)
    requirements = download_requirements(ctx.task_id)
    missing: list[str] = []
    for eid in ctx.entity_ids:
        sources = curated_sources_for_entity(ctx.task_id, ctx.batch_id, eid, etype)
        images = curated_images_for_entity(ctx.task_id, ctx.batch_id, eid, etype)
        issues = source_plan_rights_issues(
            ctx.task_id,
            ctx.batch_id,
            eid,
            etype,
            require_explicit=requirements["minSources"] >= 4,
        )
        for index, image in enumerate(images, start=1):
            issues.extend(
                f"image[{index}]: {issue}"
                for issue in validate_image_rights(image, vertical=str(ctx.spec.get("vertical") or "travel"))
            )
            relevance = str(image.get("relevance") or image.get("caption") or "")
            rel_issue = relevance_issue(
                relevance,
                entity_id=eid,
                asset_id=f"{eid}#{index}",
            )
            if rel_issue:
                issues.append(f"image[{index}]: {rel_issue}")
        if len(sources) < requirements["minSources"]:
            issues.append(f"sources={len(sources)} need>={requirements['minSources']}")
        if len(images) < requirements["minImages"]:
            issues.append(f"imageUrls={len(images)} need>={requirements['minImages']}")
        if issues:
            missing.append(f"{eid}: " + "; ".join(issues[:8]))
    return (not missing), missing


def _homepages_done(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """build_homepage checkpoint：coverage 实体三件套是否物化（用 build validate 复核）。"""
    from build.homepage import validate_entity_pages
    issues = validate_entity_pages(ctx.task_id, ctx.batch_id, ctx.spec)
    return (not issues), issues


def _content_plan_done(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """content_plan checkpoint：篇目包+注册+brief 是否就绪。"""
    from _common.content_plan import validate_content_plan

    issues = validate_content_plan(ctx.task_id, ctx.batch_id, ctx.spec)
    return (not issues), issues


def _drafts_authored(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """produce_author checkpoint：compose 后的 drafts 是否被 Agent 创作（非占位）。"""
    from _common.draft_io import is_placeholder, iter_draft_articles
    articles = iter_draft_articles(ctx.task_id, ctx.batch_id)
    if not articles:
        return False, ["(no article drafts; run compose-brief first)"]
    pending: list[str] = []
    for ref, art in articles:
        if is_placeholder(art.read_text(encoding="utf-8")):
            pending.append(ref)
    return (not pending), pending


def _content_issue_matchers(ctx: PipelineContext) -> dict[str, set[str]]:
    from _common import content_object

    matchers: dict[str, set[str]] = {}
    for ref in content_object.iter_content_refs(ctx.task_id, ctx.batch_id):
        tokens = {ref}
        try:
            rel = content_object.content_object_rel(ctx.task_id, ctx.batch_id, ref)
        except KeyError:
            matchers[ref] = tokens
            continue
        tokens.add(rel)
        if rel.startswith("posts/"):
            tokens.add(rel[len("posts/"):])
        matchers[ref] = {token for token in tokens if token}
    return matchers


def _produce_review_retry_refs(ctx: PipelineContext, issues: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """把 produce_review 的批次级问题尽量映射回受影响 ref；无法精确定位时保守回退全批。"""
    from _common import content_object
    from _common.stage_reports import iter_stage_envelopes

    matchers = _content_issue_matchers(ctx)
    affected: set[str] = set()
    for ref, env in iter_stage_envelopes(ctx.task_id, ctx.batch_id, "produce", "review_gate"):
        payload = env.get("payload") or {}
        if payload.get("passed") is False:
            affected.add(ref)

    issue_map: dict[str, list[str]] = {}
    unmatched: list[str] = []
    for raw_issue in issues or []:
        issue = str(raw_issue)
        matched_refs = [
            ref
            for ref, tokens in matchers.items()
            if any(token and token in issue for token in tokens)
        ]
        if not matched_refs:
            unmatched.append(issue)
            continue
        for ref in matched_refs:
            affected.add(ref)
            issue_map.setdefault(ref, []).append(issue)

    if not affected:
        affected = set(content_object.iter_content_refs(ctx.task_id, ctx.batch_id))

    refs = sorted(affected)
    for ref in refs:
        issue_map.setdefault(ref, [])
    if unmatched:
        for ref in refs:
            issue_map[ref].extend(unmatched)
    return refs, issue_map


def _invalidate_ref_for_retry(ctx: PipelineContext, ref: str) -> bool:
    """清理旧草稿/旧成品，让 rewound workflow 真正回到待重写状态。"""
    from _common import content_object
    from _common.draft_io import draft_package_dir, write_placeholder_draft

    try:
        obj_dir = content_object.content_object_dir(ctx.task_id, ctx.batch_id, ref)
        draft_dir = draft_package_dir(ctx.task_id, ctx.batch_id, ref)
    except KeyError:
        return False

    write_placeholder_draft(ctx.task_id, ctx.batch_id, ref)

    author_self_check = draft_dir / "author_self_check.json"
    if author_self_check.is_file():
        author_self_check.unlink()

    review_dir = obj_dir / "5.review"
    for name in ("ref_review_gate.json", "provenance.json", "review_ledger.json", "review_entities.json"):
        path = review_dir / name
        if path.is_file():
            path.unlink()

    for name in ("article.md", "gallery.md", "manifest.json", "_object.json"):
        path = obj_dir / name
        if path.is_file():
            path.unlink()

    assets_dir = obj_dir / "assets"
    if assets_dir.is_dir():
        shutil.rmtree(assets_dir)

    content_object.write_content_object_index(ctx.task_id, ctx.batch_id, ref)
    return True


def _purge_author_queue_for_stale_workflow(
    ctx: PipelineContext,
    *,
    refs: list[str] | None = None,
    reason: str,
) -> None:
    from task import object_queue as oq

    result = oq.purge_jobs(ctx.task_id, ctx.batch_id, stage="author", refs=refs)
    removed = result.get("removed") or []
    if removed:
        print(
            f"[task run] 已清理过期 author queue ({reason}): "
            + ", ".join(removed[:12])
            + (" ..." if len(removed) > 12 else "")
        )


def _write_retry_reports_for_refs(
    ctx: PipelineContext,
    *,
    refs: list[str],
    issue_map: dict[str, list[str]],
    target_stage: str,
) -> None:
    from _common.stage_reports import write_repair_report

    fallback_stage = "download" if target_stage == "download_plan" else "agent_compose"
    rerun_chain = (
        ["download", "quality_analysis", "compose-brief", "review", "materialize"]
        if fallback_stage == "download"
        else ["agent_compose", "review", "materialize"]
    )
    for ref in refs:
        write_repair_report(
            task_id=ctx.task_id,
            batch_id=ctx.batch_id,
            command="produce",
            ref=ref,
            failed_stage="review",
            failed_gate="post_verify",
            issues=issue_map.get(ref) or ["produce_review gate failed; inspect current batch issues"],
            fallback_stage=fallback_stage,
            rerun_chain=rerun_chain,
        )


def _prepare_produce_review_retry(ctx: PipelineContext, result: StageResult, target_stage: str) -> None:
    from task import object_queue as oq
    from _common.draft_io import read_writing_pack

    refs, issue_map = _produce_review_retry_refs(ctx, result.issues)
    if not refs:
        return
    _write_retry_reports_for_refs(ctx, refs=refs, issue_map=issue_map, target_stage=target_stage)
    if target_stage == "download_plan":
        _purge_author_queue_for_stale_workflow(ctx, reason="produce_review->download_plan")
        return
    _purge_author_queue_for_stale_workflow(ctx, refs=refs, reason="produce_review->produce_compose")
    reset = [ref for ref in refs if _invalidate_ref_for_retry(ctx, ref)]
    requeued = oq.requeue_refs(ctx.task_id, ctx.batch_id, reset, "author", reason="produce_review_retry") if reset else []
    missing = [ref for ref in reset if ref not in set(requeued)]
    for ref in missing:
        pack = read_writing_pack(ctx.task_id, ctx.batch_id, ref) or {}
        oq.enqueue_ref_job(
            ctx.task_id,
            ctx.batch_id,
            ref,
            "author",
            mutex_key=str(pack.get("baseSourceRef") or ref),
        )
    if reset:
        print(
            "[task run] 已为 produce_review 回退重置待重写 ref: "
            + ", ".join(reset[:12])
            + (" ..." if len(reset) > 12 else "")
        )


# ─── 确定性 stage 执行（复用既有 handler）─────────────────────────────
def _run_download_fetch(ctx: PipelineContext) -> StageResult:
    from download.handler import handle_download
    from download.gate import gate_download
    ns = argparse.Namespace(
        task=ctx.task_id, batch=ctx.batch_id,
        entity_ids=",".join(ctx.entity_ids),
        entity_type=(ctx.spec.get("scope") or {}).get("entityTypes", [""])[0]
        if (ctx.spec.get("scope") or {}).get("entityTypes") else "",
    )
    try:
        handle_download(ns)
    except SystemExit as exc:
        code = int(getattr(exc, "code", 1) or 0)
        if code not in (0,):
            issues = gate_download(ctx.task_id, ctx.batch_id)
            message = f"download gate failed with exit code {code}"
            if issues:
                message += ": " + "; ".join(issues[:5])
            return StageResult(
                "download_fetch",
                AUTO,
                "failed",
                message,
                fallback_stage="download_plan",
                issues=issues,
            )
    except Exception as exc:  # noqa: BLE001
        return StageResult(
            "download_fetch",
            AUTO,
            "failed",
            f"download handler failed: {exc}",
            fallback_stage="download_plan",
            issues=[str(exc)],
        )

    issues = gate_download(ctx.task_id, ctx.batch_id)
    if issues:
        return StageResult(
            "download_fetch",
            AUTO,
            "failed",
            "download gate failed:\n  - " + "\n  - ".join(issues[:10]),
            fallback_stage="download_plan",
            issues=issues,
        )
    return StageResult("download_fetch", AUTO, "done", "fetched sources for coverage entities")


def _run_build_prepare(ctx: PipelineContext) -> StageResult:
    from build.homepage import prepare_entity_pages
    inputs_dir, refs = prepare_entity_pages(ctx.task_id, ctx.batch_id, ctx.spec)
    return StageResult("build_prepare", AUTO, "done", f"下发 {len(refs)} 个主页产出契约 -> {inputs_dir}")


def _run_build_validate(ctx: PipelineContext) -> StageResult:
    from build.homepage import validate_entity_pages
    issues = validate_entity_pages(ctx.task_id, ctx.batch_id, ctx.spec)
    if issues:
        return StageResult("build_validate", AUTO, "failed",
                           "主页采纳门未过:\n  - " + "\n  - ".join(issues[:10]),
                           fallback_stage="build_homepage", issues=issues)
    return StageResult("build_validate", AUTO, "done", "所有 coverage 实体主页达标")


# 角度 → plan intent 映射（task.content.angles → blueprint intent）。
# 编排器默认每实体取首个 angle 生成 1 篇代表作，控制单批产量；
# 全角度扩产由独立 batch 串跑（refs 显式扩展），不在单次 run 内放大成 N×M。
_DEFAULT_ANGLE = "攻略"


def _entity_type_kind(entity_type: str) -> str:
    """scope.entityTypes 形如 '地点/景区' → plan 的 kind '景区'。"""
    return str(entity_type or "").split("/")[-1] or "景区"


def _run_produce_plan(ctx: PipelineContext) -> StageResult:
    """校验 content_plan 已物化 brief；无 quotas 时 legacy 每实体自动 brief。"""
    from _common.content_plan import (
        content_plan_quotas_required,
        load_content_plan_packet,
        validate_content_plan,
    )

    if content_plan_quotas_required(ctx.spec):
        issues = validate_content_plan(ctx.task_id, ctx.batch_id, ctx.spec)
        if issues:
            return StageResult(
                "produce_plan",
                AUTO,
                "failed",
                "content_plan 未就绪:\n  - " + "\n  - ".join(issues[:10]),
                fallback_stage="content_plan",
                issues=issues,
            )
        packet = load_content_plan_packet(ctx.task_id, ctx.batch_id) or {}
        n = len(packet.get("items") or [])
        return StageResult(
            "produce_plan",
            AUTO,
            "done",
            f"content_plan 已物化 {n} 篇 brief，跳过自动 produce_plan",
        )

    from plan.brief import resolve_compose_brief
    from plan.handler import ENTITY_KIND_MAP
    from template.registry import TemplateRegistry
    from template.router import RouteRequest
    from _common.content_object import write_brief_object

    registry = TemplateRegistry.load()
    angles = (ctx.spec.get("content") or {}).get("angles") or [_DEFAULT_ANGLE]
    intent = str(angles[0])
    vertical = "campus" if str(ctx.spec.get("vertical")) == "campus" else "travel"

    written: list[str] = []
    for target in (ctx.spec.get("scope") or {}).get("coverageTargets") or []:
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        etype = str(target.get("entityType") or "").strip()
        require_domain_etype(etype, context=f"coverageTargets[{name}]")
        kind = _entity_type_kind(etype)
        subject_type = ENTITY_KIND_MAP.get(kind, etype)
        entity_ref = f"/entity/{etype}/{name}"
        request = RouteRequest(
            vertical=vertical,
            subject_kind="entity",
            subject_type=subject_type,
            intent=intent,
        )
        brief = resolve_compose_brief(
            registry, request, title=f"{name}·{intent}", entity_refs=[entity_ref]
        )
        ref = f"{etype}__{name}".replace("/", "_")
        write_brief_object(ctx.task_id, ctx.batch_id, ref, brief, content_type="article")
        written.append(ref)
    return StageResult("produce_plan", AUTO, "done",
                       f"解析 {len(written)} 个实体 compose brief(intent={intent}) -> posts/.../3.compose/brief.json")


def _run_produce_compose(ctx: PipelineContext) -> StageResult:
    from produce.handler import handle_produce
    ns = argparse.Namespace(
        task=ctx.task_id, batch=ctx.batch_id, type="article",
        stage="compose-brief", refs="", batch_size=1,
        allow_partial=False, materialize=False,
    )
    handle_produce(ns)
    return StageResult("produce_compose", AUTO, "done", "compose-brief 写出 writing_pack + prompt")


def _run_produce_annotate(ctx: PipelineContext) -> StageResult:
    from produce.handler import handle_produce
    ns = argparse.Namespace(
        task=ctx.task_id, batch=ctx.batch_id, type="article",
        stage="annotate-entities", refs="", batch_size=1,
        allow_partial=True, materialize=False,
    )
    handle_produce(ns)
    return StageResult("produce_annotate", AUTO, "done", "实体 inline 标注完成")


def _aggregate_review_fallback(ctx: PipelineContext) -> str | None:
    """聚合 produce review gate reports 的 fallbackStage（ReAct 回退指针）。

    优先返回 download(证据不足)，否则 compose(质量/重组)；都没有则 None。
    """
    from _common.stage_reports import iter_stage_envelopes
    fallbacks: set[str] = set()
    for _ref, rep in iter_stage_envelopes(ctx.task_id, ctx.batch_id, "produce", "review_gate"):
        fb = (rep.get("payload") or rep).get("fallbackStage")
        if fb:
            fallbacks.add(str(fb))
    if "download" in fallbacks:
        return "download"
    if fallbacks:
        return sorted(fallbacks)[0]
    return None


def _run_produce_review(ctx: PipelineContext) -> StageResult:
    from produce.handler import handle_produce
    from produce.gate import gate_produce
    from _common import content_object
    from _common.draft_io import read_draft_article, read_writing_pack
    from _common.handoff import build_batch_reducer_gate, write_batch_reducer_gate
    ns = argparse.Namespace(
        task=ctx.task_id, batch=ctx.batch_id, type="article",
        stage="review", refs="", batch_size=1,
        allow_partial=True, materialize=True,
    )
    handle_produce(ns)
    issues = gate_produce(ctx.task_id, ctx.batch_id, "article")
    refs_payload: list[dict[str, str]] = []
    for ref in content_object.iter_content_refs(ctx.task_id, ctx.batch_id):
        article = read_draft_article(ctx.task_id, ctx.batch_id, ref)
        pack = read_writing_pack(ctx.task_id, ctx.batch_id, ref) or {}
        if not article:
            continue
        refs_payload.append(
            {
                "ref": ref,
                "article": article,
                "writingIntent": str(pack.get("writingIntent") or ""),
                "baseSourceRef": str(pack.get("baseSourceRef") or ""),
            }
        )
    batch_gate = build_batch_reducer_gate(refs_payload) if refs_payload else {
        "schemaVersion": "quwoquan_data.batch_reducer_gate/1",
        "passed": False,
        "issues": ["batchReducer: no draft payloads available after produce_review"],
        "affectedRefs": [],
        "sourceReuse": {},
        "intentDistribution": {},
        "imageCoverage": {},
    }
    write_batch_reducer_gate(ctx.task_id, ctx.batch_id, batch_gate)
    if batch_gate.get("passed") is False:
        issues.extend([str(issue) for issue in (batch_gate.get("issues") or [])])
    if issues:
        fb = _aggregate_review_fallback(ctx) or "produce_compose"
        return StageResult("produce_review", AUTO, "failed",
                           "发布门未过:\n  - " + "\n  - ".join(issues[:10]),
                           fallback_stage=fb, issues=issues)
    return StageResult("produce_review", AUTO, "done", "review + materialize approved，发布门通过")


# ─── checkpoint 指引 ──────────────────────────────────────────────────
def _checkpoint_download_plan(ctx: PipelineContext) -> StageResult:
    ok, missing = _source_plan_filled(ctx)
    if ok:
        return StageResult("download_plan", CHECKPOINT, "done", "source_plan 已就绪")
    # 预置对象优先 source_plan 骨架（entities/{d}/{t}/{name}/1.download/source_plan.json），Agent 填 URL+body
    from download.prepare import prepare_source_plan
    etype = _coverage_entity_type(ctx.spec)
    entities = [{"entityId": e, "canonicalName": e, "entityType": etype} for e in ctx.entity_ids]
    prepare_source_plan(ctx.task_id, ctx.batch_id, entities)
    hint = (
        f"[CHECKPOINT download_plan] Agent 检索真实素材，为以下实体写满足规模化门的 source_plan：\n"
        f"  待补实体: {missing}\n"
        f"  写入: entities/<domain>/<type>/<entityId>/1.download/source_plan.json\n"
        f"  每实体至少 4 个真实可抓取来源、10 张不重复可发布图片；来源须写 sourceUseMode，"
        f"图片须写 license/credit/sourceUrl/termsUrl/usageScope/relevance。\n"
        f"  完成后: qwq-data data workflow run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("download_plan", CHECKPOINT, "waiting", "等待 Agent 写 source_plan", hint)


def _checkpoint_content_plan(ctx: PipelineContext) -> StageResult:
    ok, issues = _content_plan_done(ctx)
    if ok:
        return StageResult("content_plan", CHECKPOINT, "done", "证据驱动篇目已就绪")
    from _common.content_plan import content_plan_quotas_required

    quotas = (ctx.spec.get("content") or {}).get("quotas") or {}
    per_target_entity = int(quotas.get("entityArticlesPerTarget") or 0)
    per_target_gallery = int(quotas.get("galleryPostsPerTarget") or 0)
    entity_q = (
        per_target_entity * len(ctx.entity_ids)
        if per_target_entity
        else int(quotas.get("entityArticles") or 0)
    ) if content_plan_quotas_required(ctx.spec) else 0
    route_q = int(quotas.get("routeArticles") or 0) if content_plan_quotas_required(ctx.spec) else 0
    gallery_q = (
        per_target_gallery * len(ctx.entity_ids)
        if per_target_gallery
        else int(quotas.get("galleryPosts") or 0)
    ) if content_plan_quotas_required(ctx.spec) else 0
    hint = (
        f"[CHECKPOINT content_plan] Agent 通读已下载来源，证据驱动规划 "
        f"{entity_q} 篇文章 + {gallery_q} 个画报 + {route_q} 篇线路：\n"
        f"  产出: batches/{ctx.batch_id}/_shared/content_plan_packet.json\n"
        f"  每条: ref, kind(entity|route), title, entityRefs, evidenceRefs(相对batch路径), rationale, mustIncludeFacts,\n"
        f"        writingIntent(planning_consultation|decision_experience|post_trip_journal 三选一，单篇唯一主线),\n"
        f"        baseSourceRef(主底稿来源 ref，作为风格与事实锚点；其它来源只能补事实)\n"
        f"  并 register_content_object + 写 posts/.../3.compose/brief.json（禁止预置营销 ref；brief 写入 writingIntent/baseSourceRef）\n"
        f"  未过项:\n    - " + "\n    - ".join(issues[:12]) + "\n"
        f"  完成后: qwq-data data workflow run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("content_plan", CHECKPOINT, "waiting", "等待 Agent 证据驱动篇目规划", hint)


def _checkpoint_build_homepage(ctx: PipelineContext) -> StageResult:
    ok, issues = _homepages_done(ctx)
    if ok:
        return StageResult("build_homepage", CHECKPOINT, "done", "实体主页三件套已就绪")
    hint = (
        f"[CHECKPOINT build_homepage] Agent 按 SOP 为 coverage 实体物化主页三件套：\n"
        f"  契约: entities/<domain>/<type>/<name>/3.compose/entity_page_input.json\n"
        f"  产出: page.md(≥800字) + _entity.json(含 conditionProfile) + manifest.json\n"
        f"  采纳门未过项:\n    - " + "\n    - ".join(issues[:10]) + "\n"
        f"  完成后: qwq-data data workflow run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("build_homepage", CHECKPOINT, "waiting", "等待 Agent 写实体主页", hint)


def _checkpoint_produce_author(ctx: PipelineContext) -> StageResult:
    ok, pending = _drafts_authored(ctx)
    if ok:
        return StageResult("produce_author", CHECKPOINT, "done", "正文已由 Agent 创作")
    hint = (
        f"[CHECKPOINT produce_author] Agent 逐篇创作正文(generator=agent)：\n"
        f"  草稿目录: posts/<type>/<angle>/<title>/<seq>/4.draft/\n"
        f"  读 <ref>/prompt.md + <ref>/writing_pack.json，写回 <ref>/draft.article.md\n"
        f"  draft_meta 记 model/styleFamily/openingStrategy/extractedEntities\n"
        f"  待创作: {pending}\n"
        f"  完成后: qwq-data data workflow run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("produce_author", CHECKPOINT, "waiting", "等待 Agent 创作正文", hint)


def _workflow_release_id(task_id: str, batch_id: str) -> str:
    task_slug = task_id.replace("/", "__")
    return f"{task_slug}__{batch_id}"


def _run_publish(ctx: PipelineContext) -> StageResult:
    from _common import content_object
    from _common.publish_materialization import materialize_task_publish_inputs
    from publish.handler import handle_publish
    from task import object_queue as oq
    summary = materialize_task_publish_inputs(ctx.task_id, ctx.batch_id)
    if summary["entityCount"] <= 0 or summary["postCount"] <= 0:
        return StageResult(
            "publish",
            AUTO,
            "failed",
            "publish 前未物化出完整任务级输入",
            fallback_stage="produce_review",
        )
    ns = argparse.Namespace(
        task=ctx.task_id,
        batch=ctx.batch_id,
        release_id=_workflow_release_id(ctx.task_id, ctx.batch_id),
        push_to_service=None,
    )
    try:
        handle_publish(ns)
    except SystemExit as exc:
        code = int(getattr(exc, "code", 1) or 0)
        return StageResult(
            "publish",
            AUTO,
            "failed",
            f"release package assemble/gate failed with exit code {code}",
            fallback_stage="produce_review",
        )
    if ctx.managed or ctx.release_only:
        from verify.gate import gate_verify

        release_id = _workflow_release_id(ctx.task_id, ctx.batch_id)
        _roots, verify_issues = gate_verify(release=release_id)
        if verify_issues:
            return StageResult(
                "publish",
                AUTO,
                "failed",
                "release verify failed:\n  - " + "\n  - ".join(verify_issues[:10]),
                fallback_stage="produce_review",
                issues=verify_issues,
            )
    authored_refs = content_object.iter_content_refs(ctx.task_id, ctx.batch_id)
    reconciled = oq.reconcile_completed_refs(
        ctx.task_id,
        ctx.batch_id,
        authored_refs,
        "author",
        reason="publish_succeeded",
    )
    _purge_author_queue_for_stale_workflow(ctx, reason="publish_succeeded")
    return StageResult(
        "publish",
        AUTO,
        "done",
        "release package assembled and gated "
        f"(entities={summary['entityCount']}, posts={summary['postCount']}, "
        f"tags={summary['tagCount']}, relations={summary['relationCount']}, "
        f"authorQueueReconciled={len(reconciled)})",
    )


# ─── DAG 定义 ─────────────────────────────────────────────────────────
# (stage_name, kind, runner)
DAG: list[tuple[str, str, Callable[[PipelineContext], StageResult]]] = [
    ("download_plan", CHECKPOINT, _checkpoint_download_plan),
    ("download_fetch", AUTO, _run_download_fetch),
    ("build_prepare", AUTO, _run_build_prepare),
    ("build_homepage", CHECKPOINT, _checkpoint_build_homepage),
    ("build_validate", AUTO, _run_build_validate),
    ("content_plan", CHECKPOINT, _checkpoint_content_plan),
    ("produce_plan", AUTO, _run_produce_plan),
    ("produce_compose", AUTO, _run_produce_compose),
    ("produce_author", CHECKPOINT, _checkpoint_produce_author),
    ("produce_annotate", AUTO, _run_produce_annotate),
    ("produce_review", AUTO, _run_produce_review),
    ("publish", AUTO, _run_publish),
]

STAGE_NAMES = [s[0] for s in DAG]


def _rewind_to(completed: set[str], target_stage: str) -> set[str]:
    """ReAct 回退：把 target_stage 及其后所有 stage 从 completed 移除，强制重跑。"""
    if target_stage not in STAGE_NAMES:
        return completed
    idx = STAGE_NAMES.index(target_stage)
    keep = set(STAGE_NAMES[:idx])
    return {s for s in completed if s in keep}


def _react_rewind(ctx: PipelineContext, state: dict, completed: set[str],
                  result: StageResult) -> tuple[set[str], bool]:
    """处理 failed 的 ReAct 回退。返回 (新 completed, 是否成功回退)。

    回退账本记 reactRewinds[stage] 计数；超 MAX_REACT_REWINDS 则不再回退（转人工）。
    """
    raw_fb = result.fallback_stage
    target = FALLBACK_DAG_STAGE.get(raw_fb, raw_fb) if raw_fb else None
    if not target or target not in STAGE_NAMES:
        return completed, False
    rewinds = state.setdefault("reactRewinds", {})
    key = result.stage
    used = int(rewinds.get(key, 0))
    if used >= MAX_REACT_REWINDS:
        print(f"[task run] ReAct 回退已达上限({MAX_REACT_REWINDS}) @ {result.stage}; 转人工", file=sys.stderr)
        return completed, False
    rewinds[key] = used + 1
    # 写 repair_report（反思账本：失败 stage → 回退链）
    from _common.stage_reports import write_repair_report
    write_repair_report(
        task_id=ctx.task_id, batch_id=ctx.batch_id, command="workflow_run",
        ref=result.stage, failed_stage=result.stage, failed_gate=f"{result.stage}_gate",
        issues=result.issues or [result.message], fallback_stage=target,
        rerun_chain=STAGE_NAMES[STAGE_NAMES.index(target):STAGE_NAMES.index(result.stage) + 1],
    )
    if result.stage == "produce_review":
        _prepare_produce_review_retry(ctx, result, target)
    new_completed = _rewind_to(completed, target)
    state["reactRewinds"] = rewinds
    state["completed"] = sorted(new_completed)
    save_workflow_state(state)
    print(f"[task run] ⟲ ReAct 回退 {result.stage} → {target} (第{used + 1}/{MAX_REACT_REWINDS}次)\n"
          f"           归因: {result.message.splitlines()[0]}")
    return new_completed, True


def run_pipeline(ctx: PipelineContext) -> int:
    """按 DAG 顺序执行；遇 waiting checkpoint 停（10），failed 走 ReAct 回退或停（1）。"""
    if ctx.baseline_packet is None or ctx.baseline_packet_path is None:
        raise RuntimeError("workflow run requires baseline freeze packet")
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    state["status"] = "running"
    state["owner"] = "managed-local" if ctx.managed else "workflow-cli"
    state["heartbeatAt"] = store.now_iso()
    state["nextAction"] = None
    completed = set(state.get("completed") or [])
    ensure_batch_layout(ctx.task_id, ctx.batch_id, "workflow_run")
    state["baselinePacketPath"] = str(ctx.baseline_packet_path)
    state["baselinePacketSummary"] = ctx.baseline_packet.get("summary") or {}
    save_workflow_state(state)
    # 批次级公共信息上提（规格 §4/§14）：任务定义快照 + 受控来源类目，不在对象目录重复。
    from _common.batch_manifest import write_batch_manifest, write_source_catalog, write_task_manifest
    write_task_manifest(ctx.task_id, ctx.spec)
    write_batch_manifest(
        ctx.task_id, ctx.batch_id,
        coverage_targets=(ctx.spec.get("scope") or {}).get("coverageTargets") or [],
        command="workflow_run",
    )
    write_source_catalog(ctx.task_id, ctx.batch_id)

    # 外层循环支持 ReAct 回退后重新遍历 DAG
    for _ in range(MAX_REACT_REWINDS * len(DAG) + len(DAG) + 1):
        progressed = False
        for stage_index, (stage_name, kind, runner) in enumerate(DAG):
            if stage_name in completed:
                continue
            next_stage = STAGE_NAMES[stage_index + 1] if stage_index + 1 < len(STAGE_NAMES) else None
            result = runner(ctx)
            if result.status == "waiting":
                state["completed"] = sorted(completed)
                state["waitingCheckpoint"] = stage_name
                state["status"] = "waiting_agent"
                state["heartbeatAt"] = store.now_iso()
                state["nextAction"] = result.checkpoint_hint
                save_workflow_state(state)
                _write_workflow_packet(
                    ctx,
                    stage_name=stage_name,
                    kind=kind,
                    result=result,
                    completed=sorted(completed),
                    next_stage=next_stage,
                    state=state,
                )
                print(f"[task run] PAUSED at checkpoint '{stage_name}'\n")
                print(result.checkpoint_hint)
                return 10
            if result.status == "failed":
                completed, rewound = _react_rewind(ctx, state, completed, result)
                _write_workflow_packet(
                    ctx,
                    stage_name=stage_name,
                    kind=kind,
                    result=result,
                    completed=sorted(completed),
                    next_stage=next_stage,
                    state=state,
                )
                if rewound:
                    progressed = True
                    break  # 回 DAG 头重跑回退目标
                state["completed"] = sorted(completed)
                state["waitingCheckpoint"] = None
                state["lastFailedStage"] = stage_name
                state["status"] = "manual_required"
                state["failedObjects"] = list(result.issues)
                state["nextAction"] = result.message
                save_workflow_state(state)
                print(f"[task run] FAILED at '{stage_name}': {result.message}", file=sys.stderr)
                return 1
            # done / skipped
            completed.add(stage_name)
            progressed = True
            state["completed"] = sorted(completed)
            state["waitingCheckpoint"] = None
            state["status"] = "running"
            state["heartbeatAt"] = store.now_iso()
            state["nextAction"] = next_stage
            state["failedObjects"] = []
            retry_counts = state.setdefault("retryCounts", {})
            retry_counts.pop(stage_name, None)
            state["retryCounts"] = retry_counts
            infrastructure_retries = state.setdefault("infrastructureRetryCounts", {})
            infrastructure_retries.pop(stage_name, None)
            state["infrastructureRetryCounts"] = infrastructure_retries
            save_workflow_state(state)
            _write_workflow_packet(
                ctx,
                stage_name=stage_name,
                kind=kind,
                result=result,
                completed=sorted(completed),
                next_stage=next_stage,
                state=state,
            )
            print(f"[task run] ✓ {stage_name} ({kind}): {result.message}")
            if ctx.until and stage_name == ctx.until:
                print(f"[task run] stopped at --until {ctx.until}")
                return 0
        else:
            # DAG 全遍历无 break → 全部 stage 完成
            print(f"[task run] WORKFLOW COMPLETE — {ctx.task_id} / {ctx.batch_id}")
            state["status"] = "succeeded"
            state["heartbeatAt"] = store.now_iso()
            state["nextAction"] = None
            save_workflow_state(state)
            return 0
        if not progressed:
            break
    print(f"[task run] FAILED: ReAct 回退耗尽未收敛 — {ctx.task_id} / {ctx.batch_id}", file=sys.stderr)
    return 1


def _managed_preflight(task_id: str, batch_id: str, spec: dict, args: argparse.Namespace) -> list[str]:
    """托管任务启动前失败快返；不创建 batch/runtime。"""
    issues: list[str] = []
    if str(spec.get("status") or "") != "active":
        issues.append(f"task status must be active for --managed, got {spec.get('status')!r}")
    targets = (spec.get("scope") or {}).get("coverageTargets") or []
    if not targets:
        issues.append("scope.coverageTargets must not be empty")
    quotas = ((spec.get("content") or {}).get("quotas") or {})
    for field, expected_min in (
        ("entityArticlesPerTarget", 1),
        ("galleryPostsPerTarget", 1),
        ("entityHomepagesPerTarget", 1),
    ):
        if int(quotas.get(field) or 0) < expected_min:
            issues.append(f"content.quotas.{field} must be >= {expected_min}")
    if str(getattr(args, "runtime", "local")) != "local":
        issues.append("--managed production runs require --runtime local")
    if not os.environ.get("CURSOR_API_KEY"):
        issues.append("CURSOR_API_KEY missing")
    try:
        import cursor_sdk  # type: ignore  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        issues.append(f"cursor_sdk unavailable in current Python: {exc}")
    for module in ("PIL", "cv2", "numpy"):
        try:
            __import__(module)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"required test/runtime dependency {module} unavailable: {exc}")
    if not task_baseline_freeze_packet_path(task_id).is_file() and not getattr(args, "baseline_packet", None):
        issues.append("baseline freeze packet missing")
    return issues


def _default_managed_agent_runner(ctx: PipelineContext, prompt: str) -> dict[str, Any]:
    """在当前 workspace 启动一个本地 Cursor Agent；只返回终态，推进由父进程校验。"""
    try:
        from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"started": False, "status": "error", "error": f"cursor_sdk unavailable: {exc}"}
    key = os.environ.get("CURSOR_API_KEY")
    if not key:
        return {"started": False, "status": "error", "error": "CURSOR_API_KEY missing"}
    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=key,
                model=ctx.model,
                local=LocalAgentOptions(cwd=str(Path.cwd())),
            ),
        )
    except CursorAgentError as exc:
        return {
            "started": False,
            "status": "error",
            "error": getattr(exc, "message", str(exc)),
            "retryable": bool(getattr(exc, "is_retryable", False)),
            "errorCode": getattr(exc, "code", None),
            "requestId": getattr(exc, "request_id", None),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "started": False,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "retryable": False,
        }
    status = str(getattr(result, "status", "error"))
    result_text = str(getattr(result, "result", "") or "").strip()
    return {
        "started": True,
        "status": status,
        "error": None if status == "finished" else (
            f"agent status={status}: {result_text[:1600]}" if result_text else f"agent status={status}"
        ),
        "result": result_text[:4000],
        "agentId": getattr(result, "agent_id", None),
        "runId": getattr(result, "id", None),
        "durationMs": int(getattr(result, "duration_ms", 0) or 0),
    }


def _checkpoint_prompts(ctx: PipelineContext, stage: str) -> list[str]:
    """把 checkpoint 拆为可并发且写集互斥的 Agent 任务。"""
    base = (
        "你是 quwoquan_data 托管工作流的执行 Agent。只完成本提示指定的 checkpoint，"
        "不要递归运行整条 workflow，不要发布到 publish/，不要修改其它 task/batch。"
        f"\n任务: {ctx.task_id}\n批次: {ctx.batch_id}\n"
    )
    if stage == "download_plan":
        from _common.source_unit import resolve_entity_object_dir

        etype = _coverage_entity_type(ctx.spec)
        done, issues = _source_plan_filled(ctx)
        if done:
            return []
        pending_entities = {
            entity
            for entity in ctx.entity_ids
            if any(issue.startswith(f"{entity}:") for issue in issues)
        }
        prompts = []
        for entity in ctx.entity_ids:
            if entity not in pending_entities:
                continue
            path = resolve_entity_object_dir(
                ctx.task_id, ctx.batch_id, entity, etype_hint=etype
            ) / "1.download" / "source_plan.json"
            prompts.append(
                base
                + f"\n对象: {entity}\n写入: {path}\n"
                "真实联网检索并填写 source_plan。至少 4 个可抓取且类别多样的来源，每个来源必须含 "
                "source_id/platform/url/sourceUseMode；普通官网、百科、攻略和游记用 "
                "factual_reference_only。仅有明确 CC、公版或书面授权证据时用 licensed_adaptation，"
                "并写 license/termsUrl/licenseSnapshot/credit。blocked 来源不得写入可消费列表。"
                "\n至少 10 张互不重复的可发布图片，每张写 url/license/credit/sourceUrl/termsUrl/"
                "usageScope/relevance，且画面必须直接呈现该景区自身或景区内部景点。禁止用邻近景点、"
                "同日环线、所在县城、交通沿线或泛川西图片凑数；禁止发现页、缩略图、社媒水印图和"
                "权利不明图片。若不足 10 张，明确保留不足状态，不得伪造达标。"
                "\n完成后自行重新读取 JSON，确认 URL、权利字段和数量真实完整。"
            )
        return prompts
    if stage == "build_homepage":
        from _common.source_unit import resolve_entity_object_dir

        etype = _coverage_entity_type(ctx.spec)
        prompts = []
        for entity in ctx.entity_ids:
            obj = resolve_entity_object_dir(ctx.task_id, ctx.batch_id, entity, etype_hint=etype)
            prompts.append(
                base
                + f"\n对象: {entity}\n对象目录: {obj}\n"
                "读取 3.compose/entity_page_input.json、已下载 source.md/source.clean.md、SOP 和图片资产，"
                "只为该实体完成 page.md、_entity.json、manifest.json 以及要求的 4.draft/5.review 证据。"
                "主页必须多来源事实综合、独立表达，不得轻改百科原文；至少引用一张已过权利和安全门的真实图。"
                "运行该实体适用的 build validate/review，修复到 validator 通过。"
            )
        return prompts
    if stage == "content_plan":
        quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
        return [
            base
            + "\n为全部 coverageTargets 完成证据驱动 content_plan。"
            f"\n配额: {json.dumps(quotas, ensure_ascii=False)}"
            "\n每景区恰好 2 篇文章（planning_consultation 与 decision_experience 各一）和 2 个 gallery，"
            "每个作品使用独立 baseSourceRef，gallery 标题/画面主题不同且图片集合不得相同。"
            "写 _shared/content_plan_packet.json，注册 content_object，并写每项 3.compose/brief.json。"
            "ref/title 必须由证据归纳；evidenceRefs 必须存在，blocked/reject 来源不可引用。"
            "\n完成后运行 content_plan validator 并修复到无问题。"
        ]
    if stage == "produce_author":
        from _common.draft_io import (
            draft_article_path,
            draft_meta_path,
            prompt_path,
            writing_pack_path,
        )

        _ok, pending = _drafts_authored(ctx)
        return [
            base
            + f"\n内容 ref: {ref}\n读取: {prompt_path(ctx.task_id, ctx.batch_id, ref)}"
            + f"\n读取: {writing_pack_path(ctx.task_id, ctx.batch_id, ref)}"
            + f"\n写入: {draft_article_path(ctx.task_id, ctx.batch_id, ref)}"
            + f"\n写入: {draft_meta_path(ctx.task_id, ctx.batch_id, ref)}"
            + "\n严格依据证据独立创作；普通网页只取事实，不复现原句/原结构；授权来源按许可改编并保留归因。"
            "只引用 writing_pack 中的 assetId 和 sourcePath。draft_meta 必须 generator=agent，记录 model、"
            "citedSourcePaths、coveredFacts、styleFamily、openingStrategy。完成后做自检，但不要运行批次发布。"
            for ref in pending
        ]
    return []


def _checkpoint_is_done(ctx: PipelineContext, stage: str) -> tuple[bool, list[str]]:
    checkers: dict[str, Callable[[PipelineContext], tuple[bool, list[str]]]] = {
        "download_plan": _source_plan_filled,
        "build_homepage": _homepages_done,
        "content_plan": _content_plan_done,
        "produce_author": _drafts_authored,
    }
    checker = checkers.get(stage)
    return checker(ctx) if checker else (False, [f"unsupported managed checkpoint {stage}"])


def _run_managed_checkpoint(ctx: PipelineContext, stage: str) -> bool:
    prompts = _checkpoint_prompts(ctx, stage)
    if not prompts:
        return False
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    state["status"] = "waiting_agent"
    state["owner"] = f"managed-local:{stage}"
    state["heartbeatAt"] = store.now_iso()
    state["nextAction"] = f"running {len(prompts)} agent job(s) for {stage}"
    save_workflow_state(state)
    runner = ctx.agent_runner or (lambda prompt: _default_managed_agent_runner(ctx, prompt))
    with ThreadPoolExecutor(max_workers=max(1, min(ctx.max_workers, len(prompts)))) as pool:
        futures = [pool.submit(runner, prompt) for prompt in prompts]
        pending = set(futures)
        outcomes: list[dict[str, Any]] = []
        while pending:
            done, pending = wait(pending, timeout=10)
            for future in done:
                try:
                    outcome = future.result()
                except Exception as exc:  # noqa: BLE001
                    outcome = {
                        "started": False,
                        "status": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                        "retryable": False,
                    }
                outcomes.append(outcome)
            state = load_workflow_state(ctx.task_id, ctx.batch_id)
            state["heartbeatAt"] = store.now_iso()
            state["nextAction"] = f"{stage}: {len(outcomes)}/{len(prompts)} agent job(s) finished"
            save_workflow_state(state)
    started_count = sum(bool(out.get("started")) for out in outcomes)
    finished_count = sum(str(out.get("status")) == "finished" for out in outcomes)
    infrastructure_failures = sum(not bool(out.get("started")) for out in outcomes)
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    state["lastAgentRun"] = {
        "stage": stage,
        "jobCount": len(outcomes),
        "startedCount": started_count,
        "finishedCount": finished_count,
        "infrastructureFailures": infrastructure_failures,
        "outcomes": outcomes,
        "finishedAt": store.now_iso(),
    }
    save_workflow_state(state)
    failures = [out for out in outcomes if str(out.get("status")) != "finished"]
    if failures:
        state = load_workflow_state(ctx.task_id, ctx.batch_id)
        state["status"] = "repairing"
        state["failedObjects"] = [str(out.get("error") or "agent failed") for out in failures]
        save_workflow_state(state)
        return False
    ok, issues = _checkpoint_is_done(ctx, stage)
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    state["owner"] = "managed-local"
    state["heartbeatAt"] = store.now_iso()
    state["failedObjects"] = list(issues)
    state["status"] = "running" if ok else "repairing"
    state["nextAction"] = None if ok else f"repair {stage}: {issues[:5]}"
    save_workflow_state(state)
    return ok


def run_managed_pipeline(ctx: PipelineContext) -> int:
    """父进程消费全部 Agent checkpoint，直到 release verify 通过或转人工。"""
    while True:
        code = run_pipeline(ctx)
        if code == 0:
            return 0
        if code != 10:
            return code
        state = load_workflow_state(ctx.task_id, ctx.batch_id)
        stage = str(state.get("waitingCheckpoint") or "")
        retries = state.setdefault("retryCounts", {})
        used = int(retries.get(stage, 0))
        if used >= MAX_REACT_REWINDS:
            state["status"] = "manual_required"
            state["nextAction"] = f"{stage} failed validation after {used} managed attempts"
            save_workflow_state(state)
            return 1
        state["status"] = "repairing" if used else "waiting_agent"
        save_workflow_state(state)
        if _run_managed_checkpoint(ctx, stage):
            state = load_workflow_state(ctx.task_id, ctx.batch_id)
            infra = state.setdefault("infrastructureRetryCounts", {})
            infra.pop(stage, None)
            state["infrastructureRetryCounts"] = infra
            save_workflow_state(state)
            continue

        state = load_workflow_state(ctx.task_id, ctx.batch_id)
        last_run = state.get("lastAgentRun") or {}
        infrastructure_failures = int(last_run.get("infrastructureFailures") or 0)
        if infrastructure_failures:
            infra = state.setdefault("infrastructureRetryCounts", {})
            infra_used = int(infra.get(stage, 0)) + 1
            infra[stage] = infra_used
            state["infrastructureRetryCounts"] = infra
            if infra_used >= MAX_MANAGED_INFRA_RETRIES:
                state["status"] = "manual_required"
                state["nextAction"] = (
                    f"{stage} infrastructure failed after {infra_used} attempts; "
                    f"{infrastructure_failures} agent job(s) did not start"
                )
                save_workflow_state(state)
                return 1
            state["nextAction"] = (
                f"retry {stage} infrastructure: attempt "
                f"{infra_used + 1}/{MAX_MANAGED_INFRA_RETRIES}"
            )
            save_workflow_state(state)
            time.sleep(min(2 ** (infra_used - 1), 5))
            continue

        retries = state.setdefault("retryCounts", {})
        retries[stage] = used + 1
        state["retryCounts"] = retries
        save_workflow_state(state)
        time.sleep(min(2 ** used, 5))

def _handle_run_fanout(args: argparse.Namespace) -> None:
    """--mode fanout：走冻结计划建 task/batch + enqueue 叶子 + 展开 assignment（幂等）。

    单模式（--mode single）= 现状 DAG；fanout 把每分区/叶子下沉到 object_queue，
    由 cursor-sdk 外部 runner 解 CHECKPOINT 接缝。--concurrency 1 即退化等价单模式。
    """
    from _common import fanout_plan as fp
    from task import fanout_dispatch as fd

    if not getattr(args, "plan", None):
        print("[task run] ERROR: --mode fanout 需要 --plan <planId>", file=sys.stderr)
        raise SystemExit(2)
    plan = fp.load_plan(args.plan)
    if plan is None:
        print(f"[task run] ERROR: 计划不存在: {args.plan}（先跑 qwq-data task decompose）", file=sys.stderr)
        raise SystemExit(2)
    if str(plan.get("status")) != "frozen":
        print(
            f"[task run] ERROR: 计划未冻结 (status={plan.get('status')})；"
            f"先 qwq-data task decompose --plan {args.plan} --freeze --confirm",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        report = fd.dispatch(
            plan,
            strategy=getattr(args, "strategy", None),
            concurrency=getattr(args, "concurrency", None),
            batch_size=getattr(args, "batch_size", None),
        )
    except (ValueError, RuntimeError) as exc:
        print(f"[task run] ERROR: dispatch failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
    totals = report["totals"]
    print(
        f"[task run --mode fanout] plan={report['planId']} strategy={report['strategy']} "
        f"concurrency={report['concurrency']}"
    )
    for part in report["perPartition"]:
        print(
            f"  - {'/'.join(part['partitionPath'])} -> task={part['taskId']} "
            f"batch={part['batchId']} enqueued={part['enqueued']} created={part['taskCreated']}"
        )
    print(
        f"[task run --mode fanout] partitions={totals['partitions']} tasksCreated={totals['tasksCreated']} "
        f"leavesEnqueued={totals['leavesEnqueued']} assignments={totals['assignments']}"
    )
    print(
        "[task run --mode fanout] 叶子已入队。外部并行执行（by-partition 默认先跑分区 orchestrator "
        "推进 download_plan/build_homepage/content_plan 三个 checkpoint，再分发叶子 author）："
        f"\n  本机多 agent: python3 agent_ops/runners/fanout_runner.py --plan {report['planId']} --strategy {report['strategy']} --runtime local --max-workers {report['concurrency']}"
        f"\n  云端 VM:     python3 agent_ops/runners/fanout_runner.py --plan {report['planId']} --strategy {report['strategy']} --runtime cloud --max-workers {report['concurrency']}"
        "\n  （两者都需 export CURSOR_API_KEY；或会话内逐分区 qwq-data data workflow run --task <taskId> --batch <batchId> 解 checkpoint）"
        " + qwq-data object-queue lease-next --task <taskId> --batch <batchId> --worker <id>（叶子）"
    )


def handle_run(args: argparse.Namespace) -> None:
    if getattr(args, "mode", "single") == "fanout":
        _handle_run_fanout(args)
        return

    task_id = args.task
    if not task_id:
        print("[task run] ERROR: --mode single 需要 --task <taskId>", file=sys.stderr)
        raise SystemExit(2)
    batch_id = args.batch
    spec = store.load_spec(task_id)
    entity_ids = _coverage_entity_ids(spec)
    if not entity_ids:
        print(f"[task run] ERROR: {task_id} 无 coverageTargets，无实体可编排", file=sys.stderr)
        raise SystemExit(2)

    managed = bool(getattr(args, "managed", False))
    if managed:
        preflight_issues = _managed_preflight(task_id, batch_id, spec, args)
        if preflight_issues:
            print("[task run] managed preflight FAILED:", file=sys.stderr)
            for issue in preflight_issues:
                print(f"  - {issue}", file=sys.stderr)
            raise SystemExit(2)

    if args.reset_state:
        p = _state_path(task_id, batch_id)
        if p.exists():
            p.unlink()
            print(f"[task run] reset workflow state: {p}")
        _purge_author_queue_for_stale_workflow(
            PipelineContext(
                task_id=task_id,
                batch_id=batch_id,
                entity_ids=[],
                spec={},
            ),
            reason="reset_state",
        )

    until = args.until if getattr(args, "until", None) else None
    if until and until not in STAGE_NAMES:
        print(f"[task run] ERROR: --until 须为 {STAGE_NAMES}", file=sys.stderr)
        raise SystemExit(2)

    try:
        baseline_packet_path, baseline_packet = _load_baseline_packet(
            task_id,
            Path(args.baseline_packet) if getattr(args, "baseline_packet", None) else None,
        )
    except RuntimeError as exc:
        print(f"[task run] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

    ctx = PipelineContext(
        task_id=task_id, batch_id=batch_id, entity_ids=entity_ids,
        spec=spec, baseline_packet=baseline_packet, baseline_packet_path=baseline_packet_path,
        until=until,
        managed=managed,
        runtime=str(getattr(args, "runtime", "local") or "local"),
        max_workers=int(getattr(args, "max_workers", 3) or 3),
        model=str(getattr(args, "model", "composer-2.5") or "composer-2.5"),
        release_only=bool(getattr(args, "release_only", False)),
        agent_runner=getattr(args, "agent_runner", None),
    )
    code = run_managed_pipeline(ctx) if managed else run_pipeline(ctx)
    if code != 0:
        raise SystemExit(code)


def register_run_parser(sub: argparse._SubParsersAction) -> None:
    pr = sub.add_parser("run", help="无人值守 workflow 编排：单模式 DAG / fanout 分区叶子调度")
    pr.add_argument(
        "--mode",
        choices=["single", "fanout"],
        default="single",
        help="single=会话内单 agent 跑 DAG（默认，现状）；fanout=按冻结计划分区/叶子调度",
    )
    pr.add_argument("--task", help="Task ID（single 模式必填）")
    pr.add_argument("--batch", default="run_1", help="Batch ID")
    pr.add_argument("--plan", help="fanout 模式：冻结计划 planId")
    pr.add_argument(
        "--strategy",
        choices=["by-partition", "flat-pool", "by-leaf", "by-batch"],
        help="fanout 模式：拉起策略（默认取计划 defaults.strategy）",
    )
    pr.add_argument("--concurrency", type=int, help="fanout 模式：并发度（设 1 即退化等价 single）")
    pr.add_argument("--batch-size", dest="batch_size", type=int, help="fanout by-batch 策略：每块叶子数")
    pr.add_argument("--resume", action="store_true",
                    help="从上次 checkpoint 继续（默认即 resume 语义：跳过已完成 stage）")
    pr.add_argument("--reset-state", dest="reset_state", action="store_true",
                    help="清空 workflow_state 从头跑")
    pr.add_argument(
        "--baseline-packet",
        help="baseline freeze packet path（默认 task/_shared/baseline_freeze_packet.json）",
    )
    pr.add_argument("--until", help=f"跑到指定 stage 即停: {STAGE_NAMES}")
    pr.add_argument("--managed", action="store_true", help="自动消费全部 Agent checkpoint 并续跑")
    pr.add_argument("--runtime", choices=["local", "cloud"], default="local")
    pr.add_argument("--max-workers", dest="max_workers", type=int, default=3)
    pr.add_argument("--model", default="composer-2.5")
    pr.add_argument(
        "--release-only",
        dest="release_only",
        action="store_true",
        help="仅组装隔离 release，不写 publish/ 或运行库（当前 managed 正式模式要求）",
    )
    pr.set_defaults(handler=handle_run)
