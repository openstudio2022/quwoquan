"""Quota-driven pursuit replaces one-shot oversampling.

Locks the four properties the engine has to keep from ten to thousand scale:
replenishment reaches the quota that a single oversampled draw would have
missed, a stall stops the loop instead of spinning, the round budget is a hard
ceiling, and a below-quota outcome is always a typed failure rather than a
smaller success.
"""
from __future__ import annotations

import pytest

from content.execution.planning.quota_pursuit import (
    QuotaPursuitPlan,
    QuotaPursuitProgress,
    QuotaPursuitRound,
    QuotaPursuitStop,
    initial_candidate_pool,
    load_quota_pursuit_progress,
    pursue_quota,
)
from content.execution.planning.source_pursuit import pursue_qualified_target_pool
from content.execution.planning.source_selection import TargetSourceQualification
from content.execution.request import resolve_candidate_pool
from core.data_issue import DataIssueCode, DataIssueError
from core.runtime_policy import QuotaPursuitPolicy, active_runtime_policy


def _policy(*, replenish: float = 1.5, max_rounds: int = 8, stall: int = 2):
    return QuotaPursuitPolicy(
        replenish_factor=replenish,
        max_rounds=max_rounds,
        stall_rounds=stall,
    )


class _ScriptedDraw:
    """Deliver a fixed yield per round from a bounded candidate supply."""

    def __init__(self, *, supply: int, yields: list[int]) -> None:
        self.supply = supply
        self.yields = yields
        self.requested: list[int] = []

    def supply_remaining(self) -> int:
        return self.supply

    def run_round(self, *, ordinal, requested_pool, remaining_deficit):
        self.requested.append(requested_pool)
        drawn = min(requested_pool, self.supply)
        self.supply -= drawn
        produced = min(
            self.yields[ordinal - 1] if ordinal <= len(self.yields) else 0,
            drawn,
            remaining_deficit,
        )
        return QuotaPursuitRound(
            ordinal=ordinal,
            requested_pool=requested_pool,
            drawn_count=drawn,
            qualified_count=produced,
            produced_count=produced,
        )


def test_runtime_policy_publishes_governed_pursuit_bounds() -> None:
    pursuit = active_runtime_policy().quota_pursuit
    assert pursuit.replenish_factor >= 1
    assert pursuit.max_rounds >= 1
    assert 1 <= pursuit.stall_rounds <= pursuit.max_rounds


def test_first_round_pool_is_the_policy_oversample_of_the_quota() -> None:
    assert initial_candidate_pool(10, oversample_factor=1.8) == 18
    quota, count = resolve_candidate_pool(quota=10, count=None)
    assert quota == 10
    assert count == initial_candidate_pool(
        10, oversample_factor=active_runtime_policy().oversample_factor
    )


def test_replenishment_reaches_a_quota_one_shot_oversampling_would_miss() -> None:
    # A 1.8 oversample of 10 draws 18 candidates. At the yields below the
    # single-draw engine would deliver 6 objects and report success.
    plan = QuotaPursuitPlan(
        approved_quota=10,
        initial_pool=18,
        frozen_target_ceiling=200,
        policy=_policy(),
    )
    draw = _ScriptedDraw(supply=200, yields=[6, 2, 1, 1])
    progress = pursue_quota(plan, draw=draw, ref="region")

    assert progress.produced_count == 10
    assert progress.remaining_deficit == 0
    assert len(progress.rounds) == 4
    # Each replenishment round is sized to the open deficit, not to the quota.
    assert draw.requested == [18, 6, 3, 2]


def test_consecutive_zero_yield_rounds_stop_the_loop_as_a_typed_failure() -> None:
    plan = QuotaPursuitPlan(
        approved_quota=10,
        initial_pool=18,
        frozen_target_ceiling=500,
        policy=_policy(stall=2),
    )
    draw = _ScriptedDraw(supply=500, yields=[4, 0, 0, 9, 9])

    with pytest.raises(DataIssueError) as excinfo:
        pursue_quota(plan, draw=draw, ref="region")

    issue = excinfo.value.issues[0]
    attrs = dict(issue.attributes)
    assert issue.code is DataIssueCode.SOURCE_QUALIFICATION_EXHAUSTED
    assert attrs["stopReason"] == QuotaPursuitStop.STALLED.value
    assert attrs["producedCount"] == "4"
    assert attrs["remainingDeficit"] == "6"
    # Stopped at the stall, not after burning the whole round budget.
    assert len(draw.requested) == 3


def test_round_budget_is_a_hard_ceiling_even_while_yield_continues() -> None:
    plan = QuotaPursuitPlan(
        approved_quota=100,
        initial_pool=180,
        frozen_target_ceiling=10_000,
        policy=_policy(max_rounds=3, stall=2),
    )
    draw = _ScriptedDraw(supply=10_000, yields=[1, 1, 1, 1, 1])

    with pytest.raises(DataIssueError) as excinfo:
        pursue_quota(plan, draw=draw, ref="region")

    attrs = dict(excinfo.value.issues[0].attributes)
    assert attrs["stopReason"] == QuotaPursuitStop.ROUND_BUDGET_EXHAUSTED.value
    assert attrs["roundCount"] == "3"
    assert len(draw.requested) == 3


