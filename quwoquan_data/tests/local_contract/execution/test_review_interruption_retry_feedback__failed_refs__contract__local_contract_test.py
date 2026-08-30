# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""Retry review feedback admits failed predecessor objects only.

`REQ-001` states that a new `retryOf` must consume both the create-once
interruption reconciliation receipt and the already-bound final reviewer results
of the remaining objects, must take only the failed refs into scope, and must
inject the typed issues into the rewritten objects of those entities; a
predecessor object that was already qualified must not enter the retry scope.
Coverage is therefore complete only when every planned object has either a bound
final independent review or a validated interruption receipt — a deterministic
reviewer projection or a bare pending file is not final review evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from content.execution.campaign.submission_reconciliation_contract import (
    canonical_digest,
    file_digest,
)
from content.execution.planning.retry_review_feedback import (
    load_retry_review_feedback_source,
    validate_retry_review_feedback,
)
from core.io import write_json

PREDECESSOR_ID = "20260728--travel-article-workload-article-1--china--scale-001"
SUCCESSOR_ID = "20260728--travel-article-workload-article-1--china--scale-002"
ENTITIES = {
    "article/攻略/都江堰/1": ("/entity/china/sichuan/dujiangyan", "dujiangyan"),
    "article/攻略/青城山/1": ("/entity/china/sichuan/qingchengshan", "qingchengshan"),
    "article/攻略/峨眉山/1": ("/entity/china/sichuan/emeishan", "emeishan"),
}
REVIEWER = {
    "provider": "cursor_sdk",
    "model": "grok-code-fast-1",
    "modelFamily": "grok",
}


def _object_dir(root: Path, object_ref: str) -> Path:
    content_type, angle, title, seq = object_ref.split("/")
    return root / "posts" / content_type / angle / title / seq


def _write_review(
    root: Path,
    object_ref: str,
    *,
    verdict: str,
    result_overrides: dict[str, Any] | None = None,
    attestation_overrides: dict[str, Any] | None = None,
    evidence_kind: str = "independent_reviewer_result",
    evidence_sha_override: str | None = None,
    write_evidence: bool = True,
) -> None:
    review_dir = _object_dir(root, object_ref) / "5.review"
    passed = verdict == "passed"
    run_id = f"review-run-{object_ref.rsplit('/', 2)[1]}"
    result_hash = "sha256:" + f"{abs(hash(object_ref)) % (10 ** 8):08d}".ljust(64, "0")
    result: dict[str, Any] = {
        "schema": "quwoquan_data.reviewer_result",
        "stage": "5.review",
        "executionId": PREDECESSOR_ID,
        "executionBinding": "frozen",
        "objectRef": object_ref,
        **REVIEWER,
        "runId": run_id,
        "verdict": verdict,
        "issues": [] if passed else ["正文未锚定到本实体"],
        "findings": [] if passed else ["标题与正文实体不一致"],
        "resultHash": result_hash,
    }
    result.update(result_overrides or {})
    result_path = review_dir / "reviewer_result.json"
    write_json(result_path, result)

    attestation: dict[str, Any] = {
        "schema": "quwoquan_data.review_attestation",
        "stage": "5.review",
        "executionId": PREDECESSOR_ID,
        "executionBinding": "frozen",
        "objectRef": object_ref,
        "decision": "approved" if passed else "revision_needed",
        "deterministicGate": {"status": "passed", "issues": []},
        "independentReviewer": {
            "status": "passed" if passed else "failed",
            **REVIEWER,
            "runId": result["runId"],
            "resultHash": result["resultHash"],
        },
        "mediaRefReview": {"status": "passed", "issues": []},
        "repair": {"status": "not_required" if passed else "pending"},
        "finalizationRef": "5.review/finalization.json",
        "evidenceIndexRef": "5.review/evidence_index.json",
    }
    for key, value in (attestation_overrides or {}).items():
        if isinstance(value, dict) and isinstance(attestation.get(key), dict):
            attestation[key] = {**attestation[key], **value}
        else:
            attestation[key] = value
    write_json(review_dir / "attestation.json", attestation)

    if not write_evidence:
        return
    write_json(
        review_dir / "evidence_index.json",
        {
            "schema": "quwoquan_data.evidence_index",
            "stage": "5.review",
            "executionId": PREDECESSOR_ID,
            "executionBinding": "frozen",
            "objectRef": object_ref,
            "evidence": [
                {
                    "kind": evidence_kind,
                    "ref": "5.review/reviewer_result.json",
                    "sha256": evidence_sha_override or file_digest(result_path),
                }
            ],
        },
    )


