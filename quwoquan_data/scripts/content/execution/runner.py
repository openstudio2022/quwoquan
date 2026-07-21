"""Internal runner for one immutable content execution work package."""
from __future__ import annotations

import argparse
from typing import Any, Mapping

from core.io import read_json, write_json
from core.python_environment import resolve_cursor_startup_timeout_seconds
from core.python_runtime import environment_preflight
from core.schema import assert_valid
from core.control_types import ExecutionStage
from core.runtime_policy import active_runtime_policy
from content.execution import store
from content.execution.qualification import prepare_execution_qualification
from content.execution.identity import validate_execution_id
from content.execution.controller.entrypoint import ControllerRequest, run_controlled_execution
from content.execution.baseline import handle_baseline
from content.source.discovery.handler import handle_explore

from .model_contract import ExecutionModel, execution_model_pair
from .workspace import execution_root


def _prepare_execution(execution_id: str) -> None:
    """Materialize the reproducible discovery and baseline inputs once per execution."""
    spec = store.load_spec(execution_id)
    scope = spec.get("scope") or {}
    region = str(scope.get("region") or "").strip()
    entity_types = [str(item).strip() for item in scope.get("entityTypes") or [] if str(item).strip()]
    if not region or not entity_types:
        raise RuntimeError("execution spec requires scope.region and scope.entityTypes")
    handle_explore(
        argparse.Namespace(
            execution_id=execution_id,
            regions=region,
            entity_types=",".join(entity_types),
        )
    )
    handle_baseline(
        argparse.Namespace(
            execution_id=execution_id,
            catalog=None,
            spec_doc=None,
            design_doc=None,
            acceptance_doc=None,
            execution_guide=None,
            command_matrix_doc=None,
            catalog_config=None,
            naming_rules=None,
            geo_band_rules=None,
            schema_files=[],
            config_files=[],
            output=None,
        )
    )


def _startup_projection(report: Mapping[str, Any], model: ExecutionModel) -> dict[str, object]:
    startup = report.get("cursorStartup") if isinstance(report.get("cursorStartup"), Mapping) else {}
    return {
        "ready": bool(startup.get("ready")),
        "status": str(startup.get("status") or "unknown"),
        "errorClass": str(startup.get("errorClass") or ""),
        "errorCode": str(startup.get("errorCode") or ""),
        "httpStatus": startup.get("httpStatus"),
        "runtime": str(startup.get("runtime") or ""),
        "model": model.model_id,
        "cacheHit": bool(startup.get("cacheHit")),
    }


def preflight_execution_models(recipe: Mapping[str, Any]) -> dict[str, object]:
    """Prove author and independent-review models can really start before work begins.

    Listing a Cursor model is not a capability guarantee.  The only acceptable
    preflight is a minimal real SDK startup for both contract-declared models.
    The returned projection contains no credential material or raw model output.
    """
    pair = execution_model_pair(recipe)
    execution = recipe.get("execution")
    assert isinstance(execution, Mapping)
    runtime = active_runtime_policy().cursor_runtime.value
    timeout_seconds = resolve_cursor_startup_timeout_seconds(
        active_runtime_policy().startup_timeout_seconds
    )

    def _probe(model: ExecutionModel) -> tuple[dict[str, object], list[str]]:
        report = environment_preflight(
            require_cursor_key=True,
            check_network=True,
            check_cursor_startup=True,
            cursor_startup_model=model.model_id,
            cursor_startup_runtime=runtime,
            cursor_startup_timeout_seconds=timeout_seconds,
        )
        startup = _startup_projection(report, model)
        issues = [str(item) for item in (report.get("issues") or []) if str(item).strip()]
        return startup, issues

    author_startup, author_issues = _probe(pair.author)
    reviewer_startup, reviewer_issues = _probe(pair.reviewer)
    blockers: list[str] = []
    if author_issues or not bool(author_startup["ready"]):
        blockers.append(
            "author model unavailable "
            f"model={pair.author.model_id} family={pair.author.family.value} "
            f"status={author_startup['status']} code={author_startup['errorCode'] or 'none'}"
        )
    if reviewer_issues or not bool(reviewer_startup["ready"]):
        blockers.append(
            "independent reviewer model unavailable "
            f"model={pair.reviewer.model_id} family={pair.reviewer.family.value} "
            f"status={reviewer_startup['status']} code={reviewer_startup['errorCode'] or 'none'}"
        )
    if blockers:
        raise RuntimeError("; ".join(blockers))
    return {
        "ready": True,
        "runtime": runtime,
        "author": {
            "model": pair.author.model_id,
            "modelFamily": pair.author.family.value,
            "startup": author_startup,
        },
        "reviewer": {
            "model": pair.reviewer.model_id,
            "modelFamily": pair.reviewer.family.value,
            "startup": reviewer_startup,
        },
    }


