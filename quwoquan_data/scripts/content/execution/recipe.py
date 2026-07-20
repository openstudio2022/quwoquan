"""`qwq-data task execute` 的单 execution 工作包编排器。

替代旧 quwoquan_ops/runners 家族 shell：
配方（control_plane/families/<ref>.recipe.yaml）声明选择策略、契约门、执行主体与
放量验收；本执行器按固定四段主干执行，禁止任何脚本级第二编排真相源：

    execution manifest → target selection → contract-gate → execute → readiness

- executionId 是唯一运行实例标识，由 CLI 显式注入，不进配方；
- 子步骤统一经 `_invoke_cli`（当前解释器 + cli.py 子进程）执行，测试可注入；
- execution 终态只写当前 execution 工作包，不建立第二个批次根。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from core.paths import (
    CONTROL_PLANE_SHARED_ROOT,
    REPO_ROOT,
    recipe_path,
)
from core.runtime_policy import apply_runtime_policy, load_runtime_policy
from content.execution import store
from content.execution.workspace import (
    execution_manifest_path,
    execution_root,
    load_execution_manifest,
)

_CLI_PATH = Path(__file__).resolve().parents[2] / "cli.py"

# 跨批去重账本默认维度（单一真相源 content.execution.selection.DEFAULT_SOURCE_TASK_ID；
# 模块导入期取值避免循环依赖延迟到调用点）。

# 可注入执行点（测试 mock；生产即默认实现）。
InvokeCli = Callable[[list[str]], int]
HOMEPAGE_RECIPE = "content/travel/homepage/homepage"
HOMEPAGE_ROLLOUT = "travel-homepage-coverage"
COLD_START_RECIPES = {
    "article": "content/travel/article/article",
    "image": "content/travel/image/image",
    "video": "content/travel/video/video",
}
SELECTION_QUOTA_FIELDS = (
    "entityArticlesPerTarget",
    "entityHomepagesPerTarget",
    "imageWorksPerTarget",
    "videoWorksPerTarget",
)


def _default_invoke_cli(argv: list[str]) -> int:
    proc = subprocess.run([sys.executable, str(_CLI_PATH), *argv], check=False)
    return int(proc.returncode)


def load_recipe(recipe_ref: str) -> dict[str, Any]:
    path = recipe_path(recipe_ref)
    if not path.is_file():
        raise FileNotFoundError(f"recipeRef '{recipe_ref}' 不存在: {path}")
    doc = store.read_yaml(path)
    if not isinstance(doc, dict) or doc.get("schema") != store.RECIPE_SCHEMA:
        raise ValueError(f"recipe '{recipe_ref}' schema 必须为 {store.RECIPE_SCHEMA}")
    errors = lint_recipe(doc, recipe_ref)
    if errors:
        raise ValueError(f"recipe '{recipe_ref}' 不合法: " + "; ".join(errors))
    return doc


def lint_recipe(doc: dict[str, Any], recipe_ref: str) -> list[str]:
    """recipe 校验：真实执行 task_recipe.schema.json（未知字段 fail-closed）+ 语义门。"""
    from core.schema import load_schema, validate_strict

    # 真实 Schema 校验（P4：执行器消费字段必须在 Schema 声明；未知字段必须失败）。
    schema = load_schema("execution", "content_recipe")
    errors: list[str] = list(validate_strict(doc, schema))
    if str(doc.get("recipeId") or "") != recipe_ref:
        errors.append(f"recipeId '{doc.get('recipeId')}' 必须等于引用路径 '{recipe_ref}'")
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
    if profile and not (CONTROL_PLANE_SHARED_ROOT / f"{profile}.runtime.yaml").is_file():
        errors.append(f"runtimeProfile '{profile}' 不存在于 control_plane/_shared/")
    try:
        from content.execution.model_contract import execution_model_pair

        execution_model_pair(doc)
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    return errors


def _apply_runtime_env(recipe: dict[str, Any]) -> None:
    """Load one typed runtime policy and project it at the process boundary."""
    profile = str(recipe.get("runtimeProfile") or "")
    if not profile:
        raise ValueError("recipe.runtimeProfile is required")
    apply_runtime_policy(load_runtime_policy(profile))


def _geo_label(region: str, profile: str) -> str:
    tail = region.split("/")[-1] if region else "中国"
    return f"{tail}景区主页{profile}".replace("_", "").replace("-", "")


_INSTANCE_PARAM_ATTRS = {
    "region": "region",
    "discovery": "discovery",
    "name": "name",
    "title": "title",
    "intentLabel": "intent_label",
    "homepageExecutionId": "homepage_execution_id",
    "mandatory": "mandatory",
    "limit": "limit",
}


def _resolve_selection(recipe: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Freeze rollout-derived instance values into the reusable selection policy."""
    selection = dict(recipe.get("selection") or {})
    for field, attr in _INSTANCE_PARAM_ATTRS.items():
        if not hasattr(args, attr):
            continue
        value = getattr(args, attr)
        if value is not None:
            selection[field] = value
    required = tuple((recipe.get("instanceParams") or {}).get("required") or ())
    missing = [field for field in required if selection.get(field) in (None, "")]
    if missing:
        raise SystemExit(
            "[task execute] GATE_BLOCK missing rollout instance parameters: "
            + ", ".join(missing)
        )
    limit = selection.get("limit")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise SystemExit("[task execute] GATE_BLOCK rollout limit must be a positive integer")
    return selection


