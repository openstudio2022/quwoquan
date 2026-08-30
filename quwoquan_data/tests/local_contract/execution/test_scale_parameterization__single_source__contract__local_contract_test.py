"""Milestone targets have one source, and progress is observable at scale.

The milestone numbers used to be restated in the campaign workload, the pool
report and the environment release selector, so raising a milestone meant
editing code in several places and any missed edit was a silent divergence.
These cases lock the single source and the operator-facing progress projection.
"""
from __future__ import annotations

import pytest

from content.execution.campaign.scale import campaign_workload_targets
from content.execution.controller.progress import project_execution_progress
from content.release.canonical import environment_release_selection, pool_inspection
from governance.coverage.distribution import load_content_distribution_policy

_CARRIERS = ("homepage", "article", "image", "video")


def test_every_milestone_consumer_reads_the_same_policy_table() -> None:
    policy_targets = load_content_distribution_policy().milestone_targets()

    assert environment_release_selection.MILESTONE_TARGETS == policy_targets
    assert pool_inspection.M100_TARGETS == policy_targets["M100"]
    for milestone, targets in policy_targets.items():
        assert campaign_workload_targets(milestone) == targets


def test_the_governed_milestones_are_declared_by_the_policy_not_by_code() -> None:
    policy = load_content_distribution_policy()

    assert policy.governed_scales() == tuple(policy.milestone_targets())
    assert set(policy.governed_scales()) == {"M100", "M1000", "M10000"}


@pytest.mark.parametrize("milestone", ["M100", "M1000", "M10000"])
def test_each_milestone_declares_an_asymmetric_target_for_every_carrier(
    milestone: str,
) -> None:
    targets = load_content_distribution_policy().milestone_targets()[milestone]

    assert set(targets) == set(_CARRIERS)
    assert all(value >= 1 for value in targets.values())
    # Video is deliberately an order of magnitude below the reading carriers.
    assert targets["video"] < targets["article"]


def test_milestones_scale_by_ten_between_governed_steps() -> None:
    table = load_content_distribution_policy().milestone_targets()

    for carrier in _CARRIERS:
        assert table["M1000"][carrier] == table["M100"][carrier] * 10
        assert table["M10000"][carrier] == table["M1000"][carrier] * 10


def test_an_ungoverned_scale_intent_stays_symmetric_across_carriers() -> None:
    targets = campaign_workload_targets("M50")

    assert targets == {carrier: 50 for carrier in _CARRIERS}


def test_an_unknown_scale_is_a_failure_not_a_default_target() -> None:
    with pytest.raises(ValueError):
        load_content_distribution_policy().scale_target("M42", "article")
    with pytest.raises(ValueError):
        load_content_distribution_policy().scale_target("M100", "podcast")


def test_progress_projects_completion_bottleneck_and_remaining_time() -> None:
    progress = project_execution_progress(
        execution_id="exec-1",
        approved_quota=1_000,
        produced_count=250,
        failed_count=7,
        completed_stages=("download_plan", "download_fetch", "content_plan"),
        total_stages=12,
        current_stage="post_author",
        started_at="2026-08-16T00:00:00Z",
        observed_at="2026-08-16T02:00:00Z",
    )

    assert progress.remaining_deficit == 750
    assert progress.object_completion_rate == pytest.approx(0.25)
    assert progress.stage_completion_rate == pytest.approx(0.25)
    assert progress.elapsed_seconds == 7_200
    # 7200s bought 250 objects, so the open 750 project to three times that.
    assert progress.estimated_remaining_seconds == 21_600
    assert progress.bottleneck is not None
    assert "post_author" in progress.render()


def test_remaining_time_stays_absent_when_no_rate_has_been_measured() -> None:
    # A fabricated estimate is worse than an admitted unknown.
    no_start = project_execution_progress(
        execution_id="exec-1",
        approved_quota=1_000,
        produced_count=10,
        failed_count=0,
        completed_stages=(),
        total_stages=12,
        current_stage="download_plan",
    )
    no_output = project_execution_progress(
        execution_id="exec-1",
        approved_quota=1_000,
        produced_count=0,
        failed_count=0,
        completed_stages=(),
        total_stages=12,
        current_stage="download_plan",
        started_at="2026-08-16T00:00:00Z",
        observed_at="2026-08-16T02:00:00Z",
    )

    assert no_start.estimated_remaining_seconds is None
    assert no_output.estimated_remaining_seconds is None
    assert no_output.elapsed_seconds == 7_200


def test_a_delivered_quota_projects_zero_remaining() -> None:
    progress = project_execution_progress(
        execution_id="exec-1",
        approved_quota=100,
        produced_count=100,
        failed_count=0,
        completed_stages=("a", "b"),
        total_stages=2,
        current_stage=None,
        started_at="2026-08-16T00:00:00Z",
        observed_at="2026-08-16T01:00:00Z",
    )

    assert progress.remaining_deficit == 0
    assert progress.estimated_remaining_seconds == 0
    assert progress.object_completion_rate == 1.0
    assert progress.stage_completion_rate == 1.0


def test_overdelivery_never_reports_above_full_completion() -> None:
    progress = project_execution_progress(
        execution_id="exec-1",
        approved_quota=10,
        produced_count=12,
        failed_count=0,
        completed_stages=("a", "b", "c"),
        total_stages=2,
        current_stage=None,
    )

    assert progress.object_completion_rate == 1.0
    assert progress.stage_completion_rate == 1.0
    assert progress.remaining_deficit == 0


def test_the_progress_document_is_stable_for_operator_tooling() -> None:
    document = project_execution_progress(
        execution_id="exec-1",
        approved_quota=1_000,
        produced_count=250,
        failed_count=0,
        completed_stages=("a",),
        total_stages=12,
        current_stage="post_author",
    ).to_document()

    assert set(document) == {
        "executionId",
        "approvedQuota",
        "producedCount",
        "failedCount",
        "remainingDeficit",
        "objectCompletionRate",
        "stageCompletionRate",
        "completedStageCount",
        "totalStageCount",
        "currentStage",
        "bottleneck",
        "elapsedSeconds",
        "estimatedRemainingSeconds",
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"approved_quota": 0},
        {"produced_count": -1},
        {"failed_count": -1},
        {"total_stages": -1},
    ],
)
def test_a_nonsensical_projection_input_is_a_failure(kwargs: dict[str, int]) -> None:
    base = {
        "execution_id": "exec-1",
        "approved_quota": 10,
        "produced_count": 1,
        "failed_count": 0,
        "completed_stages": (),
        "total_stages": 12,
        "current_stage": None,
    }
    base.update(kwargs)

    with pytest.raises(ValueError):
        project_execution_progress(**base)
