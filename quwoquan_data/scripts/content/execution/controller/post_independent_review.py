"""Run and bind one read-only independent Cursor reviewer per post object."""
from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

from content.execution import store
from content.execution.context import ExecutionContext
from content.execution.workspace import execution_root
from content.post import object_index as content_object
from content.review.independent import apply_independent_post_review
from core.io import read_json, write_json
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.prompt_render import render as render_prompt
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid
from governance.coverage.license import rights_enforcement_mode


def _existing_independent_review_issues(
    review_dir: Path,
    *,
    execution_id: str,
    object_ref: str,
    model: str,
    model_family: str,
) -> list[str]:
    result_path = review_dir / "reviewer_result.json"
    attestation_path = review_dir / "attestation.json"
    if not result_path.is_file() or not attestation_path.is_file():
        return [f"{object_ref}: independent reviewer evidence is missing"]
    try:
        result = read_json(result_path)
        attestation = read_json(attestation_path)
        assert_valid(
            result,
            "content",
            "reviewer_result",
            label=f"reviewer_result:{object_ref}",
        )
        assert_valid(
            attestation,
            "content",
            "review_attestation",
            label=f"review_attestation:{object_ref}",
        )
    except (OSError, TypeError, ValueError) as exc:
        return [f"{object_ref}: independent reviewer evidence invalid: {exc}"]
    reviewer = attestation.get("independentReviewer")
    reviewer = reviewer if isinstance(reviewer, Mapping) else {}
    expected = {
        "executionId": execution_id,
        "objectRef": object_ref,
        "provider": "cursor_sdk",
        "model": model,
        "modelFamily": model_family,
        "verdict": "passed",
    }
    issues = [
        f"{object_ref}: independent reviewer {field} mismatch"
        for field, value in expected.items()
        if result.get(field) != value
    ]
    if result.get("issues"):
        issues.append(f"{object_ref}: independent reviewer has blocking issues")
    if str(result.get("runId") or "").startswith("contract-output:"):
        issues.append(f"{object_ref}: independent reviewer runId is synthetic")
    if str(reviewer.get("status") or "") != "passed":
        issues.append(f"{object_ref}: independent reviewer attestation is not passed")
    for field in ("provider", "model", "modelFamily", "runId", "resultHash"):
        if reviewer.get(field) != result.get(field):
            issues.append(f"{object_ref}: independent reviewer {field} binding drift")
    return issues


