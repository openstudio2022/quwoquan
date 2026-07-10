"""任务规格校验：路径↔id 自洽、archetype scope 必填、实体类型真相源、重复检测。

实体类型唯一真相源 = `Entity/{维度}` 标签树一级节点（裁决 6，经
`_common.entity_type_taxonomy` 消费；旧 `sop/主页` 拍平口径与海外补充集合已退役）。
sop/主页 目录降级为「主页模板 SOP 载体」，lint 只做 sop↔Entity 树一致性校验。
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any

from _common.entity_type_taxonomy import (
    find_entity_type_node_path,
    known_entity_type_paths,
)
from _common.paths import (
    COMMITTED_TASKS_ROOT,
    REPO_ROOT,
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
    preset_defaults,
    read_yaml,
    resolve_spec,
    spec_preset_ref,
)
from _common.entity_extract import normalize_domain_etype_path
from _common.image_asset_strategy import (
    image_asset_strategy_scale_issues,
    validate_image_asset_strategy,
)
from _common.quality_gates import WRITING_INTENTS

VALID_VERTICALS = {"travel", "campus", "photography", "tech", "car"}
VALID_ORGANIZE = {"地域", "环线", "主题"}


def known_entity_types() -> set[str]:
    """合法 entityType = `{Entity维度}/{一级节点}`（如 地点/景区、机构/学校）。

    单一口径收敛（收债 9）：不再从 sop/主页 拍平派生，也不再维护海外补充集合；
    sop 子级类型（咖啡馆/民宿等 餐厅//住宿/ 细分）不可作 entityType 主类型，
    细分归属经 typeTagRefs 叶子表达。
    """
    return known_entity_type_paths()


def sop_taxonomy_consistency_errors() -> list[str]:
    """sop/主页/{domain}/{type} 目录必须能命中 `Entity/{domain}` 树内节点（任意层）。

    sop 目录是主页模板 SOP 载体，可为子级类型（如 咖啡馆 → Entity/地点/餐厅/咖啡馆）
    建 SOP，但不得出现 Entity 树查无此名的第二套类型定义。
    """
    errors: list[str] = []
    home = SOP_ROOT / "主页"
    if not home.is_dir():
        return errors
    for domain_dir in sorted(home.iterdir()):
        if not domain_dir.is_dir():
            continue
        for type_dir in sorted(domain_dir.iterdir()):
            if not type_dir.is_dir():
                continue
            node = find_entity_type_node_path(domain_dir.name, type_dir.name)
            if node is None:
                errors.append(
                    f"sop/主页/{domain_dir.name}/{type_dir.name} 未命中 Entity/{domain_dir.name} 树任何节点"
                    "（类型唯一定义处是 Entity 标签树；先 bootstrap_tags_entity 建类型再建 SOP）"
                )
    return errors


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

    # intentLabel（顶层批次目录前缀 runtime/batches/<标签>-<taskHash>__<批次>/ 的人读标签部分）：
    # 存在则必须 ≤16 字且无路径分隔符。
    intent_label = spec.get("intentLabel")
    if intent_label is not None:
        label_str = str(intent_label)
        if any(sep in label_str for sep in ("/", "\\", ":")) or label_str != label_str.strip():
            errors.append(f"intentLabel '{intent_label}' 含路径分隔符或首尾空白（顶层批次目录前缀须干净）")
        if len(label_str.strip()) > 16:
            errors.append(f"intentLabel '{intent_label}' 超过 16 字（人类可读任务意图标签上限）")

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

    errors.extend(_effective_content_errors(spec, tid))
    errors.extend(_content_contract_errors(spec, tid))
    return errors


def _effective_content_errors(spec: dict[str, Any], tid: str) -> list[str]:
    """废弃字段拦截 + presetRef 可解析 + effective content 菜单非空。"""
    errors: list[str] = []

    prov = spec.get("provenance") or {}
    if prov.get("historySourceTasks"):
        errors.append("provenance.historySourceTasks 已废弃；删除它（出处用 sourceTaskId/runs/notes 追踪）")

    try:
        effective = resolve_spec(spec, tid)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"presetRef 解析失败: {exc}")
        return errors

    eff_content = effective.get("content") or {}
    if not eff_content.get("angles"):
        errors.append("effective content.angles 为空（presetRef 家族包 preset 应提供 angles 菜单，或 task 显式声明）")

    return errors


def _content_contract_errors(spec: dict[str, Any], tid: str) -> list[str]:
    """生产内容契约：验收角度、配额与分离检索模式必须自洽。"""
    errors: list[str] = []
    try:
        effective = resolve_spec(spec, tid)
    except Exception as exc:  # noqa: BLE001
        return [f"继承解析失败: {exc}"]
    content = effective.get("content") or {}
    if str(content.get("modalityContract") or "") != "separated_research":
        return errors
    quotas = content.get("quotas") or {}
    per_target_articles = int(quotas.get("entityArticlesPerTarget") or 0)
    per_target_images = int(quotas.get("imageWorksPerTarget") or 0)
    if int(quotas.get("galleryPosts") or 0) or int(quotas.get("galleryPostsPerTarget") or 0):
        errors.append("separated_research 已废弃 galleryPosts/galleryPostsPerTarget；使用 imageWorksPerTarget")
    acceptance = effective.get("acceptance") or {}
    required_angles = [str(angle).strip() for angle in (acceptance.get("requiredAngles") or []) if str(angle).strip()]
    if required_angles:
        article_intents = [angle for angle in required_angles if angle in WRITING_INTENTS]
        image_angles = [angle for angle in required_angles if angle in {"image", "imagePost", "gallery"}]
        unknown = [
            angle
            for angle in required_angles
            if angle not in WRITING_INTENTS and angle not in {"image", "imagePost", "gallery"}
        ]
        if unknown:
            errors.append(f"acceptance.requiredAngles 含非标准生产角度 {unknown}；separated_research 只能使用 writingIntent 或 image")
        if article_intents and per_target_articles and len(article_intents) > per_target_articles:
            errors.append(
                "acceptance.requiredAngles 文章主线数量 "
                f"{len(article_intents)} 超过 entityArticlesPerTarget={per_target_articles}"
            )
        if image_angles and per_target_images < 1:
            errors.append("acceptance.requiredAngles 含 image，但 imageWorksPerTarget < 1")
    errors.extend(validate_image_asset_strategy(effective))
    errors.extend(image_asset_strategy_scale_issues(effective))
    return errors


def content_redundancy_warnings(spec: dict[str, Any], tid: str) -> list[str]:
    """PR_WARN：task 显式 content 字段与 preset 默认完全相同 → 建议删除以继承（不阻断）。"""
    del tid
    warnings: list[str] = []
    raw_content = spec.get("content") or {}
    try:
        menu = preset_defaults(spec_preset_ref(spec)).get("content") or {}
    except Exception:  # noqa: BLE001 — presetRef 解析失败由 _effective_content_errors 阻断
        return warnings
    for field in ("angles", "audiences", "carriers"):
        if field in raw_content and raw_content.get(field) == menu.get(field):
            warnings.append(f"content.{field} 与 preset 默认完全相同，建议删除该字段以继承")
    return warnings


def lint_all(
    only_task_id: str | None = None,
) -> tuple[int, dict[str, list[str]], dict[str, list[str]]]:
    valid_types = known_entity_types()
    results: dict[str, list[str]] = {}
    warnings: dict[str, list[str]] = {}
    seen_ids: dict[str, Path] = {}

    sop_errors = sop_taxonomy_consistency_errors()
    if sop_errors:
        results["sop/主页"] = sop_errors

    # instructions↔recipe 防漂移轻量门：家族说明文档引用的配方必须真实存在。
    from task.recipe import lint_family_instructions

    instructions_errors = lint_family_instructions()
    if instructions_errors:
        results["control_plane/families"] = instructions_errors

    specs = _lint_scope_specs()
    if only_task_id:
        target = committed_task_root(only_task_id) / "task.yaml"
        specs = [s for s in specs if s == target]
        if not specs and target.exists():
            specs = [target]

    total_errors = len(sop_errors) + len(instructions_errors)
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


def _lint_scope_specs() -> list[Path]:
    """门禁全量 lint 只校验受版本控制的正式任务，避免本地 tasks 残留污染。"""
    specs = iter_committed_task_specs()
    if os.environ.get("QWQ_COMMITTED_TASKS_ROOT"):
        return specs
    try:
        root_rel = COMMITTED_TASKS_ROOT.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return specs
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--", str(root_rel)],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return specs
    tracked = {
        (REPO_ROOT / line.strip()).resolve()
        for line in result.stdout.splitlines()
        if line.strip().endswith("/task.yaml")
    }
    if not tracked:
        return []
    return [spec for spec in specs if spec.resolve() in tracked]
