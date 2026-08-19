"""`qwq-data task execute` 的单 execution 工作包编排器。

配方声明选择策略、契约门、执行主体与放量验收；本执行器按固定四段主干执行，禁止任何脚本级第二编排真相源：

    execution manifest → target selection → contract-gate → execute → readiness

- executionId 由 CLI 显式注入；子步骤统一经 `_invoke_cli` 执行，终态只写当前工作包。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.control_types import TargetSelector  # noqa: F401
from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, REPO_ROOT, recipe_path
from core.source_digest import current_source_digest
from governance.provider_policy import load_provider_policy

from content.execution import store
from content.execution.queue import backend as queue_backend
from content.execution.planning.recipe import request as recipe_request, support as recipe_support
from content.execution.planning.recipe.contract import lint_recipe
from content.execution.request import (  # noqa: F401
    RuntimeExecutionRequest,
    resolve_candidate_pool,
)
from content.execution.workspace import (
    entity_catalog_digest,
    execution_manifest_path,
    execution_request_path,
    execution_root,
    load_execution_manifest,
    load_frozen_target_set,
)

_CLI_PATH = REPO_ROOT / "quwoquan_data/scripts/cli.py"
InvokeCli = Callable[[list[str]], int]


def _default_invoke_cli(argv: list[str]) -> int:
    proc = subprocess.run([sys.executable, str(_CLI_PATH), *argv], check=False)
    return int(proc.returncode)


def _current_git_commit() -> str:
    return recipe_support.current_git_commit(REPO_ROOT)


def _current_git_branch() -> str:
    return recipe_support.current_git_branch(REPO_ROOT)


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


def _contract_gate(recipe: dict[str, Any], execution_id: str) -> None:
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


def _execute(
    recipe: dict[str, Any],
    execution_id: str,
    *,
    until: str | None = None,
    recover_stage: str | None = None,
    recovery_reason: str | None = None,
) -> None:
    from content.execution.controller.execute.runner import run_execution

    try:
        run_execution(
            execution_id,
            recipe,
            until=until,
            recover_stage=recover_stage,
            recovery_reason=recovery_reason,
        )
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(
            f"[task execute] GATE_BLOCK execution={execution_id}: {exc}"
        ) from exc


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
    argv.extend(["--mode", str(readiness.get("mode") or "commercial")])
    rc = invoke(argv)
    if rc != 0:
        raise SystemExit(f"[task execute] execution-readiness rc={rc}")


def _runtime_preflight_argv(
    execution_id: str,
    semantic_selection_id: str = "default",
) -> list[str]:
    return recipe_support.runtime_preflight_argv(
        execution_root(execution_id),
        semantic_selection_id,
    )


def _retry_target_names(
    retry_of: str | None,
    *,
    count: int,
    quota: int,
    requested_target_names: tuple[str, ...],
) -> tuple[str, ...]:
    return recipe_request.retry_target_names(
        retry_of,
        count=count,
        quota=quota,
        requested_target_names=requested_target_names,
        load_frozen_target_set=load_frozen_target_set,
    )


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
        from content.execution.scale.promotion import (
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
    root_execution_id = (
        str(getattr(args, "campaign_root_execution_id", "") or "").strip()
        or identity.execution_id
    )
    campaign_bound = bool(
        str(getattr(args, "campaign_root_execution_id", "") or "").strip()
    )
    if stage == "submit-only":
        from content.execution.campaign.recipe_binding import submit_campaign_lane

        path = submit_campaign_lane(
            args,
            identity=identity,
            runtime_request=runtime_request,
            root_execution_id=root_execution_id,
        )
        print(
            f"[task execute] SUBMITTED executionId={identity.execution_id} path={path}"
        )
        return
    if campaign_bound:
        from content.execution.campaign.recipe_binding import (
            require_campaign_external_inputs,
        )

        require_campaign_external_inputs(identity)
    if campaign_bound and stage == "run":
        from content.execution.campaign.receipt import (
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
    execution_id = str(getattr(args, "execution_id", "") or "").strip()
    manifest_path = execution_manifest_path(execution_id)
    if stage == "promote-scale" and not manifest_path.is_file():
        raise SystemExit(
            f"[task execute] GATE_BLOCK execution={execution_id}: "
            "promote-scale requires an existing frozen M100 execution"
        )
    manifest_retry_of = str(getattr(args, "retry_of", "") or "") or None
    requested_semantic_selection_id = (
        str(getattr(args, "semantic_selection_id", "") or "").strip() or None
    )
    requested_semantic_preflight = str(
        getattr(args, "semantic_preflight_receipt", "") or ""
    ).strip()
    existing_manifest: dict[str, Any] | None = None
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
        resolved_selection = recipe_request.resolve_frozen_selection(
            recipe,
            frozen_request,
            repo_root=REPO_ROOT,
            vertical=identity.vertical,
            content_type=identity.content_type.value,
            intent=identity.intent,
        )
        manifest_retry_of = existing_retry_of
    else:
        from content.execution.workspace import require_clean_transaction_workspace

        require_clean_transaction_workspace(execution_id)
        resolved_selection = recipe_request.resolve_frozen_selection(
            recipe,
            runtime_request,
            repo_root=REPO_ROOT,
            vertical=identity.vertical,
            content_type=identity.content_type.value,
            intent=identity.intent,
        )
    from content.execution.planning.semantic_selection import (
        activate_frozen_semantic_selection,
        resolve_frozen_semantic_selection,
    )

    try:
        semantic_binding = resolve_frozen_semantic_selection(
            recipe,
            existing_manifest=(
                existing_manifest if manifest_path.is_file() else None
            ),
            requested_selection_id=requested_semantic_selection_id,
            retry_of=manifest_retry_of,
        )
        activate_frozen_semantic_selection(
            recipe,
            semantic_binding,
            workspace=Path.cwd(),
            execution_id=identity.execution_id,
        )
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(f"[task execute] GATE_BLOCK {exc}") from exc
    semantic_selection_id = semantic_binding.selection_id
    from content.execution.planning.semantic_preflight_admission import (
        resolve_cli_preflight_binding,
    )

    try:
        semantic_preflight_binding = resolve_cli_preflight_binding(
            existing_manifest=existing_manifest,
            requested_receipt_ref=requested_semantic_preflight,
            semantic_selection_id=semantic_selection_id,
            output_root=OUTPUT_ROOT,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task execute] GATE_BLOCK {exc}") from exc
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
        from content.execution.scale.promotion import write_scale_promotion

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
    from content.execution.controller.execute.runner import (
        preflight_execution_models,
        write_execution_model_readiness,
    )
    from content.execution.workspace import TARGET_SET_REF, frozen_target_set_digest

    # plan-only 只验证可复用输入和工作包形状；它不得冒充 Agent/来源/发布成功，
    # 因此不读取凭证也不探测模型。其余阶段必须先通过真实双模型启动证明。
    if stage != "plan-only":
        try:
            model_readiness = preflight_execution_models(
                recipe,
                semantic_selection_id,
            )
        except (RuntimeError, ValueError) as exc:
            raise SystemExit(
                f"[task execute] GATE_BLOCK execution={execution_id}: {exc}"
            ) from exc

    from core.data_issue import DataIssueError

    from content.execution.controller.execute.materialization import ensure_execution_spec

    try:
        execution_spec_id = ensure_execution_spec(
            recipe,
            resolved_selection,
            execution_id=execution_id,
            target_selector=runtime_request.selector,
            content_type=identity.content_type.value,
            target_names=runtime_request.target_names,
            inherit_frozen_targets=(
                bool(manifest_retry_of)
                and not bool(
                    getattr(args, "retry_submission_only_predecessor", False)
                )
                and not bool(getattr(args, "retry_external_media_scope", False))
            ),
            inherited_targets=tuple(getattr(args, "inherited_targets", ()) or ()),
        )
    except DataIssueError as exc:
        raise SystemExit(
            f"[task execute] GATE_BLOCK execution={execution_id}: {exc}"
        ) from exc
    frozen_manifest = create_execution_manifest(
        execution_id=execution_id,
        recipe_ref=recipe_ref,
        request=runtime_request.to_document(),
        selection_policy=SelectionPolicy.FROZEN,
        target_set_ref=TARGET_SET_REF,
        target_set_digest=frozen_target_set_digest(execution_id),
        retry_of=manifest_retry_of,
        allow_campaign_retry_scope=bool(
            getattr(args, "retry_submission_only_predecessor", False)
            or getattr(args, "retry_external_media_scope", False)
        ),
        semantic_selection_id=semantic_selection_id,
        semantic_preflight_binding=semantic_preflight_binding,
    )
    queue_backend.freeze_execution_queue_backend(
        execution_id, spec=store.load_spec(execution_id), manifest=frozen_manifest
    )
    if scale_promotion_receipt is not None and scale_promotion_carrier is not None:
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
    rc = invoke(_runtime_preflight_argv(execution_id, semantic_selection_id))
    if rc != 0:
        raise SystemExit(f"[task execute] task preflight rc={rc}")
    from content.execution.planning.recipe.checkpoint import execute_recipe_stage

    execute_recipe_stage(
        recipe,
        execution_id,
        stage=stage,
        execute=_execute,
        recover_stage=recover_stage,
        recovery_reason=recovery_reason,
    )
    if stage == "review-only":
        if campaign_bound:
            from content.execution.campaign.receipt import write_review_receipt

            write_review_receipt(
                root_execution_id=root_execution_id,
                execution_id=execution_id,
            )
        print(f"[task execute] REVIEW READY executionId={execution_id}")
        return
    _readiness(recipe, execution_id, invoke)
    if campaign_bound:
        from content.execution.campaign.receipt import write_publish_receipt
        from content.execution.campaign.workspace import CampaignRuntimePaths

        write_publish_receipt(
            root_execution_id=root_execution_id,
            execution_id=execution_id,
            runtime_paths=CampaignRuntimePaths.defaults(),
        )
    print(f"[task execute] DONE executionId={execution_id}")


def handle_execute(args: argparse.Namespace, invoke: InvokeCli | None = None) -> None:
    recipe_request.handle_execute(args, invoke, owner=sys.modules[__name__])


def register_recipe_parser(sub: argparse._SubParsersAction) -> None:
    from content.execution.planning.recipe.parser import (
        register_recipe_parser as register_parser,
    )

    register_parser(sub, handler=handle_execute)
