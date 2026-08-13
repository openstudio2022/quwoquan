"""Ranking contract for the canonical deterministic rule scorer.

rule_score 是全部 content-feed ranker 的安全底座（realtime-feed-baseline
REQ-002：模型上线必须能一键回退到规则），当前生产实验策略下也是 100% 主打
路径。本合同固化其可解释语义：权重构成、互动信号相对强度、时间衰减半衰期、
单调性与确定性。任何改动这些语义的实现变更必须先改本合同与所属规格。
"""
# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/realtime-feed-baseline/spec.md#req-002
# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/time-decay-contextual-ranking/spec.md#gwt-001
import math

import pytest

from internal.recommendation.recommendation_model_release.application.rule_scoring import (
    rule_score,
)


def _features(**overrides) -> dict:
    base = {
        "viewCount": 0,
        "likeCount": 0,
        "commentCount": 0,
        "shareCount": 0,
        "ageHours": 0.0,
    }
    base.update(overrides)
    return base


def test_total_is_popularity_60_freshness_40() -> None:
    total, parts = rule_score(_features(likeCount=10, ageHours=12.0))
    assert parts["total"] == pytest.approx(
        parts["popularity"] * 0.6 + parts["freshness"] * 0.4
    )
    assert total == parts["total"]


def test_popularity_formula_is_log1p_of_weighted_engagement() -> None:
    _, parts = rule_score(
        _features(viewCount=100, likeCount=10, commentCount=4, shareCount=2)
    )
    assert parts["popularity"] == pytest.approx(
        math.log1p(100 * 0.1 + 10 + 4 * 1.5 + 2 * 2.0)
    )


def test_engagement_signal_strength_share_over_comment_over_like_over_view() -> None:
    # 同样 +1 个单位，边际贡献按合同权重排序：share(2.0) > comment(1.5) > like(1.0) > view(0.1)。
    baseline, _ = rule_score(_features(viewCount=10, likeCount=5))
    by_share, _ = rule_score(_features(viewCount=10, likeCount=5, shareCount=1))
    by_comment, _ = rule_score(_features(viewCount=10, likeCount=5, commentCount=1))
    by_like, _ = rule_score(_features(viewCount=10, likeCount=6))
    by_view, _ = rule_score(_features(viewCount=11, likeCount=5))
    assert by_share > by_comment > by_like > by_view > baseline


def test_freshness_decay_half_life_semantics() -> None:
    _, at_zero = rule_score(_features(likeCount=1, ageHours=0.0))
    _, at_day = rule_score(_features(likeCount=1, ageHours=24.0))
    _, at_two_days = rule_score(_features(likeCount=1, ageHours=48.0))
    assert at_zero["freshness"] == pytest.approx(1.0)
    assert at_day["freshness"] == pytest.approx(math.exp(-1.0))
    assert at_two_days["freshness"] == pytest.approx(math.exp(-2.0))
    assert at_zero["freshness"] > at_day["freshness"] > at_two_days["freshness"]


def test_score_is_monotonic_in_every_positive_engagement_signal() -> None:
    base_features = _features(
        viewCount=50, likeCount=5, commentCount=2, shareCount=1, ageHours=6.0
    )
    baseline, _ = rule_score(dict(base_features))
    for field in ("viewCount", "likeCount", "commentCount", "shareCount"):
        bumped_features = dict(base_features)
        bumped_features[field] = bumped_features[field] + 1
        bumped, _ = rule_score(bumped_features)
        assert bumped > baseline, f"increasing {field} must not decrease the score"


def test_older_content_never_outranks_identical_fresher_content() -> None:
    fresher, _ = rule_score(_features(likeCount=5, ageHours=1.0))
    older, _ = rule_score(_features(likeCount=5, ageHours=30.0))
    assert fresher > older


def test_zero_engagement_scores_freshness_floor_only() -> None:
    total, parts = rule_score(_features())
    assert parts["popularity"] == pytest.approx(0.0)
    assert parts["freshness"] == pytest.approx(1.0)
    assert total == pytest.approx(0.4)


def test_deterministic_for_identical_input() -> None:
    features = _features(
        viewCount=123, likeCount=45, commentCount=6, shareCount=7, ageHours=13.5
    )
    first = rule_score(dict(features))
    second = rule_score(dict(features))
    assert first == second


def test_negative_age_clamps_to_now() -> None:
    # 时钟漂移或未来 publishedAt 不得产生超额 freshness。
    _, parts = rule_score(_features(likeCount=1, ageHours=-5.0))
    assert parts["freshness"] == pytest.approx(1.0)


def test_missing_fields_default_to_zero_not_error() -> None:
    total, parts = rule_score({})
    assert parts["popularity"] == pytest.approx(0.0)
    assert total == pytest.approx(0.4)
