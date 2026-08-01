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
from core.control_types import ExecutionStage, TargetSelector
from core.io import read_json, write_json
from core.source_digest import current_source_digest
from content.execution import store
from content.execution.request import RuntimeExecutionRequest, resolve_candidate_pool
from governance.provider_policy import load_provider_policy
from content.execution.workspace import (
    execution_manifest_path,
    execution_request_path,
    execution_root,
    load_frozen_target_set,
    load_execution_manifest,
    entity_catalog_digest,
)

_CLI_PATH = Path(__file__).resolve().parents[2] / "cli.py"
InvokeCli = Callable[[list[str]], int]
SELECTION_QUOTA_FIELDS = (
    "entityArticlesPerTarget", "entityHomepagesPerTarget",
    "imageWorksPerTarget", "videoWorksPerTarget",
)

def _default_invoke_cli(argv: list[str]) -> int:
    proc = subprocess.run([sys.executable, str(_CLI_PATH), *argv], check=False)
    return int(proc.returncode)


def _current_git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _current_git_branch() -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


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
            "limit": request.count,
            "approvedQuota": request.quota,
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
    until: str | None = None,
    recover_stage: str | None = None,
    recovery_reason: str | None = None,
) -> None:
    from content.execution.runner import run_execution

    try:
        run_execution(
            execution_id,
            recipe,
            until=until,
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


def _retry_target_names(
    retry_of: str | None,
    *,
    count: int,
    quota: int,
    requested_target_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Keep a retry on the exact immutable target set of its predecessor."""

    if not retry_of:
        return requested_target_names
    try:
        target_set = load_frozen_target_set(retry_of)
    except FileNotFoundError as exc:
        if requested_target_names:
            return requested_target_names
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "previous frozen target set is unavailable; provide every exact --target"
        ) from exc
    except ValueError as exc:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "previous frozen target set is invalid"
        ) from exc
    targets = target_set.get("targets")
    if not isinstance(targets, list):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "previous frozen target set is invalid"
        )
    inherited_names = tuple(
        str(target.get("name") or "").strip()
        for target in targets
        if isinstance(target, dict)
    )
    if (
        len(inherited_names) != len(targets)
        or any(not name for name in inherited_names)
        or len(set(inherited_names)) != len(inherited_names)
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "previous frozen target names are invalid"
        )
    if not quota <= len(inherited_names) <= count:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            f"inherited candidate pool {len(inherited_names)} must stay inside "
            f"[--quota {quota}, --count {count}]"
        )
    if requested_target_names and requested_target_names != inherited_names:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "--target must match the previous frozen target order exactly"
        )
    return inherited_names


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
    scale_promotion_receipt: dict[str, Any] | None = None
    scale_promotion_carrier: str | None = None
    if (
        identity.vertical == "travel"
        and identity.content_type.value in {"image", "video"}
        and identity.intent == "m1000"
    ):
        from content.execution.scale_promotion import (
            load_scale_promotion,
            require_m1000_promotion,
        )

        scale_promotion_carrier = identity.content_type.value
        frozen_promotion_path = (
            execution_root(identity.execution_id)
            / "0.plan"
            / f"{scale_promotion_carrier}_scale_promotion.json"
        )
        supplied_path = str(
            getattr(args, f"{scale_promotion_carrier}_scale_promotion", "") or ""
        ).strip()
        try:
            if frozen_promotion_path.is_file():
                scale_promotion_receipt = load_scale_promotion(
                    frozen_promotion_path,
                    carrier=scale_promotion_carrier,
                )
            elif supplied_path:
                scale_promotion_receipt = load_scale_promotion(
                    Path(supplied_path),
                    carrier=scale_promotion_carrier,
                )
            current_branch = _current_git_branch()
            # A detached managed clone has no current branch. The predecessor
            # receipt supplies its immutable dev1.0 branch while HEAD/source
            # digest still have to match exactly.
            receipt_branch = (
                str(scale_promotion_receipt.get("gitBranch") or "")
                if scale_promotion_receipt
                else ""
            )
            require_m1000_promotion(
                scale_promotion_receipt,
                carrier=scale_promotion_carrier,
                git_branch=current_branch or receipt_branch,
                git_commit_sha=_current_git_commit(),
                source_digest=current_source_digest().to_document(),
                entity_catalog_digest=entity_catalog_digest(
                    (
                        REPO_ROOT
                        / "quwoquan_data"
                        / "reference"
                        / identity.vertical
                        / "entities"
                        / runtime_request.region_ref
                    )
                    .relative_to(REPO_ROOT)
                    .as_posix()
                ),
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise SystemExit(
                f"[task execute] GATE_BLOCK {scale_promotion_carrier} scale promotion: {exc}"
            ) from exc
    root_execution_id = str(
        getattr(args, "campaign_root_execution_id", "") or ""
    ).strip() or identity.execution_id
    campaign_bound = bool(
        str(getattr(args, "campaign_root_execution_id", "") or "").strip()
    )
    if stage == "submit-only":
        from content.execution.campaign_submission import write_submission

        try:
            path = write_submission(
                root_execution_id=root_execution_id,
                execution_id=identity.execution_id,
                request=runtime_request,
                retry_of=str(getattr(args, "retry_of", "") or "").strip() or None,
            )
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            raise SystemExit(f"[task execute] GATE_BLOCK campaign submission: {exc}") from exc
        print(f"[task execute] SUBMITTED executionId={identity.execution_id} path={path}")
        return
    if campaign_bound and stage == "run":
        from content.execution.campaign_receipt import (
            require_lane_review_receipt,
        )

        try:
            require_lane_review_receipt(
                root_execution_id,
                execution_id=identity.execution_id,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise SystemExit(
                f"[task execute] GATE_BLOCK campaign lane review: {exc}"
            ) from exc
    # A task-output purge between plan-only and run destroys its frozen input,
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
    if stage == "promote-scale" and not manifest_path.is_file():
        raise SystemExit(
            f"[task execute] GATE_BLOCK execution={execution_id}: "
            "promote-scale requires an existing frozen M100 execution"
        )
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
    if stage == "promote-scale":
        if (
            identity.vertical != "travel"
            or identity.content_type.value not in {"image", "video"}
            or identity.intent != "m100"
        ):
            raise SystemExit(
                "[task execute] GATE_BLOCK promote-scale only accepts "
                "travel/image or travel/video M100"
            )
        envelope_value = str(getattr(args, "campaign_envelope", "") or "").strip()
        payload: dict[str, Any] | None = None
        if envelope_value:
            envelope_path = Path(envelope_value).expanduser()
            if not envelope_path.is_file():
                raise SystemExit(
                    "[task execute] GATE_BLOCK promote-scale campaign envelope is missing"
                )
            payload = read_json(envelope_path)
            if not isinstance(payload, dict):
                raise SystemExit(
                    "[task execute] GATE_BLOCK promote-scale campaign envelope must be an object"
                )
        from content.execution.scale_promotion import write_scale_promotion

        try:
            receipt_path = write_scale_promotion(
                predecessor_execution_id=execution_id,
                carrier=identity.content_type.value,
                predecessor_envelope=payload,
            )
        except (OSError, ValueError) as exc:
            raise SystemExit(
                f"[task execute] GATE_BLOCK {identity.content_type.value} "
                f"scale promotion: {exc}"
            ) from exc
        print(
            f"[task execute] {identity.content_type.value.upper()} SCALE "
            "PROMOTION APPROVED "
            f"executionId={execution_id} receipt={receipt_path}"
        )
        return
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
            inherit_frozen_targets=bool(manifest_retry_of),
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
    if (
        scale_promotion_receipt is not None
        and scale_promotion_carrier is not None
    ):
        frozen_promotion_path = (
            execution_root(execution_id)
            / "0.plan"
            / f"{scale_promotion_carrier}_scale_promotion.json"
        )
        if frozen_promotion_path.is_file():
            if read_json(frozen_promotion_path) != scale_promotion_receipt:
                raise SystemExit(
                    f"[task execute] GATE_BLOCK execution={execution_id}: "
                    f"frozen {scale_promotion_carrier} scale promotion receipt drift"
                )
        else:
            write_json(frozen_promotion_path, scale_promotion_receipt)
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
        until=(
            ExecutionStage.POST_REVIEW.value
            if stage == "review-only"
            else None
        ),
        recover_stage=recover_stage,
        recovery_reason=recovery_reason,
    )
    if stage == "review-only":
        if campaign_bound:
            from content.execution.campaign_receipt import write_review_receipt

            write_review_receipt(
                root_execution_id=root_execution_id,
                execution_id=execution_id,
            )
        print(f"[task execute] REVIEW READY executionId={execution_id}")
        return
    _readiness(recipe, execution_id, invoke)
    if campaign_bound:
        from content.execution.campaign_receipt import write_publish_receipt

        write_publish_receipt(
            root_execution_id=root_execution_id,
            execution_id=execution_id,
        )
    print(f"[task execute] DONE executionId={execution_id}")


def handle_execute(args: argparse.Namespace, invoke: InvokeCli | None = None) -> None:
    execution_id = str(getattr(args, "execution_id", "") or "").strip()
    from content.execution.identity import parse_execution_id

    identity = parse_execution_id(execution_id)
    stage = str(getattr(args, "stage", "run") or "run")
    if stage == "campaign-run":
        root_execution_id = str(
            getattr(args, "campaign_root_execution_id", "") or execution_id
        ).strip()
        if identity.content_type.value != "homepage":
            raise SystemExit(
                "[task execute] GATE_BLOCK campaign-run requires a homepage "
                "root executionId"
            )
        if root_execution_id != execution_id:
            raise SystemExit(
                "[task execute] GATE_BLOCK campaign-run executionId must equal "
                "--campaign-root-execution-id"
            )
        from content.execution.campaign_controller import run_campaign

        try:
            report_path = run_campaign(
                root_execution_id,
                submission_timeout_seconds=getattr(
                    args, "submission_timeout_seconds", None
                ),
                lane_timeout_seconds=getattr(
                    args, "campaign_lane_timeout_seconds", None
                ),
            )
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            ValueError,
            subprocess.SubprocessError,
        ) as exc:
            raise SystemExit(f"[task execute] GATE_BLOCK campaign: {exc}") from exc
        print(f"[task execute] CAMPAIGN DONE report={report_path}")
        return
    region_ref = str(getattr(args, "region_ref", "") or "").strip().strip("/")
    if not region_ref:
        raise SystemExit("[task execute] GATE_BLOCK --region-ref is required")
    discovery_path = REPO_ROOT / "quwoquan_data/reference" / identity.vertical / "entities" / region_ref
    if not discovery_path.is_dir():
        raise SystemExit(f"[task execute] GATE_BLOCK region reference does not exist: {region_ref}")
    quota, count = resolve_candidate_pool(
        quota=getattr(args, "quota", None),
        count=getattr(args, "count", None),
    )
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
    requested_target_names = tuple(getattr(args, "target_names", ()) or ())
    target_names = requested_target_names
    target_names = _retry_target_names(
        str(getattr(args, "retry_of", "") or "").strip() or None,
        count=count,
        quota=quota,
        requested_target_names=target_names,
    )
    _run_execution(
        argparse.Namespace(
            execution_id=execution_id,
            retry_of=getattr(args, "retry_of", None),
            video_scale_promotion=getattr(args, "video_scale_promotion", None),
            image_scale_promotion=getattr(args, "image_scale_promotion", None),
            campaign_envelope=getattr(args, "campaign_envelope", None),
            stage=getattr(args, "stage", "run"),
            campaign_root_execution_id=getattr(
                args, "campaign_root_execution_id", None
            ),
            recover_stage=getattr(args, "recover_stage", None),
            recovery_reason=getattr(args, "recovery_reason", None),
            family=getattr(args, "family", None),
            region_ref=region_ref,
            selector=target_selector.value,
            target_names=target_names,
            topic=getattr(args, "topic", None),
            source_providers=tuple(getattr(args, "source_providers", ()) or ()),
            vertical=identity.vertical,
            content_type=identity.content_type.value,
            intent=identity.intent,
            count=count,
            quota=quota,
        ),
        invoke=invoke,
    )


def register_recipe_parser(sub: argparse._SubParsersAction) -> None:
    from content.execution.recipe_parser import (
        register_recipe_parser as register_parser,
    )

    register_parser(sub, handler=handle_execute)
