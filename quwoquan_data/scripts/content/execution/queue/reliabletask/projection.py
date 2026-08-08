"""ReliableTask terminal-outcome projections for the typed object queue."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Mapping

from core.control_types import QueueJobStage, QueueTimelineEvent
from core.data_issue import DataIssue
from core.io import read_json

from content.execution import production_contracts as pc
from content.execution import store
from content.execution.queue.completion import author_completion_issues
from content.execution.queue.core import (
    STATE_SUCCEEDED,
    _envelope_governance_issues,
    _queue_lock,
    _read_job,
    _write_job,
)
from content.execution.queue.model import QueueJob, QueueLease
from content.execution.queue.runtime import _apply_failure, _record_failure, _stored_envelope_ref

def record_reliabletask_completion(
    execution_id: str,
    job_id: str,
    *,
    evidence_path: str | Path,
    evidence_root: str | Path,
    envelope_workspace_root: str | Path | None = None,
) -> QueueJob:
    """Mirror a fenced Mongo task result into the local execution evidence view."""
    with _queue_lock(execution_id):
        job = _read_job(execution_id, job_id)
        if job.backend.value != "reliabletask":
            raise ValueError(
                f"external ReliableTask completion requires reliabletask backend: {job_id}"
            )
        if job.state is STATE_SUCCEEDED:
            return job
        root = Path(evidence_root)
        path = Path(evidence_path)
        if not path.is_absolute():
            path = root / path
        try:
            evidence = read_json(path)
        except (OSError, ValueError) as exc:
            raise ValueError(f"ReliableTask result evidence unreadable: {exc}") from exc
        if not isinstance(evidence, Mapping):
            raise ValueError("ReliableTask result evidence must be an object")
        gate_verdicts: list[object] = []
        agent_run_id = job.agent_run_id
        if job.stage is QueueJobStage.AUTHOR:
            workspace = (
                Path(envelope_workspace_root)
                if envelope_workspace_root is not None
                else path.parent
            )
            errors = pc.validate_agent_result_envelope(
                evidence,
                workspace_root=workspace,
            )
            errors.extend(pc.assert_envelope_matches_job(evidence, job.to_document()))
            errors.extend(_envelope_governance_issues(job, evidence))
            completion_issues = author_completion_issues(job)
            errors.extend(issue.message for issue in completion_issues)
            if (
                errors
                and job.carrier is not None
                and job.carrier.value != "homepage"
                and all(" hash mismatch:" in error for error in errors)
            ):
                from content.execution.controller.post_author_evidence import (
                    refresh_post_author_evidence_from_durable_meta,
                )
                from content.execution.queue.reliabletask.author import (
                    _execution_context,
                )

                refresh_post_author_evidence_from_durable_meta(
                    _execution_context(execution_id),
                    ref=job.ref,
                )
                evidence = read_json(path)
                errors = pc.validate_agent_result_envelope(
                    evidence,
                    workspace_root=workspace,
                )
                errors.extend(
                    pc.assert_envelope_matches_job(evidence, job.to_document())
                )
                errors.extend(_envelope_governance_issues(job, evidence))
                errors.extend(
                    issue.message for issue in author_completion_issues(job)
                )
            if errors:
                raise ValueError(
                    "ReliableTask AgentResultEnvelope invalid: " + "; ".join(errors)
                )
            raw_gates = evidence.get("gates")
            if not isinstance(raw_gates, list):
                raise ValueError("ReliableTask AgentResultEnvelope.gates must be an array")
            gate_verdicts = list(raw_gates)
            agent = evidence.get("agent")
            if isinstance(agent, Mapping):
                agent_run_id = str(agent.get("runId") or "").strip()
        elif job.stage is QueueJobStage.PUBLISH:
            if (
                evidence.get("schema") != "quwoquan_data.object_transaction_apply"
                or evidence.get("status") != "applied"
                or str(evidence.get("executionId") or "") != execution_id
            ):
                raise ValueError(
                    "ReliableTask publish completion requires bound applied transaction"
                )
        else:
            raise ValueError(
                f"ReliableTask external completion unsupported for {job.stage.value}"
            )
        stored_ref = _stored_envelope_ref(path, root=root)
        now = store.now_iso()
        accepted = job.with_timing(
            QueueTimelineEvent.ENVELOPE_ACCEPTED,
            at=now,
            attributes={"envelope": stored_ref, "source": "reliabletask"},
            result_envelope_ref=stored_ref,
            gate_verdicts_json=json.dumps(
                gate_verdicts,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            agent_run_id=agent_run_id,
        )
        completed = accepted.with_timing(
            QueueTimelineEvent.SUCCEEDED,
            at=store.now_iso(),
            attributes={"source": "reliabletask"},
            state=STATE_SUCCEEDED,
            lease=QueueLease(),
            not_before_epoch=0.0,
            same_run_retryable=False,
            last_issue=None,
        )
        _write_job(completed)
        return completed


def record_reliabletask_failure(
    execution_id: str,
    job_id: str,
    *,
    attempts: int,
    issue: DataIssue,
) -> QueueJob:
    """Project a terminal service-fleet failure into the execution queue."""
    if attempts < 1:
        raise ValueError("ReliableTask terminal failure requires positive attempts")
    with _queue_lock(execution_id):
        job = _read_job(execution_id, job_id)
        if job.backend.value != "reliabletask":
            raise ValueError(
                f"external ReliableTask failure requires reliabletask backend: {job_id}"
            )
        if job.state is STATE_SUCCEEDED:
            raise ValueError(
                f"ReliableTask terminal failure conflicts with completed job: {job_id}"
            )
        observed = replace(job, attempt=attempts, lease=QueueLease())
        failed = _apply_failure(
            observed,
            issue,
            fingerprint=issue.code.value,
        )
        _record_failure(failed, issue)
        _write_job(failed)
        return failed


def record_reliabletask_stale_terminal_outcome(
    execution_id: str,
    job_id: str,
    *,
    attempts: int,
    failure_code: str,
) -> QueueJob:
    """Record a late remote DEAD without overriding verified local success."""

    with _queue_lock(execution_id):
        job = _read_job(execution_id, job_id)
        if job.backend.value != "reliabletask" or job.state is not STATE_SUCCEEDED:
            raise ValueError(
                "stale ReliableTask terminal reconciliation requires local success"
            )
        reconciled = job.with_timing(
            QueueTimelineEvent.RECONCILED,
            at=store.now_iso(),
            attributes={
                "reason": "stale_remote_terminal_after_local_success",
                "remoteStatus": "dead",
                "remoteAttempts": attempts,
                "remoteFailureCode": failure_code,
            },
        )
        _write_job(reconciled)
        return reconciled
