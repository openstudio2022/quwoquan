# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-012
"""Article entity/title anchoring evidence for the pre-freeze source prescreen.

`REQ-007` splits `在场不足` into two sub-reasons that must stay distinguishable:
`已锚定到本实体但正文篇幅不足` and `可读但未锚定到本实体`.  The first one wins
when a candidate hits both, because it already proves that a source for this
entity exists.  These tests lock the raw evidence the entity-level aggregation
needs to make that split, and deliberately assert no ratio threshold value:
`OPEN-004` states the prescreen thresholds must come from a governed
calibration receipt rather than a default constant.
"""
from __future__ import annotations

import pytest
from content.execution.controller.content_plan_article_anchor import (
    ArticleEntityAnchor,
    assess_article_entity_anchor,
)

TARGET = "青城山"
ALIASES = ("青城山景区",)


def _assess(*, body: str, title: str) -> ArticleEntityAnchor:
    return assess_article_entity_anchor(
        body=body,
        title=title,
        target=TARGET,
        aliases=ALIASES,
    )


def test_canonical_title_with_prose_mention_is_present_and_available() -> None:
    """`在场可用` requires an anchored long-form candidate for this entity."""

    anchor = _assess(
        title=TARGET,
        body="青城山的前山步道从建福宫起步，沿途可以安排半天的慢行。",
    )

    assert anchor.eligible is True
    assert anchor.title_rank == 2
    assert anchor.body_mention_count >= 1


def test_alias_title_is_ranked_below_the_canonical_target_but_stays_eligible() -> None:
    """Aliases frozen in the target set anchor the title just like the target."""

    anchor = _assess(
        title="青城山景区两日游",
        body="青城山景区的后山水路适合避开人流，青城山前山则更适合半日游。",
    )

    assert anchor.eligible is True
    assert anchor.title_rank == 1


def test_editorial_title_stays_eligible_when_the_prose_anchors_independently() -> None:
    """A creative title must not disqualify a genuine target article."""

    anchor = _assess(
        title="蜀地寻幽记",
        body="青城山的道观群沿山势展开，青城山的雨雾让整条步道都安静下来。",
    )

    assert anchor.eligible is True
    assert anchor.title_rank == 0
    assert anchor.body_mention_count >= 2


def test_anchored_but_thin_prose_keeps_the_mention_evidence_for_its_sub_reason() -> None:
    """`已锚定到本实体但正文篇幅不足` must remain readable as anchored.

    A city-wide overview that lists the entity once is not admissible, but the
    assessment still has to prove the anchor exists so the entity-level rollup
    can pick the `篇幅不足` sub-reason instead of `不是本实体`.
    """

    overview = "成都周边的可选目的地很多。" * 40 + "青城山也在其中。"
    anchor = _assess(title="成都周边一日游全攻略", body=overview)

    assert anchor.eligible is False
    assert anchor.title_rank == 0
    assert anchor.body_mention_count >= 1


def test_readable_prose_without_any_target_mention_is_not_this_entity() -> None:
    """`可读但未锚定到本实体` must be a zero-mention outcome, not a thin one."""

    anchor = _assess(
        title="都江堰水利工程漫游",
        body="都江堰的鱼嘴、飞沙堰与宝瓶口构成了整套分水体系，步行一圈约两小时。",
    )

    assert anchor.eligible is False
    assert anchor.body_mention_count == 0


def test_the_two_present_but_insufficient_sub_reasons_stay_distinguishable() -> None:
    """`REQ-007` forbids the two `在场不足` sub-reasons from collapsing."""

    thin = _assess(
        title="成都周边一日游全攻略",
        body="成都周边的可选目的地很多。" * 40 + "青城山也在其中。",
    )
    unanchored = _assess(
        title="都江堰水利工程漫游",
        body="都江堰的鱼嘴、飞沙堰与宝瓶口构成了整套分水体系。" * 20,
    )

    assert thin.eligible is False
    assert unanchored.eligible is False
    assert thin.body_mention_count > unanchored.body_mention_count
    assert unanchored.body_mention_count == 0


def test_figure_captions_are_media_evidence_and_do_not_anchor_the_prose() -> None:
    """`正文篇幅` is prose; a caption naming the entity is media evidence."""

    body = (
        ":::figure\n"
        "青城山 青城山 青城山 青城山\n"
        ":::\n"
        "都江堰的分水堤在枯水期尤其清晰，沿岸步道可以走完全程。"
    )
    anchor = _assess(title="川西影像手记", body=body)

    assert anchor.eligible is False
    assert anchor.body_mention_count == 0


def test_grouped_figure_fences_are_removed_before_measuring_the_prose() -> None:
    """Grouped figure fences carry the same media-evidence semantics."""

    body = (
        ":::figuregroup\n"
        "青城山 青城山 青城山\n"
        ":::\n"
        "沿岸步道在枯水期尤其清晰。"
    )
    anchor = _assess(title="川西影像手记", body=body)

    assert anchor.body_mention_count == 0


def test_short_inferred_aliases_are_not_admitted_as_identity_tokens() -> None:
    """Only the canonical target and frozen aliases may anchor an article."""

    anchor = assess_article_entity_anchor(
        body="青的字样在这篇通稿里出现了很多次。" * 20,
        title="青",
        target="青",
        aliases=(),
    )

    assert anchor.eligible is False
    assert anchor.title_rank == 0
    assert anchor.body_mention_count == 0


def test_candidate_fields_expose_the_assessment_as_replayable_evidence() -> None:
    """`GWT-012` requires an operator-readable typed outcome, not a log line."""

    anchor = _assess(
        title=TARGET,
        body="青城山的前山步道从建福宫起步。",
    )
    fields = anchor.candidate_fields()

    assert fields["entityAnchorEligible"] is anchor.eligible
    assert fields["entityTitleAnchorRank"] == anchor.title_rank
    assert fields["entityBodyMentionCount"] == anchor.body_mention_count
    assert fields["entityAnchorScore"] == pytest.approx(
        anchor.body_anchor_ratio,
        abs=5e-7,
    )
    assert "titleRank=" in anchor.diagnostic()
    assert "mentions=" in anchor.diagnostic()
