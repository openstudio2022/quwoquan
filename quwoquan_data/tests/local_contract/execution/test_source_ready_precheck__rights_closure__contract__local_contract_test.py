"""Source-ready grading runs before provider quota is spent.

Rights closure used to surface at pool admission, after the semantic agent had
already authored the object. These cases lock the grade partition, and in
particular that an absent ``distributionDecision`` is graded apart from a
blocking one: the first is an upstream contract gap that names the writer to
fix, the second is a rights denial.
"""
from __future__ import annotations

import pytest

from content.execution.planning.source_ready_precheck import (
    DecisionShape,
    SourceReadyGrade,
    SourceReadyVerdict,
    grade_source_ready_candidate,
    precheck_source_ready_pool,
)
from governance.coverage.distribution import DistributionDecision


def _row(name: str, *decisions: object) -> dict[str, object]:
    assets = []
    for index, decision in enumerate(decisions):
        asset: dict[str, object] = {"assetId": f"{name}-asset-{index}"}
        if decision is not ...:
            asset["distributionDecision"] = decision
        assets.append(asset)
    return {"name": name, "assets": assets}


def test_closed_rights_grade_ready() -> None:
    verdict = grade_source_ready_candidate(
        _row(
            "entity-a",
            DistributionDecision.RESEARCH_ALLOWED.value,
            DistributionDecision.COMMERCIAL_ALLOWED.value,
        )
    )

    assert verdict.grade is SourceReadyGrade.READY
    assert verdict.ready is True
    assert verdict.to_document() == {
        "name": "entity-a",
        "grade": "ready",
        "ready": True,
    }


@pytest.mark.parametrize(
    ("raw", "shape"),
    [
        (..., DecisionShape.KEY_MISSING),
        (None, DecisionShape.NULL),
        ("", DecisionShape.EMPTY_STRING),
        ("   ", DecisionShape.EMPTY_STRING),
        ("maybe-later", DecisionShape.UNRECOGNIZED),
        (7, DecisionShape.UNRECOGNIZED),
    ],
)
def test_every_unusable_decision_shape_is_graded_absent_and_attributed(
    raw: object, shape: DecisionShape
) -> None:
    verdict = grade_source_ready_candidate(_row("entity-a", raw))

    assert verdict.grade is SourceReadyGrade.RIGHTS_DECISION_ABSENT
    assert verdict.decision_shape is shape
    assert verdict.offending_asset_ids == ("entity-a-asset-0",)
    assert shape.value in verdict.reason


def test_an_absent_decision_is_never_graded_as_a_block() -> None:
    # Collapsing absent into blocked would report a writer defect as a rights
    # denial and hide the writer that has to be fixed.
    absent = grade_source_ready_candidate(_row("entity-a", ""))
    blocked = grade_source_ready_candidate(
        _row("entity-b", DistributionDecision.BLOCKED.value)
    )

    assert absent.grade is SourceReadyGrade.RIGHTS_DECISION_ABSENT
    assert blocked.grade is SourceReadyGrade.RIGHTS_NOT_CLOSED
    assert blocked.decision_shape is None


def test_an_absent_decision_outranks_a_block_in_the_same_candidate() -> None:
    verdict = grade_source_ready_candidate(
        _row("entity-a", DistributionDecision.BLOCKED.value, "")
    )

    assert verdict.grade is SourceReadyGrade.RIGHTS_DECISION_ABSENT


def test_a_candidate_without_assets_is_graded_source_absent() -> None:
    verdict = grade_source_ready_candidate({"name": "entity-a", "assets": []})

    assert verdict.grade is SourceReadyGrade.SOURCE_ABSENT
    assert verdict.ready is False


def test_asset_grading_can_be_waived_for_carriers_that_carry_none() -> None:
    verdict = grade_source_ready_candidate(
        {"name": "entity-a", "assets": []}, require_assets=False
    )

    assert verdict.grade is SourceReadyGrade.READY


def test_a_nameless_candidate_row_is_a_failure_not_a_skip() -> None:
    with pytest.raises(ValueError):
        grade_source_ready_candidate({"name": "  ", "assets": []})


@pytest.mark.parametrize("assets", ["not-a-list", [7]])
def test_malformed_asset_rows_fail_instead_of_grading_ready(assets: object) -> None:
    with pytest.raises(ValueError):
        grade_source_ready_candidate({"name": "entity-a", "assets": assets})


def test_a_ready_verdict_cannot_carry_a_rejection_reason() -> None:
    with pytest.raises(ValueError):
        SourceReadyVerdict(
            name="entity-a",
            grade=SourceReadyGrade.READY,
            reason="rejected anyway",
        )


def test_a_rejected_verdict_must_carry_its_reason() -> None:
    with pytest.raises(ValueError):
        SourceReadyVerdict(name="entity-a", grade=SourceReadyGrade.SOURCE_ABSENT)


def test_a_decision_shape_only_describes_an_absent_decision() -> None:
    with pytest.raises(ValueError):
        SourceReadyVerdict(
            name="entity-a",
            grade=SourceReadyGrade.RIGHTS_NOT_CLOSED,
            reason="blocked",
            decision_shape=DecisionShape.NULL,
        )


def test_pool_precheck_partitions_the_pool_before_production() -> None:
    precheck = precheck_source_ready_pool(
        [
            _row("ok-1", DistributionDecision.RESEARCH_ALLOWED.value),
            _row("ok-2", DistributionDecision.COMMERCIAL_ALLOWED.value),
            _row("absent", ...),
            _row("blocked", DistributionDecision.BLOCKED.value),
            {"name": "no-assets", "assets": []},
        ]
    )

    assert precheck.ready_names == ("ok-1", "ok-2")
    report = precheck.report()
    assert report["evaluatedCount"] == 5
    assert report["readyCount"] == 2
    assert report["gradeCounts"] == {
        "ready": 2,
        "rights_decision_absent": 1,
        "rights_not_closed": 1,
        "source_absent": 1,
    }