def write_execution_model_readiness(execution_id: str, report: Mapping[str, object]) -> None:
    """Persist the runtime-only model capability proof inside its work package."""
    normalized = validate_execution_id(execution_id)
    payload = {
        "schema": "quwoquan_data.execution_model_readiness",
        "executionId": normalized,
        **dict(report),
    }
    assert_valid(
        payload,
        "execution",
        "model_readiness",
        label=f"execution_model_readiness:{normalized}",
    )
    write_json(execution_root(normalized) / "evidence" / "model_readiness.json", payload)


def require_execution_model_readiness(
    execution_id: str,
    recipe: Mapping[str, Any],
) -> None:
    """Require the public facade's model proof before entering the controller.

    ``task execute`` owns the real Cursor startup probe and records the result
    in the immutable execution work package.  Re-probing in the controller
    turns a transient provider result into an inconsistent resume decision:
    the same execution may have already completed author work with the exact
    model that a second probe reports as unavailable.  The controller instead
    verifies that the recorded proof belongs to its current model contract.
    """
    normalized = validate_execution_id(execution_id)
    path = execution_root(normalized) / "evidence" / "model_readiness.json"
    if not path.is_file():
        raise RuntimeError("execution model readiness evidence is required before controller run")
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise RuntimeError("execution model readiness evidence must be an object")
    assert_valid(
        dict(payload),
        "execution",
        "model_readiness",
        label=f"execution_model_readiness:{normalized}",
    )
    if str(payload.get("executionId") or "") != normalized:
        raise RuntimeError("execution model readiness evidence belongs to another execution")
    if not bool(payload.get("ready")):
        raise RuntimeError("execution model readiness evidence is not ready")
    pair = execution_model_pair(recipe)
    runtime = active_runtime_policy().cursor_runtime.value
    expected = (
        ("author", pair.author),
        ("reviewer", pair.reviewer),
    )
    if str(payload.get("runtime") or "") != runtime:
        raise RuntimeError("execution model readiness runtime does not match active runtime policy")
    for role, model in expected:
        proof = payload.get(role)
        if not isinstance(proof, Mapping):
            raise RuntimeError(f"execution model readiness {role} proof is required")
        startup = proof.get("startup")
        if (
            str(proof.get("model") or "") != model.model_id
            or str(proof.get("modelFamily") or "") != model.family.value
            or not isinstance(startup, Mapping)
            or not bool(startup.get("ready"))
            or str(startup.get("runtime") or "") != runtime
            or str(startup.get("model") or "") != model.model_id
        ):
            raise RuntimeError(
                f"execution model readiness {role} proof does not match the immutable model contract"
            )


def run_execution(
    execution_id: str,
    recipe: dict[str, Any],
    *,
    recover_stage: str | None = None,
    recovery_reason: str | None = None,
) -> None:
    """Run exactly one execution without exposing another orchestration surface."""
    execution_id = validate_execution_id(execution_id)
    if bool(recover_stage) != bool(recovery_reason):
        raise ValueError("recover_stage and recovery_reason must be provided together")
    # The public facade performs the only live startup probe.  The controller
    # verifies that durable proof instead of issuing a second transient probe.
    require_execution_model_readiness(execution_id, recipe)
    _prepare_execution(execution_id)
    prepare_execution_qualification(execution_id)
    run_controlled_execution(
        ControllerRequest(
            execution_id=execution_id,
            resume=True,
            recover_stage=ExecutionStage(recover_stage) if recover_stage else None,
            recovery_reason=recovery_reason,
            baseline_packet=None,
            managed=True,
            force_clean_workspace_agent_state=False,
            release_only=False,
        )
    )
