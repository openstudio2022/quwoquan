"""Create-once object disposition evidence for partial semantic checkpoints."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

from content.execution.agent.outcome import ManagedAgentJobOutcome
from content.execution.workspace import execution_root
from core.control_types import ExecutionStage
from core.io import read_json
from core.schema import assert_valid


_EXCLUSION_STAGES = {
    ExecutionStage.BUILD_HOMEPAGE,
    ExecutionStage.POST_AUTHOR,
}


def _canonical_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _typed_stage(stage: str | ExecutionStage) -> ExecutionStage:
    typed = stage if isinstance(stage, ExecutionStage) else ExecutionStage(str(stage))
    if typed not in _EXCLUSION_STAGES:
        raise ValueError(f"semantic checkpoint exclusion does not support {typed.value}")
    return typed


def semantic_checkpoint_exclusion_path(
    execution_id: str,
    *,
    stage: str | ExecutionStage,
    object_ref: str,
) -> Path:
    typed_stage = _typed_stage(stage)
    normalized_ref = str(object_ref or "").strip()
    if not normalized_ref:
        raise ValueError("semantic checkpoint exclusion requires objectRef")
    ref_key = hashlib.sha256(normalized_ref.encode("utf-8")).hexdigest()
    return (
        execution_root(execution_id)
        / "_shared"
        / "semantic_checkpoint_exclusions"
        / typed_stage.value
        / f"{ref_key}.json"
    )


def _write_create_once(path: Path, document: Mapping[str, object]) -> Path:
    body = _canonical_bytes(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            raise FileExistsError(
                f"semantic checkpoint exclusion create-once conflict: {path}"
            ) from None
        return path
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def write_semantic_checkpoint_exclusion(
    execution_id: str,
    *,
    stage: str | ExecutionStage,
    job_outcome: ManagedAgentJobOutcome,
    recorded_at: str,
) -> Path:
    """Freeze one failed invocation without claiming an unstarted task terminal."""
    typed_stage = _typed_stage(stage)
    if job_outcome.succeeded:
        raise ValueError("successful semantic task cannot be excluded")
    object_ref = str(job_outcome.ref or "").strip()
    if not object_ref:
        raise ValueError("failed semantic task cannot be excluded without objectRef")
    terminal = job_outcome.to_document()
    issue_records = terminal.get("issueRecords")
    if not isinstance(issue_records, list) or not issue_records:
        raise ValueError("semantic checkpoint exclusion requires typed issueRecords")
    task_started = bool(job_outcome.outcome.started)
    retry_of_required = bool(job_outcome.outcome.retryable)
    document: dict[str, object] = {
        "schema": "quwoquan_data.semantic_checkpoint_exclusion",
        "executionId": execution_id,
        "stage": typed_stage.value,
        "objectRef": object_ref,
        "disposition": "excluded" if task_started else "not_started_shortfall",
        "taskStarted": task_started,
        "shortfallCount": 1,
        "terminalOutcome": terminal,
        "terminalOutcomeDigest": _digest(terminal),
        "issueRecords": issue_records,
        "repairAction": (
            "new_execution_retry_of" if retry_of_required else "human_decision"
        ),
        "retryOfRequired": retry_of_required,
        "recordedAt": str(recorded_at or "").strip(),
    }
    document["receiptDigest"] = _digest(document)
    assert_valid(
        document,
        "execution",
        "semantic_checkpoint_exclusion",
        label=f"semantic_checkpoint_exclusion:{execution_id}:{object_ref}",
    )
    path = semantic_checkpoint_exclusion_path(
        execution_id,
        stage=typed_stage,
        object_ref=object_ref,
    )
    return _write_create_once(path, document)


def load_semantic_checkpoint_exclusion(
    execution_id: str,
    *,
    stage: str | ExecutionStage,
    object_ref: str,
) -> dict[str, object] | None:
    """Load and re-derive one exclusion before downstream work may consume it."""
    typed_stage = _typed_stage(stage)
    path = semantic_checkpoint_exclusion_path(
        execution_id,
        stage=typed_stage,
        object_ref=object_ref,
    )
    if not path.is_file():
        return None
    if path.is_symlink():
        raise ValueError("semantic checkpoint exclusion cannot be a symlink")
    document = read_json(path)
    if not isinstance(document, dict):
        raise ValueError(f"semantic checkpoint exclusion must be an object: {path}")
    assert_valid(
        document,
        "execution",
        "semantic_checkpoint_exclusion",
        label=f"semantic_checkpoint_exclusion:{execution_id}:{object_ref}",
    )
    if document.get("executionId") != execution_id:
        raise ValueError("semantic checkpoint exclusion executionId drift")
    if document.get("stage") != typed_stage.value:
        raise ValueError("semantic checkpoint exclusion stage drift")
    if document.get("objectRef") != object_ref:
        raise ValueError("semantic checkpoint exclusion objectRef drift")
    terminal = document.get("terminalOutcome")
    if not isinstance(terminal, dict):
        raise ValueError("semantic checkpoint exclusion terminalOutcome is invalid")
    if document.get("terminalOutcomeDigest") != _digest(terminal):
        raise ValueError("semantic checkpoint exclusion terminalOutcomeDigest drift")
    unsigned = {key: value for key, value in document.items() if key != "receiptDigest"}
    if document.get("receiptDigest") != _digest(unsigned):
        raise ValueError("semantic checkpoint exclusion receiptDigest drift")
    decoded = ManagedAgentJobOutcome.from_document(
        terminal,
        label=f"semantic checkpoint exclusion outcome:{object_ref}",
    )
    if decoded.succeeded or decoded.ref != object_ref:
        raise ValueError("semantic checkpoint exclusion does not bind a failed object")
    if bool(document.get("taskStarted")) != decoded.outcome.started:
        raise ValueError("semantic checkpoint exclusion taskStarted drift")
    if document.get("issueRecords") != terminal.get("issueRecords"):
        raise ValueError("semantic checkpoint exclusion issueRecords drift")
    retry_of_required = bool(decoded.outcome.retryable)
    if bool(document.get("retryOfRequired")) != retry_of_required:
        raise ValueError("semantic checkpoint exclusion retryOfRequired drift")
    expected_repair_action = (
        "new_execution_retry_of" if retry_of_required else "human_decision"
    )
    if document.get("repairAction") != expected_repair_action:
        raise ValueError("semantic checkpoint exclusion repairAction drift")
    return document


def semantic_checkpoint_exclusions(
    execution_id: str,
    *,
    stage: str | ExecutionStage,
    object_refs: Iterable[str],
) -> dict[str, dict[str, object]]:
    exclusions: dict[str, dict[str, object]] = {}
    for raw_ref in object_refs:
        object_ref = str(raw_ref or "").strip()
        if not object_ref or object_ref in exclusions:
            continue
        document = load_semantic_checkpoint_exclusion(
            execution_id,
            stage=stage,
            object_ref=object_ref,
        )
        if document is not None:
            exclusions[object_ref] = document
    return exclusions


def current_semantic_checkpoint_exclusions(
    execution_id: str,
    *,
    stage: str | ExecutionStage,
    object_refs: Iterable[str],
) -> dict[str, dict[str, object]]:
    """Reconcile create-once receipts with the current typed run record.

    Downstream stages must not infer that a missing author output was excluded.
    The latest typed checkpoint names the expected excluded refs and every one
    must have a valid create-once receipt before it may be filtered.
    """
    from content.execution.agent.history import last_managed_agent_run
    from content.execution.context import load_execution_state
    from core.control_types import ManagedAgentCheckpointStatus

    typed_stage = _typed_stage(stage)
    normalized_refs = tuple(
        dict.fromkeys(
            normalized
            for raw_ref in object_refs
            if (normalized := str(raw_ref or "").strip())
        )
    )
    documents = semantic_checkpoint_exclusions(
        execution_id,
        stage=typed_stage,
        object_refs=normalized_refs,
    )
    run = last_managed_agent_run(load_execution_state(execution_id))
    expected_refs: tuple[str, ...] = ()
    if (
        run is not None
        and run.stage is typed_stage
        and run.status
        in {
            ManagedAgentCheckpointStatus.PARTIAL,
            ManagedAgentCheckpointStatus.BLOCKED,
        }
    ):
        expected_refs = run.excluded_refs
    expected = set(expected_refs)
    indexed = set(normalized_refs)
    missing_from_index = sorted(expected - indexed)
    missing_receipts = sorted(expected - set(documents))
    unexpected_receipts = sorted(set(documents) - expected)
    if missing_from_index or missing_receipts or unexpected_receipts:
        details: list[str] = []
        if missing_from_index:
            details.append(f"excluded refs missing from object index={missing_from_index}")
        if missing_receipts:
            details.append(
                f"excluded refs missing create-once receipt={missing_receipts}"
            )
        if unexpected_receipts:
            details.append(
                f"receipts absent from current typed run={unexpected_receipts}"
            )
        raise ValueError(
            "semantic checkpoint exclusion evidence does not close: "
            + "; ".join(details)
        )
    return documents


__all__ = [
    "current_semantic_checkpoint_exclusions",
    "load_semantic_checkpoint_exclusion",
    "semantic_checkpoint_exclusion_path",
    "semantic_checkpoint_exclusions",
    "write_semantic_checkpoint_exclusion",
]
