"""In-place resume continues unfinished work without rewriting evidence.

The boundary under test: a finished object's evidence is never re-entered, an
unfinished object may append inside the same execution, and a drifted identity
still forces a new ``retryOf`` sequence. Attempt budgets widen only through an
append-only grant that names its cause and its owner.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.execution.agent.semantic_task_journal import (
    SemanticTaskRecoveryReason,
    grant_semantic_task_attempts,
    granted_extra_attempts,
    recovery_grants_root,
)
from content.execution.planning.resume_admission import (
    ResumeAdmission,
    ResumeBlocker,
    ResumeDisposition,
    admit_in_place_resume,
)

_REQUEST = {
    "workUnitId": "sha256:" + "a" * 64,
    "requestDigest": "sha256:" + "d" * 64,
    "maxAttempts": 2,
}


def test_unfinished_objects_resume_while_finished_objects_stay_untouched() -> None:
    admission = admit_in_place_resume(
        execution_id="exec-1",
        object_refs=("obj-a", "obj-b", "obj-c"),
        finished_refs=("obj-a",),
    )

    assert admission.admitted is True
    assert admission.finished_refs == ("obj-a",)
    assert admission.resumable_refs == ("obj-b", "obj-c")
    finished = next(
        row for row in admission.decisions if row.object_ref == "obj-a"
    )
    assert finished.disposition is ResumeDisposition.FINISHED_IMMUTABLE


def test_a_fully_finished_execution_has_nothing_to_resume() -> None:
    admission = admit_in_place_resume(
        execution_id="exec-1",
        object_refs=("obj-a",),
        finished_refs=("obj-a",),
    )

    assert admission.admitted is True
    assert admission.resumable_refs == ()


@pytest.mark.parametrize(
    ("drift", "blocker"),
    [
        ({"runtimeProfile": True}, ResumeBlocker.RUNTIME_PROFILE_DRIFT),
        ({"semanticBinding": True}, ResumeBlocker.SEMANTIC_BINDING_DRIFT),
    ],
)
def test_identity_drift_forces_a_new_retry_of_sequence(
    drift: dict[str, bool], blocker: ResumeBlocker
) -> None:
    admission = admit_in_place_resume(
        execution_id="exec-1",
        object_refs=("obj-a", "obj-b"),
        finished_refs=("obj-a",),
        identity_drift=drift,
    )

    assert admission.admitted is False
    assert admission.blocker is blocker
    # Even when resume is refused, finished evidence keeps its disposition: the
    # successor execution must not re-produce it.
    assert admission.finished_refs == ("obj-a",)
    assert admission.resumable_refs == ()
    assert all(
        row.disposition is ResumeDisposition.REQUIRES_NEW_RETRY_OF
        for row in admission.decisions
        if row.object_ref == "obj-b"
    )


def test_a_superseded_execution_is_never_resumed_in_place() -> None:
    admission = admit_in_place_resume(
        execution_id="exec-1",
        object_refs=("obj-a",),
        finished_refs=(),
        superseded_by="exec-2",
    )

    assert admission.blocker is ResumeBlocker.SUPERSEDED_EXECUTION
    assert "exec-2" in admission.blocker_reason
    assert admission.resumable_refs == ()


def test_supersession_outranks_identity_drift() -> None:
    admission = admit_in_place_resume(
        execution_id="exec-1",
        object_refs=("obj-a",),
        finished_refs=(),
        identity_drift={"runtimeProfile": True},
        superseded_by="exec-2",
    )

    assert admission.blocker is ResumeBlocker.SUPERSEDED_EXECUTION


def test_a_finished_ref_outside_the_frozen_object_set_is_a_failure() -> None:
    with pytest.raises(ValueError):
        admit_in_place_resume(
            execution_id="exec-1",
            object_refs=("obj-a",),
            finished_refs=("obj-a", "obj-ghost"),
        )


@pytest.mark.parametrize("object_refs", [("obj-a", "obj-a"), ("obj-a", "  ")])
def test_a_malformed_object_set_is_a_failure_not_a_partial_resume(
    object_refs: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        admit_in_place_resume(
            execution_id="exec-1",
            object_refs=object_refs,
            finished_refs=(),
        )


def test_a_blocker_without_its_reason_cannot_be_constructed() -> None:
    with pytest.raises(ValueError):
        ResumeAdmission(
            execution_id="exec-1",
            decisions=(),
            blocker=ResumeBlocker.SUPERSEDED_EXECUTION,
        )


def test_attempt_grant_appends_and_widens_the_budget(tmp_path: Path) -> None:
    journal_root = tmp_path / "journal"
    journal_root.mkdir()

    assert granted_extra_attempts(journal_root, request_digest=_REQUEST["requestDigest"]) == 0

    path = grant_semantic_task_attempts(
        journal_root,
        request=_REQUEST,
        grant=2,
        reason=SemanticTaskRecoveryReason.PROVIDER_QUOTA_EXHAUSTED,
        granted_by="operator/line-b",
    )
    document = json.loads(path.read_text(encoding="utf-8"))

    assert document["grant"] == 2
    assert document["grantedAttempts"] == 4
    assert document["reason"] == "provider_quota_exhausted"
    assert document["grantedBy"] == "operator/line-b"
    assert granted_extra_attempts(
        journal_root, request_digest=_REQUEST["requestDigest"]
    ) == 2


def test_successive_grants_accumulate_without_rewriting_the_first(
    tmp_path: Path,
) -> None:
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    first = grant_semantic_task_attempts(
        journal_root,
        request=_REQUEST,
        grant=1,
        reason=SemanticTaskRecoveryReason.TRANSPORT_UNAVAILABLE,
        granted_by="operator/line-b",
    )
    before = first.read_text(encoding="utf-8")

    grant_semantic_task_attempts(
        journal_root,
        request=_REQUEST,
        grant=3,
        reason=SemanticTaskRecoveryReason.INFRASTRUCTURE_INTERRUPTION,
        granted_by="operator/line-b",
    )

    assert first.read_text(encoding="utf-8") == before
    assert len(sorted(recovery_grants_root(journal_root).glob("*.json"))) == 2
    assert granted_extra_attempts(
        journal_root, request_digest=_REQUEST["requestDigest"]
    ) == 4


def test_a_grant_never_reopens_a_work_unit_that_already_succeeded(
    tmp_path: Path,
) -> None:
    journal_root = tmp_path / "journal"
    attempts = journal_root / "attempts"
    attempts.mkdir(parents=True)
    (attempts / "0001.json").write_text(
        json.dumps({"attempt": 1, "status": "succeeded"}), encoding="utf-8"
    )

    with pytest.raises(ValueError):
        grant_semantic_task_attempts(
            journal_root,
            request=_REQUEST,
            grant=1,
            reason=SemanticTaskRecoveryReason.OPERATOR_DISPOSITION,
            granted_by="operator/line-b",
        )


def test_a_grant_bound_to_another_request_is_a_failure_not_a_silent_zero(
    tmp_path: Path,
) -> None:
    # One journal root is one frozen work unit. A grant for a different digest
    # sitting in it means the evidence is mismatched, and reading that as "no
    # extra attempts" would let a foreign grant pass unnoticed.
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    grant_semantic_task_attempts(
        journal_root,
        request=_REQUEST,
        grant=5,
        reason=SemanticTaskRecoveryReason.OPERATOR_DISPOSITION,
        granted_by="operator/line-b",
    )

    with pytest.raises(ValueError):
        granted_extra_attempts(journal_root, request_digest="sha256:" + "e" * 64)


@pytest.mark.parametrize(
    ("grant", "granted_by"),
    [(0, "operator/line-b"), (-1, "operator/line-b"), (1, "   ")],
)
def test_an_unattributed_or_empty_grant_is_refused(
    tmp_path: Path, grant: int, granted_by: str
) -> None:
    journal_root = tmp_path / "journal"
    journal_root.mkdir()

    with pytest.raises(ValueError):
        grant_semantic_task_attempts(
            journal_root,
            request=_REQUEST,
            grant=grant,
            reason=SemanticTaskRecoveryReason.OPERATOR_DISPOSITION,
            granted_by=granted_by,
        )


def test_an_untyped_recovery_reason_is_refused(tmp_path: Path) -> None:
    journal_root = tmp_path / "journal"
    journal_root.mkdir()

    with pytest.raises(TypeError):
        grant_semantic_task_attempts(
            journal_root,
            request=_REQUEST,
            grant=1,
            reason="provider_quota_exhausted",
            granted_by="operator/line-b",
        )
