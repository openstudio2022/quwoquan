"""`qwq-data task geo-homepages` 的单 execution 工作包编排器。

替代旧 quwoquan_ops/runners 家族 shell：
配方（control_plane/families/<ref>.recipe.yaml）声明选择策略、契约门、执行主体与
放量验收；本执行器按固定四段主干执行，禁止任何脚本级第二编排真相源：

    execution manifest → target selection → contract-gate → execute → readiness

- executionId 是唯一运行实例标识，由 CLI 显式注入，不进配方；
- 子步骤统一经 `_invoke_cli`（当前解释器 + cli.py 子进程）执行，测试可注入；
- workflow 终态只写当前 execution 工作包，不建立第二个批次根。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from core.paths import (
    CONTROL_PLANE_SHARED_ROOT,
    REPO_ROOT,
    recipe_path,
)
from core.control_types import ReadinessMode, RolloutMilestone, RuntimeEnvironment
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
GEO_HOMEPAGE_RECIPE = "content/travel/homepage/homepage"
GEO_HOMEPAGE_ROLLOUT = "travel-homepage-coverage"


def _default_invoke_cli(argv: list[str]) -> int:
    proc = subprocess.run([sys.executable, str(_CLI_PATH), *argv], check=False)
    return int(proc.returncode)


def load_recipe(recipe_ref: str) -> dict[str, Any]:
    path = recipe_path(recipe_ref)
    if not path.is_file():
        raise FileNotFoundError(f"recipeRef '{recipe_ref}' 不存在: {path}")
    doc = store.read_yaml(path)
    if not isinstance(doc, dict) or doc.get("schemaVersion") != store.RECIPE_VERSION:
        raise ValueError(f"recipe '{recipe_ref}' schemaVersion 必须为 {store.RECIPE_VERSION}")
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
    profile = str(doc.get("runtimeProfile") or "")
    if profile and not (CONTROL_PLANE_SHARED_ROOT / f"{profile}.runtime.yaml").is_file():
        errors.append(f"runtimeProfile '{profile}' 不存在于 control_plane/_shared/")
    try:
        from content.execution.model_contract import execution_model_pair

        execution_model_pair(doc)
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    return errors


def required_instance_params(recipe: dict[str, Any]) -> list[str]:
    params = (recipe.get("instanceParams") or {}).get("required") or []
    return [str(p) for p in params]


def instance_param_gate(recipe: dict[str, Any]) -> list[str]:
    """通用 family recipe 的实例参数门：声明为 required 的参数必须已注入 generate。"""
    generate = recipe.get("selection") or {}
    missing = [
        param
        for param in required_instance_params(recipe)
        if str(generate.get(param) or "").strip() == ""
    ]
    return [
        f"instanceParams.required 未注入: {missing}（通用 recipe 必须经 CLI 传 "
        "--region/--discovery/--name 等实例参数，模板不携带省市名）"
    ] if missing else []


def _apply_runtime_env(recipe: dict[str, Any]) -> None:
    """Load one typed runtime policy and project it at the process boundary."""
    profile = str(recipe.get("runtimeProfile") or "")
    if not profile:
        raise ValueError("recipe.runtimeProfile is required")
    apply_runtime_policy(load_runtime_policy(profile))


def _apply_runtime_overrides(recipe: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Apply CLI instance parameters without mutating the committed recipe."""

    generate = dict(recipe.get("selection") or {})
    changed = False
    for arg_name, field in (
        ("discovery", "discovery"),
        ("region", "region"),
        ("name", "name"),
        ("title", "title"),
        ("intent_label", "intentLabel"),
        ("mandatory", "mandatory"),
    ):
        value = getattr(args, arg_name, None)
        if value is None or str(value).strip() == "":
            continue
        generate[field] = str(value).strip()
        changed = True
    limit = getattr(args, "limit", None)
    if limit is not None:
        generate["limit"] = int(limit)
        changed = True
    readiness_mode = str(getattr(args, "readiness_mode", "") or "").strip()
    daily_target = getattr(args, "daily_target", None)
    if readiness_mode or daily_target is not None:
        changed = True
    if not changed:
        return recipe
    updated = {**recipe, "selection": generate}
    if limit is not None:
        contract = dict(updated.get("contract") or {})
        if contract.get("targetObjectCount") is not None:
            contract["targetObjectCount"] = int(limit)
        readiness = dict(updated.get("readiness") or {})
        if readiness.get("target") is not None:
            readiness["target"] = int(limit)
        updated["contract"] = contract
        updated["readiness"] = readiness
    readiness = dict(updated.get("readiness") or {})
    if daily_target is not None:
        # dailyTarget 是 plan aggregate 容量目标，不随单批 limit/分区 leaf count 联动。
        readiness["dailyTarget"] = int(daily_target)
    if readiness_mode:
        if readiness_mode == ReadinessMode.COMMERCIAL:
            readiness.update(
                {
                    "mode": "commercial",
                    "failOnNoGo": True,
                    "acceptEstimatedTokenLedger": False,
                    "minPassRate": 1.0,
                }
            )
        elif readiness_mode == ReadinessMode.CALIBRATION:
            readiness.update(
                {
                    "mode": "trial",
                    "failOnNoGo": False,
                    "acceptEstimatedTokenLedger": True,
                }
            )
        else:
            raise ValueError(f"unsupported readiness mode: {readiness_mode}")
    updated["readiness"] = readiness
    return updated


