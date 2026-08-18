"""Quota-driven candidate pursuit for one execution.

A single ``ceil(quota * factor)`` draw cannot recover from below-forecast pass
rates: once the frozen pool is spent the execution delivers fewer objects than
the approved quota and reports success. This module replaces that draw with a
bounded pursuit loop that keeps replenishing candidates until the quota is
attained or a typed stop reason is proven.

Freeze boundary
---------------
The immutable ``executionSpec`` owns the *promise* and the *bounds*:
``approvedQuota``, the initial oversampled pool and the pursuit policy that
was admitted. It never records how many rounds actually ran. Round-by-round
progress is runtime evidence and lives in an append-only ledger under
``_shared/quota_pursuit_ledger.json``; replaying it can never widen the frozen
promise, so tampering with the ledger cannot buy admission.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from core.data_issue import (
    DataIssueCode,
    DataIssueError,
    DataIssueStage,
    data_issue,
)
from core.runtime_policy import QuotaPursuitPolicy, active_runtime_policy

QUOTA_PURSUIT_LEDGER_SCHEMA = "quwoquan_data.quota_pursuit_ledger"


class QuotaPursuitStop(StrEnum):
    """Why the pursuit loop stopped. Exactly one applies to a finished loop."""

    ATTAINED = "attained"
    SUPPLY_EXHAUSTED = "supply_exhausted"
    STALLED = "stalled"
    ROUND_BUDGET_EXHAUSTED = "round_budget_exhausted"


@dataclass(frozen=True, slots=True)
class QuotaPursuitRound:
    """One completed pursuit round.

    ``qualified_count`` counts candidates that passed pre-production grading;
    ``produced_count`` counts objects the round actually delivered. Progress is
    measured on delivery, so a round that qualifies candidates but delivers
    nothing still counts as no progress.
    """

    ordinal: int
    requested_pool: int
    drawn_count: int
    qualified_count: int
    produced_count: int

    def __post_init__(self) -> None:
        if self.ordinal < 1:
            raise ValueError("pursuit round ordinal must be >= 1")
        for label, value in (
            ("requestedPool", self.requested_pool),
            ("drawnCount", self.drawn_count),
            ("qualifiedCount", self.qualified_count),
            ("producedCount", self.produced_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"pursuit round {label} must be a non-negative integer")
        if self.drawn_count > self.requested_pool:
            raise ValueError("pursuit round cannot draw more than it requested")
        if self.qualified_count > self.drawn_count:
            raise ValueError("pursuit round cannot qualify more than it drew")
        if self.produced_count > self.qualified_count:
            raise ValueError("pursuit round cannot produce more than it qualified")

    def to_document(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "requestedPool": self.requested_pool,
            "drawnCount": self.drawn_count,
            "qualifiedCount": self.qualified_count,
            "producedCount": self.produced_count,
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> "QuotaPursuitRound":
        return cls(
            ordinal=_required_int(value, "ordinal"),
            requested_pool=_required_int(value, "requestedPool"),
            drawn_count=_required_int(value, "drawnCount"),
            qualified_count=_required_int(value, "qualifiedCount"),
            produced_count=_required_int(value, "producedCount"),
        )


def _required_int(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"pursuit round {field} must be an integer")
    return value


def initial_candidate_pool(quota: int, *, oversample_factor: float) -> int:
    """The first round draws the policy oversample of the delivery promise."""

    if isinstance(quota, bool) or not isinstance(quota, int) or quota < 1:
        raise ValueError("quota must be a positive integer")
    if (
        isinstance(oversample_factor, bool)
        or not isinstance(oversample_factor, (int, float))
        or oversample_factor < 1
    ):
        raise ValueError("oversampleFactor must be a number >= 1")
    return int(math.ceil(quota * float(oversample_factor)))


@dataclass(frozen=True, slots=True)
class QuotaPursuitPlan:
    """The admitted, frozen bounds of one pursuit loop."""

    approved_quota: int
    initial_pool: int
    policy: QuotaPursuitPolicy

    def __post_init__(self) -> None:
        if isinstance(self.approved_quota, bool) or self.approved_quota < 1:
            raise ValueError("approvedQuota must be a positive integer")
        if self.initial_pool < self.approved_quota:
            raise ValueError("initial candidate pool cannot be smaller than the quota")

    @classmethod
    def for_quota(
        cls,
        quota: int,
        *,
        oversample_factor: float | None = None,
        policy: QuotaPursuitPolicy | None = None,
    ) -> "QuotaPursuitPlan":
        runtime = active_runtime_policy()
        factor = (
            runtime.oversample_factor
            if oversample_factor is None
            else oversample_factor
        )
        return cls(
            approved_quota=quota,
            initial_pool=initial_candidate_pool(quota, oversample_factor=factor),
            policy=policy or runtime.quota_pursuit,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "approvedQuota": self.approved_quota,
            "initialPool": self.initial_pool,
            "replenishFactor": self.policy.replenish_factor,
            "maxRounds": self.policy.max_rounds,
            "stallRounds": self.policy.stall_rounds,
        }


@dataclass(frozen=True, slots=True)
class QuotaPursuitProgress:
    """Runtime projection of one pursuit loop; the operator-visible answer."""

    plan: QuotaPursuitPlan
    rounds: tuple[QuotaPursuitRound, ...]

    @property
    def produced_count(self) -> int:
        return sum(row.produced_count for row in self.rounds)

    @property
    def remaining_deficit(self) -> int:
        return max(0, self.plan.approved_quota - self.produced_count)

    @property
    def consecutive_stalled_rounds(self) -> int:
        stalled = 0
        for row in reversed(self.rounds):
            if row.produced_count:
                break
            stalled += 1
        return stalled

    @property
    def attained(self) -> bool:
        return self.remaining_deficit == 0

    def next_round_pool(self) -> int:
        """Candidates the next round should draw, sized to the open deficit."""

        if self.attained:
            raise ValueError("attained pursuit has no next round")
        if not self.rounds:
            return self.plan.initial_pool
        return int(
            math.ceil(self.remaining_deficit * self.plan.policy.replenish_factor)
        )

    def stop_reason(self, *, supply_remaining: int) -> QuotaPursuitStop | None:
        """The proven stop reason, or absent while the loop may still continue.

        ``None`` means no stop condition holds yet. It never means "failed":
        every non-attained terminal outcome is a distinct typed stop reason.
        """

        if isinstance(supply_remaining, bool) or not isinstance(supply_remaining, int):
            raise TypeError("supply_remaining must be an integer")
        if supply_remaining < 0:
            raise ValueError("supply_remaining must be non-negative")
        if self.attained:
            return QuotaPursuitStop.ATTAINED
        if self.consecutive_stalled_rounds >= self.plan.policy.stall_rounds:
            return QuotaPursuitStop.STALLED
        if supply_remaining == 0:
            return QuotaPursuitStop.SUPPLY_EXHAUSTED
        if len(self.rounds) >= self.plan.policy.max_rounds:
            return QuotaPursuitStop.ROUND_BUDGET_EXHAUSTED
        return None

    def with_round(self, round_row: QuotaPursuitRound) -> "QuotaPursuitProgress":
        expected = len(self.rounds) + 1
        if round_row.ordinal != expected:
            raise ValueError(
                f"pursuit rounds must be append-only and contiguous: "
                f"expected {expected}, got {round_row.ordinal}"
            )
        return QuotaPursuitProgress(
            plan=self.plan,
            rounds=(*self.rounds, round_row),
        )

    def to_document(self, *, execution_id: str) -> dict[str, Any]:
        return {
            "schema": QUOTA_PURSUIT_LEDGER_SCHEMA,
            "executionId": execution_id,
            "plan": self.plan.to_document(),
            "rounds": [row.to_document() for row in self.rounds],
            "producedCount": self.produced_count,
            "remainingDeficit": self.remaining_deficit,
        }


def pursuit_shortfall_issue(
    progress: QuotaPursuitProgress,
    *,
    stop: QuotaPursuitStop,
    ref: str,
    stage: DataIssueStage = DataIssueStage.SOURCE_GATE,
    lane_attributes: Mapping[str, object] | None = None,
):
    """Render a non-attained pursuit outcome as one typed data issue.

    A pursuit that stops short of the approved quota is a failure: it must not
    be reported as a smaller successful delivery. ``lane_attributes`` carries the
    evidence only the calling lane can see, so a lane that already publishes
    named shortfall attributes keeps publishing them.
    """

    if stop is QuotaPursuitStop.ATTAINED:
        raise ValueError("attained pursuit has no shortfall issue")
    return data_issue(
        DataIssueCode.SOURCE_QUALIFICATION_EXHAUSTED,
        stage=stage,
        ref=ref,
        message=(
            "配额驱动循环未达准出配额："
            f"已产出 {progress.produced_count}/{progress.plan.approved_quota}，"
            f"停止原因 {stop.value}"
        ),
        attributes={
            "stopReason": stop.value,
            "approvedQuota": progress.plan.approved_quota,
            "producedCount": progress.produced_count,
            "remainingDeficit": progress.remaining_deficit,
            "roundCount": len(progress.rounds),
            "maxRounds": progress.plan.policy.max_rounds,
            "stalledRounds": progress.consecutive_stalled_rounds,
            **dict(lane_attributes or {}),
        },
    )


class QuotaPursuitDraw(Protocol):
    """One round of generate, pre-screen and produce for a pursuit loop."""

    def supply_remaining(self) -> int:
        """Candidates still available outside every round drawn so far."""

    def run_round(
        self,
        *,
        ordinal: int,
        requested_pool: int,
        remaining_deficit: int,
    ) -> QuotaPursuitRound:
        """Draw, pre-screen and produce for one round."""


QuotaPursuitObserver = Callable[[QuotaPursuitProgress], None]


def pursue_quota(
    plan: QuotaPursuitPlan,
    *,
    draw: QuotaPursuitDraw,
    ref: str,
    stage: DataIssueStage = DataIssueStage.SOURCE_GATE,
    observer: QuotaPursuitObserver | None = None,
    lane_attributes: Callable[[], Mapping[str, object]] | None = None,
) -> QuotaPursuitProgress:
    """Run the bounded pursuit loop until the quota is attained or it stops.

    ``draw`` owns generation, pre-production grading and production for one
    round; this loop owns only the quota arithmetic, the stall detection and
    the round budget, so the same loop drives ten, hundred and thousand scale.

    ``lane_attributes`` is read only when the pursuit fails, so a lane can attach
    evidence that exists only after the rounds have run.
    """

    progress = QuotaPursuitProgress(plan=plan, rounds=())
    while True:
        stop = progress.stop_reason(supply_remaining=draw.supply_remaining())
        if stop is not None:
            break
        outcome = draw.run_round(
            ordinal=len(progress.rounds) + 1,
            requested_pool=progress.next_round_pool(),
            remaining_deficit=progress.remaining_deficit,
        )
        progress = progress.with_round(outcome)
        if observer is not None:
            observer(progress)
    if stop is not QuotaPursuitStop.ATTAINED:
        raise DataIssueError(
            (
                pursuit_shortfall_issue(
                    progress,
                    stop=stop,
                    ref=ref,
                    stage=stage,
                    lane_attributes=None if lane_attributes is None else lane_attributes(),
                ),
            )
        )
    return progress


def quota_pursuit_ledger_path(execution_root_dir: Path) -> Path:
    return execution_root_dir / "_shared" / "quota_pursuit_ledger.json"


def write_quota_pursuit_ledger(
    execution_root_dir: Path,
    progress: QuotaPursuitProgress,
    *,
    execution_id: str,
) -> Path:
    """Persist the runtime pursuit ledger outside the frozen execution spec."""

    from core.io import write_json
    from core.schema import assert_valid

    document = progress.to_document(execution_id=execution_id)
    assert_valid(
        document,
        "execution",
        "quota_pursuit_ledger",
        label=f"quota pursuit ledger:{execution_id}",
    )
    path = quota_pursuit_ledger_path(execution_root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, document)
    return path


def load_quota_pursuit_progress(
    value: Mapping[str, Any],
    *,
    policy: QuotaPursuitPolicy,
) -> QuotaPursuitProgress:
    """Rebuild pursuit progress from a persisted ledger for resume and reporting."""

    raw_plan = value.get("plan")
    if not isinstance(raw_plan, Mapping):
        raise ValueError("quota pursuit ledger plan must be an object")
    raw_rounds = value.get("rounds")
    if not isinstance(raw_rounds, Sequence) or isinstance(raw_rounds, (str, bytes)):
        raise ValueError("quota pursuit ledger rounds must be an array")
    plan = QuotaPursuitPlan(
        approved_quota=_required_int(raw_plan, "approvedQuota"),
        initial_pool=_required_int(raw_plan, "initialPool"),
        policy=policy,
    )
    progress = QuotaPursuitProgress(plan=plan, rounds=())
    for raw in _rows(raw_rounds):
        progress = progress.with_round(QuotaPursuitRound.from_document(raw))
    return progress


def _rows(values: Iterable[Any]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for raw in values:
        if not isinstance(raw, Mapping):
            raise ValueError("quota pursuit ledger rounds must contain objects")
        rows.append(raw)
    return rows


__all__ = [
    "QUOTA_PURSUIT_LEDGER_SCHEMA",
    "QuotaPursuitDraw",
    "QuotaPursuitPlan",
    "QuotaPursuitProgress",
    "QuotaPursuitRound",
    "QuotaPursuitStop",
    "initial_candidate_pool",
    "load_quota_pursuit_progress",
    "pursue_quota",
    "pursuit_shortfall_issue",
    "quota_pursuit_ledger_path",
    "write_quota_pursuit_ledger",
]