def _media_policy(object_dir: Path, manifest: Mapping[str, Any]) -> str:
    vertical = str(manifest.get("vertical") or "").strip()
    if not vertical:
        raise ValueError("post manifest missing vertical rights policy owner")
    mode = rights_enforcement_mode(vertical)
    assets: list[dict[str, object]] = []
    for raw in manifest.get("assets") or []:
        if not isinstance(raw, Mapping):
            continue
        file_name = str(raw.get("fileName") or "").strip()
        direct = object_dir / file_name
        nested = object_dir / "assets" / file_name
        path = direct if direct.is_file() else nested
        assets.append(
            {
                "assetId": str(raw.get("assetId") or ""),
                "fileName": file_name,
                "exists": path.is_file(),
                "bytes": path.stat().st_size if path.is_file() else 0,
                "sha256": str(raw.get("sha256") or ""),
                "caption": str(raw.get("caption") or ""),
                "rightsAuditStatus": str(raw.get("rightsAuditStatus") or ""),
                "rightsAuditIssues": [
                    str(issue)
                    for issue in raw.get("rightsAuditIssues") or []
                    if str(issue).strip()
                ],
            }
        )
    return json.dumps(
        {
            "vertical": vertical,
            "rightsEnforcementMode": mode.value,
            "rightsDecisionRule": (
                "record rights audit gaps as findings; do not add them to issues"
                if mode.value == "audit_only"
                else "missing rights proof is a blocking issue"
            ),
            "sourceUrls": [
                str(url)
                for url in manifest.get("sourceUrls") or []
                if str(url).strip()
            ],
            "assets": assets,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _result_from_text(
    text: str,
    *,
    execution_id: str,
    object_ref: str,
) -> dict[str, Any] | None:
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        candidates.insert(0, fenced.group(1))
    first, last = text.find("{"), text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            assert_valid(
                payload,
                "content",
                "post_reviewer_response",
                label=f"post_reviewer_response:{object_ref}",
            )
        except (TypeError, ValueError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("executionId") == execution_id
            and payload.get("objectRef") == object_ref
        ):
            return payload
    return None


def _run_post_independent_reviews_serial(
    ctx: ExecutionContext,
    refs: list[str],
) -> list[DataIssue]:
    """Review current deterministic-approved posts and bind real SDK evidence."""
    from content.execution.agent.agent_runner import _redact_managed_secret
    from content.execution.agent.agent_worker import _default_managed_agent_runner_isolated
    from content.execution.model_contract import execution_model_pair_for_execution

    pair = execution_model_pair_for_execution(ctx.execution_id)
    model = pair.reviewer.model_id
    model_family = pair.reviewer.family.value
    reviewer_workers = active_runtime_policy().reviewer_workers
    issues: list[DataIssue] = []
    for ref in refs:
        object_dir = content_object.content_object_dir(ctx.execution_id, ref)
        review_dir = object_dir / "5.review"
        recorded = _existing_independent_review_issues(
            review_dir,
            execution_id=ctx.execution_id,
            object_ref=ref,
            model=model,
            model_family=model_family,
        )
        if not recorded:
            continue
        manifest_path = object_dir / "manifest.json"
        if not manifest_path.is_file():
            issues.append(
                data_issue(
                    DataIssueCode.CONTRACT_INVALID,
                    stage=DataIssueStage.POST_REVIEW,
                    ref=ref,
                    message="post manifest missing before independent review",
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                )
            )
            continue
        try:
            manifest = read_json(manifest_path)
            media_policy = _media_policy(object_dir, manifest)
        except (OSError, TypeError, ValueError) as exc:
            issues.append(
                data_issue(
                    DataIssueCode.CONTRACT_INVALID,
                    stage=DataIssueStage.POST_REVIEW,
                    ref=ref,
                    message=f"independent review input invalid: {exc}",
                    recovery=DataRecoveryAction.REWIND_COMPOSE,
                )
            )
            continue
        output_path = review_dir / "reviewer_response.pending.json"
        output_path.unlink(missing_ok=True)
        prompt = render_prompt(
            "post_independent_review",
            task_vars={
                "execution_id": ctx.execution_id,
                "object_ref": ref,
                "object_dir": str(object_dir),
                "output_path": str(output_path),
                "media_policy": media_policy,
            },
        )
        review_ctx = ExecutionContext(
            execution_id=ctx.execution_id,
            entity_ids=list(ctx.entity_ids),
            spec=ctx.spec.to_dict(),
            managed=True,
            runtime=ctx.runtime,
            max_workers=reviewer_workers,
            model=model,
            model_parameters=pair.reviewer.parameters,
            agent_provider=ctx.agent_provider,
            release_only=ctx.release_only,
        )
        outcome = _default_managed_agent_runner_isolated(review_ctx, prompt)
        payload: dict[str, Any] | None = None
        if output_path.is_file():
            try:
                candidate = read_json(output_path)
                assert_valid(
                    candidate,
                    "content",
                    "post_reviewer_response",
                    label=f"post_reviewer_response:{ref}",
                )
            except (OSError, TypeError, ValueError):
                candidate = None
            if (
                isinstance(candidate, dict)
                and candidate.get("executionId") == ctx.execution_id
                and candidate.get("objectRef") == ref
            ):
                payload = candidate
        if payload is None and outcome.succeeded:
            payload = _result_from_text(
                outcome.result_text,
                execution_id=ctx.execution_id,
                object_ref=ref,
            )
        output_path.unlink(missing_ok=True)
        if not outcome.succeeded or payload is None:
            failure_root = execution_root(ctx.execution_id) / "evidence/reviewer_failures"
            failure_root.mkdir(parents=True, exist_ok=True)
            failure_path = failure_root / (
                hashlib.sha256(ref.encode("utf-8")).hexdigest()[:20] + ".json"
            )
            write_json(
                failure_path,
                {
                    "schema": "quwoquan_data.post_review_failure",
                    "executionId": ctx.execution_id,
                    "objectRef": ref,
                    "model": model,
                    "modelFamily": model_family,
                    "status": outcome.status.value,
                    "runId": outcome.run_id,
                    "agentId": outcome.agent_id,
                    "requestId": outcome.request_id,
                    "durationMs": outcome.duration_ms,
                    "errorCode": outcome.error_code,
                    "error": _redact_managed_secret(outcome.message),
                    "recordedAt": store.now_iso(),
                },
            )
            issues.append(
                data_issue(
                    DataIssueCode.AGENT_REVIEW_INVALID,
                    stage=DataIssueStage.POST_REVIEW,
                    ref=ref,
                    message="independent reviewer did not produce valid evidence",
                    recovery=DataRecoveryAction.RETRY_AGENT,
                )
            )
            continue
        bound = apply_independent_post_review(
            review_dir=review_dir,
            provider="cursor_sdk",
            model=model,
            model_family=model_family,
            run_id=outcome.run_id,
            result_payload=payload,
        )
        issues.extend(
            data_issue(
                DataIssueCode.QUALITY_FAILED,
                stage=DataIssueStage.POST_REVIEW,
                ref=ref,
                message=issue,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            )
            for issue in bound
        )
    return issues


def run_post_independent_reviews(
    ctx: ExecutionContext,
    refs: list[str],
) -> list[DataIssue]:
    """Review posts concurrently, preserving input-order issue reporting."""
    reviewer_workers = active_runtime_policy().reviewer_workers
    with ThreadPoolExecutor(max_workers=reviewer_workers) as executor:
        futures = [
            executor.submit(_run_post_independent_reviews_serial, ctx, [ref])
            for ref in refs
        ]
        return [issue for future in futures for issue in future.result()]


__all__ = ["run_post_independent_reviews"]