def _resolve_execution_recipe(
    recipe: dict[str, Any],
    args: argparse.Namespace,
    *,
    execution_id: str,
    recover_stage: str | None,
) -> dict[str, Any]:
    """Resolve selection once, or reuse the immutable selection for recovery.

    A checkpoint recovery is not a new selection request.  Reapplying CLI
    defaults can turn equivalent geographic input into a different serialized
    value, which would violate the execution manifest before the controller
    reaches the repaired stage.  The manifest remains authoritative; recipe
    fingerprint validation is still performed by ``create_execution_manifest``.
    """
    if not recover_stage or not execution_manifest_path(execution_id).is_file():
        return _apply_runtime_overrides(recipe, args)
    manifest = load_execution_manifest(execution_id)
    frozen_params = manifest.get("resolvedParams")
    if not isinstance(frozen_params, dict) or not frozen_params:
        raise ValueError(
            f"execution manifest has no valid resolvedParams for recovery: {execution_id}"
        )
    frozen_recipe = {**recipe, "selection": dict(frozen_params)}
    # ``limit`` is an execution input and also determines the derived contract
    # and readiness targets. Reapply only that deterministic projection; never
    # accept the current invocation's selection parameters during recovery.
    frozen_limit = frozen_params.get("limit")
    if frozen_limit is None:
        return frozen_recipe
    try:
        limit = int(frozen_limit)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"execution manifest has invalid resolvedParams.limit for recovery: {execution_id}"
        ) from exc
    return _apply_runtime_overrides(frozen_recipe, argparse.Namespace(limit=limit))


def _geo_region(args: argparse.Namespace) -> str:
    parts = [
        str(getattr(args, "country", "") or "").strip(),
        str(getattr(args, "province", "") or "").strip(),
        str(getattr(args, "city", "") or "").strip(),
        str(getattr(args, "district", "") or "").strip(),
    ]
    return "/".join(part for part in parts if part) or "中国"


def _geo_discovery(args: argparse.Namespace) -> str:
    """Resolve the one committed coverage source for a geographic execution.

    Geography is an execution parameter, not a recipe field.  The facade derives
    its default discovery input from the coverage master tree so an operator does
    not need to copy a source path into every province invocation.  An explicit
    path remains useful for a deliberately scoped operator run, but it never
    becomes committed recipe configuration.
    """
    explicit = str(getattr(args, "discovery", "") or "").strip()
    if explicit:
        return explicit

    from governance.coverage.master_list import COVERAGE_MASTER_ROOT

    province = str(getattr(args, "province", "") or "").strip()
    city = str(getattr(args, "city", "") or "").strip()
    source = COVERAGE_MASTER_ROOT
    if province:
        source = source / province
    if city:
        source = source / f"{city}.yaml"
    if not source.exists():
        raise SystemExit(
            "[geo-homepages] coverage discovery 不存在："
            f"{source}（请先修复 coverage 主清单，或显式传 --discovery）"
        )
    try:
        return source.relative_to(REPO_ROOT).as_posix()
    except ValueError as exc:
        raise SystemExit(f"[geo-homepages] coverage discovery 不在仓库内：{source}") from exc


