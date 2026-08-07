"""Strict reusable recipe validation owned outside the execution facade."""

from __future__ import annotations

from typing import Any

from core.paths import CONTROL_PLANE_SHARED_ROOT
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


__all__ = ["SELECTION_QUOTA_FIELDS", "lint_recipe"]