def test_exhausted_supply_stops_before_the_round_budget() -> None:
    plan = QuotaPursuitPlan(
        approved_quota=10,
        initial_pool=18,
        frozen_target_ceiling=100,
        policy=_policy(),
    )
    draw = _ScriptedDraw(supply=18, yields=[5, 0])

    with pytest.raises(DataIssueError) as excinfo:
        pursue_quota(plan, draw=draw, ref="region")

    attrs = dict(excinfo.value.issues[0].attributes)
    assert attrs["stopReason"] == QuotaPursuitStop.SUPPLY_EXHAUSTED.value


def test_pursuit_rounds_are_append_only_and_contiguous() -> None:
    plan = QuotaPursuitPlan(
        approved_quota=5,
        initial_pool=9,
        frozen_target_ceiling=9,
        policy=_policy(),
    )
    progress = QuotaPursuitProgress(plan=plan, rounds=())

    with pytest.raises(ValueError):
        progress.with_round(
            QuotaPursuitRound(
                ordinal=2,
                requested_pool=9,
                drawn_count=9,
                qualified_count=1,
                produced_count=1,
            )
        )


def test_ledger_round_trip_preserves_progress_without_widening_the_promise() -> None:
    plan = QuotaPursuitPlan(
        approved_quota=10,
        initial_pool=18,
        frozen_target_ceiling=18,
        policy=_policy(),
    )
    progress = QuotaPursuitProgress(plan=plan, rounds=()).with_round(
        QuotaPursuitRound(
            ordinal=1,
            requested_pool=18,
            drawn_count=18,
            qualified_count=7,
            produced_count=6,
        )
    )
    document = progress.to_document(execution_id="exec-1")

    replayed = load_quota_pursuit_progress(document, policy=_policy())

    assert replayed.produced_count == 6
    assert replayed.remaining_deficit == 4
    assert replayed.plan.approved_quota == plan.approved_quota


class _QualifiedSource:
    def to_dict(self) -> dict[str, str]:
        return {"sourceId": "s"}


def _every_third_candidate(candidate) -> TargetSourceQualification:
    ordinal = int(candidate.name.rsplit("-", 1)[1])
    if ordinal % 3 == 0:
        return TargetSourceQualification(
            accepted=True,
            qualified_source=_QualifiedSource(),
        )
    return TargetSourceQualification(
        accepted=False,
        qualified_source=None,
        rejection_code=DataIssueCode.SOURCE_MISSING,
    )


def _rows(count: int) -> list[dict[str, object]]:
    return [
        {"name": f"entity-{index}", "entityType": "地点/景区", "geoTagRef": "geo/x"}
        for index in range(count)
    ]


def test_target_qualification_replenishes_until_the_quota_is_filled() -> None:
    pool = pursue_qualified_target_pool(
        _rows(200),
        quota=10,
        frozen_target_ceiling=200,
        discovery_ref="region/ref",
        source_qualifier=_every_third_candidate,
    )

    assert len(pool.targets) == 10
    assert pool.progress.remaining_deficit == 0
    assert len(pool.progress.rounds) > 1
    assert pool.report()["approvedQuota"] == 10


def test_declared_count_bounds_the_frozen_target_set_not_the_examined_pool() -> None:
    # 请求声明 --count 1，策略 oversample 抽 2 条且两条都合格。冻结集只能是 1 条，
    # 否则 retryOf 会因为「继承池 2 超过 --count 1」永久判否；而第 2 条仍要留在
    # 合格报告里——它被看过，只是不属于这次执行的目标。
    pool = pursue_qualified_target_pool(
        [
            {"name": "entity-0", "entityType": "地点/景区", "geoTagRef": "geo/x"},
            {"name": "entity-3", "entityType": "地点/景区", "geoTagRef": "geo/x"},
        ],
        quota=1,
        frozen_target_ceiling=1,
        discovery_ref="region/ref",
        source_qualifier=lambda candidate: TargetSourceQualification(
            accepted=True,
            qualified_source=_QualifiedSource(),
        ),
    )

    assert [row["name"] for row in pool.targets] == ["entity-0"]
    assert pool.progress.drawn_count == 2, "候选抽取不受目标上限约束"
    assert pool.report()["acceptedCount"] == 2, "余量留在报告里，不被抹掉"


def test_unqualified_leading_candidates_do_not_exhaust_a_count_one_request() -> None:
    # --count 1 时若把声明当成候选上限，第一条不合格就会直接判 exhausted，
    # 后面本来合格的实体永远轮不到——这正是补采存在的理由。
    pool = pursue_qualified_target_pool(
        _rows(9)[1:],  # entity-1 / entity-2 不合格，第一个合格的是 entity-3
        quota=1,
        frozen_target_ceiling=1,
        discovery_ref="region/ref",
        source_qualifier=_every_third_candidate,
    )

    assert [row["name"] for row in pool.targets] == ["entity-3"]
    assert pool.progress.drawn_count > 1


def test_target_qualification_shortfall_is_a_failure_not_a_smaller_pool() -> None:
    with pytest.raises(DataIssueError) as excinfo:
        pursue_qualified_target_pool(
            _rows(12),
            quota=10,
            frozen_target_ceiling=12,
            discovery_ref="region/ref",
            source_qualifier=_every_third_candidate,
        )

    issue = excinfo.value.issues[0]
    assert issue.code is DataIssueCode.SOURCE_QUALIFICATION_EXHAUSTED
    assert dict(issue.attributes)["stopReason"] == (
        QuotaPursuitStop.SUPPLY_EXHAUSTED.value
    )