def _geo_label(region: str, profile: str) -> str:
    tail = region.split("/")[-1] if region else "中国"
    return f"{tail}景区主页{profile}".replace("_", "").replace("-", "")


def _ensure_execution_spec(
    recipe: dict[str, Any],
    invoke: InvokeCli,
    *,
    execution_id: str,
    force: bool,
    rollout_excluded: tuple[str, ...] = (),
) -> str:
    generate = recipe.get("selection") or {}
    if not generate:
        raise SystemExit("[geo-homepages] recipe.selection is required for an execution work package")
    if store.spec_exists(execution_id) and not force:
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
            region=str(generate.get("region") or "中国"),
            category=str(generate.get("category") or "景区"),
            name=str(generate.get("name")),
            title=str(generate.get("title") or generate.get("name")),
            intent_label=str(generate.get("intentLabel") or generate.get("name")),
            preset_ref=str(recipe.get("presetRef")),
            entity_articles_per_target=int(generate.get("entityArticlesPerTarget", 0)),
            entity_homepages_per_target=int(generate.get("entityHomepagesPerTarget", 1)),
            image_works_per_target=int(generate.get("imageWorksPerTarget", 0)),
            created_by="geo-homepages",
            selection_policy=SelectionPolicy.FROZEN,
            force=force,
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
        workflow = spec.get("workflowPolicy") or {}
        actual = int(workflow.get("targetObjectCount") or 0)
        if actual != target:
            errors.append(f"workflowPolicy.targetObjectCount={actual} != {target}")
        selected = _selected_count(execution_id, spec)
        if selected < target:
            errors.append(f"selection shortfall: selected={selected} < target={target}")
    if errors:
        raise SystemExit("[geo-homepages] 契约门 BLOCK: " + "; ".join(errors))


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
        raise SystemExit(f"[geo-homepages] GATE_BLOCK execution={execution_id}: {exc}") from exc


def _readiness(
    recipe: dict[str, Any],
    execution_id: str,
    invoke: InvokeCli,
) -> None:
    """Single-execution readiness; no secondary identity or fan-out aggregate exists."""
    readiness = recipe.get("readiness") or {}
    argv = ["verify", "execution-readiness", "--execution-id", execution_id]
    if bool(readiness.get("requireReviewed", False)):
        argv.append("--require-reviewed")
    rc = invoke(argv)
    if rc != 0:
        raise SystemExit(f"[geo-homepages] execution-readiness rc={rc}")
    return


def _env_ready_argv(recipe: dict[str, Any], execution_id: str) -> list[str]:
    execution = recipe.get("execution") or {}
    policy = load_runtime_policy(str(recipe.get("runtimeProfile") or ""))
    evidence = execution_root(execution_id) / "evidence" / "environment_readiness.json"
    return [
        "task",
        "preflight",
        "--model",
        str(execution.get("model") or policy.cursor_model),
        "--runtime",
        str(execution.get("runtime") or RuntimeEnvironment.LOCAL),
        "--startup-timeout-seconds",
        str(policy.startup_timeout_seconds),
        "--report-out",
        str(evidence),
    ]

