# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""Explicit active workloads for one coordinated campaign.

`REQ-001` states that the active executions of one request form mutually
independent, separately schedulable workloads, that the scheduler may run them
serially or overlapped, and that a fixed four-lane concurrency must never be a
precondition for submission, dispatch, object admission or promotion.
`campaign-freeze` levels the immutable submissions of exactly this request's
explicit active workload, and `campaign-finalize` aggregates only the create-once
receipts of the workloads that were actually active — so no hidden lane may
appear and no quota may be defaulted in from a sibling field (`GWT-009`).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.planning.carrier_demand import (
    CAMPAIGN_CARRIERS,
    normalize_active_carriers,
    normalize_workloads,
)
from content.execution.campaign.plan import write_report
from content.execution.campaign.plan_lane_state import empty_lane
from content.execution.campaign.workspace import CampaignRuntimePaths
from core.io import read_json


def _runtime(tmp_path: Path) -> CampaignRuntimePaths:
    return CampaignRuntimePaths(
        repo_root=tmp_path / "repo",
        output_root=tmp_path / "output",
        publish_root=tmp_path / "publish",
        campaigns_root=tmp_path / "campaigns",
        workspaces_root=tmp_path / "workspaces",
    )


def _write_article_report(
    tmp_path: Path,
    *,
    lanes: dict[str, dict[str, object]],
) -> Path:
    return write_report(
        _runtime(tmp_path),
        "20260822--travel-article-workload--china--scale-001",
        status="awaiting_submissions",
        phase="submission",
        plan_digest=None,
        git_branch=None,
        git_commit_sha=None,
        source_digest=None,
        entity_catalog_digest=None,
        lanes=lanes,
        started_at="2026-08-22T00:00:00+00:00",
        failure=None,
        active_carriers=("article",),
        workloads={"article": 1},
    )


def test_campaign_report_accepts_exact_single_article_lane(tmp_path: Path) -> None:
    path = _write_article_report(
        tmp_path,
        lanes={"article": empty_lane("article-execution")},
    )

    report = read_json(path)
    assert report["activeCarriers"] == ["article"]
    assert report["workloads"] == {"article": 1}
    assert set(report["lanes"]) == {"article"}


@pytest.mark.parametrize(
    "lanes",
    [
        {},
        {
            "article": empty_lane("article-execution"),
            "video": empty_lane("hidden-video-execution"),
        },
    ],
)
def test_campaign_report_rejects_lane_set_different_from_active_workload(
    tmp_path: Path,
    lanes: dict[str, dict[str, object]],
) -> None:
    with pytest.raises(
        ValueError,
        match="campaign report lanes must exactly match active carriers",
    ):
        _write_article_report(tmp_path, lanes=lanes)


def test_the_four_carriers_are_the_closed_canonical_order() -> None:
    """The carrier closed set and its canonical order are frozen."""

    assert CAMPAIGN_CARRIERS == ("homepage", "article", "image", "video")


@pytest.mark.parametrize("carrier", CAMPAIGN_CARRIERS)
def test_a_single_carrier_is_a_legal_active_workload(carrier: str) -> None:
    """A fixed four-lane workload is not a precondition for submission."""

    assert normalize_active_carriers([carrier]) == (carrier,)


def test_a_two_carrier_active_workload_is_legal() -> None:
    """Any non-empty carrier subset may be the explicit active workload."""

    assert normalize_active_carriers(["video", "article"]) == ("article", "video")


def test_active_carriers_are_returned_in_canonical_order() -> None:
    """Request order must not become a second ordering truth source."""

    assert normalize_active_carriers(
        ["video", "homepage", "image", "article"]
    ) == CAMPAIGN_CARRIERS


def test_an_empty_active_workload_fails_closed() -> None:
    """An absent active workload may not collapse into an implicit four lanes."""

    with pytest.raises(ValueError, match="at least one active carrier"):
        normalize_active_carriers([])


def test_a_repeated_carrier_fails_closed() -> None:
    """One carrier is one lane; a repeat would double-claim its execution."""

    with pytest.raises(ValueError, match="must be unique"):
        normalize_active_carriers(["article", "article"])


def test_an_unknown_carrier_fails_closed() -> None:
    """No hidden lane may enter the frozen active workload."""

    with pytest.raises(ValueError, match="active carriers are invalid"):
        normalize_active_carriers(["article", "podcast"])


def test_surrounding_whitespace_is_normalized_not_treated_as_a_new_carrier() -> None:
    """Carrier identity is exact; whitespace is not part of it."""

    assert normalize_active_carriers([" article ", "video\n"]) == ("article", "video")


def test_workloads_must_exactly_match_the_explicit_active_carriers() -> None:
    """`campaign-freeze` levels submissions for exactly this active workload."""

    assert normalize_workloads(
        {"video": 10, "article": 100},
        active_carriers=["article", "video"],
    ) == {"article": 100, "video": 10}


def test_a_workload_without_a_matching_active_carrier_fails_closed() -> None:
    """An extra quota row would finalize a lane that was never active."""

    with pytest.raises(ValueError, match="must exactly match active carriers"):
        normalize_workloads(
            {"article": 100, "image": 100},
            active_carriers=["article"],
        )


def test_an_active_carrier_without_a_workload_fails_closed() -> None:
    """A missing quota may not be defaulted in from another carrier."""

    with pytest.raises(ValueError, match="must exactly match active carriers"):
        normalize_workloads(
            {"article": 100},
            active_carriers=["article", "image"],
        )


def test_workloads_derive_their_own_active_carriers_when_not_given() -> None:
    """The quota map alone is a complete explicit active workload."""

    assert normalize_workloads({"video": 10, "homepage": 100}) == {
        "homepage": 100,
        "video": 10,
    }


def test_each_carrier_carries_its_own_independent_object_floor() -> None:
    """Per-carrier quotas are independent; one lane never rewrites another."""

    normalized = normalize_workloads(
        {"homepage": 100, "article": 100, "image": 100, "video": 10}
    )

    assert normalized == {
        "homepage": 100,
        "article": 100,
        "image": 100,
        "video": 10,
    }
    assert list(normalized) == list(CAMPAIGN_CARRIERS)


@pytest.mark.parametrize("quota", [0, -1, -100])
def test_a_non_positive_quota_fails_closed(quota: int) -> None:
    """An object floor of zero is not an active workload."""

    with pytest.raises(ValueError, match="workload quota must be positive"):
        normalize_workloads({"article": quota})


@pytest.mark.parametrize("quota", [True, False])
def test_a_boolean_quota_fails_closed(quota: object) -> None:
    """A boolean must not be coerced into an object floor."""

    with pytest.raises(ValueError, match="workload quota must be positive"):
        normalize_workloads({"article": quota})  # type: ignore[dict-item]


@pytest.mark.parametrize("quota", [1.0, "100", None, [100]])
def test_a_non_integer_quota_fails_closed(quota: object) -> None:
    """The object floor is a governed integer, never a coerced scalar."""

    with pytest.raises(ValueError, match="workload quota must be positive"):
        normalize_workloads({"article": quota})  # type: ignore[dict-item]


def test_an_empty_workload_map_fails_closed() -> None:
    """Present-and-empty quotas are not a campaign; they fail closed."""

    with pytest.raises(ValueError, match="at least one active carrier"):
        normalize_workloads({})


def test_normalization_is_idempotent_for_replayed_freeze() -> None:
    """Repeating `campaign-freeze` must observe the same frozen workload."""

    first = normalize_workloads({"video": 10, "article": 100})
    second = normalize_workloads(first)

    assert first == second
    assert normalize_active_carriers(first) == normalize_active_carriers(second)
