"""task run — 无人值守产线编排器（DAG 薄编排壳，目标① 全流程自动化）。

把零散的 download/build/plan/produce/review/ship 串成固定 DAG，运营只在入口
(task.yaml) 与出口(抽检)介入，中间不再逐步手敲 10+ 条 CLI。

设计原则（与 13-coding-discipline R24 抽象克制一致）：
- 薄编排：不重写任何 stage 逻辑，只按 DAG 顺序调用既有 handler / 既有薄函数。
- 双类节点：
  * 确定性节点(deterministic)：CLI 直接跑（download fetch / build validate /
    produce review --materialize / ship）。
  * Agent checkpoint：写 assistant_tasks 清单 + 暂停，输出明确指引；Agent 物化产物
    后用 `task run --resume` 继续。这是「Agent 会话创作 = 自动化执行者」的接缝，
    不是人手工断点。
- 可 resume：pipeline 状态落 runtime/tasks/<taskId>/batches/<batch>/pipeline_state.json，
  记录已完成 stage、当前等待的 checkpoint、ReAct 回退指针。

DAG（stage 序）：
  download_plan(checkpoint:Agent 写 source_plan)
  -> download_fetch(auto)
  -> build_prepare(auto 下发主页契约) -> build_homepage(checkpoint:Agent 写 page 三件套)
  -> build_validate(auto 采纳门)
  -> produce_plan(auto 解析 compose brief)
  -> produce_compose(auto compose-brief) -> produce_author(checkpoint:Agent 写 article)
  -> produce_annotate(auto) -> produce_review(auto review --materialize)
  -> ship(auto)
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
    batch_assistant_task,
    batch_inputs_dir,
    batch_command_root,
    ensure_batch_layout,
    task_data,
)
from task import store

PIPELINE_STATE_VERSION = "quwoquan.task.pipeline_state"

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
    until: str | None = None
    completed: list[str] = field(default_factory=list)


def _state_path(task_id: str, batch_id: str) -> Path:
    return batch_command_root(task_id, batch_id, "pipeline") / "pipeline_state.json"


def load_pipeline_state(task_id: str, batch_id: str) -> dict:
    p = _state_path(task_id, batch_id)
    if p.exists():
        return read_json(p)
    return {
        "schemaVersion": PIPELINE_STATE_VERSION,
        "taskId": task_id,
        "batchId": batch_id,
        "completed": [],
        "waitingCheckpoint": None,
        "updatedAt": store.now_iso(),
    }


def save_pipeline_state(state: dict) -> Path:
    state["updatedAt"] = store.now_iso()
    p = _state_path(state["taskId"], state["batchId"])
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, state)
    return p


# ─── coverage 实体解析（download/build 的输入）────────────────────────
def _coverage_entity_ids(spec: dict) -> list[str]:
    out: list[str] = []
    for target in (spec.get("scope") or {}).get("coverageTargets") or []:
        name = str(target.get("name") or "").strip()
        if name:
            out.append(name)
    return out


# ─── checkpoint 完成度探测（resume 判定 Agent 是否已物化产物）──────────
def _source_plan_filled(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """download_plan checkpoint：每个 coverage 实体的 source_plan 是否有可消费 sources。"""
    from download.source_inputs import curated_sources_for_entity
    missing: list[str] = []
    for eid in ctx.entity_ids:
        if not curated_sources_for_entity(ctx.task_id, ctx.batch_id, eid):
            missing.append(eid)
    return (not missing), missing


def _homepages_done(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """build_homepage checkpoint：coverage 实体三件套是否物化（用 build validate 复核）。"""
    from build.homepage import validate_entity_pages
    issues = validate_entity_pages(ctx.task_id, ctx.spec)
    return (not issues), issues


def _drafts_authored(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """produce_author checkpoint：compose 后的 drafts 是否被 Agent 创作（非占位）。"""
    from _common.draft_io import drafts_dir, is_placeholder
    pending: list[str] = []
    d = drafts_dir(ctx.task_id, ctx.batch_id)
    if not d.is_dir():
        return False, ["(no drafts dir; run compose-brief first)"]
    articles = sorted(d.glob("*/article.md"))
    if not articles:
        return False, ["(no article drafts; run compose-brief first)"]
    for art in articles:
        if is_placeholder(art.read_text(encoding="utf-8")):
            pending.append(art.parent.name)
    return (not pending), pending


# ─── 确定性 stage 执行（复用既有 handler）─────────────────────────────
def _run_download_fetch(ctx: PipelineContext) -> StageResult:
    from download.handler import handle_download
    ns = argparse.Namespace(
        task=ctx.task_id, batch=ctx.batch_id,
        entity_ids=",".join(ctx.entity_ids),
        entity_type=(ctx.spec.get("scope") or {}).get("entityTypes", [""])[0]
        if (ctx.spec.get("scope") or {}).get("entityTypes") else "",
    )
    handle_download(ns)
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
    """为每个 coverage 实体解析 compose brief，写入 produce/inputs/compose/<ref>.json。

    薄编排：复用 plan.resolve_compose_brief（与 `qwq-data plan` 同一真相源），不重写路由。
    每实体默认取 task.content.angles 首个角度产 1 篇，brief 关联实体主页 entityRef，
    让 compose-brief 能据此生成 writing_pack + prompt。
    """
    from plan.brief import resolve_compose_brief, write_brief
    from plan.handler import ENTITY_KIND_MAP
    from template.registry import TemplateRegistry
    from template.router import RouteRequest

    registry = TemplateRegistry.load()
    compose_dir = batch_inputs_dir(ctx.task_id, ctx.batch_id, "produce", "compose")
    compose_dir.mkdir(parents=True, exist_ok=True)
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
        write_brief(compose_dir / f"{ref}.json", brief)
        written.append(ref)
    return StageResult("produce_plan", AUTO, "done",
                       f"解析 {len(written)} 个实体 compose brief(intent={intent}) -> {compose_dir}")


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
    from _common.paths import batch_results_dir
    gate_dir = batch_results_dir(ctx.task_id, ctx.batch_id, "produce", "review_gate")
    fallbacks: set[str] = set()
    if gate_dir.is_dir():
        for f in gate_dir.glob("*.json"):
            try:
                rep = read_json(f)
            except Exception:
                continue
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
    plan_dir = batch_inputs_dir(ctx.task_id, ctx.batch_id, "download", "source_plan")
    plan_dir.mkdir(parents=True, exist_ok=True)
    # 预置空 source_plan 骨架，Agent 填 URL+body
    from download.prepare import prepare_source_plan
    entities = [{"entityId": e, "canonicalName": e,
                 "entityType": (ctx.spec.get("scope") or {}).get("entityTypes", [""])[0]
                 if (ctx.spec.get("scope") or {}).get("entityTypes") else ""}
                for e in ctx.entity_ids]
    prepare_source_plan(ctx.task_id, ctx.batch_id, entities)
    hint = (
        f"[CHECKPOINT download_plan] Agent 检索真实素材，为以下实体各写 ≥2 个可消费 source 到 source_plan：\n"
        f"  待补实体: {missing}\n"
        f"  写入: {plan_dir}/<entityId>.json 的 payload.sources=[{{source_id,platform,url,body}}]\n"
        f"  (web_search/浏览器检索，URL+正文 body；含图则填 imageUrls)\n"
        f"  完成后: qwq-data task run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("download_plan", CHECKPOINT, "waiting", "等待 Agent 写 source_plan", hint)


def _checkpoint_build_homepage(ctx: PipelineContext) -> StageResult:
    ok, issues = _homepages_done(ctx)
    if ok:
        return StageResult("build_homepage", CHECKPOINT, "done", "实体主页三件套已就绪")
    hint = (
        f"[CHECKPOINT build_homepage] Agent 按 SOP 为 coverage 实体物化主页三件套：\n"
        f"  契约: {batch_inputs_dir(ctx.task_id, ctx.batch_id, 'build', 'entity_page')}/<ref>.json\n"
        f"  产出: page.md(≥800字) + _entity.json(含 conditionProfile) + manifest.json\n"
        f"  采纳门未过项:\n    - " + "\n    - ".join(issues[:10]) + "\n"
        f"  完成后: qwq-data task run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("build_homepage", CHECKPOINT, "waiting", "等待 Agent 写实体主页", hint)


def _checkpoint_produce_author(ctx: PipelineContext) -> StageResult:
    ok, pending = _drafts_authored(ctx)
    if ok:
        return StageResult("produce_author", CHECKPOINT, "done", "正文已由 Agent 创作")
    hint = (
        f"[CHECKPOINT produce_author] Agent 逐篇创作正文(generator=agent)：\n"
        f"  草稿目录: {batch_command_root(ctx.task_id, ctx.batch_id, 'produce')}/drafts/\n"
        f"  读 <ref>/prompt.md + <ref>/writing_pack.json，写回 <ref>/article.md\n"
        f"  draft_meta 记 model/styleFamily/openingStrategy/extractedEntities\n"
        f"  待创作: {pending}\n"
        f"  完成后: qwq-data task run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("produce_author", CHECKPOINT, "waiting", "等待 Agent 创作正文", hint)


def _run_ship(ctx: PipelineContext) -> StageResult:
    from ship.handler import handle_ship
    ns = argparse.Namespace(
        release_id=None, task=ctx.task_id, batch=ctx.batch_id,
        copy_entities=True, env=None, skip_promote=False,
        skip_index=False, import_to_db=False, mongo_uri=None,
    )
    handle_ship(ns)
    return StageResult("ship", AUTO, "done", "promote + 采样 + publish_meta 更新")


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
    ("ship", AUTO, _run_ship),
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
        task_id=ctx.task_id, batch_id=ctx.batch_id, command="pipeline",
        ref=result.stage, failed_stage=result.stage, failed_gate=f"{result.stage}_gate",
        issues=result.issues or [result.message], fallback_stage=target,
        rerun_chain=STAGE_NAMES[STAGE_NAMES.index(target):STAGE_NAMES.index(result.stage) + 1],
    )
    new_completed = _rewind_to(completed, target)
    state["reactRewinds"] = rewinds
    state["completed"] = sorted(new_completed)
    save_pipeline_state(state)
    print(f"[task run] ⟲ ReAct 回退 {result.stage} → {target} (第{used + 1}/{MAX_REACT_REWINDS}次)\n"
          f"           归因: {result.message.splitlines()[0]}")
    return new_completed, True


def run_pipeline(ctx: PipelineContext) -> int:
    """按 DAG 顺序执行；遇 waiting checkpoint 停（10），failed 走 ReAct 回退或停（1）。"""
    state = load_pipeline_state(ctx.task_id, ctx.batch_id)
    completed = set(state.get("completed") or [])
    ensure_batch_layout(ctx.task_id, ctx.batch_id, "pipeline")

    # 外层循环支持 ReAct 回退后重新遍历 DAG
    for _ in range(MAX_REACT_REWINDS * len(DAG) + len(DAG) + 1):
        progressed = False
        for stage_name, kind, runner in DAG:
            if stage_name in completed:
                continue
            result = runner(ctx)
            if result.status == "waiting":
                state["completed"] = sorted(completed)
                state["waitingCheckpoint"] = stage_name
                save_pipeline_state(state)
                print(f"[task run] PAUSED at checkpoint '{stage_name}'\n")
                print(result.checkpoint_hint)
                return 10
            if result.status == "failed":
                completed, rewound = _react_rewind(ctx, state, completed, result)
                if rewound:
                    progressed = True
                    break  # 回 DAG 头重跑回退目标
                state["completed"] = sorted(completed)
                state["waitingCheckpoint"] = None
                state["lastFailedStage"] = stage_name
                save_pipeline_state(state)
                print(f"[task run] FAILED at '{stage_name}': {result.message}", file=sys.stderr)
                return 1
            # done / skipped
            completed.add(stage_name)
            progressed = True
            print(f"[task run] ✓ {stage_name} ({kind}): {result.message}")
            state["completed"] = sorted(completed)
            state["waitingCheckpoint"] = None
            save_pipeline_state(state)
            if ctx.until and stage_name == ctx.until:
                print(f"[task run] stopped at --until {ctx.until}")
                return 0
        else:
            # DAG 全遍历无 break → 全部 stage 完成
            print(f"[task run] PIPELINE COMPLETE — {ctx.task_id} / {ctx.batch_id}")
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
            print(f"[task run] reset pipeline state: {p}")

    until = args.until if getattr(args, "until", None) else None
    if until and until not in STAGE_NAMES:
        print(f"[task run] ERROR: --until 须为 {STAGE_NAMES}", file=sys.stderr)
        raise SystemExit(2)

    ctx = PipelineContext(
        task_id=task_id, batch_id=batch_id, entity_ids=entity_ids,
        spec=spec, until=until,
    )
    code = run_pipeline(ctx)
    if code != 0:
        raise SystemExit(code)


def register_run_parser(sub: argparse._SubParsersAction) -> None:
    pr = sub.add_parser("run", help="无人值守产线编排：按 DAG 跑 download→build→produce→ship")
    pr.add_argument("--task", required=True, help="Task ID")
    pr.add_argument("--batch", default="run_1", help="Batch ID")
    pr.add_argument("--resume", action="store_true",
                    help="从上次 checkpoint 继续（默认即 resume 语义：跳过已完成 stage）")
    pr.add_argument("--reset-state", dest="reset_state", action="store_true",
                    help="清空 pipeline_state 从头跑")
    pr.add_argument("--until", help=f"跑到指定 stage 即停: {STAGE_NAMES}")
    pr.set_defaults(handler=handle_run)