def _run_geo_homepage_execution(args: argparse.Namespace, invoke: InvokeCli | None = None) -> None:
    invoke = invoke or _default_invoke_cli
    recover_stage = str(getattr(args, "recover_stage", "") or "").strip() or None
    recovery_reason = str(getattr(args, "recovery_reason", "") or "").strip() or None
    if bool(recover_stage) != bool(recovery_reason):
        raise SystemExit(
            "[geo-homepages] --recover-stage and --recovery-reason must be provided together"
        )
    recipe_ref = GEO_HOMEPAGE_RECIPE
    recipe = load_recipe(recipe_ref)
    execution_id = str(getattr(args, "execution_id", "") or "").strip()
    from content.execution import parse_execution_id

    parse_execution_id(execution_id)
    recipe = _resolve_execution_recipe(
        recipe,
        args,
        execution_id=execution_id,
        recover_stage=recover_stage,
    )
    param_errors = instance_param_gate(recipe)
    if param_errors:
        raise SystemExit("[geo-homepages] 实例参数门 BLOCK: " + "; ".join(param_errors))
    _apply_runtime_env(recipe)
    from content.execution import create_execution_manifest
    from content.execution.identity import SelectionPolicy
    from content.execution.workspace import TARGET_SET_REF, frozen_target_set_sha256
    from content.execution.runner import (
        preflight_execution_models,
        write_execution_model_readiness,
    )

    from content.release.canonical.rollout_milestone import RolloutMilestoneError, assert_rollout_start

    if getattr(args, "rollout", None):
        try:
            assert_rollout_start(execution_id)
        except RolloutMilestoneError as exc:
            raise SystemExit(f"[geo-homepages] GATE_BLOCK execution={execution_id}: {exc}") from exc
    stage = str(getattr(args, "stage", "run") or "run")
    # plan-only 只验证可复用输入和工作包形状；它不得冒充 Agent/来源/发布成功，
    # 因此不读取凭证也不探测模型。其余阶段必须先通过真实双模型启动证明。
    if stage != "plan-only":
        try:
            model_readiness = preflight_execution_models(recipe)
        except (RuntimeError, ValueError) as exc:
            raise SystemExit(
                f"[geo-homepages] GATE_BLOCK execution={execution_id}: {exc}"
            ) from exc
        write_execution_model_readiness(execution_id, model_readiness)

    execution_spec_id = _ensure_execution_spec(
        recipe,
        invoke,
        execution_id=execution_id,
        force=bool(getattr(args, "force_execution_write", False)),
        rollout_excluded=tuple(getattr(args, "rollout_excluded", ()) or ()),
    )
    resolved_params = dict(recipe.get("selection") or {})
    create_execution_manifest(
        execution_id=execution_id,
        recipe_ref=recipe_ref,
        resolved_params=resolved_params,
        selection_policy=SelectionPolicy.FROZEN,
        target_set_ref=TARGET_SET_REF,
        target_set_sha256=frozen_target_set_sha256(execution_id),
        retry_of=str(getattr(args, "retry_of", "") or "") or None,
    )
    _contract_gate(recipe, execution_spec_id)
    from content.execution import prepare_execution_qualification

    prepare_execution_qualification(execution_id)
    print(f"[geo-homepages] executionId={execution_id} stage={stage}")
    if stage == "plan-only":
        return
    if stage == "readiness-only":
        _readiness(recipe, execution_id, invoke)
        return
    rc = invoke(_env_ready_argv(recipe, execution_id))
    if rc != 0:
        raise SystemExit(f"[geo-homepages] task preflight rc={rc}")
    _execute(
        recipe,
        execution_id,
        recover_stage=recover_stage,
        recovery_reason=recovery_reason,
    )
    _readiness(recipe, execution_id, invoke)
    print(f"[geo-homepages] DONE executionId={execution_id}")


