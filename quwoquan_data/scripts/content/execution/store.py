"""Execution 规格、进度、运行记录与 family preset 存取。"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

import yaml

from core.io import read_json, write_json
from core.paths import (
    execution_spec_path,
    normalize_family_ref,
    preset_path,
    sanitize_intent_label,
)
from content.execution.workspace import execution_progress_path, execution_root

SPEC_VERSION = "quwoquan.content.execution_spec"
PROGRESS_VERSION = "quwoquan.content.execution_progress"
RUN_VERSION = "quwoquan.content.workflow"
PRESET_VERSION = "quwoquan.content.preset"
RECIPE_VERSION = "quwoquan.content.recipe"

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
    execution_id: str,
    vertical: str,
    organize_by: str,
    key: str,
    name: str,
    category: str | None = None,
    archetype: str | None = None,
    title: str | None = None,
    intent_label: str | None = None,
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
    arche = archetype or ORGANIZE_ARCHETYPE.get(organize_by, "region_category_coverage")
    spec: dict[str, Any] = {
        "schemaVersion": SPEC_VERSION,
        "executionId": execution_id,
        "title": title or f"{key}{category or ''}{name}",
        "intentLabel": sanitize_intent_label(intent_label or name),
        "executionArchetype": arche,
        "vertical": vertical,
        "organizeBy": organize_by,
        "key": key,
        "entityCategory": category,
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


def init_progress(execution_id: str, remaining: list[str] | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": PROGRESS_VERSION,
        "executionId": execution_id,
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
    from core.schema import assert_valid

    assert_valid(spec, "execution", "execution_spec", label=f"execution_spec:{spec.get('executionId', '')}")
    path = execution_spec_path(spec["executionId"])
    write_yaml(path, spec)
    return path


def load_raw_spec(execution_id: str) -> dict[str, Any]:
    """读取未合并默认的 execution spec（save / lint / 编辑用）。"""
    return read_yaml(execution_spec_path(execution_id))


def load_spec(execution_id: str) -> dict[str, Any]:
    """读取合并 preset 默认后的 effective spec（ops/post 消费）。

    execution spec 的 presetRef 指向家族包 preset；preset.defaults deep-merge 后
    再叠加 execution spec（执行实例显式声明覆盖默认，list 替换语义）。
    """
    return resolve_spec(load_raw_spec(execution_id), execution_id)


def spec_exists(execution_id: str) -> bool:
    return execution_spec_path(execution_id).exists()


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
    """读取家族包 preset 文档（schemaVersion 必须是 quwoquan.content.preset）。"""
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


def resolve_spec(raw_spec: dict[str, Any], execution_id: str | None = None) -> dict[str, Any]:
    """合并 presetRef 默认 + 原始 spec。身份字段始终来自 raw_spec；无 presetRef 则原样返回。"""
    del execution_id  # 默认值只由 presetRef 决定，与 executionId 路径无关。
    return _deep_merge(preset_defaults(spec_preset_ref(raw_spec)), raw_spec)


def save_progress(progress: dict[str, Any]) -> Path:
    from core.schema import assert_valid

    progress["updatedAt"] = now_iso()
    assert_valid(
        progress,
        "execution",
        "execution_progress",
        label=f"execution_progress:{progress.get('executionId', '')}",
    )
    path = execution_progress_path(progress["executionId"])
    write_json(path, progress)
    return path


def load_progress(execution_id: str) -> dict[str, Any]:
    path = execution_progress_path(execution_id)
    if path.exists():
        return read_json(path)
    return init_progress(execution_id)
