"""Select one immutable ReliableTask stage attempt without mixing revisions."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import execution_root
from core.schema import assert_valid

from content.execution.queue.backend import (
    freeze_reliabletask_job_set,
    load_reliabletask_job_set_envelopes,
)
from content.execution.runtime_contract import canonical_sha256


def _attempts(execution_id: str, stage: str) -> tuple[dict[str, Any], ...]:
    try:
        rows = load_reliabletask_job_set_envelopes(execution_id)
    except ValueError as exc:
        if "job-set envelope is missing" not in str(exc):
            raise
        return ()
    return tuple(row for row in rows if row.get("stage") == stage)


def select_or_freeze_job_set_attempt(
    execution_id: str,
    stage: str,
    *,
    active_tasks: Sequence[Mapping[str, Any]],
    required_workers: int,
) -> dict[str, Any]:
    """Return one attempt containing active identities, or append a new one.

    A resumed controller reuses the exact earlier attempt whose remote tasks
    already carry its digests. A repair revision has a new idempotency key and
    therefore receives a new content-addressed attempt containing only new
    identities; it never rebinds unchanged tasks from an older attempt.
    """
    if not active_tasks:
        raise ValueError("ReliableTask attempt requires active tasks")
    attempts = _attempts(execution_id, stage)
    known: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for attempt in attempts:
        for raw in attempt.get("expectedTasks") or []:
            if not isinstance(raw, dict):
                raise TypeError("ReliableTask attempt task must be an object")
            key = str(raw.get("idempotencyKey") or "").strip()
            if key in known:
                raise ValueError("ReliableTask attempts repeat an idempotencyKey")
            known[key] = (attempt, raw)
    active_by_key = {
        str(row.get("idempotencyKey") or "").strip(): dict(row)
        for row in active_tasks
    }
    if "" in active_by_key or len(active_by_key) != len(active_tasks):
        raise ValueError("ReliableTask active task identities are invalid")
    new_tasks = [row for key, row in active_by_key.items() if key not in known]
    if new_tasks:
        return freeze_reliabletask_job_set(
            execution_id,
            stage,
            expected_tasks=new_tasks,
            required_workers=required_workers,
        )
    candidates = sorted(
        {
            int(known[key][0]["attemptOrdinal"]): known[key][0]
            for key in active_by_key
        }.values(),
        key=lambda row: int(row["attemptOrdinal"]),
        reverse=True,
    )
    for attempt in candidates:
        if int(attempt.get("requiredWorkers") or 0) != required_workers:
            continue
        expected_by_key = {
            str(row.get("idempotencyKey") or ""): row
            for row in attempt.get("expectedTasks") or []
            if isinstance(row, Mapping)
        }
        matching = set(active_by_key) & set(expected_by_key)
        if not matching:
            continue
        for key in matching:
            current = active_by_key[key]
            frozen = expected_by_key[key]
            for field in (
                "entityRef", "carrier", "sourceRevision", "jobId",
                "executionId", "ref", "stage",
            ):
                if str(current.get(field) or "") != str(frozen.get(field) or ""):
                    raise ValueError("ReliableTask active task drifted from its attempt")
        return attempt
    raise ValueError(
        "ReliableTask active tasks cannot reuse an attempt with different workers"
    )


def attempt_evidence_dir(
    execution_id: str,
    attempt: Mapping[str, Any],
) -> Path:
    stage = str(attempt.get("stage") or "").strip()
    digest = str(attempt.get("jobSetDigest") or "").strip()
    if stage not in {"author", "publish"} or not digest.startswith("sha256:"):
        raise ValueError("ReliableTask attempt evidence identity is invalid")
    return (
        execution_root(execution_id)
        / "evidence/reliabletask"
        / stage
        / digest.removeprefix("sha256:")
    )


def latest_attempt_report_path(execution_id: str, stage: str) -> Path | None:
    attempts = _attempts(execution_id, stage)
    if not attempts:
        return None
    latest = max(attempts, key=lambda row: int(row["attemptOrdinal"]))
    path = attempt_evidence_dir(execution_id, latest) / "report.json"
    return path if path.is_file() else None


def latest_attempt_report_path_from_root(
    root: Path,
    stage: str,
) -> Path | None:
    """Resolve a report from its validated append-only plan chain."""
    plan_root = root / "0.plan/reliabletask_job_sets" / stage
    attempts: list[dict[str, Any]] = []
    paths = sorted(plan_root.glob("*.json")) if plan_root.is_dir() else ()
    for path in paths:
        row = read_json(path)
        if not isinstance(row, dict):
            raise TypeError("ReliableTask attempt envelope must be an object")
        assert_valid(
            row,
            "execution",
            "reliabletask_job_set_envelope",
            label=f"ReliableTask job-set envelope:{path}",
        )
        stable = {
            key: value for key, value in row.items() if key != "envelopeDigest"
        }
        if row.get("envelopeDigest") != canonical_sha256(stable):
            raise ValueError("ReliableTask attempt envelope digest drift")
        if path.stem != str(row.get("jobSetDigest") or "")[7:]:
            raise ValueError("ReliableTask attempt content-addressed path drift")
        attempts.append(row)
    attempts.sort(key=lambda row: int(row["attemptOrdinal"]))
    previous: str | None = None
    for ordinal, row in enumerate(attempts, start=1):
        if (
            row.get("stage") != stage
            or row.get("attemptOrdinal") != ordinal
            or row.get("previousJobSetEnvelopeDigest") != previous
        ):
            raise ValueError("ReliableTask attempt chain drift")
        previous = str(row["envelopeDigest"])
    if not attempts:
        return None
    report = (
        root
        / "evidence/reliabletask"
        / stage
        / str(attempts[-1]["jobSetDigest"])[7:]
        / "report.json"
    )
    return report if report.is_file() else None


def write_attempt_document_create_once(
    path: Path,
    payload: Mapping[str, Any],
) -> None:
    encoded = (json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != encoded:
            raise ValueError(f"ReliableTask attempt evidence collision: {path}")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


__all__ = [
    "attempt_evidence_dir",
    "latest_attempt_report_path",
    "latest_attempt_report_path_from_root",
    "select_or_freeze_job_set_attempt",
    "write_attempt_document_create_once",
]
