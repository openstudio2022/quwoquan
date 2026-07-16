"""Internal runner for one immutable content execution work package."""
from __future__ import annotations

import argparse
import os
from typing import Any, Mapping

from core.io import write_json
from core.python_environment import resolve_cursor_startup_timeout_seconds
from core.python_runtime import environment_preflight
from core.schema import assert_valid
from core.control_types import AgentProvider, RuntimeEnvironment
from core.runtime_policy import active_runtime_policy
from content.execution import store
from content.execution.qualification import prepare_execution_qualification
from content.execution.identity import validate_execution_id
from content.execution.pipeline.cli import handle_run
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
            workflow_doc=None,
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
    runtime = str(execution.get("runtime") or "local")
    timeout_seconds = resolve_cursor_startup_timeout_seconds(
        active_runtime_policy().startup_timeout_seconds
    )

    def _probe(model: ExecutionModel) -> tuple[dict[str, object], list[str]]:
        report = environment_preflight(
            require_cursor_key=True,
            check_network=True,
            check_cursor_cloud_api=True,
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
        "contractVersion": "execution-model-readiness-v1",
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
        "schemaVersion": "quwoquan_data.execution_model_readiness/1",
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


def run_execution(
    execution_id: str,
    recipe: dict[str, Any],
    *,
    recover_stage: str | None = None,
    recovery_reason: str | None = None,
) -> None:
    """Run exactly one execution without exposing another CLI workflow surface."""
    execution_id = validate_execution_id(execution_id)
    if bool(recover_stage) != bool(recovery_reason):
        raise ValueError("recover_stage and recovery_reason must be provided together")
    pair = execution_model_pair(recipe)
    # Internal callers must not bypass the public facade's G0 capability proof.
    preflight_execution_models(recipe)
    execution = recipe.get("execution") or {}
    policy = active_runtime_policy()
    os.environ["QWQ_HOMEPAGE_AUTHOR_MODEL_FAMILY"] = pair.author.family.value
    os.environ["QWQ_HOMEPAGE_REVIEW_MODEL"] = pair.reviewer.model_id
    os.environ["QWQ_HOMEPAGE_REVIEW_MODEL_FAMILY"] = pair.reviewer.family.value
    _prepare_execution(execution_id)
    prepare_execution_qualification(execution_id)
    handle_run(
        argparse.Namespace(
            mode="single",
            execution_id=execution_id,
            resume=True,
            reset_state=False,
            reset_stage_retries=recover_stage,
            reset_stage_reason=recovery_reason,
            reset_react_rewinds=False,
            baseline_packet=None,
            until=None,
            managed=True,
            runtime=str(execution.get("runtime") or RuntimeEnvironment.LOCAL),
            max_workers=policy.author_workers,
            agent_provider=AgentProvider.CURSOR_SDK.value,
            model=str(execution.get("model") or policy.cursor_model),
            startup_timeout_seconds=float(policy.startup_timeout_seconds),
            force_clean_workspace_agent_state=bool(execution.get("forceCleanWorkspaceAgentState", True)),
            release_only=False,
        )
    )
