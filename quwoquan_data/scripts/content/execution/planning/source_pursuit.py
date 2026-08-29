"""Quota-driven replenishment for source-ready target qualification.

``qualify_source_ready_targets`` grades one fixed slice of the ordered
reference set. When the oversample factor under-forecasts the rejection rate
that slice ends below the approved quota and the execution has no way to draw
more candidates. This driver keeps the same per-slice grader but re-enters it
against disjoint later slices until the quota is met or a typed stop reason is
proven, so a low pass rate costs extra rounds instead of delivered objects.

Grading runs before production by construction: a candidate rejected here never
reaches the semantic agent and therefore never spends provider quota.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.data_issue import DataIssueStage
from core.runtime_policy import QuotaPursuitPolicy, active_runtime_policy
from governance.coverage.entity_diversity_ledger import EntityDiversityGate

from content.execution.planning.quota_pursuit import (
    QuotaPursuitPlan,
    QuotaPursuitProgress,
    QuotaPursuitRound,
    pursue_quota,
)
from content.execution.planning.source_selection import (
    TargetSourceQualifier,
    rejection_summary,
    qualify_source_ready_targets,
)


@dataclass(slots=True)
class _QualificationDraw:
    """Grade disjoint slices of one ordered reference set, round by round."""

    candidate_rows: list[dict[str, Any]]
    discovery_ref: str
    source_qualifier: TargetSourceQualifier
    qualification_source_key: str
    persist_qualified_source: bool
    diversity_gate: EntityDiversityGate | None = None
    consumed: int = 0
    accepted_rows: list[dict[str, Any]] = field(default_factory=list)
    qualification_rows: list[dict[str, Any]] = field(default_factory=list)
    diversity_rejected_count: int = 0

    def supply_remaining(self) -> int:
        return max(0, len(self.candidate_rows) - self.consumed)

    def run_round(
        self,
        *,
        ordinal: int,
        requested_pool: int,
        remaining_deficit: int,
    ) -> QuotaPursuitRound:
        slice_rows = self.candidate_rows[
            self.consumed : self.consumed + requested_pool
        ]
        self.consumed += len(slice_rows)
        if not slice_rows:
            return QuotaPursuitRound(
                ordinal=ordinal,
                requested_pool=requested_pool,
                drawn_count=0,
                qualified_count=0,
                produced_count=0,
            )
        # The per-slice grader is given quota 0 so it cannot veto the execution
        # on its own slice; only the pursuit loop, which sees every round, is
        # allowed to decide that the approved quota is unreachable.
        selected, report, _requested = qualify_source_ready_targets(
            [dict(row) for row in slice_rows],
            discovery_ref=self.discovery_ref,
            limit=len(slice_rows),
            quota=0,
            source_qualifier=self.source_qualifier,
            target_names=(),
            qualification_source_key=self.qualification_source_key,
            persist_qualified_source=self.persist_qualified_source,
            qualification_supply_count=len(slice_rows),
        )
        accepted_names = {
            str(row.get("name") or "")
            for row in report.get("candidates") or []
            if row.get("accepted")
        }
        qualified = [
            row for row in selected if str(row.get("name") or "") in accepted_names
        ]
        # 多样性准入放在 source 分级之后、写入 accepted_rows 之前：被累计上限或
        # 集中度挡下的实体不是失败，只是不入选，所以本轮少收的量交给下一轮补齐。
        if self.diversity_gate is not None and qualified:
            diverse = self.diversity_gate.admit_rows(qualified)
            self.diversity_rejected_count += len(qualified) - len(diverse)
            qualified = [dict(row) for row in diverse]
        # Every qualified row in the drawn slice is kept, not just the ones the
        # open deficit still needs: ``quota`` is the delivery floor and the
        # oversampled surplus is what downstream admission and milestone
        # promotion read. Only the decision to draw *another* slice is bounded by
        # the deficit.
        self.accepted_rows.extend(qualified)
        self.qualification_rows.extend(
            dict(row) for row in report.get("candidates") or []
        )
        return QuotaPursuitRound(
            ordinal=ordinal,
            requested_pool=requested_pool,
            drawn_count=len(slice_rows),
            qualified_count=len(qualified),
            produced_count=len(qualified),
        )


@dataclass(frozen=True, slots=True)
class PursuedTargetPool:
    """Quota-attained target pool plus the runtime evidence that produced it."""

    targets: tuple[dict[str, Any], ...]
    qualification_rows: tuple[dict[str, Any], ...]
    progress: QuotaPursuitProgress
    diversity: dict[str, Any] = field(default_factory=dict)

    def report(self) -> dict[str, Any]:
        """The qualification report, in the one-shot lane's exact shape.

        Consumers read this report positionally by key, so the pursuit lane must
        publish the same fields. ``oversampleFilled`` is always 0 here: filling a
        pool with rejected rows is the non-persisting lane's behaviour, and this
        driver only runs where every selected row is authority-qualified.
        """

        return {
            "evaluatedCount": len(self.qualification_rows),
            "acceptedCount": sum(
                1 for row in self.qualification_rows if row.get("accepted")
            ),
            "rejectedCount": sum(
                1 for row in self.qualification_rows if not row.get("accepted")
            ),
            "candidates": [dict(row) for row in self.qualification_rows],
            "oversampleFilled": 0,
            "approvedQuota": self.progress.plan.approved_quota,
            "availableSupplyCount": len(self.targets),
            "supplyShortfallCount": self.progress.remaining_deficit,
            "qualificationCandidateCount": None,
            "unmatchedQualificationNames": [],
            "pursuitRoundCount": len(self.progress.rounds),
            "entityDiversity": dict(self.diversity),
        }


def pursue_qualified_target_pool(
    candidate_rows: list[dict[str, Any]],
    *,
    quota: int,
    frozen_target_ceiling: int,
    discovery_ref: str,
    source_qualifier: TargetSourceQualifier,
    qualification_source_key: str = "qualifiedHomepageSource",
    persist_qualified_source: bool = True,
    policy: QuotaPursuitPolicy | None = None,
    oversample_factor: float | None = None,
    stage: DataIssueStage = DataIssueStage.SOURCE_GATE,
    diversity_gate: EntityDiversityGate | None = None,
) -> PursuedTargetPool:
    """Qualify candidates in replenishing rounds until the quota is attained.

    The returned pool is what gets frozen as the execution's target set, so it
    never exceeds ``frozen_target_ceiling`` — the count the request declared.
    Candidates beyond the ceiling stay visible in the qualification report
    instead: they were examined, they just are not this execution's targets.

    Raises ``DataIssueError`` carrying the exact stop reason when the reference
    set, the target ceiling, the round budget or the stall detector prevents
    attainment; a below-quota pool is never returned as a success.
    """

    runtime = active_runtime_policy()
    plan = QuotaPursuitPlan.for_quota(
        quota,
        frozen_target_ceiling=frozen_target_ceiling,
        oversample_factor=(
            runtime.oversample_factor
            if oversample_factor is None
            else oversample_factor
        ),
        policy=policy or runtime.quota_pursuit,
    )
    draw = _QualificationDraw(
        candidate_rows=[dict(row) for row in candidate_rows],
        discovery_ref=discovery_ref,
        source_qualifier=source_qualifier,
        qualification_source_key=qualification_source_key,
        persist_qualified_source=persist_qualified_source,
        diversity_gate=diversity_gate,
    )
    progress = pursue_quota(
        plan,
        draw=draw,
        ref=discovery_ref,
        stage=stage,
        lane_attributes=lambda: {
            "candidatePool": plan.initial_pool,
            "acceptedCount": len(draw.accepted_rows),
            "evaluatedCount": len(draw.qualification_rows),
            "candidateCount": draw.consumed,
            "rejectionCounts": rejection_summary(draw.qualification_rows),
            "diversityRejectedCount": draw.diversity_rejected_count,
        },
    )
    return PursuedTargetPool(
        targets=tuple(draw.accepted_rows[:frozen_target_ceiling]),
        qualification_rows=tuple(draw.qualification_rows),
        progress=progress,
        diversity=(
            diversity_gate.report() if diversity_gate is not None else {}
        ),
    )


__all__ = ["PursuedTargetPool", "pursue_qualified_target_pool"]
