"""任务规格校验：路径↔id 自洽、archetype scope 必填、实体类型真相源、重复检测。

实体类型真相源 = sop/主页/<领域>/<类型> ∪ 海外补充集合（历史已用但 sop 暂未建）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from _common.paths import (
    SOP_ROOT,
    committed_task_root,
    iter_committed_task_specs,
    normalize_task_id,
    task_id_from_committed_path,
)
from task.store import (
    ARCHETYPE_REQUIRED_SCOPE,
    LABEL_VERTICAL,
    ORGANIZE_ARCHETYPE,
    VERTICAL_LABEL,
    defaults_merged,
    read_yaml,
    resolve_spec,
)
from _common.entity_extract import normalize_domain_etype_path

# 历史已用但不在 sop/主页 的实体类型（海外/特殊），允许其作为 entityType
OVERSEAS_SUPPLEMENT = {
    "地点/演艺场馆",
    "地点/交通枢纽",
    "地点/主题乐园",
}

VALID_VERTICALS = {"travel", "campus", "photography", "tech", "car"}
VALID_ORGANIZE = {"地域", "环线", "主题"}


def known_entity_types() -> set[str]:
    types: set[str] = set(OVERSEAS_SUPPLEMENT)
    home = SOP_ROOT / "主页"
    if home.is_dir():
        for domain_dir in home.iterdir():
            if not domain_dir.is_dir():
                continue
            for type_dir in domain_dir.iterdir():
                if type_dir.is_dir():
                    types.add(f"{domain_dir.name}/{type_dir.name}")
    return types


def lint_spec(spec: dict[str, Any], spec_path: Path, valid_types: set[str]) -> list[str]:
    errors: list[str] = []
    tid = spec.get("taskId", "")

    # 路径 ↔ id 自洽
    try:
        derived = task_id_from_committed_path(spec_path.parent)
    except ValueError:
        derived = None
    if derived and normalize_task_id(tid) != derived:
        errors.append(f"taskId '{tid}' 与目录路径 '{derived}' 不一致")

    # 必填字段
    for field in ("schemaVersion", "taskId", "title", "taskArchetype", "vertical", "organizeBy", "key", "scope"):
        if not spec.get(field):
            errors.append(f"缺少必填字段 {field}")

    vertical = spec.get("vertical")
    if vertical and vertical not in VALID_VERTICALS:
        errors.append(f"非法 vertical: {vertical}")
    # 路径顶层中文标签须与 vertical 对应
    top_segment = normalize_task_id(tid).split("/", 1)[0] if tid else ""
    if vertical and top_segment and LABEL_VERTICAL.get(top_segment) != vertical:
        errors.append(f"taskId 顶层 '{top_segment}' 与 vertical '{vertical}'(应为 '{VERTICAL_LABEL.get(vertical)}') 不一致")

    organize = spec.get("organizeBy")
    if organize and organize not in VALID_ORGANIZE:
        errors.append(f"非法 organizeBy: {organize}")

    archetype = spec.get("taskArchetype")
    if archetype not in ARCHETYPE_REQUIRED_SCOPE:
        errors.append(f"非法 taskArchetype: {archetype}")
    else:
        # organizeBy 与 archetype 协调（province_overview 例外：归属地域轴）
        expected = ORGANIZE_ARCHETYPE.get(organize)
        if expected and archetype not in (expected, "province_overview"):
            errors.append(f"organizeBy '{organize}' 期望 archetype '{expected}'，实得 '{archetype}'")
        scope = spec.get("scope") or {}
        for req in ARCHETYPE_REQUIRED_SCOPE[archetype]:
            val = scope.get(req)
            if not val:
                errors.append(f"archetype {archetype} 要求 scope.{req}")

    # 实体类型真相源
    scope = spec.get("scope") or {}
    for et in scope.get("entityTypes", []) or []:
        if et not in valid_types:
            errors.append(f"未知 entityType '{et}'（不在 sop/主页 ∪ 海外补充）")
    for tgt in scope.get("coverageTargets", []) or []:
        et = tgt.get("entityType")
        if et and et not in valid_types:
            errors.append(f"coverageTargets 未知 entityType '{et}'（实体 {tgt.get('name')}）")
    scenic_targets: dict[str, set[str]] = {}
    for tgt in scope.get("coverageTargets", []) or []:
        name = str(tgt.get("name") or "").strip()
        et = str(tgt.get("entityType") or "").strip()
        if not name or not et:
            continue
        try:
            normalized = normalize_domain_etype_path(
                et,
                context=f"coverageTargets[{name}]",
                allow_default_on_missing=False,
                allow_default_on_unknown=False,
            )
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if normalized in {"地点/景区", "地点/打卡地"}:
            scenic_targets.setdefault(name, set()).add(normalized)
    for name, rows in sorted(scenic_targets.items()):
        if len(rows) > 1:
            errors.append(
                f"coverageTargets 同名实体 '{name}' 同时声明为 {sorted(rows)}；"
                "景区/打卡地 双树共存会导致目录与发布漂移，必须显式纠偏为唯一类型"
            )

    errors.extend(_condition_axes_errors(spec, tid, vertical))
    return errors


def _condition_axes_errors(spec: dict[str, Any], tid: str, vertical: Any) -> list[str]:
    """废弃字段拦截 + 继承解析后(effective)非空 + task 显式 conditionAxes 须为地域全谱子集。"""
    errors: list[str] = []

    prov = spec.get("provenance") or {}
    if prov.get("historySourceTasks"):
        errors.append("provenance.historySourceTasks 已废弃；删除它（出处用 sourceTaskId/runs/notes 追踪）")

    try:
        effective = resolve_spec(spec, tid)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"继承解析失败: {exc}")
        return errors

    eff_content = effective.get("content") or {}
    if not eff_content.get("angles"):
        errors.append("effective content.angles 为空（垂类 _defaults.yaml 应提供 angles 菜单）")
    eff_axes = eff_content.get("conditionAxes") or {}
    if not eff_axes.get("seasons"):
        errors.append("effective conditionAxes.seasons 为空（_defaults.yaml 应提供四季/旱雨季）")
    if vertical == "travel" and not eff_axes.get("regions"):
        errors.append("travel effective conditionAxes.regions 为空（地域/环线 _defaults.yaml 应提供地形全谱）")

    raw_axes = ((spec.get("content") or {}).get("conditionAxes")) or {}
    if raw_axes.get("regions") or raw_axes.get("seasons"):
        menu = (defaults_merged(tid).get("content") or {}).get("conditionAxes") or {}
        menu_regions = set(menu.get("regions") or [])
        menu_seasons = set(menu.get("seasons") or [])
        for r in raw_axes.get("regions") or []:
            if menu_regions and r not in menu_regions:
                errors.append(f"conditionAxes.regions '{r}' 不在继承地形全谱 {sorted(menu_regions)} 内")
        for s in raw_axes.get("seasons") or []:
            if menu_seasons and s not in menu_seasons:
                errors.append(f"conditionAxes.seasons '{s}' 不在继承季节全谱 {sorted(menu_seasons)} 内")

    return errors


def content_redundancy_warnings(spec: dict[str, Any], tid: str) -> list[str]:
    """PR_WARN：task 显式 content 字段与继承默认完全相同 → 建议删除以继承（不阻断）。"""
    warnings: list[str] = []
    raw_content = spec.get("content") or {}
    menu = defaults_merged(tid).get("content") or {}
    for field in ("angles", "audiences", "carriers"):
        if field in raw_content and raw_content.get(field) == menu.get(field):
            warnings.append(f"content.{field} 与继承默认完全相同，建议删除该字段以继承")
    raw_ca = raw_content.get("conditionAxes")
    if raw_ca is not None and raw_ca == menu.get("conditionAxes"):
        warnings.append("content.conditionAxes 与继承默认完全相同，建议删除以继承地域全谱")
    return warnings


def lint_all(
    only_task_id: str | None = None,
) -> tuple[int, dict[str, list[str]], dict[str, list[str]]]:
    valid_types = known_entity_types()
    results: dict[str, list[str]] = {}
    warnings: dict[str, list[str]] = {}
    seen_ids: dict[str, Path] = {}

    specs = iter_committed_task_specs()
    if only_task_id:
        target = committed_task_root(only_task_id) / "task.yaml"
        specs = [s for s in specs if s == target]
        if not specs and target.exists():
            specs = [target]

    total_errors = 0
    for spec_path in specs:
        try:
            spec = read_yaml(spec_path)
        except Exception as exc:  # noqa: BLE001
            results[str(spec_path)] = [f"YAML 解析失败: {exc}"]
            total_errors += 1
            continue
        tid = spec.get("taskId", str(spec_path))
        errors = lint_spec(spec, spec_path, valid_types)
        if tid in seen_ids:
            errors.append(f"重复 taskId（另见 {seen_ids[tid]}）")
        else:
            seen_ids[tid] = spec_path
        warns = content_redundancy_warnings(spec, tid)
        if warns:
            warnings[tid] = warns
        if errors:
            results[tid] = errors
            total_errors += len(errors)
    return total_errors, results, warnings
