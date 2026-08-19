"""Typed immutable execution-policy contract admitted by planning."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.control_types import SelectionPolicy


def _string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"executionPolicy.{field} must be a non-empty string")
    return value.strip()


def _optional_string(payload: Mapping[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"executionPolicy.{field} must be string or null")
    return value.strip() or None


def _integer(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"executionPolicy.{field} must be non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    selection_policy: SelectionPolicy
    target_entity_count: int
    target_object_count: int
    approved_quota: int
    oversample_factor: float
    partition_count: int
    capacity_plan_digest: str
    capacity_calibration: Mapping[str, Any]
    execution_branch: str
    git_commit_sha: str
    scale_source_pool: Mapping[str, Any] | None = None
    source_pool_evidence_root_ref: str | None = None
    source_pool_selection: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.approved_quota < 1:
            raise ValueError(
                "executionPolicy.approvedQuota must be positive"
            )
        if self.oversample_factor < 1:
            raise ValueError("executionPolicy oversampleFactor is invalid")
        from content.execution.planning.capacity_calibration import (
            assert_capacity_source_binding,
            freeze_capacity_source_binding,
        )

        source_binding = {
            key: value
            for key in (
                "calibrationId",
                "calibrationReceiptRef",
                "calibrationReceiptDigest",
                "applicability",
                "frozenCapacity",
            )
            if (value := self.capacity_calibration.get(key)) is not None
        }
        assert_capacity_source_binding(source_binding)
        frozen = freeze_capacity_source_binding(
            source_binding,
            work_unit_count=self.target_object_count,
            frozen_at_epoch_seconds=int(
                self.capacity_calibration["frozenAtEpochSeconds"]
            ),
        )
        if frozen != dict(self.capacity_calibration):
            raise ValueError("executionPolicy capacityCalibration drift")
        if self.partition_count not in {16, 32, 64, 128, 256}:
            raise ValueError("executionPolicy.partitionCount is not governed")
        digest = self.capacity_plan_digest
        if len(digest) != 71 or not digest.startswith("sha256:") or any(
            char not in "0123456789abcdef" for char in digest[7:]
        ):
            raise ValueError("executionPolicy.capacityPlanDigest must be sha256")
        pool = (
            self.scale_source_pool,
            self.source_pool_evidence_root_ref,
            self.source_pool_selection,
        )
        if any(value is not None for value in pool) and not all(
            value is not None for value in pool
        ):
            raise ValueError("executionPolicy source pool binding is incomplete")

    @property
    def auto_research_max_concurrent_workers(self) -> int:
        return int(
            self.capacity_calibration["frozenCapacity"][
                "autoResearchMaxConcurrentWorkers"
            ]
        )

    @property
    def fleet_max_concurrent_workers(self) -> int:
        return int(
            self.capacity_calibration["frozenCapacity"][
                "fleetMaxConcurrentWorkers"
            ]
        )

    @property
    def fleet_batch_deadline_epoch_seconds(self) -> int:
        return int(self.capacity_calibration["fleetBatchDeadlineEpochSeconds"])

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionPolicy":
        factor = payload.get("oversampleFactor")
        if isinstance(factor, bool) or not isinstance(factor, (int, float)):
            raise ValueError("executionPolicy.oversampleFactor must be a number")
        return cls(
            selection_policy=SelectionPolicy(_string(payload, "selectionPolicy")),
            target_entity_count=_integer(payload, "targetEntityCount"),
            target_object_count=_integer(payload, "targetObjectCount"),
            approved_quota=_integer(payload, "approvedQuota"),
            oversample_factor=float(factor),
            partition_count=_integer(payload, "partitionCount"),
            capacity_plan_digest=_string(payload, "capacityPlanDigest"),
            capacity_calibration=(
                dict(payload["capacityCalibration"])
                if isinstance(payload.get("capacityCalibration"), Mapping)
                else {}
            ),
            execution_branch=_string(payload, "executionBranch"),
            git_commit_sha=_string(payload, "gitCommitSha"),
            scale_source_pool=(
                dict(payload["scaleSourcePool"])
                if isinstance(payload.get("scaleSourcePool"), Mapping)
                else None
            ),
            source_pool_evidence_root_ref=_optional_string(
                payload, "sourcePoolEvidenceRootRef"
            ),
            source_pool_selection=(
                dict(payload["sourcePoolSelection"])
                if isinstance(payload.get("sourcePoolSelection"), Mapping)
                else None
            ),
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "selectionPolicy": self.selection_policy.value,
            "targetEntityCount": self.target_entity_count,
            "targetObjectCount": self.target_object_count,
            "approvedQuota": self.approved_quota,
            "oversampleFactor": self.oversample_factor,
            "partitionCount": self.partition_count,
            "capacityPlanDigest": self.capacity_plan_digest,
            "capacityCalibration": dict(self.capacity_calibration),
            "executionBranch": self.execution_branch,
            "gitCommitSha": self.git_commit_sha,
        }
        if self.scale_source_pool is not None:
            result.update(
                {
                    "scaleSourcePool": dict(self.scale_source_pool),
                    "sourcePoolEvidenceRootRef": self.source_pool_evidence_root_ref,
                    "sourcePoolSelection": dict(self.source_pool_selection or {}),
                }
            )
        return result


__all__ = ["ExecutionPolicy"]
