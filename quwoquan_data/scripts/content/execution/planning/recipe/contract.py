"""Strict reusable recipe validation owned outside the execution facade."""

from __future__ import annotations

from typing import Any

from core.paths import CONTROL_PLANE_SHARED_ROOT, REPO_ROOT
from core.schema import load_schema, validate_strict

from content.execution import store

SELECTION_QUOTA_FIELDS = (
    "entityArticlesPerTarget",
    "entityHomepagesPerTarget",
    "imageWorksPerTarget",
    "videoWorksPerTarget",
)


def lint_recipe(doc: dict[str, Any], recipe_ref: str) -> list[str]:
    """Validate one recipe with strict schema and semantic ownership gates."""

    schema = load_schema("execution", "content_recipe")
    errors: list[str] = list(validate_strict(doc, schema))
    if str(doc.get("recipeId") or "") != recipe_ref:
        errors.append(
            f"recipeId '{doc.get('recipeId')}' 必须等于引用路径 '{recipe_ref}'"
        )
    preset_ref = str(doc.get("presetRef") or "")
    if preset_ref:
        try:
            store.load_preset(preset_ref)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"presetRef 解析失败: {exc}")
    if not doc.get("selection"):
        errors.append("selection is required for an execution work package")
    else:
        selection = doc["selection"]
        missing_quotas = [key for key in SELECTION_QUOTA_FIELDS if key not in selection]
        if missing_quotas:
            errors.append(f"selection quota fields are required: {missing_quotas}")
    profile = str(doc.get("runtimeProfile") or "")
    if (
        profile
        and not (CONTROL_PLANE_SHARED_ROOT / f"{profile}.runtime.yaml").is_file()
    ):
        errors.append(f"runtimeProfile '{profile}' 不存在于 control_plane/_shared/")
    try:
        from content.execution.model_contract import execution_model_pair

        execution_model_pair(doc)
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    return errors


__all__ = ["SELECTION_QUOTA_FIELDS", "gate_recipe_contract", "lint_recipe"]


def gate_recipe_contract(recipe: dict[str, Any], execution_id: str) -> None:
    contract = recipe.get("contract") or {}
    spec = store.load_spec(execution_id)
    errors: list[str] = []
    declared_preset = store.spec_preset_ref(spec)
    if declared_preset != str(recipe.get("presetRef") or ""):
        errors.append(
            f"content.presetRef={declared_preset!r} 与配方 presetRef={recipe.get('presetRef')!r} 不一致"
        )
    if (
        bool(contract.get("requireActiveStatus", True))
        and str(spec.get("status") or "") != "active"
    ):
        errors.append(f"task status 必须 active，实得 {spec.get('status')!r}")
    # 分支治理（P4）：recipe 禁止声明 executionBranch（临时 feature 分支绑定已废止）；
    # 商业执行只校验 branch policy（quwoquan_ops/policies/branch_policy.yaml）。
    if contract.get("executionBranch"):
        errors.append(
            "contract.executionBranch 已废止：recipe 不得绑定 Git 分支，"
            "正式分支由 branch_policy.yaml 治理"
        )
    from core.execution_branch import execution_branch_issues

    errors.extend(execution_branch_issues(spec, cwd=REPO_ROOT))
    if errors:
        raise SystemExit("[task execute] 契约门 BLOCK: " + "; ".join(errors))
