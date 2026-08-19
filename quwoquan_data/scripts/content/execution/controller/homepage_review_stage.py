"""Independent homepage review stage."""
from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

from core.data_issue import (
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.io import read_json, write_json
from core.paths import execution_root
from core.prompt_render import render as render_prompt
from core.schema import assert_valid
from governance.coverage.entity_extract import entity_ref, require_domain_etype
from governance.coverage.license import RightsEnforcementMode, rights_proof_required

from content.execution import store
from content.execution.agent.agent_runner import _redact_managed_secret
from content.execution.agent.agent_worker import _default_managed_agent_runner_isolated
from content.execution.agent.outcome import AgentRunOutcome
from content.execution.context import ExecutionContext
from content.execution.controller.homepage_authoring import (
    _homepage_independent_review_issues,
)
from content.execution.model_contract import execution_model_pair_for_execution
from content.homepage.homepage_review import (
    apply_independent_homepage_review,
    homepage_asset_file_evidence,
    homepage_media_review_dispositions,
)
from content.source.source_unit import resolve_entity_object_dir


def _valid_payload(payload: Any, *, execution_id: str, object_ref: str) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("executionId") != execution_id or payload.get("objectRef") != object_ref:
        return False
    try:
        assert_valid(
            payload,
            "content",
            "homepage_reviewer_response",
            label=f"homepage_reviewer_response:{object_ref}",
        )
    except ValueError:
        return False
    return True


def _payload_from_outcome(
    outcome: AgentRunOutcome,
    *,
    execution_id: str,
    object_ref: str,
) -> dict[str, Any] | None:
    text = outcome.result_text.strip()
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        candidates.insert(0, fenced.group(1))
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if _valid_payload(payload, execution_id=execution_id, object_ref=object_ref):
            return payload
    return None


def _review_homepage_target(
    ctx: ExecutionContext,
    target: Mapping[str, Any],
    *,
    review_model: str,
    review_model_family: str,
    review_parameters: tuple[Any, ...],
    reviewer_workers: int,
) -> list[str]:
    name = str(target.get("name") or "").strip()
    if not name:
        return []
    domain, etype = require_domain_etype(target.get("entityType"), context=name)
    obj = resolve_entity_object_dir(
        ctx.execution_id,
        name,
        etype_hint=f"{domain}/{etype}",
    )
    review_dir = obj / "5.review"
    attestation_path = review_dir / "attestation.json"
    if not attestation_path.is_file():
        return [f"{name}: review attestation missing"]
    attestation = read_json(attestation_path)
    independent = attestation.get("independentReviewer")
    review_status = (
        str(independent.get("status") or "")
        if isinstance(independent, Mapping)
        else ""
    )
    if review_status == "passed":
        return _homepage_independent_review_issues(ctx, domain, etype, name)
    output_path = review_dir / "reviewer_response.pending.json"
    output_path.unlink(missing_ok=True)
    object_ref = entity_ref(domain, etype, name)
    manifest = read_json(obj / "manifest.json")
    vertical = str(manifest.get("vertical") or ctx.spec.vertical).strip()
    rights_mode = (
        RightsEnforcementMode.ENFORCE
        if rights_proof_required(vertical)
        else RightsEnforcementMode.AUDIT_ONLY
    )
    media_policy = json.dumps(
        {
            "vertical": vertical,
            "rightsEnforcementMode": rights_mode.value,
            "rightsDecisionRule": (
                "record rights audit gaps as findings; do not add them to issues"
                if rights_mode.value == "audit_only"
                else "missing rights proof is a blocking issue"
            ),
            "assets": homepage_media_review_dispositions(manifest),
            "assetFileEvidence": homepage_asset_file_evidence(obj, manifest),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    prompt = render_prompt(
        "homepage_independent_review",
        task_vars={
            "object_ref": object_ref,
            "object_dir": str(obj),
            "output_path": str(output_path),
            "media_policy": media_policy,
        },
    )
    review_ctx = ExecutionContext(
        execution_id=ctx.execution_id,
        entity_ids=[name],
        spec=ctx.spec.to_dict(),
        managed=True,
        runtime=ctx.runtime,
        max_workers=reviewer_workers,
        model=review_model,
        model_parameters=review_parameters,
        agent_provider=ctx.agent_provider,
        semantic_role="reviewer",
        release_only=ctx.release_only,
    )

    def _complete(path: Path = output_path) -> bool:
        if not path.is_file():
            return False
        try:
            payload = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        return _valid_payload(
            payload,
            execution_id=ctx.execution_id,
            object_ref=object_ref,
        )

    outcome = _default_managed_agent_runner_isolated(review_ctx, prompt)
    payload: dict[str, Any] | None = read_json(output_path) if _complete() else None
    if payload is None and outcome.succeeded:
        payload = _payload_from_outcome(
            outcome,
            execution_id=ctx.execution_id,
            object_ref=object_ref,
        )
        if payload is not None:
            write_json(output_path, payload)
    if not outcome.succeeded or payload is None:
        outcome_status = outcome.status.value
        issue_code = (
            DataIssueCode.AGENT_REVIEW_INVALID
            if outcome.succeeded
            else DataIssueCode.AGENT_REVIEW_UNAVAILABLE
        )
        review_issue = data_issue(
            issue_code,
            stage=DataIssueStage.REVIEW,
            ref=object_ref,
            lane=DataIssueLane.HOMEPAGE,
            recovery=DataRecoveryAction.STOP,
            message=(
                "independent reviewer returned invalid response"
                if issue_code == DataIssueCode.AGENT_REVIEW_INVALID
                else "independent reviewer model did not finish"
            ),
            attributes={
                "model": review_model,
                "modelFamily": review_model_family,
                "outcomeStatus": outcome_status,
                "errorCode": outcome.error_code,
            },
        )
        failure_root = execution_root(ctx.execution_id) / "evidence/reviewer_failures"
        failure_root.mkdir(parents=True, exist_ok=True)
        failure_path = failure_root / (
            hashlib.sha256(object_ref.encode("utf-8")).hexdigest()[:20] + ".json"
        )
        write_json(
            failure_path,
            {
                "schema": "quwoquan_data.homepage_review_failure",
                "executionId": ctx.execution_id,
                "objectRef": object_ref,
                "model": review_model,
                "modelFamily": review_model_family,
                "status": outcome_status,
                "issue": review_issue.as_dict(),
                "runId": outcome.run_id,
                "agentId": outcome.agent_id,
                "requestId": outcome.request_id,
                "durationMs": outcome.duration_ms,
                "errorCode": outcome.error_code,
                "error": _redact_managed_secret(outcome.message or "invalid reviewer output"),
                "result": _redact_managed_secret(outcome.result_text)[:4000],
                "recordedAt": store.now_iso(),
            },
        )
        output_path.unlink(missing_ok=True)
        return [str(review_issue)]
    output_path.unlink(missing_ok=True)
    bound = apply_independent_homepage_review(
        review_dir=review_dir,
        provider=outcome.provider.value,
        model=review_model,
        model_family=review_model_family,
        run_id=outcome.run_id,
        result_payload=payload,
    )
    return [f"{name}: {item}" for item in bound]


def independent_reviewer_precondition_issues(execution_id: str) -> list[str]:
    """Validate the frozen pair; per-object run IDs prove review independence."""
    execution_model_pair_for_execution(execution_id)
    return []


def run_homepage_independent_reviews(
    ctx: ExecutionContext,
    runtime_spec: Mapping[str, Any],
) -> list[str]:
    """Run read-only Cursor reviews at the runtime-policy concurrency.

    返回的是逐对象审阅问题；批次级前置条件由
    ``independent_reviewer_precondition_issues`` 单独判定。
    """
    precondition = independent_reviewer_precondition_issues(ctx.execution_id)
    if precondition:
        return precondition
    model_pair = execution_model_pair_for_execution(ctx.execution_id)
    scope = runtime_spec.get("scope")
    raw_targets = scope.get("coverageTargets") if isinstance(scope, Mapping) else []
    targets = [target for target in raw_targets or [] if isinstance(target, Mapping)]
    reviewer_workers = ctx.spec.execution_policy.fleet_max_concurrent_workers
    with ThreadPoolExecutor(max_workers=reviewer_workers) as executor:
        futures = [
            executor.submit(
                _review_homepage_target,
                ctx,
                target,
                review_model=model_pair.reviewer.model_id,
                review_model_family=model_pair.reviewer.family.value,
                review_parameters=model_pair.reviewer.parameters,
                reviewer_workers=reviewer_workers,
            )
            for target in targets
        ]
        return [issue for future in futures for issue in future.result()]


__all__ = [
    "independent_reviewer_precondition_issues",
    "run_homepage_independent_reviews",
]
