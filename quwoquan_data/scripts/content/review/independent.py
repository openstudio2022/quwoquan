"""Bind an independent Cursor reviewer result to one post review package."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from content.execution.runtime_contract import canonical_sha256, file_sha256
from core.io import read_json, write_json
from core.schema import assert_valid


def apply_independent_post_review(
    *,
    review_dir: Path,
    provider: str,
    model: str,
    model_family: str,
    run_id: str,
    result_payload: dict[str, Any],
) -> list[str]:
    """Replace deterministic reviewer projection with bound independent evidence."""
    attestation_path = review_dir / "attestation.json"
    evidence_index_path = review_dir / "evidence_index.json"
    review_path = review_dir / "review.json"
    required = (attestation_path, evidence_index_path, review_path)
    if any(not path.is_file() for path in required):
        return [f"{review_dir}: deterministic review evidence is incomplete"]
    try:
        assert_valid(
            result_payload,
            "content",
            "post_reviewer_response",
            label=f"post_reviewer_response:{review_dir}",
        )
    except ValueError as exc:
        return [str(exc)]
    normalized_run_id = run_id.strip()
    if not normalized_run_id or normalized_run_id.startswith("contract-output:"):
        return [f"{review_dir}: independent reviewer must bind a real Cursor SDK runId"]
    decision = str(result_payload.get("decision") or "")
    issues = [
        str(item).strip()
        for item in result_payload.get("issues") or []
        if str(item).strip()
    ]
    findings = [
        str(item).strip()
        for item in result_payload.get("findings") or []
        if str(item).strip()
    ]
    passed = decision == "approved" and not issues
    reviewer_result = {
        "schema": "quwoquan_data.reviewer_result",
        "stage": "5.review",
        "executionId": str(result_payload.get("executionId") or ""),
        "executionBinding": "frozen",
        "objectRef": str(result_payload.get("objectRef") or ""),
        "provider": provider,
        "model": model,
        "modelFamily": model_family,
        "runId": normalized_run_id,
        "verdict": "passed" if passed else "failed",
        "issues": issues,
        "findings": findings,
        "resultHash": canonical_sha256(result_payload),
    }
    attestation = read_json(attestation_path)
    attestation["decision"] = "approved" if passed else decision
    attestation["independentReviewer"] = {
        "status": reviewer_result["verdict"],
        "provider": provider,
        "model": model,
        "modelFamily": model_family,
        "runId": normalized_run_id,
        "resultHash": reviewer_result["resultHash"],
    }
    attestation["repair"] = {"status": "not_required" if passed else "pending"}
    try:
        assert_valid(
            reviewer_result,
            "content",
            "reviewer_result",
            label=f"reviewer_result:{review_dir}",
        )
        assert_valid(
            attestation,
            "content",
            "review_attestation",
            label=f"review_attestation:{review_dir}",
        )
    except ValueError as exc:
        return [str(exc)]
    write_json(review_dir / "reviewer_result.json", reviewer_result)
    write_json(attestation_path, attestation)
    evidence_index = read_json(evidence_index_path)
    evidence = [
        item
        for item in evidence_index.get("evidence") or []
        if isinstance(item, dict)
        and str(item.get("ref") or "") != "5.review/reviewer_result.json"
    ]
    evidence.append(
        {
            "kind": "independent_reviewer_result",
            "ref": "5.review/reviewer_result.json",
            "sha256": file_sha256(review_dir / "reviewer_result.json"),
        }
    )
    evidence_index["evidence"] = evidence
    try:
        assert_valid(
            evidence_index,
            "content",
            "evidence_index",
            label=f"evidence_index:{review_dir}",
        )
    except ValueError as exc:
        return [str(exc)]
    write_json(evidence_index_path, evidence_index)
    return [] if passed else issues or [f"{review_dir}: independent review {decision}"]


__all__ = ["apply_independent_post_review"]