def _predecessor_root(
    tmp_path: Path,
    *,
    verdicts: dict[str, str],
    plan_refs: tuple[str, ...] | None = None,
    index_refs: tuple[str, ...] | None = None,
    **review_kwargs: Any,
) -> Path:
    root = tmp_path / "output" / "data" / "tasks" / PREDECESSOR_ID
    planned = plan_refs if plan_refs is not None else tuple(verdicts)
    indexed = index_refs if index_refs is not None else tuple(verdicts)
    write_json(
        root / "_shared/content_plan_packet.json",
        {
            "executionId": PREDECESSOR_ID,
            "items": [
                {"ref": ref, "entityRefs": [ENTITIES[ref][0]]} for ref in planned
            ],
        },
    )
    write_json(
        root / "_shared/content_object_index.json",
        {
            "schema": "quwoquan_data.content_object_index",
            "refs": {
                ref: {
                    "contentType": ref.split("/")[0],
                    "angle": ref.split("/")[1],
                    "title": ref.split("/")[2],
                    "seq": ref.split("/")[3],
                }
                for ref in indexed
            },
        },
    )
    for ref, verdict in verdicts.items():
        _write_review(root, ref, verdict=verdict, **review_kwargs)
    return root


def _load(root: Path, **kwargs: Any):
    return load_retry_review_feedback_source(
        root,
        predecessor_execution_id=PREDECESSOR_ID,
        **kwargs,
    )


def test_only_failed_predecessor_objects_enter_the_retry_scope(
    tmp_path: Path,
) -> None:
    """A predecessor object that already qualified must stay out of scope."""

    root = _predecessor_root(
        tmp_path,
        verdicts={
            "article/攻略/都江堰/1": "failed",
            "article/攻略/青城山/1": "passed",
            "article/攻略/峨眉山/1": "failed",
        },
    )

    source = _load(root)

    assert source.object_refs == ("article/攻略/都江堰/1", "article/攻略/峨眉山/1")
    assert "article/攻略/青城山/1" not in source.object_refs
    assert source.predecessor_execution_id == PREDECESSOR_ID


def test_each_failed_ref_carries_its_own_entity_and_target_identity(
    tmp_path: Path,
) -> None:
    """Typed issues are injected into the rewritten object of that entity."""

    root = _predecessor_root(
        tmp_path,
        verdicts={
            "article/攻略/都江堰/1": "failed",
            "article/攻略/青城山/1": "passed",
        },
    )

    source = _load(root)

    assert source.entity_refs == (ENTITIES["article/攻略/都江堰/1"][0],)
    assert source.target_names == (ENTITIES["article/攻略/都江堰/1"][1],)
    assert len(source.items) == 1
    item = source.items[0]
    assert item["predecessorObjectRef"] == "article/攻略/都江堰/1"
    assert item["decision"] == "revision_needed"
    assert item["issues"] == ["正文未锚定到本实体"]
    assert item["evidenceKind"] == "final_reviewer_result"
    assert item["evidenceRef"].startswith("data/tasks/")
    assert item["reviewer"]["modelFamily"] == "grok"


def test_a_fully_qualified_predecessor_has_no_retry_scope(tmp_path: Path) -> None:
    """A retry needs at least one failed object; it is not a blanket rerun."""

    root = _predecessor_root(
        tmp_path,
        verdicts={
            "article/攻略/都江堰/1": "passed",
            "article/攻略/青城山/1": "passed",
        },
    )

    with pytest.raises(ValueError, match="no failed final-review objects"):
        _load(root)


def test_required_refs_must_exactly_match_the_derived_failed_refs(
    tmp_path: Path,
) -> None:
    """The declared retry scope is verified against predecessor evidence."""

    root = _predecessor_root(
        tmp_path,
        verdicts={
            "article/攻略/都江堰/1": "failed",
            "article/攻略/青城山/1": "passed",
            "article/攻略/峨眉山/1": "failed",
        },
    )

    source = _load(
        root,
        required_object_refs=["article/攻略/都江堰/1", "article/攻略/峨眉山/1"],
    )

    assert source.object_refs == ("article/攻略/都江堰/1", "article/攻略/峨眉山/1")


