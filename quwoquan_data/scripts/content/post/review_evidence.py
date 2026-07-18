"""Write the canonical review evidence set for one materialized content object."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from content.execution.runtime_contract import canonical_sha256
from core.io import read_json, write_json
from core.schema import assert_valid


def write_review_evidence(
    review_dir: Path,
    *,
    execution: Mapping[str, str],
    object_ref: str,
    review_payload: Mapping[str, Any],
) -> None:
    issues = [str(issue) for issue in (review_payload.get("issues") or [])]
    passed = str(review_payload.get("decision") or "") == "approved" and not issues
    reviewer_run_id = str(review_payload.get("runId") or f"review_{object_ref}")
    reviewer_model = str(review_payload.get("model") or "deterministic")
    reviewer_family = str(review_payload.get("modelFamily") or "deterministic")
    reviewer_result = {
        "schema": "quwoquan_data.reviewer_result",
        "stage": "5.review",
        **execution,
        "objectRef": object_ref,
        "provider": str(review_payload.get("provider") or "review_controller"),
        "model": reviewer_model,
        "modelFamily": reviewer_family,
        "runId": reviewer_run_id,
        "verdict": "passed" if passed else "failed",
        "issues": issues,
        "resultHash": canonical_sha256(review_payload),
    }
    deterministic_gate = {
        "schema": "quwoquan_data.deterministic_gate",
        "stage": "5.review",
        **execution,
        "objectRef": object_ref,
        "passed": passed,
        "issues": issues,
        "checks": list(review_payload.get("checks") or []),
    }
    media_ref_review = {
        "schema": "quwoquan_data.media_ref_review",
        "stage": "5.review",
        **execution,
        "objectRef": object_ref,
        "passed": passed,
        "mediaIssues": [issue for issue in issues if "image" in issue.lower() or "media" in issue.lower()],
        "referenceIssues": [issue for issue in issues if "source" in issue.lower() or "ref" in issue.lower()],
    }
    evidence_names = (
        "deterministic_gate.json",
        "reviewer_result.json",
        "media_ref_review.json",
        "provenance.json",
        "finalization_report.json",
    )
    assert_valid(
        reviewer_result,
        "content",
        "reviewer_result",
        label=f"reviewer_result:{object_ref}",
    )
    write_json(review_dir / evidence_names[0], deterministic_gate)
    write_json(review_dir / evidence_names[1], reviewer_result)
    write_json(review_dir / evidence_names[2], media_ref_review)
    write_json(
        review_dir / "evidence_index.json",
        {
            "schema": "quwoquan_data.evidence_index",
            "stage": "5.review",
            **execution,
            "objectRef": object_ref,
            "evidence": [
                {
                    "kind": "runtime_review",
                    "ref": f"5.review/{name}",
                    "sha256": canonical_sha256(read_json(review_dir / name)),
                }
                for name in evidence_names
            ],
        },
    )
    attestation = {
            "schema": "quwoquan_data.review_attestation",
            "stage": "5.review",
            **execution,
            "objectRef": object_ref,
            "decision": "approved" if passed else "revision_needed",
            "deterministicGate": {
                "status": "passed" if passed else "failed",
                "issues": deterministic_gate["issues"],
            },
            "independentReviewer": {
                "status": reviewer_result["verdict"],
                "provider": reviewer_result["provider"],
                "model": reviewer_result["model"],
                "modelFamily": reviewer_result["modelFamily"],
                "runId": reviewer_run_id,
                "resultHash": reviewer_result["resultHash"],
            },
            "mediaRefReview": {
                "status": "passed" if passed else "failed",
                "issues": [
                    *media_ref_review["mediaIssues"],
                    *media_ref_review["referenceIssues"],
                ],
            },
            "repair": {"status": "not_required" if passed else "pending"},
            "finalizationRef": "5.review/finalization_report.json",
            "evidenceIndexRef": "5.review/evidence_index.json",
    }
    assert_valid(
        attestation,
        "content",
        "review_attestation",
        label=f"review_attestation:{object_ref}",
    )
    write_json(review_dir / "attestation.json", attestation)