def _ensure_execution_spec(
    recipe: dict[str, Any],
    selection: dict[str, Any],
    *,
    execution_id: str,
    rollout_excluded: tuple[str, ...] = (),
) -> str:
    generate = selection
    if not generate:
        raise SystemExit("[task execute] recipe.selection is required for an execution work package")
    if store.spec_exists(execution_id):
        return execution_id
    from content.execution.identity import SelectionPolicy
    from content.execution.selection import SelectionRequest, create_execution_selection

    mandatory = str(generate.get("mandatory") or "")
    create_execution_selection(
        SelectionRequest(
            execution_id=execution_id,
            discovery_path=REPO_ROOT / str(generate.get("discovery")),
            limit=int(generate.get("limit")),
            mandatory=tuple(item.strip() for item in mandatory.split(",") if item.strip()),
            excluded=frozenset(rollout_excluded),
            region=str(generate["region"]),
            category=str(generate["category"]),
            name=str(generate["name"]),
            title=str(generate["title"]),
            intent_label=str(generate["intentLabel"]),
            preset_ref=str(recipe.get("presetRef")),
            entity_articles_per_target=int(generate["entityArticlesPerTarget"]),
            entity_homepages_per_target=int(generate["entityHomepagesPerTarget"]),
            image_works_per_target=int(generate["imageWorksPerTarget"]),
            video_works_per_target=int(generate["videoWorksPerTarget"]),
            created_by="task execute",
            selection_policy=SelectionPolicy.FROZEN,
            force=False,
        )
    )
    return execution_id


def _contract_gate(recipe: dict[str, Any], execution_id: str) -> None:
    contract = recipe.get("contract") or {}
    spec = store.load_spec(execution_id)
    errors: list[str] = []
    declared_preset = store.spec_preset_ref(spec)
    if declared_preset != str(recipe.get("presetRef") or ""):
        errors.append(f"content.presetRef={declared_preset!r} 与配方 presetRef={recipe.get('presetRef')!r} 不一致")
    if bool(contract.get("requireActiveStatus", True)) and str(spec.get("status") or "") != "active":
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
    target = int(contract.get("targetObjectCount") or 0)
    if target:
        execution = spec.get("executionPolicy") or {}
        actual = int(execution.get("targetObjectCount") or 0)
        if actual != target:
            errors.append(f"executionPolicy.targetObjectCount={actual} != {target}")
        selected = _selected_count(execution_id, spec)
        if selected < target:
            errors.append(f"selection shortfall: selected={selected} < target={target}")
    if errors:
        raise SystemExit("[task execute] 契约门 BLOCK: " + "; ".join(errors))


def _selected_count(execution_id: str, spec: dict[str, Any]) -> int:
    selection_path = execution_root(execution_id) / "_shared" / "target_selection.json"
    if selection_path.is_file():
        payload = json.loads(selection_path.read_text(encoding="utf-8"))
        return int(payload.get("selectedCount") or 0)
    scope = spec.get("scope") or {}
    return len(scope.get("coverageTargets") or [])


def _execute(
    recipe: dict[str, Any],
    execution_id: str,
    *,
    recover_stage: str | None = None,
    recovery_reason: str | None = None,
) -> None:
    from content.execution.runner import run_execution

    try:
        run_execution(
            execution_id,
            recipe,
            recover_stage=recover_stage,
            recovery_reason=recovery_reason,
        )
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(f"[task execute] GATE_BLOCK execution={execution_id}: {exc}") from exc


def _readiness(
    recipe: dict[str, Any],
    execution_id: str,
    invoke: InvokeCli,
) -> None:
    """Single-execution readiness; no secondary identity or fan-out aggregate exists."""
    readiness = recipe.get("readiness") or {}
    argv = [
        "verify",
        "execution-readiness",
        "--execution-id",
        execution_id,
        "--min-pass-rate",
        str(float(readiness.get("minPassRate", 1.0))),
        "--mode",
        str(readiness.get("mode") or "commercial"),
    ]
    if bool(readiness.get("requireReviewed", False)):
        argv.append("--require-reviewed")
    if bool(readiness.get("failOnNoGo", False)):
        argv.append("--fail-on-no-go")
    rc = invoke(argv)
    if rc != 0:
        raise SystemExit(f"[task execute] execution-readiness rc={rc}")
    return


