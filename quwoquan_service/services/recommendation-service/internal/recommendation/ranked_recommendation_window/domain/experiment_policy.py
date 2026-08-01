from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import threading
from typing import Protocol


EXPERIMENT_ID = "rec_model_vs_rule"
ALLOWED_BUCKETS = frozenset({"model", "rule"})


@dataclass(frozen=True, slots=True)
class PolicyVariant:
    key: str
    allocation_basis_points: int


@dataclass(frozen=True, slots=True)
class ExperimentPolicy:
    experiment_id: str
    revision: int
    status: str
    variants: tuple[PolicyVariant, ...]
    starts_at: datetime | None
    ends_at: datetime | None
    updated_at: datetime
    digest: str


@dataclass(frozen=True, slots=True)
class Assignment:
    experiment_id: str
    experiment_revision: int
    subject_key: str
    bucket: str
    policy_digest: str
    assigned_at: datetime


class AssignmentPublisher(Protocol):
    def publish(self, assignment: Assignment) -> None: ...


class ExperimentAssignments:
    def __init__(self, publisher: AssignmentPublisher) -> None:
        if publisher is None:
            raise ValueError("recommendation experiment assignment publisher is required")
        self._publisher = publisher
        self._policy: ExperimentPolicy | None = None
        self._lock = threading.RLock()

    def apply_policy(self, policy: ExperimentPolicy) -> None:
        canonical = canonical_policy(policy)
        with self._lock:
            if self._policy is not None:
                if canonical.revision < self._policy.revision:
                    return
                if canonical.revision == self._policy.revision:
                    if canonical.digest != self._policy.digest:
                        raise ValueError("recommendation Experiment policy revision conflicts")
                    return
            self._policy = canonical

    def assign(self, subject_key: str, *, now: datetime | None = None) -> Assignment:
        normalized_subject = subject_key.strip()
        if not normalized_subject:
            raise ValueError("recommendation experiment subject key is required")
        with self._lock:
            policy = self._policy
        if policy is None:
            raise RuntimeError("recommendation ExperimentPolicyActivated is unavailable")
        assigned_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if policy.status != "running" or (
            policy.starts_at is not None and assigned_at < policy.starts_at
        ) or (policy.ends_at is not None and assigned_at >= policy.ends_at):
            raise RuntimeError("recommendation Experiment policy is not active")
        bucket = assign_bucket(
            policy.experiment_id,
            normalized_subject,
            policy.variants,
        )
        assignment = Assignment(
            experiment_id=policy.experiment_id,
            experiment_revision=policy.revision,
            subject_key=normalized_subject,
            bucket=bucket,
            policy_digest=policy.digest,
            assigned_at=assigned_at,
        )
        self._publisher.publish(assignment)
        return assignment

    def healthy(self, *, now: datetime | None = None) -> bool:
        with self._lock:
            policy = self._policy
        if policy is None or policy.status != "running":
            return False
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return not (
            policy.starts_at is not None and current < policy.starts_at
        ) and not (policy.ends_at is not None and current >= policy.ends_at)


def canonical_policy(policy: ExperimentPolicy) -> ExperimentPolicy:
    experiment_id = policy.experiment_id.strip()
    status = policy.status.strip()
    if experiment_id != EXPERIMENT_ID or policy.revision <= 0:
        raise ValueError("recommendation Experiment policy identity is invalid")
    if status not in {"draft", "scheduled", "running", "paused", "ended"}:
        raise ValueError("recommendation Experiment policy status is invalid")
    updated_at = _aware(policy.updated_at, "updatedAt")
    starts_at = _optional_aware(policy.starts_at, "startsAt")
    ends_at = _optional_aware(policy.ends_at, "endsAt")
    if starts_at is not None and ends_at is not None and ends_at <= starts_at:
        raise ValueError("recommendation Experiment policy window is invalid")
    variants = tuple(
        PolicyVariant(item.key.strip(), int(item.allocation_basis_points))
        for item in policy.variants
    )
    if (
        {item.key for item in variants} != ALLOWED_BUCKETS
        or len(variants) != len(ALLOWED_BUCKETS)
        or any(item.allocation_basis_points < 0 for item in variants)
        or not any(item.allocation_basis_points > 0 for item in variants)
        or sum(item.allocation_basis_points for item in variants) != 10_000
    ):
        raise ValueError("recommendation Experiment variants are invalid")
    digest_payload = {
        "experimentId": experiment_id,
        "revision": policy.revision,
        "status": status,
        "variants": [
            {"key": item.key, "allocationBasisPoints": item.allocation_basis_points}
            for item in variants
        ],
        "startsAt": starts_at.isoformat() if starts_at else None,
        "endsAt": ends_at.isoformat() if ends_at else None,
        "updatedAt": updated_at.isoformat(),
    }
    digest = "sha256:" + hashlib.sha256(
        json.dumps(
            digest_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return replace(
        policy,
        experiment_id=experiment_id,
        status=status,
        variants=variants,
        starts_at=starts_at,
        ends_at=ends_at,
        updated_at=updated_at,
        digest=digest,
    )


def assign_bucket(
    experiment_id: str,
    subject_key: str,
    variants: tuple[PolicyVariant, ...],
) -> str:
    identity = f"{experiment_id.strip()}:{subject_key.strip()}".encode("utf-8")
    hash_value = 2_166_136_261
    for byte in identity:
        hash_value ^= byte
        hash_value = (hash_value * 16_777_619) & 0xFFFFFFFF
    position = hash_value % 10_000
    cumulative = 0
    for variant in variants:
        cumulative += variant.allocation_basis_points
        if position < cumulative:
            return variant.key
    raise ValueError("recommendation Experiment variants do not cover hash space")


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"recommendation Experiment {field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _optional_aware(value: datetime | None, field: str) -> datetime | None:
    return None if value is None else _aware(value, field)
