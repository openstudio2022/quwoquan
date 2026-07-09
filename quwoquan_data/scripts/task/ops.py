"""任务运维操作：list/show/resume/status/record-run/trace/hydrate。"""
from __future__ import annotations

import datetime as _dt
import json
import shutil
from pathlib import Path
from typing import Any

from _common.io import read_json
from _common.paths import (
    PUBLISH_ROOT,
    TASK_SHARED_LEDGER_FILENAMES,
    committed_task_notes,
    committed_task_root,
    committed_task_runs_dir,
    iter_committed_task_specs,
    iter_existing_task_legacy_entries,
    iter_task_batch_dirs,
    publish_data,
    task_id_from_committed_path,
    task_root,
    task_shared_dir,
)
from task.store import (
    append_run,
    load_progress,
    load_raw_spec,
    load_spec,
    read_lock,
    read_yaml,
    runtime_task_root,
    save_progress,
)


def _entity_ref(target: dict[str, Any]) -> str:
    return f"{target.get('entityType')}/{target.get('name')}"


# ─── list / tree ────────────────────────────────────────────────────
def collect_rows(vertical: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec_path in iter_committed_task_specs():
        try:
            spec = read_yaml(spec_path)
        except Exception:  # noqa: BLE001
            continue
        if vertical and spec.get("vertical") != vertical:
            continue
        tid = spec.get("taskId") or task_id_from_committed_path(spec_path.parent)
        prog = load_progress(tid)
        ent = prog.get("coverage", {}).get("entities", {})
        lock = read_lock(tid)
        rows.append({
            "taskId": tid,
            "title": spec.get("title", ""),
            "top": tid.split("/", 1)[0],
            "vertical": spec.get("vertical", ""),
            "organizeBy": spec.get("organizeBy", ""),
            "key": spec.get("key", ""),
            "category": spec.get("entityCategory") or "",
            "archetype": spec.get("taskArchetype", ""),
            "status": spec.get("status", "draft"),
            "done": len(ent.get("done", [])),
            "remaining": len(ent.get("remaining", [])),
            "lock": (lock or {}).get("owner") if lock else None,
        })
    rows.sort(key=lambda r: r["taskId"])
    return rows


def print_list(vertical: str | None = None) -> None:
    rows = collect_rows(vertical)
    if not rows:
        print("[task] 无任务（quwoquan_data/control_plane/tasks/ 为空）")
        return
    print(f"{'taskId':<46} {'arch':<24} {'status':<8} {'cov(done/rem)':<14} lock")
    print("-" * 104)
    for r in rows:
        cov = f"{r['done']}/{r['done'] + r['remaining']}"
        print(f"{r['taskId']:<46} {r['archetype']:<24} {r['status']:<8} {cov:<14} {r['lock'] or '-'}")
    print(f"\n总计 {len(rows)} 个任务")


def print_tree(vertical: str | None = None) -> None:
    rows = collect_rows(vertical)
    if not rows:
        print("[task] 无任务")
        return
    tree: dict[str, Any] = {}
    for r in rows:
        v = tree.setdefault(r["top"], {})
        o = v.setdefault(r["organizeBy"], {})
        k = o.setdefault(r["key"], [])
        k.append(r)
    for v, obys in sorted(tree.items()):
        print(f"{v}")
        for oby, keys in sorted(obys.items()):
            print(f"  {oby}")
            for key, items in sorted(keys.items()):
                print(f"    {key}")
                for r in items:
                    cov = f"{r['done']}/{r['done'] + r['remaining']}"
                    cat = f"{r['category']}/" if r["category"] else ""
                    lock = f" [lock:{r['lock']}]" if r["lock"] else ""
                    print(f"      {cat}{r['title']}  ({r['status']}, cov {cov}){lock}")
    print(f"\n总计 {len(rows)} 个任务")


# ─── show ───────────────────────────────────────────────────────────
def show(task_id: str) -> None:
    raw = load_raw_spec(task_id)
    effective = load_spec(task_id)
    prog = load_progress(task_id)
    lock = read_lock(task_id)
    print(json.dumps(
        {
            "rawSpec": raw,
            "effectiveSpec": effective,
            "progress": prog,
            "lock": lock,
            "postOutputs": latest_post_outputs(task_id),
        },
        ensure_ascii=False, indent=2,
    ))


# ─── resume / status ────────────────────────────────────────────────
def compute_gaps(task_id: str) -> dict[str, Any]:
    spec = load_spec(task_id)
    prog = load_progress(task_id)
    ent = prog.get("coverage", {}).get("entities", {})
    remaining_entities = list(ent.get("remaining", []))
    done_entities = list(ent.get("done", []))

    angles = spec.get("content", {}).get("angles", []) or []
    angles_by_entity = prog.get("anglesByEntity", {})
    missing_angles: dict[str, list[str]] = {}
    for e in done_entities:
        have = set(angles_by_entity.get(e, []))
        miss = [a for a in angles if a not in have]
        if miss:
            missing_angles[e] = miss

    return {
        "remainingEntities": remaining_entities,
        "missingAnglesByEntity": missing_angles,
        "openGaps": prog.get("openGaps", []),
    }


def latest_post_outputs(task_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return materialized post package locations under top-level runtime/batches."""
    rows: list[dict[str, Any]] = []
    # 顶层 runtime/batches/<intentLabel>__<batch>/ 反查该任务批次（依据 batch_manifest.taskId）。
    for batch_dir in iter_task_batch_dirs(task_id):
        posts_root = batch_dir / "posts"
        if not posts_root.is_dir():
            continue
        manifest_meta = read_json(batch_dir / "batch_manifest.json") if (batch_dir / "batch_manifest.json").is_file() else {}
        batch_id = str((manifest_meta or {}).get("batchId") or "")
        # 对象优先：成品落 batch/posts/{type}/{angle}/{title}/{seq}/。
        for manifest in sorted(posts_root.rglob("manifest.json")):
            leaf = manifest.parent
            try:
                rel = leaf.relative_to(batch_dir)
            except ValueError:
                continue
            parts = rel.parts
            if len(parts) < 4 or parts[0] != "posts":
                continue
            if not ((leaf / "article.md").exists() or (leaf / "gallery.md").exists()):
                continue
            try:
                data = read_json(manifest)
            except Exception:  # noqa: BLE001
                continue
            rows.append(
                {
                    "batchId": batch_id,
                    "title": data.get("publishTitle") or data.get("title") or manifest.parent.parent.name,
                    "contentType": data.get("contentType") or "",
                    "path": str(rel).replace("\\", "/"),
                    "articlePath": str((rel / "article.md")).replace("\\", "/"),
                    "sourceBatchId": data.get("sourceBatchId") or batch_id,
                }
            )
    rows.sort(key=lambda r: (r["batchId"], r["path"]), reverse=True)
    return rows[:limit]


def resume(task_id: str) -> None:
    spec = load_spec(task_id)
    gaps = compute_gaps(task_id)
    print(f"[resume] {task_id} — {spec.get('title')}")
    print(f"  archetype={spec.get('taskArchetype')} status={spec.get('status')}")
    if gaps["openGaps"]:
        print("  已知缺口(openGaps):")
        for g in gaps["openGaps"]:
            print(f"    - {g}")
    if gaps["remainingEntities"]:
        print(f"  待补实体 ({len(gaps['remainingEntities'])}):")
        for e in gaps["remainingEntities"][:30]:
            print(f"    - {e}")
    if gaps["missingAnglesByEntity"]:
        print("  缺角度(已建实体):")
        for e, angs in list(gaps["missingAnglesByEntity"].items())[:30]:
            print(f"    - {e}: {', '.join(angs)}")
    if not any([gaps["remainingEntities"], gaps["missingAnglesByEntity"], gaps["openGaps"]]):
        print("  无缺口：任务覆盖已达成。")
    reflections = recent_reflections(task_id, limit=3)
    if reflections:
        print("  历史反思（近 3 条，复用经验加速）:")
        for r in reflections:
            print(f"    - [{r.get('runId')}] 归因={r.get('attribution') or '—'} → 决策={r.get('decision') or '—'}")
    print(f"\n  下一步：lock → explore/produce 补上述缺口 → record-run。runtime 工作区：{runtime_task_root(task_id)}")


def status(task_id: str) -> None:
    spec = load_spec(task_id)
    prog = load_progress(task_id)
    ent = prog.get("coverage", {}).get("entities", {})
    done, rem = len(ent.get("done", [])), len(ent.get("remaining", []))
    total = done + rem
    pct = (done / total * 100) if total else 0.0
    print(f"[status] {task_id}")
    print(f"  广度: {done}/{total} 实体 ({pct:.0f}%)")
    print(f"  深度: anglesByEntity={len(prog.get('anglesByEntity', {}))} 实体有角度记录")
    print(f"  计数: entities={prog.get('counts', {}).get('entities', 0)} posts={prog.get('counts', {}).get('posts', 0)}")
    print(f"  lastRunId: {prog.get('lastRunId')}")
    outputs = latest_post_outputs(task_id, limit=5)
    if outputs:
        print("  最新文章产物:")
        for item in outputs:
            print(f"    - [{item['batchId']}] {item['title']} -> {item['articlePath']}")


# ─── record-run + 反思账本 ──────────────────────────────────────────
def _normalize_reflections(reflections: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """规范反思条目为 {query, attribution, decision}，丢弃全空条目。"""
    out: list[dict[str, str]] = []
    for r in reflections or []:
        item = {
            "query": str(r.get("query") or "").strip(),
            "attribution": str(r.get("attribution") or "").strip(),
            "decision": str(r.get("decision") or "").strip(),
        }
        if any(item.values()):
            out.append(item)
    return out


def _append_reflection_notes(task_id: str, run_id: str, reflections: list[dict[str, str]]) -> None:
    """把反思账本追加到 notes.md「经验沉淀」，供下次任务复用（单一沉淀位）。"""
    if not reflections:
        return
    path = committed_task_notes(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"\n### 反思账本 · {run_id}\n"]
    for r in reflections:
        lines.append(f"- query: {r['query'] or '—'}\n")
        lines.append(f"  - 归因: {r['attribution'] or '—'}\n")
        lines.append(f"  - 决策: {r['decision'] or '—'}\n")
    with open(path, "a", encoding="utf-8") as f:
        f.writelines(lines)


def recent_reflections(task_id: str, limit: int = 3) -> list[dict[str, Any]]:
    """读最近 limit 个 run 的反思（最新优先），供 resume 加载历史经验。"""
    runs_dir = committed_task_runs_dir(task_id)
    if not runs_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for f in sorted(runs_dir.glob("run_*.json"), reverse=True):
        try:
            data = read_json(f)
        except Exception:  # noqa: BLE001
            continue
        for r in data.get("reflections", []):
            out.append({"runId": data.get("runId"), **r})
            if len(out) >= limit:
                return out
    return out


def record_run(
    task_id: str,
    *,
    owner: str,
    summary: str,
    entities_added: int = 0,
    posts_added: int = 0,
    mark_done: list[str] | None = None,
    next_suggested: list[str] | None = None,
    batches: list[str] | None = None,
    reflections: list[dict[str, Any]] | None = None,
    open_gaps: list[str] | None = None,
) -> Path:
    run_id = "run_" + _dt.datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    norm_reflections = _normalize_reflections(reflections)
    run = {
        "schemaVersion": "quwoquan.task.run",
        "runId": run_id,
        "taskId": task_id,
        "startedAt": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "finishedAt": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "owner": owner,
        "batches": batches or [],
        "delta": {"entitiesAdded": entities_added, "postsAdded": posts_added, "entitiesUpdated": 0, "postsUpdated": 0},
        "sessionSummary": summary,
        "decisions": [],
        "reflections": norm_reflections,
        "nextSuggested": next_suggested or [],
    }
    run_path = append_run(task_id, run)
    _append_reflection_notes(task_id, run_id, norm_reflections)

    prog = load_progress(task_id)
    ent = prog["coverage"]["entities"]
    for e in (mark_done or []):
        if e in ent["remaining"]:
            ent["remaining"].remove(e)
        if e not in ent["done"]:
            ent["done"].append(e)
    for gap in (open_gaps or []):
        if gap and gap not in prog.setdefault("openGaps", []):
            prog["openGaps"].append(gap)
    prog["counts"]["entities"] = prog["counts"].get("entities", 0) + entities_added
    prog["counts"]["posts"] = prog["counts"].get("posts", 0) + posts_added
    prog["lastRunId"] = run_id
    save_progress(prog)
    print(f"[record-run] {run_path}  (lastRunId={run_id}, reflections={len(norm_reflections)})")
    return run_path


# ─── trace / hydrate（溯源反查 / 拉回工作区）─────────────────────────
def _iter_publish_manifests() -> list[tuple[Path, dict[str, Any]]]:
    out: list[tuple[Path, dict[str, Any]]] = []
    posts_root = PUBLISH_ROOT / "posts"
    if posts_root.is_dir():
        for mf in posts_root.rglob("manifest.json"):
            try:
                out.append((mf, read_json(mf)))
            except Exception:  # noqa: BLE001
                continue
    ents_root = PUBLISH_ROOT / "entities"
    if ents_root.is_dir():
        for ef in ents_root.rglob("_entity.json"):
            try:
                out.append((ef, read_json(ef)))
            except Exception:  # noqa: BLE001
                continue
    return out


def trace(*, ref: str | None = None, task_id: str | None = None) -> None:
    """ref 模式：查某 publish 路径片段来自哪个任务；task_id 模式：列任务在 publish 的全部产物。"""
    hits = 0
    for path, data in _iter_publish_manifests():
        src = data.get("sourceTaskId")
        rel = str(path.relative_to(PUBLISH_ROOT))
        if ref and ref in rel:
            print(f"  {rel}  <- sourceTaskId={src}")
            hits += 1
        elif task_id and src == task_id:
            print(f"  {rel}")
            hits += 1
    print(f"[trace] 命中 {hits} 项")


def _ref_matches(entity_refs: list, prefixes: list[str]) -> bool:
    for raw in entity_refs or []:
        norm = str(raw).strip().lstrip("/")
        if norm.startswith("entity/"):
            norm = norm[len("entity/"):]
        for p in prefixes:
            if norm.startswith(p):
                return True
    return False


def adopt_publish(task_id: str, entity_type_prefixes: list[str], *, batch_id: str = "adopted_history", force: bool = False) -> dict:
    """把 publish 现有内容纳入某任务：给匹配的 post manifest / _entity.json 回填 sourceTaskId。

    用于历史 bootstrap 内容（无任务归属）正式发布到某任务体系下，使其可溯源/可 ship。
    幂等：默认只补缺失（force 覆盖）。返回计数 + 采纳的实体 ref。
    """
    posts_done = 0
    ents_done = 0
    adopted_entities: list[str] = []

    posts_root = PUBLISH_ROOT / "posts"
    if posts_root.is_dir():
        for mf in posts_root.rglob("manifest.json"):
            try:
                data = read_json(mf)
            except Exception:  # noqa: BLE001
                continue
            if not _ref_matches(data.get("entityRefs", []), entity_type_prefixes):
                continue
            if data.get("sourceTaskId") and not force:
                continue
            data["sourceTaskId"] = task_id
            data.setdefault("sourceBatchId", batch_id)
            from _common.io import write_json as _wj
            _wj(mf, data)
            posts_done += 1

    ents_root = PUBLISH_ROOT / "entities"
    for prefix in entity_type_prefixes:
        base = ents_root / prefix
        if not base.is_dir():
            continue
        for ef in base.rglob("_entity.json"):
            try:
                data = read_json(ef)
            except Exception:  # noqa: BLE001
                continue
            rel = ef.parent.relative_to(ents_root)
            adopted_entities.append(str(rel).replace("\\", "/"))
            if data.get("sourceTaskId") and not force:
                continue
            data["sourceTaskId"] = task_id
            from _common.io import write_json as _wj
            _wj(ef, data)
            ents_done += 1

    print(f"[adopt] {task_id}: posts+={posts_done} entities+={ents_done} (matched entities={len(adopted_entities)})")
    return {"posts": posts_done, "entities": ents_done, "adoptedEntities": sorted(set(adopted_entities))}


def _prune_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return
    for d in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()


def prune_publish(*, orphans_only: bool = True) -> dict:
    """清除 publish 中无任务归属(sourceTaskId 为空)的孤儿 posts/entities。

    被 adopt/materialize 写过 sourceTaskId 的内容保留；历史 bootstrap 未认领内容清除。
    """
    removed_posts = 0
    removed_entities = 0

    posts_root = PUBLISH_ROOT / "posts"
    if posts_root.is_dir():
        victims = []
        for mf in posts_root.rglob("manifest.json"):
            try:
                data = read_json(mf)
            except Exception:  # noqa: BLE001
                continue
            if orphans_only and not data.get("sourceTaskId"):
                victims.append(mf.parent)
        for d in victims:
            shutil.rmtree(d, ignore_errors=True)
            removed_posts += 1

    ents_root = PUBLISH_ROOT / "entities"
    if ents_root.is_dir():
        victims = []
        for ef in ents_root.rglob("_entity.json"):
            try:
                data = read_json(ef)
            except Exception:  # noqa: BLE001
                continue
            if orphans_only and not data.get("sourceTaskId"):
                victims.append(ef.parent)
        for d in victims:
            shutil.rmtree(d, ignore_errors=True)
            removed_entities += 1

    _prune_empty_dirs(posts_root)
    _prune_empty_dirs(ents_root)
    print(f"[prune] removed orphan posts={removed_posts} entities={removed_entities}")
    return {"posts": removed_posts, "entities": removed_entities}


def hydrate(task_id: str) -> None:
    """按 sourceTaskId 把该任务在 publish 的 posts/entities 拉回 runtime 工作区以修改重 promote。"""
    dst_root = runtime_task_root(task_id)
    copied = 0
    for path, data in _iter_publish_manifests():
        if data.get("sourceTaskId") != task_id:
            continue
        rel = path.parent.relative_to(PUBLISH_ROOT)
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(path.parent, dst)
        copied += 1
    print(f"[hydrate] {task_id}: 拉回 {copied} 项到 {dst_root}")


def cleanup_runtime(task_id: str) -> dict[str, Any]:
    """一次性收敛 task runtime 根目录：迁移 `_shared` 账本并清理历史镜像位。"""
    root = task_root(task_id)
    if not root.is_dir():
        raise FileNotFoundError(f"task runtime root not found: {root}")
    shared_dir = task_shared_dir(task_id)
    shared_dir.mkdir(parents=True, exist_ok=True)

    migrated: list[str] = []
    removed: list[str] = []
    skipped: list[str] = []

    for filename in TASK_SHARED_LEDGER_FILENAMES:
        legacy = root / filename
        canonical = shared_dir / filename
        if not legacy.exists():
            continue
        if canonical.exists():
            skipped.append(f"{filename}: canonical exists, drop legacy")
        else:
            canonical.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy), str(canonical))
            migrated.append(filename)
            continue
        if legacy.is_dir():
            shutil.rmtree(legacy, ignore_errors=True)
        else:
            legacy.unlink(missing_ok=True)
        removed.append(filename)

    for legacy in iter_existing_task_legacy_entries(task_id):
        if legacy.name in TASK_SHARED_LEDGER_FILENAMES:
            continue
        if legacy.is_dir():
            shutil.rmtree(legacy, ignore_errors=True)
        else:
            legacy.unlink(missing_ok=True)
        removed.append(legacy.name)

    remaining_legacy = [path.name for path in iter_existing_task_legacy_entries(task_id)]
    result = {
        "taskId": task_id,
        "migrated": sorted(migrated),
        "removed": sorted(set(removed)),
        "skipped": skipped,
        "remainingLegacyEntries": remaining_legacy,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result
