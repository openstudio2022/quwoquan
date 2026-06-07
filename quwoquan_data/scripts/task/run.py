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
  -> produce_plan(auto 解析 compose brief)
  -> produce_compose(auto compose-brief) -> produce_author(checkpoint:Agent 写 article)
  -> produce_annotate(auto) -> produce_review(auto review+media gate --materialize)
  -> publish(auto)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

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
    """scope.entityTypes 首项（download/build 对象目录解析用）。"""
    scope = spec.get("scope") or {}
    types = scope.get("entityTypes") or []
    return str(types[0]) if types else ""


def _source_plan_filled(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """download_plan checkpoint：每个 coverage 实体的 source_plan 是否有可消费 sources。"""
    from download.source_inputs import curated_sources_for_entity
    etype = _coverage_entity_type(ctx.spec)
    missing: list[str] = []
    for eid in ctx.entity_ids:
        if not curated_sources_for_entity(ctx.task_id, ctx.batch_id, eid, etype):
            missing.append(eid)
    return (not missing), missing


def _homepages_done(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """build_homepage checkpoint：coverage 实体三件套是否物化（用 build validate 复核）。"""
    from build.homepage import validate_entity_pages
    issues = validate_entity_pages(ctx.task_id, ctx.spec)
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
    issues = validate_entity_pages(ctx.task_id, ctx.spec)
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
    """为每个 coverage 实体解析 compose brief，写入对象树 `posts/.../3.compose/brief.json`。

    薄编排：复用 plan.resolve_compose_brief（与 `qwq-data plan` 同一真相源），不重写路由。
    每实体默认取 task.content.angles 首个角度产 1 篇，brief 关联实体主页 entityRef，
    让 compose-brief 能据此生成 writing_pack + prompt。
    """
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
        etype = str(target.get("entityType") or "地点/景区")
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
    ns = argparse.Namespace(
        task=ctx.task_id, batch=ctx.batch_id, type="article",
        stage="review", refs="", batch_size=1,
        allow_partial=True, materialize=True,
    )
    handle_produce(ns)
    issues = gate_produce(ctx.task_id, ctx.batch_id, "article")
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
        f"[CHECKPOINT download_plan] Agent 检索真实素材，为以下实体各写 ≥2 个可消费 source 到 source_plan：\n"
        f"  待补实体: {missing}\n"
        f"  写入: entities/<domain>/<type>/<entityId>/1.download/source_plan.json 的 payload.sources=[{{source_id,platform,url,body}}]\n"
        f"  (web_search/浏览器检索，URL+正文 body；含图则填 imageUrls)\n"
        f"  完成后: qwq-data data workflow run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("download_plan", CHECKPOINT, "waiting", "等待 Agent 写 source_plan", hint)


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
        f"  读 <ref>/prompt.md + <ref>/writing_pack.json，写回 <ref>/article.md\n"
        f"  draft_meta 记 model/styleFamily/openingStrategy/extractedEntities\n"
        f"  待创作: {pending}\n"
        f"  完成后: qwq-data data workflow run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("produce_author", CHECKPOINT, "waiting", "等待 Agent 创作正文", hint)


def _workflow_release_id(task_id: str, batch_id: str) -> str:
    task_slug = task_id.replace("/", "__")
    return f"{task_slug}__{batch_id}"


def _run_publish(ctx: PipelineContext) -> StageResult:
    from _common.publish_materialization import materialize_task_publish_inputs
    from publish.handler import handle_publish
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
    return StageResult(
        "publish",
        AUTO,
        "done",
        "release package assembled and gated "
        f"(entities={summary['entityCount']}, posts={summary['postCount']}, "
        f"tags={summary['tagCount']}, relations={summary['relationCount']})",
    )


# ─── DAG 定义 ─────────────────────────────────────────────────────────
# (stage_name, kind, runner)
DAG: list[tuple[str, str, Callable[[PipelineContext], StageResult]]] = [
    ("download_plan", CHECKPOINT, _checkpoint_download_plan),
    ("download_fetch", AUTO, _run_download_fetch),
    ("build_prepare", AUTO, _run_build_prepare),
    ("build_homepage", CHECKPOINT, _checkpoint_build_homepage),
    ("build_validate", AUTO, _run_build_validate),
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
                save_workflow_state(state)
                print(f"[task run] FAILED at '{stage_name}': {result.message}", file=sys.stderr)
                return 1
            # done / skipped
            completed.add(stage_name)
            progressed = True
            state["completed"] = sorted(completed)
            state["waitingCheckpoint"] = None
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
            return 0
        if not progressed:
            break
    print(f"[task run] FAILED: ReAct 回退耗尽未收敛 — {ctx.task_id} / {ctx.batch_id}", file=sys.stderr)
    return 1

def handle_run(args: argparse.Namespace) -> None:
    task_id = args.task
    batch_id = args.batch
    spec = store.load_spec(task_id)
    entity_ids = _coverage_entity_ids(spec)
    if not entity_ids:
        print(f"[task run] WARN: {task_id} 无 coverageTargets，无实体可编排", file=sys.stderr)

    if args.reset_state:
        p = _state_path(task_id, batch_id)
        if p.exists():
            p.unlink()
            print(f"[task run] reset workflow state: {p}")

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
    )
    code = run_pipeline(ctx)
    if code != 0:
        raise SystemExit(code)


def register_run_parser(sub: argparse._SubParsersAction) -> None:
    pr = sub.add_parser("run", help="无人值守 workflow 编排：按 DAG 跑 download→build→produce→publish")
    pr.add_argument("--task", required=True, help="Task ID")
    pr.add_argument("--batch", default="run_1", help="Batch ID")
    pr.add_argument("--resume", action="store_true",
                    help="从上次 checkpoint 继续（默认即 resume 语义：跳过已完成 stage）")
    pr.add_argument("--reset-state", dest="reset_state", action="store_true",
                    help="清空 workflow_state 从头跑")
    pr.add_argument(
        "--baseline-packet",
        help="baseline freeze packet path（默认 task/_shared/baseline_freeze_packet.json）",
    )
    pr.add_argument("--until", help=f"跑到指定 stage 即停: {STAGE_NAMES}")
    pr.set_defaults(handler=handle_run)