def _runtime_preflight_argv(execution_id: str) -> list[str]:
    evidence = execution_root(execution_id) / "evidence" / "runtime_preflight.json"
    return [
        "task",
        "preflight",
        "--cursor-startup",
        "--report-out",
        str(evidence),
    ]


def _run_execution(args: argparse.Namespace, invoke: InvokeCli | None = None) -> None:
    invoke = invoke or _default_invoke_cli
    recover_stage = str(getattr(args, "recover_stage", "") or "").strip() or None
    recovery_reason = str(getattr(args, "recovery_reason", "") or "").strip() or None
    if bool(recover_stage) != bool(recovery_reason):
        raise SystemExit(
            "[task execute] --recover-stage and --recovery-reason must be provided together"
        )
    rollout_id = str(args.rollout)
    from governance.coverage.cold_start_supply import load_cold_start_supply_policy
    from content.execution.identity import parse_execution_id

    cold_start_rollout = load_cold_start_supply_policy().policy_id
    identity = parse_execution_id(str(getattr(args, "execution_id", "") or ""))
    if rollout_id == HOMEPAGE_ROLLOUT:
        recipe_ref = HOMEPAGE_RECIPE
    elif rollout_id == cold_start_rollout:
        try:
            recipe_ref = COLD_START_RECIPES[identity.content_type.value]
        except KeyError as exc:
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={identity.execution_id}: "
                "cold-start rollout only accepts article, image, or video"
            ) from exc
    else:
        raise SystemExit(f"[task execute] GATE_BLOCK unknown rollout: {rollout_id}")
    recipe = load_recipe(recipe_ref)
    execution_id = str(getattr(args, "execution_id", "") or "").strip()
    _apply_runtime_env(recipe)
    manifest_path = execution_manifest_path(execution_id)
    manifest_retry_of = str(getattr(args, "retry_of", "") or "") or None
    if manifest_path.is_file():
        existing_manifest = load_execution_manifest(execution_id)
        existing_recipe = existing_manifest.get("recipe")
        existing_recipe_ref = (
            str(existing_recipe.get("ref") or "").strip()
            if isinstance(existing_recipe, dict)
            else ""
        )
        if existing_recipe_ref != recipe_ref:
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={execution_id}: "
                f"manifest recipe.ref={existing_recipe_ref!r} does not match "
                f"rollout recipe {recipe_ref!r}"
            )
        existing_retry_of = str(existing_manifest.get("retryOf") or "") or None
        if manifest_retry_of is not None and manifest_retry_of != existing_retry_of:
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={execution_id}: "
                "resume may not change retryOf"
            )
        frozen_params = existing_manifest.get("resolvedParams")
        if not isinstance(frozen_params, dict):
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={execution_id}: "
                "manifest resolvedParams must be an object"
            )
        resolved_selection = dict(frozen_params)
        manifest_retry_of = existing_retry_of
    else:
        resolved_selection = _resolve_selection(recipe, args)
    from content.execution import create_execution_manifest
    from content.execution.identity import SelectionPolicy
    from content.execution.workspace import TARGET_SET_REF, frozen_target_set_sha256
    from content.execution.runner import (
        preflight_execution_models,
        write_execution_model_readiness,
    )

    from content.release.canonical.rollout_milestone import RolloutMilestoneError, assert_rollout_start

    try:
        assert_rollout_start(execution_id)
    except RolloutMilestoneError as exc:
        raise SystemExit(f"[task execute] GATE_BLOCK execution={execution_id}: {exc}") from exc
    stage = str(getattr(args, "stage", "run") or "run")
    # plan-only 只验证可复用输入和工作包形状；它不得冒充 Agent/来源/发布成功，
    # 因此不读取凭证也不探测模型。其余阶段必须先通过真实双模型启动证明。
    if stage != "plan-only":
        try:
            model_readiness = preflight_execution_models(recipe)
        except (RuntimeError, ValueError) as exc:
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={execution_id}: {exc}"
            ) from exc

    execution_spec_id = _ensure_execution_spec(
        recipe,
        resolved_selection,
        execution_id=execution_id,
        rollout_excluded=tuple(getattr(args, "rollout_excluded", ()) or ()),
    )
    create_execution_manifest(
        execution_id=execution_id,
        recipe_ref=recipe_ref,
        resolved_params=resolved_selection,
        selection_policy=SelectionPolicy.FROZEN,
        target_set_ref=TARGET_SET_REF,
        target_set_sha256=frozen_target_set_sha256(execution_id),
        retry_of=manifest_retry_of,
    )
    if stage != "plan-only":
        write_execution_model_readiness(execution_id, model_readiness)
    _contract_gate(recipe, execution_spec_id)
    from content.execution import prepare_execution_qualification

    prepare_execution_qualification(execution_id)
    print(f"[task execute] executionId={execution_id} stage={stage}")
    if stage == "plan-only":
        return
    if stage == "readiness-only":
        _readiness(recipe, execution_id, invoke)
        return
    rc = invoke(_runtime_preflight_argv(execution_id))
    if rc != 0:
        raise SystemExit(f"[task execute] task preflight rc={rc}")
    _execute(
        recipe,
        execution_id,
        recover_stage=recover_stage,
        recovery_reason=recovery_reason,
    )
    _readiness(recipe, execution_id, invoke)
    print(f"[task execute] DONE executionId={execution_id}")


