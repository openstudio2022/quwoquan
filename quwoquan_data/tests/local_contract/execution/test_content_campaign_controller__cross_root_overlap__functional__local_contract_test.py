# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""Cross-root isolation for campaign submissions and lane execution roots.

`REQ-001` requires the controller to allocate an independent execution root,
queue namespace and staging prefix per active lane, and to fail closed on
collision.  `GWT-001` states that the active execution roots are mutually
isolated and that a submission collision leaves a blocked report rather than
silently joining a second campaign.

These tests exercise the collision guard and the lane execution-root resolver
directly, which is how neighbouring campaign tests lock the individual
fail-closed predicates of the submission freeze path.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.campaign import submission as campaign_submission
from content.execution.campaign.submission import campaign_root, submission_path
from content.execution.campaign.workspace import (
    CampaignRuntimePaths,
    lane_execution_root,
)
from core.io import write_json

ROOT_A = "20260728--travel-homepage-workload-homepage-1--china--scale-001"
ROOT_B = "20260729--travel-homepage-workload-homepage-1--china--scale-001"
CARRIERS = ("homepage", "article", "image", "video")


def _runtime(tmp_path: Path) -> CampaignRuntimePaths:
    output_root = tmp_path / "output"
    return CampaignRuntimePaths(
        repo_root=tmp_path / "repo",
        output_root=output_root,
        publish_root=tmp_path / "publish",
        campaigns_root=(
            output_root / "data/local/workspace/content-campaign-submissions"
        ),
        workspaces_root=output_root / "data/local/cache/campaign-workspaces",
    )


def _execution_id(carrier: str, *, sequence: str = "001") -> str:
    return f"20260728--travel-{carrier}-workload-{carrier}-1--china--scale-{sequence}"


def _place_submission(
    campaigns_dir: Path,
    *,
    root_execution_id: str,
    execution_id: str,
) -> Path:
    path = submission_path(root_execution_id, execution_id, root=campaigns_dir)
    write_json(path, {"rootExecutionId": root_execution_id, "executionId": execution_id})
    return path


def test_one_execution_may_not_be_claimed_by_a_second_campaign_root(
    tmp_path: Path,
) -> None:
    """A submission collision across campaign roots must fail closed."""

    campaigns_dir = tmp_path / "campaigns"
    execution_id = _execution_id("article")
    _place_submission(
        campaigns_dir,
        root_execution_id=ROOT_A,
        execution_id=execution_id,
    )

    with pytest.raises(ValueError, match="already belongs to campaign"):
        campaign_submission._assert_no_cross_campaign_collision(
            campaigns_dir=campaigns_dir,
            root_execution_id=ROOT_B,
            execution_id=execution_id,
        )


def test_the_owning_campaign_root_may_re_admit_its_own_execution(
    tmp_path: Path,
) -> None:
    """Idempotent replay inside the owning campaign is not a collision."""

    campaigns_dir = tmp_path / "campaigns"
    execution_id = _execution_id("article")
    _place_submission(
        campaigns_dir,
        root_execution_id=ROOT_A,
        execution_id=execution_id,
    )

    campaign_submission._assert_no_cross_campaign_collision(
        campaigns_dir=campaigns_dir,
        root_execution_id=ROOT_A,
        execution_id=execution_id,
    )


def test_the_collision_guard_names_the_conflicting_owner(tmp_path: Path) -> None:
    """The blocked report must identify the campaign that already owns it."""

    campaigns_dir = tmp_path / "campaigns"
    execution_id = _execution_id("image")
    _place_submission(
        campaigns_dir,
        root_execution_id=ROOT_A,
        execution_id=execution_id,
    )

    with pytest.raises(ValueError) as excinfo:
        campaign_submission._assert_no_cross_campaign_collision(
            campaigns_dir=campaigns_dir,
            root_execution_id=ROOT_B,
            execution_id=execution_id,
        )

    assert ROOT_A in str(excinfo.value)
    assert execution_id in str(excinfo.value)


def test_sibling_lanes_of_other_campaigns_do_not_collide(tmp_path: Path) -> None:
    """Only the same execution identity collides, not a neighbouring lane."""

    campaigns_dir = tmp_path / "campaigns"
    for carrier in ("article", "image", "video"):
        _place_submission(
            campaigns_dir,
            root_execution_id=ROOT_A,
            execution_id=_execution_id(carrier),
        )

    campaign_submission._assert_no_cross_campaign_collision(
        campaigns_dir=campaigns_dir,
        root_execution_id=ROOT_B,
        execution_id=_execution_id("article", sequence="002"),
    )


def test_an_empty_campaign_tree_reports_no_collision(tmp_path: Path) -> None:
    """An absent submission tree is present-and-empty, not a failure."""

    campaign_submission._assert_no_cross_campaign_collision(
        campaigns_dir=tmp_path / "campaigns",
        root_execution_id=ROOT_A,
        execution_id=_execution_id("article"),
    )


def test_campaign_roots_are_disjoint_directories(tmp_path: Path) -> None:
    """Two campaigns never share a submission directory."""

    campaigns_dir = tmp_path / "campaigns"
    first = campaign_root(ROOT_A, root=campaigns_dir)
    second = campaign_root(ROOT_B, root=campaigns_dir)

    assert first != second
    assert first.parent == second.parent == campaigns_dir


def test_every_active_lane_gets_its_own_execution_root(tmp_path: Path) -> None:
    """`REQ-001` allocates one independent execution root per active lane."""

    runtime = _runtime(tmp_path)
    roots = {
        carrier: lane_execution_root(runtime, _execution_id(carrier))
        for carrier in CARRIERS
    }

    assert len(set(roots.values())) == len(CARRIERS)
    for carrier, root in roots.items():
        assert root.name == _execution_id(carrier)
        assert root.parent == (runtime.output_root / "data" / "tasks").resolve()


def test_lane_execution_roots_never_nest_inside_each_other(tmp_path: Path) -> None:
    """Nested roots would let one lane observe or clobber another lane."""

    runtime = _runtime(tmp_path)
    roots = [
        lane_execution_root(runtime, _execution_id(carrier)) for carrier in CARRIERS
    ]

    for outer in roots:
        for inner in roots:
            if outer == inner:
                continue
            assert outer not in inner.parents


def test_two_campaigns_never_share_a_lane_execution_root(tmp_path: Path) -> None:
    """A different sequence is a different execution and a different root."""

    runtime = _runtime(tmp_path)

    assert lane_execution_root(
        runtime,
        _execution_id("article", sequence="001"),
    ) != lane_execution_root(runtime, _execution_id("article", sequence="002"))


def test_a_lane_execution_root_may_not_escape_the_output_root(
    tmp_path: Path,
) -> None:
    """A traversing execution id must not resolve outside the governed tree."""

    runtime = _runtime(tmp_path)

    with pytest.raises(ValueError):
        lane_execution_root(runtime, "../escaped")


def test_submission_paths_are_unique_per_root_and_execution(tmp_path: Path) -> None:
    """The submission file is the create-once identity of one lane."""

    campaigns_dir = tmp_path / "campaigns"
    paths = {
        submission_path(root, _execution_id(carrier), root=campaigns_dir)
        for root in (ROOT_A, ROOT_B)
        for carrier in CARRIERS
    }

    assert len(paths) == 2 * len(CARRIERS)