def test_a_qualified_ref_may_not_be_declared_in_the_retry_scope(
    tmp_path: Path,
) -> None:
    """Declaring a qualified object would rewrite an approved object."""

    root = _predecessor_root(
        tmp_path,
        verdicts={
            "article/攻略/都江堰/1": "failed",
            "article/攻略/青城山/1": "passed",
        },
    )

    with pytest.raises(ValueError, match="must exactly match predecessor failed"):
        _load(
            root,
            required_object_refs=[
                "article/攻略/都江堰/1",
                "article/攻略/青城山/1",
            ],
        )


def test_a_partial_declared_retry_scope_fails_closed(tmp_path: Path) -> None:
    """Dropping a failed object would silently abandon its shortfall."""

    root = _predecessor_root(
        tmp_path,
        verdicts={
            "article/攻略/都江堰/1": "failed",
            "article/攻略/峨眉山/1": "failed",
        },
    )

    with pytest.raises(ValueError, match="must exactly match predecessor failed"):
        _load(root, required_object_refs=["article/攻略/都江堰/1"])


def test_a_reordered_declared_retry_scope_fails_closed(tmp_path: Path) -> None:
    """Scope order follows the frozen predecessor plan, not the caller."""

    root = _predecessor_root(
        tmp_path,
        verdicts={
            "article/攻略/都江堰/1": "failed",
            "article/攻略/峨眉山/1": "failed",
        },
    )

    with pytest.raises(ValueError, match="must exactly match predecessor failed"):
        _load(
            root,
            required_object_refs=[
                "article/攻略/峨眉山/1",
                "article/攻略/都江堰/1",
            ],
        )


def test_a_repeated_declared_ref_fails_closed(tmp_path: Path) -> None:
    """One failed object is rewritten once."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
    )

    with pytest.raises(ValueError, match="must exactly match predecessor failed"):
        _load(
            root,
            required_object_refs=[
                "article/攻略/都江堰/1",
                "article/攻略/都江堰/1",
            ],
        )


def test_an_object_without_final_review_evidence_blocks_the_retry(
    tmp_path: Path,
) -> None:
    """Incomplete coverage must fail closed instead of narrowing the scope."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
    )
    _write_review(
        root,
        "article/攻略/青城山/1",
        verdict="failed",
        write_evidence=False,
    )
    write_json(
        root / "_shared/content_plan_packet.json",
        {
            "executionId": PREDECESSOR_ID,
            "items": [
                {"ref": ref, "entityRefs": [ENTITIES[ref][0]]}
                for ref in ("article/攻略/都江堰/1", "article/攻略/青城山/1")
            ],
        },
    )
    write_json(
        root / "_shared/content_object_index.json",
        {
            "schema": "quwoquan_data.content_object_index",
            "refs": {
                ref: {
                    "contentType": ref.split("/")[0],
                    "angle": ref.split("/")[1],
                    "title": ref.split("/")[2],
                    "seq": ref.split("/")[3],
                }
                for ref in ("article/攻略/都江堰/1", "article/攻略/青城山/1")
            },
        },
    )

    with pytest.raises(ValueError, match="final review coverage is incomplete"):
        _load(root)


def test_a_deterministic_projection_is_not_final_review_evidence(
    tmp_path: Path,
) -> None:
    """Only an `independent_reviewer_result` row binds a final review."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
        evidence_kind="deterministic_reviewer_projection",
    )

    with pytest.raises(ValueError, match="final review coverage is incomplete"):
        _load(root)


def test_reviewer_result_byte_drift_is_not_final_review_evidence(
    tmp_path: Path,
) -> None:
    """The bound evidence digest must still match the reviewer result bytes."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
        evidence_sha_override="sha256:" + "0" * 64,
    )

    with pytest.raises(ValueError, match="final review coverage is incomplete"):
        _load(root)


def test_independent_reviewer_binding_drift_fails_closed(tmp_path: Path) -> None:
    """The attestation must name the exact reviewer run that produced it."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
        attestation_overrides={"independentReviewer": {"runId": "other-run"}},
    )

    with pytest.raises(ValueError, match="independent reviewer runId drift"):
        _load(root)


def test_a_failed_review_without_a_pending_repair_fails_closed(
    tmp_path: Path,
) -> None:
    """A failed verdict and a closed repair contradict each other."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
        attestation_overrides={"repair": {"status": "completed"}},
    )

    with pytest.raises(ValueError, match="failed review closure drift"):
        _load(root)