def handle_geo_homepages(args: argparse.Namespace, invoke: InvokeCli | None = None) -> None:
    execution_id = str(getattr(args, "execution_id", "") or "").strip()
    from content.execution.identity import parse_execution_id
    identity = parse_execution_id(execution_id)
    rollout_id = str(getattr(args, "rollout", "") or "").strip()
    from content.release.canonical.rollout_milestone import RolloutMilestoneError, geo_rollout_parameters
    if rollout_id:
        if rollout_id != GEO_HOMEPAGE_ROLLOUT:
            raise SystemExit(f"[geo-homepages] unsupported rollout: {rollout_id}")
        forbidden = ("region", "discovery", "limit", "mandatory", "name", "title", "intent_label")
        supplied = [name for name in forbidden if getattr(args, name, None) not in (None, "")]
        if supplied:
            raise SystemExit(
                "[geo-homepages] governed rollout rejects selection overrides: "
                + ", ".join(sorted(supplied))
            )
        try:
            province, limit, mandatory, rollout_excluded = geo_rollout_parameters(
                execution_id=execution_id,
                retry_of=getattr(args, "retry_of", None),
            )
        except (RolloutMilestoneError, ValueError) as exc:
            raise SystemExit(f"[geo-homepages] GATE_BLOCK execution={execution_id}: {exc}") from exc
        region = f"中国/{province}"
        discovery = f"quwoquan_data/verticals/travel/coverage/中国/{province}"
        label = _geo_label(region, identity.milestone.value)
        name = f"{province}主页{identity.milestone.value}"
    else:
        region = str(getattr(args, "region", "") or "").strip()
        discovery = str(getattr(args, "discovery", "") or "").strip()
        limit = getattr(args, "limit", None)
        name = str(getattr(args, "name", "") or "").strip()
        mandatory = str(getattr(args, "mandatory", "") or "").strip() or None
        rollout_excluded = ()
        if not region or not discovery or limit is None or not name:
            raise SystemExit(
                "[geo-homepages] ad-hoc mode requires --region, --discovery, --limit and --name"
            )
        label = str(getattr(args, "intent_label", "") or "").strip() or name
    _run_geo_homepage_execution(
        argparse.Namespace(
            execution_id=execution_id,
            retry_of=getattr(args, "retry_of", None),
            stage=getattr(args, "stage", "run"),
            force_execution_write=getattr(args, "force_execution_write", False),
            recover_stage=getattr(args, "recover_stage", None),
            recovery_reason=getattr(args, "recovery_reason", None),
            rollout=rollout_id or None,
            discovery=discovery,
            limit=limit,
            region=region,
            name=name,
            title=str(getattr(args, "title", "") or "").strip() or name,
            intent_label=label,
            mandatory=mandatory,
            rollout_excluded=rollout_excluded,
        ),
        invoke=invoke,
    )


def register_recipe_parser(sub: argparse._SubParsersAction) -> None:
    pg = sub.add_parser(
        "geo-homepages",
        help="按国家/省/市区聚合 homepage execution（选择→准入→执行→readiness）",
    )
    pg.add_argument("--execution-id", required=True, help="唯一 executionId")
    pg.add_argument("--retry-of", help="新 sequence 重试时指向原 executionId")
    selection = pg.add_mutually_exclusive_group(required=True)
    selection.add_argument("--rollout", choices=[GEO_HOMEPAGE_ROLLOUT])
    selection.add_argument("--region", help="ad-hoc 显式地域，例如 中国/浙江省")
    pg.add_argument("--discovery", help="覆盖 discovery 文件路径")
    pg.add_argument("--limit", type=int, help="ad-hoc 覆盖目标数量")
    pg.add_argument("--mandatory", help="运行实例 mandatory，逗号分隔")
    pg.add_argument("--name", help="覆盖任务名")
    pg.add_argument("--title", help="覆盖任务标题")
    pg.add_argument("--intent-label", dest="intent_label", help="覆盖批次 intentLabel")
    pg.add_argument(
        "--stage",
        choices=["run", "plan-only", "readiness-only"],
        default="run",
    )
    pg.add_argument("--force-execution-write", dest="force_execution_write", action="store_true")
    from content.execution.pipeline.dag import STAGE_NAMES

    pg.add_argument(
        "--recover-stage",
        choices=STAGE_NAMES,
        help="代码或基础设施修复后的受审计恢复起点；必须同时提供 --recovery-reason",
    )
    pg.add_argument(
        "--recovery-reason",
        help="受审计恢复原因；必须同时提供 --recover-stage",
    )
    pg.set_defaults(handler=handle_geo_homepages)