def handle_execute(args: argparse.Namespace, invoke: InvokeCli | None = None) -> None:
    execution_id = str(getattr(args, "execution_id", "") or "").strip()
    from content.execution.identity import parse_execution_id
    identity = parse_execution_id(execution_id)
    rollout_id = str(getattr(args, "rollout", "") or "").strip()
    from content.release.canonical.rollout_milestone import RolloutMilestoneError, geo_rollout_parameters
    from governance.coverage.cold_start_supply import (
        cold_start_execution_parameters,
        load_cold_start_supply_policy,
    )
    cold_start_rollout = load_cold_start_supply_policy().policy_id
    try:
        if rollout_id == HOMEPAGE_ROLLOUT:
            province, limit, mandatory, rollout_excluded = geo_rollout_parameters(
                execution_id=execution_id,
                retry_of=getattr(args, "retry_of", None),
            )
        elif rollout_id == cold_start_rollout:
            parameters = cold_start_execution_parameters(
                execution_id=execution_id,
                retry_of=getattr(args, "retry_of", None),
                homepage_execution_id=getattr(args, "homepage_execution_id", None),
            )
            province = parameters.province
            limit = parameters.limit
            mandatory = parameters.mandatory
            rollout_excluded = ()
        else:
            raise ValueError(f"unknown rollout: {rollout_id}")
    except (RolloutMilestoneError, ValueError) as exc:
        raise SystemExit(f"[task execute] GATE_BLOCK execution={execution_id}: {exc}") from exc
    region = f"中国/{province}"
    discovery = f"quwoquan_data/verticals/travel/coverage/中国/{province}"
    if rollout_id == cold_start_rollout:
        kind = identity.content_type.value
        name = f"{province}冷启动{kind}{identity.milestone.value}"
        label = name.replace("_", "").replace("-", "")
    else:
        label = _geo_label(region, identity.milestone.value)
        name = f"{province}主页{identity.milestone.value}"
    _run_execution(
        argparse.Namespace(
            execution_id=execution_id,
            retry_of=getattr(args, "retry_of", None),
            stage=getattr(args, "stage", "run"),
            recover_stage=getattr(args, "recover_stage", None),
            recovery_reason=getattr(args, "recovery_reason", None),
            rollout=rollout_id,
            homepage_execution_id=getattr(args, "homepage_execution_id", None),
            discovery=discovery,
            limit=limit,
            region=region,
            name=name,
            title=name,
            intent_label=label,
            mandatory=mandatory,
            rollout_excluded=rollout_excluded,
        ),
        invoke=invoke,
    )


def register_recipe_parser(sub: argparse._SubParsersAction) -> None:
    pg = sub.add_parser(
        "execute",
        help="按 rollout 合同执行内容工作包（选择→准入→执行→readiness）",
    )
    pg.add_argument("--execution-id", required=True, help="唯一 executionId")
    pg.add_argument("--retry-of", help="新 sequence 重试时指向原 executionId")
    pg.add_argument(
        "--homepage-execution-id",
        help="文章/图片/视频执行必须绑定同省同档已 canonical 的 homepage executionId",
    )
    from governance.coverage.cold_start_supply import load_cold_start_supply_policy

    pg.add_argument(
        "--rollout",
        required=True,
        choices=sorted((HOMEPAGE_ROLLOUT, load_cold_start_supply_policy().policy_id)),
    )
    pg.add_argument(
        "--stage",
        choices=["run", "plan-only", "readiness-only"],
        default="run",
    )
    from content.execution.controller.dag import STAGE_NAMES

    pg.add_argument(
        "--recover-stage",
        choices=STAGE_NAMES,
        help="代码或基础设施修复后的受审计恢复起点；必须同时提供 --recovery-reason",
    )
    pg.add_argument(
        "--recovery-reason",
        help="受审计恢复原因；必须同时提供 --recover-stage",
    )
    pg.set_defaults(handler=handle_execute)
