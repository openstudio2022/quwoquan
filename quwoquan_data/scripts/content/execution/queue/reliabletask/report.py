"""Typed decoding for ReliableTask fleet reports."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping


_FLEET_TASK_STATUSES = frozenset(
    {"ready", "processing", "retry_wait", "succeeded", "dead"}
)
_FLEET_ACCEPTED_CONTENT_STATUSES = frozenset(
    {
        "MEASURED",
        "GATE_BLOCK_NO_COMMERCIAL_BATCH",
        "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH",
    }
)


@dataclass(frozen=True, slots=True)
class ReliableTaskFleetOutcome:
    job_id: str
    status: str
    attempts: int
    failure_code: str = ""

    @classmethod
    def from_document(cls, value: object) -> "ReliableTaskFleetOutcome":
        if not isinstance(value, Mapping):
            raise ValueError("ReliableTask fleet task outcome must be an object")
        job_id = str(value.get("jobId") or "").strip()
        status = str(value.get("status") or "").strip()
        failure_code = str(value.get("failureCode") or "").strip()
        try:
            attempts = int(value.get("attempts"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "ReliableTask fleet task outcome attempts must be an integer"
            ) from exc
        if not job_id or status not in _FLEET_TASK_STATUSES or attempts < 0:
            raise ValueError("ReliableTask fleet task outcome is invalid")
        return cls(job_id, status, attempts, failure_code)


@dataclass(frozen=True, slots=True)
class ReliableTaskFleetReport:
    total: int
    succeeded: int
    outcomes: tuple[ReliableTaskFleetOutcome, ...]
    passed: bool = True
    accepted_content_throughput_status: str = "MEASURED"
    finalized_object_count: int = 0
    recovery_eligible_count: int = 0
    automatic_recovered_count: int = 0
    manual_recovered_count: int = 0
    automatic_recovery_status: str = "NOT_EXERCISED"
    automatic_recovery_rate: float = 0.0

    @classmethod
    def from_document(cls, value: object) -> "ReliableTaskFleetReport":
        if not isinstance(value, Mapping):
            raise ValueError("ReliableTask fleet report must be an object")
        try:
            total = int(value.get("total"))
            succeeded = int(value.get("succeeded"))
            finalized_object_count = int(value.get("finalizedObjectCount") or 0)
            recovery_eligible_count = int(value.get("recoveryEligibleCount"))
            automatic_recovered_count = int(value.get("automaticRecoveredCount"))
            manual_recovered_count = int(value.get("manualRecoveredCount"))
            automatic_recovery_rate = float(value.get("automaticRecoveryRate"))
        except (TypeError, ValueError) as exc:
            raise ValueError("ReliableTask fleet report counts must be integers") from exc
        raw_outcomes = value.get("taskOutcomes")
        if not isinstance(raw_outcomes, list):
            raise ValueError("ReliableTask fleet report taskOutcomes must be an array")
        passed = value.get("passed")
        accepted_status = str(
            value.get("acceptedContentThroughputStatus") or ""
        ).strip()
        automatic_recovery_status = str(
            value.get("automaticRecoveryStatus") or ""
        ).strip()
        if not isinstance(passed, bool):
            raise ValueError("ReliableTask fleet report passed must be a boolean")
        if accepted_status not in _FLEET_ACCEPTED_CONTENT_STATUSES:
            raise ValueError(
                "ReliableTask fleet report accepted throughput status is invalid"
            )
        if finalized_object_count < 0:
            raise ValueError("ReliableTask fleet report finalizedObjectCount is invalid")
        if (
            recovery_eligible_count < 0
            or automatic_recovered_count < 0
            or manual_recovered_count < 0
            or automatic_recovered_count + manual_recovered_count
            > recovery_eligible_count
        ):
            raise ValueError("ReliableTask fleet recovery counts are invalid")
        expected_recovery_status = (
            "MEASURED" if recovery_eligible_count else "NOT_EXERCISED"
        )
        expected_recovery_rate = (
            automatic_recovered_count / recovery_eligible_count
            if recovery_eligible_count
            else 0.0
        )
        if (
            automatic_recovery_status != expected_recovery_status
            or not math.isclose(
                automatic_recovery_rate,
                expected_recovery_rate,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            raise ValueError(
                "ReliableTask fleet automatic recovery metric drift: "
                f"status={automatic_recovery_status!r} "
                f"rate={automatic_recovery_rate} expectedStatus="
                f"{expected_recovery_status!r} expectedRate="
                f"{expected_recovery_rate}"
            )
        outcomes = tuple(
            ReliableTaskFleetOutcome.from_document(item) for item in raw_outcomes
        )
        if total < 1 or succeeded < 0 or len(outcomes) != total:
            raise ValueError("ReliableTask fleet report outcome count is invalid")
        if len({outcome.job_id for outcome in outcomes}) != len(outcomes):
            raise ValueError("ReliableTask fleet report contains duplicate job outcomes")
        return cls(
            total=total,
            succeeded=succeeded,
            outcomes=outcomes,
            passed=passed,
            accepted_content_throughput_status=accepted_status,
            finalized_object_count=finalized_object_count,
            recovery_eligible_count=recovery_eligible_count,
            automatic_recovered_count=automatic_recovered_count,
            manual_recovered_count=manual_recovered_count,
            automatic_recovery_status=automatic_recovery_status,
            automatic_recovery_rate=automatic_recovery_rate,
        )


__all__ = ["ReliableTaskFleetOutcome", "ReliableTaskFleetReport"]