def test_a_failed_review_without_typed_issues_fails_closed(tmp_path: Path) -> None:
    """A failed object must carry the typed issues the retry will inject."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
        result_overrides={"issues": []},
    )

    with pytest.raises(ValueError, match="failed review closure drift"):
        _load(root)


def test_a_passed_review_with_a_revision_decision_fails_closed(
    tmp_path: Path,
) -> None:
    """A passed verdict may not be paired with a revision decision."""

    root = _predecessor_root(
        tmp_path,
        verdicts={
            "article/攻略/都江堰/1": "failed",
            "article/攻略/青城山/1": "passed",
        },
    )
    _write_review(
        root,
        "article/攻略/青城山/1",
        verdict="passed",
        attestation_overrides={"decision": "revision_needed"},
    )

    with pytest.raises(ValueError, match="passed review closure drift"):
        _load(root)


def test_plan_and_object_index_coverage_drift_fails_closed(tmp_path: Path) -> None:
    """Both faces of the frozen predecessor closure must agree exactly."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
        plan_refs=("article/攻略/都江堰/1", "article/攻略/青城山/1"),
        index_refs=("article/攻略/都江堰/1",),
    )

    with pytest.raises(ValueError, match="plan/object index coverage drift"):
        _load(root)


def test_a_predecessor_root_that_is_not_the_execution_fails_closed(
    tmp_path: Path,
) -> None:
    """The retry binds one named predecessor execution root."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
    )

    with pytest.raises(ValueError, match="predecessor execution root is unavailable"):
        _load(root.parent)


def test_a_plan_item_without_exactly_one_entity_ref_fails_closed(
    tmp_path: Path,
) -> None:
    """One object rewrite targets exactly one entity."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
    )
    write_json(
        root / "_shared/content_plan_packet.json",
        {
            "executionId": PREDECESSOR_ID,
            "items": [
                {
                    "ref": "article/攻略/都江堰/1",
                    "entityRefs": [
                        ENTITIES["article/攻略/都江堰/1"][0],
                        ENTITIES["article/攻略/青城山/1"][0],
                    ],
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="requires one entityRef"):
        _load(root)


def test_the_retry_feedback_document_binds_a_later_successor_sequence(
    tmp_path: Path,
) -> None:
    """The successor must be a later sequence inside the same frozen scope."""

    root = _predecessor_root(
        tmp_path,
        verdicts={
            "article/攻略/都江堰/1": "failed",
            "article/攻略/青城山/1": "passed",
        },
    )
    source = _load(root)

    document = source.to_document(SUCCESSOR_ID)

    assert document["executionId"] == SUCCESSOR_ID
    assert document["retryOf"] == PREDECESSOR_ID
    assert document["failedObjectRefs"] == ["article/攻略/都江堰/1"]
    assert validate_retry_review_feedback(document) == document


def test_the_successor_may_not_reuse_the_predecessor_sequence(
    tmp_path: Path,
) -> None:
    """A `retryOf` is always a new execution sequence."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
    )
    source = _load(root)

    with pytest.raises(ValueError, match="later sequence in the same scope"):
        source.to_document(PREDECESSOR_ID)


def test_the_successor_may_not_change_the_carrier(tmp_path: Path) -> None:
    """The retry stays in the same lane as the predecessor."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
    )
    source = _load(root)

    with pytest.raises(ValueError, match="later sequence in the same scope"):
        source.to_document(
            "20260728--travel-image-workload-image-1--china--scale-002"
        )


def test_feedback_digest_drift_fails_closed(tmp_path: Path) -> None:
    """The feedback document is replayable only through its own digest."""

    root = _predecessor_root(
        tmp_path,
        verdicts={"article/攻略/都江堰/1": "failed"},
    )
    document = _load(root).to_document(SUCCESSOR_ID)
    document["feedbackDigest"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="feedback digest drift"):
        validate_retry_review_feedback(document)


def test_feedback_item_scope_drift_fails_closed(tmp_path: Path) -> None:
    """`failedObjectRefs` and the item order must stay one single truth."""

    root = _predecessor_root(
        tmp_path,
        verdicts={
            "article/攻略/都江堰/1": "failed",
            "article/攻略/峨眉山/1": "failed",
        },
    )
    document = _load(root).to_document(SUCCESSOR_ID)
    document["failedObjectRefs"] = list(reversed(document["failedObjectRefs"]))
    resealed = {key: value for key, value in document.items() if key != "feedbackDigest"}
    document["feedbackDigest"] = canonical_digest(resealed)

    with pytest.raises(ValueError, match="item order/scope drift"):
        validate_retry_review_feedback(document)
