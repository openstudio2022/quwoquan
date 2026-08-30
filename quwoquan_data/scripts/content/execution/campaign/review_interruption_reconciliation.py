"""Create-once evidence for a reviewer response stranded by interruption.

The receipt deliberately does not update the predecessor ``reviewer_result`` or
attestation.  It only binds the sole schema-valid pending response to the sole
finished reviewer work unit that is not already referenced by independent
review evidence.  Ambiguous or incomplete evidence fails closed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.campaign.failed_execution_reconciliation_common import (
    _lock,
    _now,
    file_binding,
)
from content.execution.campaign.submission_reconciliation_contract import (
    canonical_digest,
    campaigns_root,
    file_digest,
    resolve_ref,
)
from content.execution.identity import parse_execution_id
from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid

SCHEMA = "quwoquan_data.campaign_review_interruption_reconciliation_receipt"
_RECEIPT_DIR = "review-interruption"
_BINDING_RULE = (
    "sole_unbound_finished_reviewer_work_unit_for_sole_pending_response"
)


def _journal_digest(value: Mapping[str, Any]) -> str:
    body = (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _object_token(object_ref: str) -> str:
    return hashlib.sha256(object_ref.encode("utf-8")).hexdigest()


def review_interruption_receipt_path(
    root_execution_id: str,
    object_ref: str,
    *,
    output_root: Path | None = None,
) -> Path:
    root_id = parse_execution_id(root_execution_id).execution_id
    normalized_ref = str(object_ref or "").strip()
    if not normalized_ref:
        raise ValueError("review interruption objectRef is required")
    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    return (
        campaigns_root(resolved_output)
        / root_id
        / "reconciliation"
        / _RECEIPT_DIR
        / f"{_object_token(normalized_ref)}.json"
    )


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be one regular file: {path}")
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be one object")
    return payload


def _safe_directory_ref(
    raw_ref: object,
    *,
    output_root: Path,
    label: str,
) -> tuple[str, Path]:
    raw = Path(str(raw_ref or "").strip())
    if raw.is_absolute() or not raw.parts or ".." in raw.parts:
        raise ValueError(f"{label} is not a safe output-relative ref")
    path = (output_root / raw).resolve()
    try:
        path.relative_to(output_root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes output root") from exc
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} must be one real directory")
    return raw.as_posix(), path


def _content_object_paths(
    execution_root: Path,
    *,
    execution_id: str,
) -> tuple[Path, dict[str, Path]]:
    index_path = execution_root / "_shared/content_object_index.json"
    index = _read_object(index_path, label="content object index")
    if index.get("schema") != "quwoquan_data.content_object_index":
        raise ValueError("content object index schema is invalid")
    raw_refs = index.get("refs")
    if not isinstance(raw_refs, Mapping) or not raw_refs:
        raise ValueError("content object index refs are invalid")
    resolved: dict[str, Path] = {}
    for raw_ref, raw_row in raw_refs.items():
        ref = str(raw_ref or "").strip()
        if not ref or not isinstance(raw_row, Mapping):
            raise ValueError("content object index row is invalid")
        parts = (
            "posts",
            str(raw_row.get("contentType") or "").strip(),
            str(raw_row.get("angle") or "").strip(),
            str(raw_row.get("title") or "").strip(),
            str(raw_row.get("seq") or "").strip(),
        )
        if any(not part or part in {".", ".."} or "/" in part for part in parts):
            raise ValueError(f"content object index path is invalid: {ref}")
        object_dir = (execution_root / Path(*parts)).resolve()
        try:
            object_dir.relative_to(execution_root.resolve())
        except ValueError as exc:
            raise ValueError(f"content object path escapes execution: {ref}") from exc
        resolved[ref] = object_dir
    return index_path, resolved


def _bound_independent_run_ids(
    object_paths: Mapping[str, Path],
    *,
    execution_id: str,
) -> set[str]:
    run_ids: set[str] = set()
    for object_ref, object_dir in object_paths.items():
        review_dir = object_dir / "5.review"
        result_path = review_dir / "reviewer_result.json"
        evidence_path = review_dir / "evidence_index.json"
        if not result_path.is_file() or not evidence_path.is_file():
            continue
        result = _read_object(result_path, label="reviewer result")
        evidence = _read_object(evidence_path, label="review evidence index")
        try:
            assert_valid(result, "content", "reviewer_result")
            assert_valid(evidence, "content", "evidence_index")
        except (FileNotFoundError, TypeError, ValueError):
            continue
        if (
            result.get("executionId") != execution_id
            or result.get("objectRef") != object_ref
        ):
            continue
        expected_sha = file_digest(result_path)
        independently_bound = any(
            isinstance(row, Mapping)
            and row.get("kind") == "independent_reviewer_result"
            and row.get("ref") == "5.review/reviewer_result.json"
            and row.get("sha256") == expected_sha
            for row in evidence.get("evidence") or []
        )
        run_id = str(result.get("runId") or "").strip()
        if independently_bound and run_id:
            run_ids.add(run_id)
    return run_ids


def _pending_responses(
    object_paths: Mapping[str, Path],
    *,
    execution_id: str,
) -> dict[str, tuple[Path, dict[str, Any]]]:
    pending: dict[str, tuple[Path, dict[str, Any]]] = {}
    for object_ref, object_dir in object_paths.items():
        path = object_dir / "5.review/reviewer_response.pending.json"
        if not path.is_file():
            continue
        payload = _read_object(path, label="pending reviewer response")
        assert_valid(payload, "content", "post_reviewer_response")
        if (
            payload.get("executionId") != execution_id
            or payload.get("objectRef") != object_ref
            or payload.get("decision") not in {"revision_needed", "rejected"}
            or not payload.get("issues")
        ):
            raise ValueError(f"pending reviewer response binding is invalid: {object_ref}")
        pending[object_ref] = (path, payload)
    return pending


def _unbound_finished_reviewer_attempts(
    execution_root: Path,
    *,
    execution_id: str,
    manifest: Mapping[str, Any],
    bound_run_ids: set[str],
) -> list[tuple[Path, dict[str, Any], Path, dict[str, Any]]]:
    model_binding = manifest.get("modelBinding")
    if not isinstance(model_binding, Mapping):
        raise ValueError("execution reviewer model binding is missing")
    expected_provider = str(model_binding.get("provider") or "").strip()
    expected_model = str(model_binding.get("reviewerModel") or "").strip()
    expected_family = str(model_binding.get("reviewerModelFamily") or "").strip()
    if not expected_provider or not expected_model or expected_family != "grok":
        raise ValueError("interrupted review reconciliation requires frozen Grok binding")
    candidates: list[tuple[Path, dict[str, Any], Path, dict[str, Any]]] = []
    journal_root = execution_root / "_shared/semantic_tasks"
    for request_path in sorted(journal_root.glob("*/request.json")):
        request = _read_object(request_path, label="semantic reviewer request")
        if request.get("stage") != "reviewer":
            continue
        assert_valid(request, "execution", "semantic_task_journal_request")
        stable_request = {
            key: value for key, value in request.items() if key != "requestDigest"
        }
        work_identity = {
            "executionId": execution_id,
            "stage": "reviewer",
            "promptSha256": request.get("promptSha256"),
        }
        if (
            request.get("executionId") != execution_id
            or request.get("stage") != "reviewer"
            or request.get("provider") != expected_provider
            or request.get("model") != expected_model
            or request.get("requestDigest") != _journal_digest(stable_request)
            or request.get("workUnitId") != _journal_digest(work_identity)
            or request_path.parent.name
            != str(request.get("workUnitId") or "").removeprefix("sha256:")
        ):
            raise ValueError("semantic reviewer request digest or identity drift")
        for attempt_path in sorted((request_path.parent / "attempts").glob("*.json")):
            attempt = _read_object(attempt_path, label="semantic reviewer attempt")
            assert_valid(attempt, "execution", "semantic_task_journal_attempt")
            stable_attempt = {
                key: value for key, value in attempt.items() if key != "attemptDigest"
            }
            run_id = str(attempt.get("runId") or "").strip()
            if (
                attempt.get("workUnitId") != request.get("workUnitId")
                or attempt.get("requestDigest") != request.get("requestDigest")
                or attempt.get("provider") != expected_provider
                or attempt.get("attemptDigest") != _journal_digest(stable_attempt)
            ):
                raise ValueError("semantic reviewer attempt digest or identity drift")
            if (
                attempt.get("started") is True
                and attempt.get("status") == "finished"
                and run_id
                and run_id not in bound_run_ids
            ):
                candidates.append((request_path, request, attempt_path, attempt))
    return candidates


def _derive_receipt(
    root_execution_id: str,
    execution_id: str,
    object_ref: str,
    *,
    output_root: Path,
) -> dict[str, Any]:
    root_id = parse_execution_id(root_execution_id).execution_id
    identity = parse_execution_id(execution_id)
    normalized_ref = str(object_ref or "").strip()
    if not normalized_ref:
        raise ValueError("review interruption objectRef is required")
    campaign_dir = campaigns_root(output_root) / root_id
    plan_path = campaign_dir / "campaign_plan.json"
    report_path = campaign_dir / "campaign_report.json"
    claim_path = campaign_dir / "claims" / f"{identity.content_type.value}.json"
    plan = _read_object(plan_path, label="campaign plan")
    report = _read_object(report_path, label="campaign report")
    claim = _read_object(claim_path, label="campaign claim")
    report_lanes = report.get("lanes")
    lane = (
        report_lanes.get(identity.content_type.value)
        if isinstance(report_lanes, Mapping)
        else None
    )
    if (
        plan.get("rootExecutionId") != root_id
        or report.get("rootExecutionId") != root_id
        or not isinstance(lane, Mapping)
        or lane.get("executionId") != identity.execution_id
        or claim.get("rootExecutionId") != root_id
        or claim.get("executionId") != identity.execution_id
        or claim.get("carrier") != identity.content_type.value
        or claim.get("status") != "failed"
        or not isinstance(claim.get("returnCode"), int)
        or claim.get("returnCode") == 0
        or report.get("status") != "blocked"
    ):
        raise ValueError("campaign interruption evidence is not terminal and exact")

    execution_root = (output_root / "data/tasks" / identity.execution_id).resolve()
    try:
        execution_root.relative_to(output_root.resolve())
    except ValueError as exc:
        raise ValueError("execution root escapes output root") from exc
    if execution_root.name != identity.execution_id or not execution_root.is_dir():
        raise ValueError("interrupted execution root is unavailable")
    manifest_path = execution_root / "execution_manifest.json"
    state_path = execution_root / "_shared/execution_state.json"
    manifest = _read_object(manifest_path, label="execution manifest")
    state = _read_object(state_path, label="execution state")
    if (
        manifest.get("executionId") != identity.execution_id
        or state.get("executionId") != identity.execution_id
        or state.get("status") != "manual_required"
        or state.get("lastFailedStage") != "execution"
        or not str(state.get("interruptReason") or "").strip()
    ):
        raise ValueError("execution does not preserve an interrupted terminal state")
    model_binding = manifest.get("modelBinding")
    if not isinstance(model_binding, Mapping):
        raise ValueError("execution model binding is missing")
    if (
        plan.get("semanticSelectionId") != manifest.get("semanticSelectionId")
        or plan.get("gitCommitSha") != str(lane.get("sourceCapsuleCommitSha") or "")
        or plan.get("sourceDigest") != manifest.get("sourceDigest", {}).get("digest")
        or plan.get("executionBundle") != manifest.get("executionBundle")
        or plan.get("entityCatalogDigest")
        != manifest.get("sourceDigest", {}).get("entityCatalogDigest", plan.get("entityCatalogDigest"))
    ):
        # The manifest's sourceDigest intentionally has no entity catalog field;
        # the campaign plan and capsule provide that separate identity component.
        if (
            plan.get("semanticSelectionId") != manifest.get("semanticSelectionId")
            or plan.get("gitCommitSha") != str(lane.get("sourceCapsuleCommitSha") or "")
            or plan.get("sourceDigest") != manifest.get("sourceDigest", {}).get("digest")
            or plan.get("executionBundle") != manifest.get("executionBundle")
        ):
            raise ValueError("campaign and execution source/model identity drift")

    capsule_ref, capsule_dir = _safe_directory_ref(
        lane.get("sourceCapsuleRef"),
        output_root=output_root,
        label="source capsule",
    )
    capsule_digest = str(lane.get("sourceCapsuleDigest") or "").strip()
    if (
        not capsule_digest.startswith("sha256:")
        or capsule_dir.name != capsule_digest.removeprefix("sha256:")
    ):
        raise ValueError("source capsule ref/digest drift")
    capsule_manifest_path = capsule_dir / ".qwq_campaign_capsule.json"
    capsule_manifest = _read_object(
        capsule_manifest_path,
        label="source capsule manifest",
    )
    if (
        capsule_manifest.get("capsuleDigest") != capsule_digest
        or capsule_manifest.get("gitCommitSha") != plan.get("gitCommitSha")
        or capsule_manifest.get("sourceDigest") != plan.get("sourceDigest")
        or capsule_manifest.get("executionBundle") != plan.get("executionBundle")
        or capsule_manifest.get("entityCatalogDigest")
        != plan.get("entityCatalogDigest")
    ):
        raise ValueError("source capsule identity drift")

    index_path, object_paths = _content_object_paths(
        execution_root,
        execution_id=identity.execution_id,
    )
    if normalized_ref not in object_paths:
        raise ValueError("pending objectRef is absent from content object index")
    pending = _pending_responses(
        object_paths,
        execution_id=identity.execution_id,
    )
    if set(pending) != {normalized_ref}:
        raise ValueError(
            "review interruption receipt requires exactly one pending response"
        )
    pending_path, response = pending[normalized_ref]
    bound_run_ids = _bound_independent_run_ids(
        object_paths,
        execution_id=identity.execution_id,
    )
    attempts = _unbound_finished_reviewer_attempts(
        execution_root,
        execution_id=identity.execution_id,
        manifest=manifest,
        bound_run_ids=bound_run_ids,
    )
    if len(attempts) != 1:
        raise ValueError(
            "review interruption receipt requires exactly one unbound finished reviewer work unit"
        )
    request_path, request, attempt_path, attempt = attempts[0]
    expected_provider = str(model_binding.get("provider") or "")
    expected_model = str(model_binding.get("reviewerModel") or "")
    expected_family = str(model_binding.get("reviewerModelFamily") or "")

    return {
        "schema": SCHEMA,
        "rootExecutionId": root_id,
        "executionId": identity.execution_id,
        "carrier": identity.content_type.value,
        "objectRef": normalized_ref,
        "decision": response["decision"],
        "issues": list(response["issues"]),
        "findings": list(response["findings"]),
        "bindingRule": _BINDING_RULE,
        "campaignEvidence": {
            "plan": file_binding(plan_path, output_root=output_root, label="campaign plan"),
            "report": file_binding(report_path, output_root=output_root, label="campaign report"),
            "claim": file_binding(claim_path, output_root=output_root, label="campaign claim"),
            "capsule": {
                "ref": capsule_ref,
                "digest": capsule_digest,
                "manifest": file_binding(
                    capsule_manifest_path,
                    output_root=output_root,
                    label="source capsule manifest",
                ),
                "treeDigest": str(capsule_manifest.get("treeDigest") or ""),
                "gitCommitSha": str(capsule_manifest.get("gitCommitSha") or ""),
                "sourceDigest": str(capsule_manifest.get("sourceDigest") or ""),
            },
        },
        "executionEvidence": {
            "manifest": file_binding(
                manifest_path, output_root=output_root, label="execution manifest"
            ),
            "state": file_binding(
                state_path, output_root=output_root, label="execution state"
            ),
            "objectIndex": file_binding(
                index_path, output_root=output_root, label="content object index"
            ),
            "pendingResponse": {
                **file_binding(
                    pending_path,
                    output_root=output_root,
                    label="pending reviewer response",
                ),
                "responseDigest": canonical_digest(response),
            },
            "interruptedStatus": str(state.get("status") or ""),
            "interruptReason": str(state.get("interruptReason") or ""),
        },
        "semanticEvidence": {
            "workUnitId": str(request["workUnitId"]),
            "request": file_binding(
                request_path,
                output_root=output_root,
                label="semantic reviewer request",
            ),
            "requestDigest": str(request["requestDigest"]),
            "promptSha256": str(request["promptSha256"]),
            "attempt": file_binding(
                attempt_path,
                output_root=output_root,
                label="semantic reviewer attempt",
            ),
            "attemptDigest": str(attempt["attemptDigest"]),
            "provider": expected_provider,
            "model": expected_model,
            "modelFamily": expected_family,
            "runId": str(attempt["runId"]),
            "resultSha256": str(attempt["resultSha256"]),
            "status": str(attempt["status"]),
        },
        "retryPolicy": "new_execution_with_retryOf_failed_objects_only",
    }


def validate_review_interruption_reconciliation_receipt(
    path: Path,
    *,
    output_root: Path | None = None,
) -> dict[str, Any]:
    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    payload = _read_object(path, label="review interruption reconciliation receipt")
    assert_valid(
        payload,
        "execution",
        "campaign_review_interruption_reconciliation_receipt",
    )
    stable = {key: value for key, value in payload.items() if key != "receiptDigest"}
    if payload.get("receiptDigest") != canonical_digest(stable):
        raise ValueError("review interruption receipt digest drift")
    expected_path = review_interruption_receipt_path(
        str(payload["rootExecutionId"]),
        str(payload["objectRef"]),
        output_root=resolved_output,
    )
    if path.resolve() != expected_path.resolve():
        raise ValueError("review interruption receipt path drift")
    expected = _derive_receipt(
        str(payload["rootExecutionId"]),
        str(payload["executionId"]),
        str(payload["objectRef"]),
        output_root=resolved_output,
    )
    expected["recordedAt"] = payload["recordedAt"]
    expected["receiptDigest"] = canonical_digest(expected)
    if payload != expected:
        raise ValueError("review interruption receipt evidence drift")
    # Resolve every embedded file ref again so a same-shaped ref cannot point
    # outside the governed output root.
    for evidence in (
        payload["campaignEvidence"]["plan"],
        payload["campaignEvidence"]["report"],
        payload["campaignEvidence"]["claim"],
        payload["campaignEvidence"]["capsule"]["manifest"],
        payload["executionEvidence"]["manifest"],
        payload["executionEvidence"]["state"],
        payload["executionEvidence"]["objectIndex"],
        payload["executionEvidence"]["pendingResponse"],
        payload["semanticEvidence"]["request"],
        payload["semanticEvidence"]["attempt"],
    ):
        evidence_path = resolve_ref(
            evidence["ref"],
            output_root=resolved_output,
            label="review interruption evidence",
        )
        if file_digest(evidence_path) != evidence["sha256"]:
            raise ValueError("review interruption evidence digest drift")
    return payload


def reconcile_interrupted_post_review(
    root_execution_id: str,
    execution_id: str,
    object_ref: str,
    *,
    output_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Write or return the exact create-once interruption receipt."""

    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    path = review_interruption_receipt_path(
        root_execution_id,
        object_ref,
        output_root=resolved_output,
    )
    with _lock(path):
        if path.is_file():
            return (
                validate_review_interruption_reconciliation_receipt(
                    path,
                    output_root=resolved_output,
                ),
                path,
            )
        stable = _derive_receipt(
            root_execution_id,
            execution_id,
            object_ref,
            output_root=resolved_output,
        )
        stable["recordedAt"] = _now()
        receipt = {**stable, "receiptDigest": canonical_digest(stable)}
        assert_valid(
            receipt,
            "execution",
            "campaign_review_interruption_reconciliation_receipt",
        )
        write_json(path, receipt)
    return (
        validate_review_interruption_reconciliation_receipt(
            path,
            output_root=resolved_output,
        ),
        path,
    )


__all__ = [
    "reconcile_interrupted_post_review",
    "review_interruption_receipt_path",
    "validate_review_interruption_reconciliation_receipt",
]
