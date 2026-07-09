"""任务规格/进度/run 存取 + 脚手架 + 锁。

committed: quwoquan_data/control_plane/tasks/<taskId>/ {task.yaml(入库), progress.json, runs/, notes.md(本地)}
preset   : quwoquan_data/control_plane/families/<presetRef>.preset.yaml（受版本控制，默认值唯一真相源）
runtime  : QWQ_OUTPUT_ROOT/local/data-runtime/tasks/<taskId>/ {.lock, 生成产物}
taskId    : 斜杠路径 <vertical>/<organizeBy>/<key>[/<category>]/<name>
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any

import yaml

from _common.io import read_json, write_json
from _common.paths import (
    clear_intent_label_cache,
    committed_task_notes,
    committed_task_progress,
    committed_task_root,
    committed_task_runs_dir,
    committed_task_spec,
    normalize_family_ref,
    normalize_task_id,
    preset_path,
    sanitize_intent_label,
    task_lock_path,
    task_root,
)

SPEC_VERSION = "quwoquan.task.spec"
PROGRESS_VERSION = "quwoquan.task.progress"
RUN_VERSION = "quwoquan.task.run"
PRESET_VERSION = "quwoquan.task.preset"
RECIPE_VERSION = "quwoquan.task.recipe"

# vertical(英文 id，供 --vertical/采样) ↔ 路径顶层中文标签（对齐 app home channel 显示名）
VERTICAL_LABEL = {
    "travel": "旅行",
    "campus": "校园",
    "photography": "摄影",
    "tech": "科技",
    "car": "汽车",
}
LABEL_VERTICAL = {v: k for k, v in VERTICAL_LABEL.items()}

# organizeBy → 默认 archetype
ORGANIZE_ARCHETYPE = {
    "地域": "region_category_coverage",
    "环线": "loop_route",
    "主题": "theme_collection",
}

# archetype → scope 必填键（lint 用）
ARCHETYPE_REQUIRED_SCOPE: dict[str, list[str]] = {
    "region_category_coverage": ["region", "entityTypes"],
    "province_overview": ["region"],
    "loop_route": ["route", "anchorEntities"],
    "theme_collection": ["theme"],
}


def build_task_id(vertical: str, organize_by: str, key: str, category: str | None, name: str) -> str:
    top = VERTICAL_LABEL.get(vertical, vertical)
    parts = [top, organize_by, key]
    if category:
        parts.append(category)
    parts.append(name)
    return "/".join(p.strip().strip("/") for p in parts if p and p.strip())


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _prune_empty(value: Any) -> Any:
    """去掉空 dict/list/None，使省略字段沿 presetRef 默认继承（不以空值覆盖默认）。"""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            pruned = _prune_empty(v)
            if pruned not in (None, {}, []):
                out[k] = pruned
        return out
    return value


def default_preset_ref(vertical: str) -> str | None:
    """按垂类解析默认 presetRef（家族包存在才返回；不产生指向空文件的引用）。"""
    ref = f"content/{vertical}/article/base"
    return ref if preset_path(ref).is_file() else None


def scaffold_spec(
    *,
    vertical: str,
    organize_by: str,
    key: str,
    name: str,
    category: str | None = None,
    archetype: str | None = None,
    title: str | None = None,
    intent_label: str | None = None,
    parent_task_id: str | None = None,
    preset_ref: str | None = None,
    scope: dict[str, Any] | None = None,
    content: dict[str, Any] | None = None,
    acceptance: dict[str, Any] | None = None,
    created_by: str = "task new",
) -> dict[str, Any]:
    """脚手架最小化 spec：只写身份 + presetRef + scope + 非空 content/acceptance override。

    默认值唯一真相源 = presetRef 指向的家族包 preset；未显式给出时按垂类解析
    `content/<vertical>/article/base`（存在才写入，不做运行期隐式回退）。
    intentLabel = ≤16 字人类可读任务意图标签（顶层批次目录前缀真相源），
    缺省由任务名清洗截断；用户指令/对话应给出更精炼的意图标签。
    """
    task_id = build_task_id(vertical, organize_by, key, category, name)
    arche = archetype or ORGANIZE_ARCHETYPE.get(organize_by, "region_category_coverage")
    spec: dict[str, Any] = {
        "schemaVersion": SPEC_VERSION,
        "taskId": task_id,
        "title": title or f"{key}{category or ''}{name}",
        "intentLabel": sanitize_intent_label(intent_label or name),
        "taskArchetype": arche,
        "vertical": vertical,
        "organizeBy": organize_by,
        "key": key,
        "entityCategory": category,
        "parentTaskId": parent_task_id,
        "status": "draft",
        "scope": scope or {},
        "provenance": {"createdAt": now_iso(), "createdBy": created_by},
    }
    resolved_preset = normalize_family_ref(preset_ref or "") or default_preset_ref(vertical)
    if resolved_preset:
        spec["presetRef"] = resolved_preset
    pruned_content = _prune_empty(content or {})
    if pruned_content:
        spec["content"] = pruned_content
    pruned_acceptance = _prune_empty(acceptance or {})
    if pruned_acceptance:
        spec["acceptance"] = pruned_acceptance
    return spec


def init_progress(task_id: str, remaining: list[str] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": PROGRESS_VERSION,
        "taskId": task_id,
        "updatedAt": now_iso(),
        "coverage": {
            "entities": {"done": [], "remaining": remaining or []},
            "categoriesDone": [],
        },
        "anglesByEntity": {},
        "openGaps": [],
        "counts": {"entities": 0, "posts": 0},
        "lastRunId": None,
    }


# ─── IO ─────────────────────────────────────────────────────────────
def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def read_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_spec(spec: dict[str, Any]) -> Path:
    path = committed_task_spec(spec["taskId"])
    write_yaml(path, spec)
    # committed 规格变更后，刷新 intentLabel 解析缓存（顶层批次目录前缀依赖它）。
    clear_intent_label_cache()
    return path


def load_raw_spec(task_id: str) -> dict[str, Any]:
    """读取未合并默认的原始 task.yaml（save / lint / 编辑用）。"""
    return read_yaml(committed_task_spec(task_id))


def load_spec(task_id: str) -> dict[str, Any]:
    """读取合并 preset 默认后的 effective spec（ops/produce 消费）。

    raw task.yaml 的 presetRef 指向家族包 preset；preset.defaults deep-merge 后
    再叠加原始 task.yaml（task 显式声明覆盖默认，list 替换语义）。
    """
    return resolve_spec(load_raw_spec(task_id), task_id)


def spec_exists(task_id: str) -> bool:
    return committed_task_spec(task_id).exists()


# ─── preset resolver（默认值唯一真相源）──────────────────────────────
def _deep_merge(base: Any, override: Any) -> Any:
    """dict 递归合并；list/标量由 override 整体替换。"""
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = _deep_merge(out[k], v) if k in out else v
        return out
    return override


def spec_preset_ref(spec: dict[str, Any]) -> str:
    """读取 spec 声明的 presetRef（归一化；未声明返回空串）。"""
    return normalize_family_ref(str(spec.get("presetRef") or ""))


def load_preset(preset_ref: str) -> dict[str, Any]:
    """读取家族包 preset 文档（schemaVersion 必须是 quwoquan.task.preset）。"""
    ref = normalize_family_ref(preset_ref)
    path = preset_path(ref)
    if not path.is_file():
        raise FileNotFoundError(f"presetRef '{ref}' 不存在: {path}")
    doc = read_yaml(path)
    if not isinstance(doc, dict) or doc.get("schemaVersion") != PRESET_VERSION:
        raise ValueError(f"preset '{ref}' schemaVersion 必须为 {PRESET_VERSION}")
    return doc


def preset_defaults(preset_ref: str) -> dict[str, Any]:
    """某 preset 的默认值菜单（task 未显式声明的字段由此补齐；list 替换语义）。"""
    ref = normalize_family_ref(preset_ref)
    if not ref:
        return {}
    defaults = load_preset(ref).get("defaults") or {}
    return defaults if isinstance(defaults, dict) else {}


def resolve_spec(raw_spec: dict[str, Any], task_id: str | None = None) -> dict[str, Any]:
    """合并 presetRef 默认 + 原始 spec。身份字段始终来自 raw_spec；无 presetRef 则原样返回。"""
    del task_id  # 默认值只由 presetRef 决定，与 taskId 路径无关（旧路径继承链已退役）
    return _deep_merge(preset_defaults(spec_preset_ref(raw_spec)), raw_spec)


def save_progress(progress: dict[str, Any]) -> Path:
    progress["updatedAt"] = now_iso()
    path = committed_task_progress(progress["taskId"])
    write_json(path, progress)
    return path


def load_progress(task_id: str) -> dict[str, Any]:
    path = committed_task_progress(task_id)
    if path.exists():
        return read_json(path)
    return init_progress(task_id)


def append_run(task_id: str, run: dict[str, Any]) -> Path:
    runs_dir = committed_task_runs_dir(task_id)
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run['runId']}.json"
    write_json(path, run)
    return path


def write_notes_if_absent(task_id: str, body: str) -> Path:
    path = committed_task_notes(task_id)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return path


# ─── 锁 ─────────────────────────────────────────────────────────────
STALE_LOCK_SECONDS = 6 * 3600


def read_lock(task_id: str) -> dict[str, Any] | None:
    path = task_lock_path(task_id)
    if not path.exists():
        return None
    try:
        return read_json(path)
    except Exception:
        return {"corrupt": True, "path": str(path)}


def acquire_lock(task_id: str, owner: str, *, force: bool = False) -> tuple[bool, str]:
    path = task_lock_path(task_id)
    existing = read_lock(task_id)
    if existing and not force:
        ts = existing.get("ts", "")
        if not _lock_is_stale(ts):
            return False, f"locked by {existing.get('owner')} (pid={existing.get('pid')}, ts={ts})"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, {
        "taskId": task_id,
        "owner": owner,
        "pid": os.getpid(),
        "ts": _real_now(),
    })
    return True, "acquired"


def release_lock(task_id: str) -> bool:
    path = task_lock_path(task_id)
    if path.exists():
        path.unlink()
        return True
    return False


def _real_now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _lock_is_stale(ts: str) -> bool:
    if not ts:
        return True
    try:
        t = _dt.datetime.fromisoformat(ts)
    except ValueError:
        return True
    age = (_dt.datetime.now().astimezone() - t).total_seconds()
    return age > STALE_LOCK_SECONDS


def runtime_task_root(task_id: str) -> Path:
    return task_root(normalize_task_id(task_id))
