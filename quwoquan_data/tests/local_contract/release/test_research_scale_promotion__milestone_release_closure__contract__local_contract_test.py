"""A milestone is attained by one immutable release proving its own closure.

The three cumulative milestones are fixed per carrier, and promotion has to satisfy
every carrier at once with zero shortfall. That leaves the interesting question of
where the count comes from: a promotion that trusted a declared number would let a
release claim attainment it cannot show objects for, and the receipt would then be
a statement about a spreadsheet rather than about a cohort. So the release's
header, desired state and asset admission must agree object for object, and the
counted population is the one the release can enumerate.

The targets are lower bounds, not caps. A cohort that overshoots promotes with its
real count and zero shortfall, because truncating a frontier to hit a round number
would throw away qualified objects. And capacity, provider, popularity and recovery
evidence stay diagnostics: none of them can move the count, so none of them can
decide attainment.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical.research_scale_promotion import (  # noqa: E402
    ResearchScalePromotionError,
)
from content.release.canonical.research_scale_promotion_release import (  # noqa: E402
    CARRIERS,
    ResearchMilestoneReleaseError,
    load_research_milestone_release,
)

from quwoquan_data.tests.support.m100_alpha_acceptance_fixture import (  # noqa: E402
    m100_targets,
    write_m100_milestone_release,
    write_m100_promotion,
)

RELEASE_ID = "research-m100"


def _load(output_root: Path):
    return load_research_milestone_release(
        output_root / "data/releases" / RELEASE_ID,
        release_id=RELEASE_ID,
        target_scale="M100",
    )


def _carrier_row(receipt: dict, carrier: str) -> dict:
    (row,) = [
        item for item in receipt["carrierCounts"] if item["carrier"] == carrier
    ]
    return row


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_the_m100_target_is_the_governed_hundred_hundred_hundred_ten() -> None:
    """The milestone is a governed number, not one each release picks."""

    assert m100_targets() == {
        "homepage": 100,
        "article": 100,
        "image": 100,
        "video": 10,
    }


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
def test_a_cohort_at_target_attains_the_milestone(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    write_m100_milestone_release(output_root, release_id=RELEASE_ID)

    milestone = _load(output_root)

    assert milestone.counts == m100_targets()
    assert {carrier: len(refs) for carrier, refs in milestone.refs_by_carrier.items()} == (
        m100_targets()
    )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_a_declared_count_cannot_stand_in_for_the_release_closure(
    tmp_path: Path,
) -> None:
    """Ninety-nine objects plus a claim of a hundred is a shortfall, not attainment."""

    output_root = tmp_path / "output"
    counts = {**m100_targets(), "homepage": 99}
    write_m100_milestone_release(
        output_root,
        release_id=RELEASE_ID,
        counts=counts,
        admission_overrides={
            "carrierCounts": [
                {
                    "carrier": carrier,
                    "researchAcceptedCount": (
                        100 if carrier == "homepage" else counts[carrier]
                    ),
                    "objectCount": 100 if carrier == "homepage" else counts[carrier],
                    "assetCount": counts["image"] if carrier == "image" else 0,
                    "commercialAcceptedCount": 0,
                }
                for carrier in CARRIERS
            ]
        },
    )

    with pytest.raises(ResearchMilestoneReleaseError, match="ATTAINMENT_SHORTFALL"):
        _load(output_root)


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_one_carrier_short_refuses_the_whole_milestone(tmp_path: Path) -> None:
    """Three carriers at target cannot pay for the fourth."""

    output_root = tmp_path / "output"
    write_m100_milestone_release(
        output_root,
        release_id=RELEASE_ID,
        counts={**m100_targets(), "video": 9},
    )

    with pytest.raises(ResearchMilestoneReleaseError) as failure:
        _load(output_root)

    assert "ATTAINMENT_SHORTFALL" in str(failure.value)
    assert "video" in str(failure.value)


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
def test_a_cohort_above_target_promotes_with_its_real_count(tmp_path: Path) -> None:
    """The milestone is a lower bound; overshooting is not truncated."""

    output_root = tmp_path / "output"
    counts = {**m100_targets(), "video": 20, "article": 140}
    write_m100_milestone_release(output_root, release_id=RELEASE_ID, counts=counts)

    receipt, _ = write_m100_promotion(output_root, release_id=RELEASE_ID)

    video = _carrier_row(receipt, "video")
    article = _carrier_row(receipt, "article")
    assert (video["totalUniqueFinalizedCount"], video["targetCount"]) == (20, 10)
    assert (article["totalUniqueFinalizedCount"], article["targetCount"]) == (140, 100)
    assert all(row["shortfallCount"] == 0 for row in receipt["carrierCounts"])
    assert {row["carrier"] for row in receipt["carrierCounts"]} == set(CARRIERS)


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_a_release_cannot_redefine_the_milestone_it_claims(tmp_path: Path) -> None:
    """The target is governed centrally, so a header cannot lower its own bar."""

    output_root = tmp_path / "output"
    write_m100_milestone_release(
        output_root,
        release_id=RELEASE_ID,
        header_overrides={
            "milestoneTargets": {**m100_targets(), "video": 1},
        },
    )

    with pytest.raises(ResearchMilestoneReleaseError, match="milestoneTargets"):
        _load(output_root)


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-001
def test_a_milestone_cohort_is_environment_neutral(tmp_path: Path) -> None:
    """Environment-targeted manifests truncate to a per-environment cap.

    A milestone cohort is the frozen population all four environments consume in
    turn, so one environment's truncated prefix cannot be promoted as the cohort.
    """

    output_root = tmp_path / "output"
    write_m100_milestone_release(
        output_root,
        release_id=RELEASE_ID,
        header_overrides={
            "selectionScope": "target_environment",
            "targetEnvironment": "alpha",
        },
        header_removals=("milestone", "milestoneTargets"),
    )

    with pytest.raises(
        ResearchMilestoneReleaseError, match="environment-neutral exact milestone"
    ):
        _load(output_root)


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_the_milestone_count_does_not_gate_on_a_predecessor_promotion(
    tmp_path: Path,
) -> None:
    """A predecessor receipt records lineage; M100 has none and still promotes."""

    output_root = tmp_path / "output"
    write_m100_milestone_release(output_root, release_id=RELEASE_ID)

    receipt, path = write_m100_promotion(output_root, release_id=RELEASE_ID)

    assert "predecessorPromotion" not in receipt
    assert receipt["targetScale"] == "M100"
    assert receipt["nextScaleEligible"] == "M1000"
    assert json.loads(path.read_text(encoding="utf-8")) == receipt


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
def test_capacity_and_popularity_evidence_cannot_decide_attainment(
    tmp_path: Path,
) -> None:
    """Absent soak and popularity evidence is reported, never counted.

    Attainment is a property of the object closure, so evidence that never
    entered the count cannot remove objects from it. The receipt still has to say
    the evidence was unavailable instead of implying it was fine.
    """

    output_root = tmp_path / "output"
    write_m100_milestone_release(output_root, release_id=RELEASE_ID)

    receipt, _ = write_m100_promotion(output_root, release_id=RELEASE_ID)

    popularity = receipt["statistics"]["videoPopularity"]
    assert popularity["nonBlocking"] is True
    assert popularity["statistical"] is True
    assert popularity["observationIssues"], (
        "unavailable popularity evidence must be reported rather than implied"
    )
    assert all(row["shortfallCount"] == 0 for row in receipt["carrierCounts"])
    assert "campaignEvidenceRef" not in receipt


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-004
def test_a_promotion_receipt_is_written_once(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    write_m100_milestone_release(output_root, release_id=RELEASE_ID)
    _, path = write_m100_promotion(output_root, release_id=RELEASE_ID)
    before = path.read_bytes()

    with pytest.raises(ResearchScalePromotionError, match="append-only"):
        write_m100_promotion(output_root, release_id=RELEASE_ID)

    assert path.read_bytes() == before
