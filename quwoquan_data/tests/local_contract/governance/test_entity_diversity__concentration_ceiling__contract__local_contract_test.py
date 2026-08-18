"""Cross-execution entity diversity caps and Top-N concentration.

The catalog drifted to 34 entities concentrated in two provinces because nothing
counted an entity's output across executions. These cases lock the per-entity
cap, the Top-N share ceiling, the explicit-evidence requirement on a raised cap,
and the property that an already-concentrated catalog can still be repaired.
"""
from __future__ import annotations

import pytest

from governance.coverage.entity_diversity import (
    CARRIERS,
    EntityDiversityError,
    EntityDiversityPolicy,
    HotEntityAllowance,
    admit_diverse_entities,
    load_content_diversity_policy,
)


def _allowance(**overrides) -> HotEntityAllowance:
    kwargs = {
        "entity_ref": "entity/hot",
        "caps": (("article", 12),),
        "signal": "12 distinct primary authorities",
        "observed_at": "2026-08-16",
        "reviewer": "governance/coverage",
        "justification": "province-level hub with independent authorities",
    }
    kwargs.update(overrides)
    return HotEntityAllowance(**kwargs)


def _policy(**overrides) -> EntityDiversityPolicy:
    base = {
        "policy_id": "test-diversity",
        "default_caps": (
            ("homepage", 1),
            ("article", 4),
            ("image", 6),
            ("video", 3),
        ),
        "top_entity_count": 5,
        "top_entity_share_ceiling": 0.5,
        "minimum_cumulative_objects": 20,
        "hot_entities": (),
    }
    base.update(overrides)
    return EntityDiversityPolicy(**base)


def test_shipped_policy_loads_and_bounds_every_carrier() -> None:
    policy = load_content_diversity_policy()

    for carrier in CARRIERS:
        assert policy.entity_cap("entity/any", carrier=carrier) >= 1
    assert 0 < policy.top_entity_share_ceiling <= 1
    assert policy.minimum_cumulative_objects >= 1


def test_per_entity_cap_counts_cumulatively_across_executions() -> None:
    admission = admit_diverse_entities(
        ("entity/a", "entity/b"),
        carrier="article",
        cumulative_counts={"entity/a": 4, "entity/b": 1},
        policy=_policy(),
    )

    assert admission.admitted == ("entity/b",)
    assert [ref for ref, _reason in admission.entity_cap_rejected] == ["entity/a"]


def test_repeated_candidate_consumes_its_own_remaining_cap() -> None:
    admission = admit_diverse_entities(
        ("entity/a",) * 3,
        carrier="article",
        cumulative_counts={"entity/a": 2},
        policy=_policy(),
    )

    assert admission.admitted == ("entity/a", "entity/a")
    assert len(admission.entity_cap_rejected) == 1


def test_top_n_ceiling_blocks_further_piling_onto_the_leaders() -> None:
    leaders = {"entity/a": 6, "entity/b": 5, "entity/c": 4, "entity/d": 3, "entity/e": 3}
    tail = {f"entity/t{index}": 1 for index in range(20)}
    counts = {**leaders, **tail}
    policy = _policy()

    assert policy.top_entity_share(counts) > policy.top_entity_share_ceiling

    admission = admit_diverse_entities(
        ("entity/c",),
        carrier="image",
        cumulative_counts=counts,
        policy=policy,
    )

    assert admission.admitted == ()
    assert [ref for ref, _reason in admission.concentration_rejected] == ["entity/c"]


def test_concentration_gate_is_dormant_below_the_minimum_sample() -> None:
    admission = admit_diverse_entities(
        ("entity/a", "entity/a"),
        carrier="image",
        cumulative_counts={"entity/a": 1},
        policy=_policy(minimum_cumulative_objects=20),
    )

    assert admission.admitted == ("entity/a", "entity/a")
    assert admission.concentration_rejected == ()


def test_concentration_gate_is_dormant_while_the_population_is_within_top_n() -> None:
    # With five or fewer entities the top-5 share is 1.0 however the objects are
    # spread, so it cannot distinguish concentrated from diverse.
    policy = _policy(top_entity_count=5)
    counts = {f"entity/{index}": 8 for index in range(4)}

    assert policy.top_entity_share(counts) == 1.0
    assert not policy.concentration_exceeded(counts)


def test_an_already_concentrated_catalog_still_admits_tail_entities() -> None:
    # A ceiling that rejects everything once breached would deadlock the catalog
    # in exactly the state the constraint exists to escape.
    counts = {"entity/a": 20, "entity/b": 18}

    admission = admit_diverse_entities(
        ("entity/new",),
        carrier="image",
        cumulative_counts=counts,
        policy=_policy(),
    )

    assert admission.admitted == ("entity/new",)


def test_hot_entity_allowance_raises_only_its_declared_carrier() -> None:
    policy = _policy(hot_entities=(_allowance(),))

    assert policy.entity_cap("entity/hot", carrier="article") == 12
    assert policy.entity_cap("entity/hot", carrier="image") == 6
    assert policy.entity_cap("entity/other", carrier="article") == 4


@pytest.mark.parametrize(
    "field",
    ["signal", "observed_at", "reviewer", "justification"],
)
def test_a_raised_cap_without_its_evidence_is_rejected(field: str) -> None:
    with pytest.raises(EntityDiversityError):
        _allowance(**{field: "   "})


def test_an_allowance_that_only_restates_the_default_is_rejected() -> None:
    with pytest.raises(EntityDiversityError):
        _policy(hot_entities=(_allowance(caps=(("article", 4),)),))


def test_an_allowance_naming_an_unknown_carrier_is_rejected() -> None:
    with pytest.raises(EntityDiversityError):
        _policy(hot_entities=(_allowance(caps=(("podcast", 9),)),))


def test_policy_missing_a_carrier_is_a_failure_not_an_unbounded_default() -> None:
    with pytest.raises(EntityDiversityError):
        _policy(default_caps=(("homepage", 1), ("article", 4)))


def test_unknown_carrier_lookup_fails_instead_of_defaulting() -> None:
    with pytest.raises(EntityDiversityError):
        _policy().entity_cap("entity/a", carrier="podcast")


def test_blank_candidate_ref_is_a_failure_not_a_silent_skip() -> None:
    with pytest.raises(EntityDiversityError):
        admit_diverse_entities(
            ("  ",),
            carrier="article",
            cumulative_counts={},
            policy=_policy(),
        )


def test_admission_report_names_both_rejection_reasons_separately() -> None:
    report = admit_diverse_entities(
        ("entity/a", "entity/b"),
        carrier="article",
        cumulative_counts={"entity/a": 4},
        policy=_policy(),
    ).report()

    assert report["admittedCount"] == 1
    assert report["entityCapRejectedCount"] == 1
    assert report["concentrationRejectedCount"] == 0
    assert report["entityCapRejected"][0]["entityRef"] == "entity/a"
