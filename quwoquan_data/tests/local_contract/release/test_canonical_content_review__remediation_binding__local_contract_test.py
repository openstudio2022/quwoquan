# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#req-005
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-005
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#req-002
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.review_rights_binding import validate_content_review_document
from core.schema import assert_valid

D = "sha256:" + "1" * 64
P = {"schemaVersion": "1.0.0", "dialectVersion": "1.0.0", "canonicalizationVersion": "1.0.0"}
R = {"contentRevision": 2, "sourceRevision": 2, "layoutRevision": 2}
AUTHOR = {"host": "cursor", "modelFamily": "GPT-5", "sessionId": "author", "invocation": {"provider": "openai", "model": "GPT", "runId": "author-run"}}
REVIEWER = {"host": "cursor", "modelFamily": "GPT-5", "sessionId": "reviewer", "invocation": {"provider": "openai", "model": "GPT", "runId": "reviewer-run"}}


def _binding(path: Path, root: Path) -> dict[str, str]:
    return {"ref": path.relative_to(root).as_posix(), "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()}


def _review(root: Path, *, origin: str = "immutable_remediation_artifact") -> dict:
    candidate = root / "candidate"; candidate.mkdir(parents=True)
    page = candidate / "page.md"; page.write_text("# page\n")
    manifest = candidate / "manifest.json"; manifest.write_text("{}\n")
    semantic = candidate / "semantic.document.json"; semantic.write_text("{}\n")
    return {
        "schema": "quwoquan_data.content_review", "stage": "5.review", "executionId": "remediation-a3",
        "objectRef": "entities/travel/beijing/entity-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "objectIdentity": {"entityId": "entity-temple-of-emperors", "entityRef": "/entity/travel/beijing/temple-of-emperors"},
        "decision": "rejected", "author": AUTHOR, "reviewer": REVIEWER,
        "candidateBindings": {"origin": origin, "page": _binding(page, root),
                              "manifest": _binding(manifest, root) if origin == "immutable_remediation_artifact" else None,
                              "semanticDocument": _binding(semantic, root) if origin == "immutable_remediation_artifact" else None},
        "dimensions": [{"name": "content", "decision": "rejected", "issues": ["test"]}],
        "blockingIssues": ["test"], "assetRights": [], "protocol": P, "objectRevision": R,
        "dispositions": [{"issueId": "i", "objectRef": "same", "sourceDigest": D, "targetDigest": D,
            "detectedType": "TEST", "proposedMapping": None, "lossFields": [], "severity": "error",
            "actor": {"actorId": "reviewer", "actorType": "independent_reviewer"}, "reason": "test",
            "policyVersion": "1.0.0", "reviewStatus": "reviewed_rejected", "outcome": "definitive_reject",
            "processingDisposition": "blocked_unsafe", "protocol": P, "objectRevision": R}],
    }


def test_deep_locator_and_immutable_three_digest_bindings(tmp_path: Path) -> None:
    review = _review(tmp_path)
    assert_valid(review, "content", "content_review")
    validate_content_review_document(review, execution_id="remediation-a3", object_ref=review["objectRef"],
                                     required_asset_refs=(), candidate_root=tmp_path)


def test_path_traversal_and_absolute_candidate_refs_are_rejected(tmp_path: Path) -> None:
    review = _review(tmp_path)
    for ref in ("../page.md", "/tmp/page.md", "candidate//page.md"):
        review["candidateBindings"]["page"]["ref"] = ref
        with pytest.raises((ValueError, ObjectTransactionError)):
            assert_valid(review, "content", "content_review")
            validate_content_review_document(review, execution_id="remediation-a3", object_ref=review["objectRef"], required_asset_refs=(), candidate_root=tmp_path)


def test_execution_draft_and_reviewer_independence(tmp_path: Path) -> None:
    review = _review(tmp_path, origin="execution_draft")
    review["candidateBindings"]["page"]["ref"] = "4.draft/page.md"
    path = tmp_path / "4.draft/page.md"; path.parent.mkdir(); path.write_text("# page\n")
    review["candidateBindings"]["page"]["digest"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert_valid(review, "content", "content_review")
    review["reviewer"] = AUTHOR
    with pytest.raises(ObjectTransactionError, match="reviewer-author conflict"):
        validate_content_review_document(review, execution_id="remediation-a3", object_ref=review["objectRef"], required_asset_refs=(), candidate_root=tmp_path)


def test_digest_drift_and_approved_non_auto_disposition_are_rejected(tmp_path: Path) -> None:
    review = _review(tmp_path)
    review["candidateBindings"]["manifest"]["digest"] = D
    with pytest.raises(ObjectTransactionError, match="binding drift"):
        validate_content_review_document(review, execution_id="remediation-a3", object_ref=review["objectRef"], required_asset_refs=(), candidate_root=tmp_path)
    review = _review(tmp_path / "other")
    review["decision"] = "approved"; review["blockingIssues"] = []; review["dimensions"] = [{"name":"content","decision":"approved","issues":[]}]
    with pytest.raises(ValueError):
        assert_valid(review, "content", "content_review")
