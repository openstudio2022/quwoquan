"""`qwq-data task execute` 的单 execution 工作包编排器。

配方声明选择策略、契约门、执行主体与放量验收；本执行器按固定四段主干执行，禁止任何脚本级第二编排真相源：

    execution manifest → target selection → contract-gate → execute → readiness

- executionId 由 CLI 显式注入；子步骤统一经 `_invoke_cli` 执行，终态只写当前工作包。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from core.paths import CONTROL_PLANE_SHARED_ROOT, REPO_ROOT, recipe_path
from core.runtime_policy import apply_runtime_policy, load_runtime_policy
from core.control_types import TargetSelector
from content.execution import store
from content.execution.homepage_binding import published_homepage_target_names
from content.execution.request import RuntimeExecutionRequest
from governance.provider_policy import load_provider_policy
from content.execution.workspace import (
    execution_manifest_path,
    execution_request_path,
    execution_root,
    load_execution_manifest,
)

_CLI_PATH = Path(__file__).resolve().parents[2] / "cli.py"
InvokeCli = Callable[[list[str]], int]
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


def _resolve_selection(
    recipe: dict[str, Any],
    request: RuntimeExecutionRequest,
    *,
    vertical: str,
    content_type: str,
    intent: str,
) -> dict[str, Any]:
    """Derive the frozen selection from the single runtime request.

    The selection object is written only to the execution work package.  A
    reusable family never carries a region, discovery path, title, count, or
    mandatory target list.
    """
    selection = dict(recipe.get("selection") or {})
    discovery = REPO_ROOT / "quwoquan_data/reference" / vertical / "entities" / request.region_ref
    name = request.topic or f"{request.region_ref.rsplit('/', 1)[-1]}-{content_type}"
    selection.update(
        {
            "region": request.region_ref,
            "discovery": discovery.relative_to(REPO_ROOT).as_posix(),
            "name": name,
            "title": name,
            "intentLabel": intent,
            "homepageExecutionId": request.homepage_execution_id or "",
            "limit": request.count,
        }
    )
    return selection


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
    if errors:
        raise SystemExit("[task execute] 契约门 BLOCK: " + "; ".join(errors))


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
    ]
    if bool(readiness.get("requireReviewed", False)):
        argv.append("--require-reviewed")
    argv.extend(
        [
            "--min-pass-rate",
            str(float(readiness.get("minPassRate", 1.0))),
            "--mode",
            str(readiness.get("mode") or "commercial"),
        ]
    )
    if bool(readiness.get("failOnNoGo", True)):
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
        "--require-reliabletask-fleet",
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
    from content.execution.identity import parse_execution_id

    identity = parse_execution_id(str(getattr(args, "execution_id", "") or ""))
    runtime_request = RuntimeExecutionRequest.from_args(args)
    recipe_ref = runtime_request.family_ref
    if not recipe_ref:
        raise SystemExit("[task execute] GATE_BLOCK --family is required")
    if f"/{identity.content_type.value}/" not in f"/{recipe_ref}/":
        raise SystemExit(
            f"[task execute] GATE_BLOCK execution={identity.execution_id}: "
            "execution content type does not match --family"
        )
    recipe = load_recipe(recipe_ref)
    stage = str(getattr(args, "stage", "run") or "run")
    try:
        load_provider_policy(identity.vertical).require_declared(
            runtime_request.source_providers
        )
    except ValueError as exc:
        raise SystemExit(f"[task execute] GATE_BLOCK {exc}") from exc
    # Every facade stage reads or writes the same immutable work package.
    # A task-output purge between plan-only and run destroys its frozen input,
    # so conflict admission must happen before *any* stage materializes it.
    from content.execution.agent.agent_conflicts import (
        ManagedWorkspaceConflictError,
        assert_managed_workspace_available,
    )
    from core.runtime_policy import active_runtime_policy

    try:
        assert_managed_workspace_available(
            Path.cwd(),
            provider=active_runtime_policy().cursor_provider.value,
            execution_id=identity.execution_id,
        )
    except ManagedWorkspaceConflictError as exc:
        raise SystemExit(f"[task execute] GATE_BLOCK {exc}") from exc
    execution_id = str(getattr(args, "execution_id", "") or "").strip()
    _apply_runtime_env(recipe)
    manifest_path = execution_manifest_path(execution_id)
    manifest_retry_of = str(getattr(args, "retry_of", "") or "") or None
    if manifest_path.is_file():
        existing_manifest = load_execution_manifest(execution_id)
        existing_recipe = existing_manifest.get("familyRef")
        existing_recipe_ref = (
            str(existing_recipe.get("ref") or "").strip()
            if isinstance(existing_recipe, dict)
            else ""
        )
        if existing_recipe_ref != recipe_ref:
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={execution_id}: "
                f"manifest recipe.ref={existing_recipe_ref!r} does not match "
                f"family {recipe_ref!r}"
            )
        existing_retry_of = str(existing_manifest.get("retryOf") or "") or None
        if manifest_retry_of is not None and manifest_retry_of != existing_retry_of:
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={execution_id}: "
                "resume may not change retryOf"
            )
        frozen_request = RuntimeExecutionRequest.from_document(
            store.read_json(execution_request_path(execution_id))
        )
        if frozen_request != runtime_request:
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={execution_id}: "
                "resume may not change the frozen runtime request"
            )
        resolved_selection = _resolve_selection(
            recipe,
            frozen_request,
            vertical=identity.vertical,
            content_type=identity.content_type.value,
            intent=identity.intent,
        )
        manifest_retry_of = existing_retry_of
    else:
        from content.execution.workspace import require_clean_transaction_workspace

        require_clean_transaction_workspace(execution_id)
        resolved_selection = _resolve_selection(
            recipe,
            runtime_request,
            vertical=identity.vertical,
            content_type=identity.content_type.value,
            intent=identity.intent,
        )
    from content.execution import create_execution_manifest
    from content.execution.identity import SelectionPolicy
    from content.execution.workspace import TARGET_SET_REF, frozen_target_set_digest
    from content.execution.runner import (
        preflight_execution_models,
        write_execution_model_readiness,
    )

    # plan-only 只验证可复用输入和工作包形状；它不得冒充 Agent/来源/发布成功，
    # 因此不读取凭证也不探测模型。其余阶段必须先通过真实双模型启动证明。
    if stage != "plan-only":
        try:
            model_readiness = preflight_execution_models(recipe)
        except (RuntimeError, ValueError) as exc:
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={execution_id}: {exc}"
            ) from exc

    from content.execution.materialization import ensure_execution_spec
    from core.data_issue import DataIssueError

    try:
        execution_spec_id = ensure_execution_spec(
            recipe,
            resolved_selection,
            execution_id=execution_id,
            target_selector=runtime_request.selector,
            content_type=identity.content_type.value,
            target_names=runtime_request.target_names,
        )
    except DataIssueError as exc:
        raise SystemExit(
            f"[task execute] GATE_BLOCK execution={execution_id}: {exc}"
        ) from exc
    create_execution_manifest(
        execution_id=execution_id,
        recipe_ref=recipe_ref,
        request=runtime_request.to_document(),
        selection_policy=SelectionPolicy.FROZEN,
        target_set_ref=TARGET_SET_REF,
        target_set_digest=frozen_target_set_digest(execution_id),
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
    region_ref = str(getattr(args, "region_ref", "") or "").strip().strip("/")
    if not region_ref:
        raise SystemExit("[task execute] GATE_BLOCK --region-ref is required")
    discovery_path = REPO_ROOT / "quwoquan_data/reference" / identity.vertical / "entities" / region_ref
    if not discovery_path.is_dir():
        raise SystemExit(f"[task execute] GATE_BLOCK region reference does not exist: {region_ref}")
    count = getattr(args, "count", None)
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise SystemExit("[task execute] GATE_BLOCK --count must be a positive integer")
    selector = str(getattr(args, "selector", "") or "").strip()
    try:
        target_selector = TargetSelector(selector)
    except ValueError as exc:
        choices = ", ".join(item.value for item in TargetSelector)
        raise SystemExit(
            f"[task execute] GATE_BLOCK --selector must be one of: {choices}"
        ) from exc
    if (
        identity.content_type.value == "homepage"
        and target_selector is not TargetSelector.SOURCE_READY_PRIORITY
    ):
        raise SystemExit(
            "[task execute] GATE_BLOCK homepage carrier requires --selector source-ready-priority"
        )
    homepage_execution_id = str(getattr(args, "homepage_execution_id", "") or "").strip()
    if identity.content_type.value != "homepage" and not homepage_execution_id:
        raise SystemExit("[task execute] GATE_BLOCK post families require --homepage-execution-id")
    requested_target_names = tuple(getattr(args, "target_names", ()) or ())
    if identity.content_type.value != "homepage" and requested_target_names:
        raise SystemExit(
            "[task execute] GATE_BLOCK post targets are derived from --homepage-execution-id; "
            "--target is homepage-only"
        )
    target_names = (
        requested_target_names
        if identity.content_type.value == "homepage"
        else published_homepage_target_names(
            homepage_execution_id, region_ref=region_ref, count=count
        )
    )
    _run_execution(
        argparse.Namespace(
            execution_id=execution_id,
            retry_of=getattr(args, "retry_of", None),
            stage=getattr(args, "stage", "run"),
            recover_stage=getattr(args, "recover_stage", None),
            recovery_reason=getattr(args, "recovery_reason", None),
            family=getattr(args, "family", None),
            homepage_execution_id=homepage_execution_id or None,
            region_ref=region_ref,
            selector=target_selector.value,
            target_names=target_names,
            topic=getattr(args, "topic", None),
            source_providers=tuple(getattr(args, "source_providers", ()) or ()),
            vertical=identity.vertical,
            content_type=identity.content_type.value,
            intent=identity.intent,
            count=count,
        ),
        invoke=invoke,
    )


def register_recipe_parser(sub: argparse._SubParsersAction) -> None:
    pg = sub.add_parser(
        "execute",
        help="按 family 与运行 request 执行内容工作包（选择→准入→执行→readiness）",
    )
    pg.add_argument("--execution-id", required=True, help="唯一 executionId")
    pg.add_argument("--retry-of", help="新 sequence 重试时指向原 executionId")
    pg.add_argument(
        "--homepage-execution-id",
        help="文章、图片、视频必须绑定已 canonical 的主页 executionId",
    )
    pg.add_argument("--family", required=True, help="control_plane family recipe reference")
    pg.add_argument("--region-ref", required=True, help="reference/<vertical>/entities 下的区域引用")
    pg.add_argument(
        "--selector",
        required=True,
        choices=tuple(item.value for item in TargetSelector),
    )
    pg.add_argument("--count", required=True, type=int, help="本次冻结目标数，仅写入运行 request")
    pg.add_argument("--target", dest="target_names", action="append", default=[], help="仅在本次运行请求中限定候选实体；可重复，数量必须等于 --count")
    pg.add_argument("--topic", help="文章、图片或视频的主题")
    pg.add_argument(
        "--source-provider",
        dest="source_providers",
        action="append",
        default=[],
        help="限制到已声明 provider，可重复",
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
