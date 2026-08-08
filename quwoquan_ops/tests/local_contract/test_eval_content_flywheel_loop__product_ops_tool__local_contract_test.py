#!/usr/bin/env python3
"""Unit tests for eval_content_flywheel_loop.evaluate_flywheel (pure, no Mongo).

Run: python3 -m pytest quwoquan_ops/tests/local_contract/test_eval_content_flywheel_loop__product_ops_tool__local_contract_test.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "eval_content_flywheel_loop",
    _ROOT
    / "quwoquan_service/scripts/product-ops-service/tools/eval_content_flywheel_loop.py",
)
flywheel = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(flywheel)


def _feature(uid, *, has_features=True, segments_updated=True, segments=("foodie",)):
    return {
        "userId": uid,
        "hasFeatures": has_features,
        "segmentsUpdated": segments_updated,
        "segments": list(segments),
    }


def _profile(uid, *, has_interests=True, lifecycle="active", segments=("foodie",)):
    return {
        "userId": uid,
        "hasInterests": has_interests,
        "lifecycleStage": lifecycle,
        "segments": list(segments),
    }


def _proactive(
    uid,
    *,
    personalized=True,
    interest_tags=("Topic/coffee",),
    matched_segments=("foodie",),
    lifecycle="active",
):
    return {
        "userId": uid,
        "personalized": personalized,
        "interestTags": list(interest_tags),
        "matchedSegments": list(matched_segments),
        "lifecycleStage": lifecycle,
    }


def test_fully_closed_loop_is_closed():
    features = [_feature("u1"), _feature("u2", segments=("foodie", "traveler"))]
    profiles = [_profile("u1"), _profile("u2", segments=("foodie", "traveler"))]
    proactive = [_proactive("u1"), _proactive("u2", matched_segments=("foodie", "traveler"))]
    report = flywheel.evaluate_flywheel(
        features, profiles, learning_event_count=42, proactive_messages=proactive
    )

    assert report["verdict"] == "closed"
    assert report["failingStages"] == []
    assert report["summary"]["interestCoverageRate"] == 1.0
    assert report["summary"]["segmentConsistencyRate"] == 1.0
    assert report["stages"]["proactive_consumption"]["withProfileEvidenceCount"] == 2
    assert report["stages"]["proactive_consumption"]["linkedToProfileRate"] == 1.0
    assert all(report["stages"][name]["ok"] for name in flywheel.CRITICAL_STAGES)


def test_missing_segment_backfill_breaks_loop():
    # 派生作业从未回写 segments（segmentsUpdatedAt 缺失）→ 中段断裂。
    features = [_feature("u1", segments_updated=False, segments=())]
    profiles = [_profile("u1", segments=())]
    report = flywheel.evaluate_flywheel(features, profiles, learning_event_count=5)

    assert report["verdict"] == "broken"
    assert "features_to_segments" in report["failingStages"]
    assert report["stages"]["features_to_segments"]["ok"] is False


def test_segment_inconsistency_across_projections_breaks_loop():
    # 同一用户在宽表与画像两路 segments 不一致 → CQRS 单源被破坏。
    features = [_feature("u1", segments=("foodie",))]
    profiles = [_profile("u1", segments=("traveler",))]
    report = flywheel.evaluate_flywheel(
        features, profiles, learning_event_count=5, min_segment_consistency=0.99
    )

    assert report["stages"]["segment_cqrs_consistency"]["ok"] is False
    assert report["stages"]["segment_cqrs_consistency"]["overlapUsers"] == 1
    assert report["summary"]["segmentConsistencyRate"] == 0.0
    assert "segment_cqrs_consistency" in report["failingStages"]


def test_no_overlap_does_not_fail_consistency():
    # 两路投影无共同用户 → 一致性无法比对，不应误判 broken。
    features = [_feature("u1")]
    profiles = [_profile("u2")]
    report = flywheel.evaluate_flywheel(features, profiles, learning_event_count=5)

    stage = report["stages"]["segment_cqrs_consistency"]
    assert stage["ok"] is True
    assert stage["overlapUsers"] == 0
    assert report["summary"]["segmentConsistencyRate"] == 1.0


def test_no_feedback_events_breaks_loop():
    features = [_feature("u1")]
    profiles = [_profile("u1")]
    report = flywheel.evaluate_flywheel(features, profiles, learning_event_count=0)

    assert report["stages"]["feedback_events"]["ok"] is False
    assert "feedback_events" in report["failingStages"]
    assert report["verdict"] == "broken"


def test_empty_inputs_are_broken_not_crash():
    report = flywheel.evaluate_flywheel([], [], learning_event_count=0)
    assert report["verdict"] == "broken"
    # 关键分段除一致性外应全部失败（一致性因空交集为真）。
    assert set(report["failingStages"]) == {
        "behavior_to_features",
        "features_to_segments",
        "interest_projection",
        "feedback_events",
        "proactive_consumption",
    }


def test_interest_coverage_rate_partial():
    features = [_feature("u1"), _feature("u2")]
    profiles = [
        _profile("u1", has_interests=True),
        _profile("u2", has_interests=False),
    ]
    report = flywheel.evaluate_flywheel(features, profiles, learning_event_count=3)
    assert report["summary"]["interestCoverageRate"] == 0.5
    # 仍有覆盖（>0）→ 投影分段判定为闭合。
    assert report["stages"]["interest_projection"]["ok"] is True


def test_proactive_personalized_with_evidence_closes_loop():
    # 飞轮末端：画像被主动消费，主动消息带派生 tags/segments 且用户有画像投影。
    features = [_feature("u1")]
    profiles = [_profile("u1")]
    proactive = [_proactive("u1")]
    report = flywheel.evaluate_flywheel(
        features, profiles, learning_event_count=3, proactive_messages=proactive
    )
    stage = report["stages"]["proactive_consumption"]
    assert stage["ok"] is True
    assert stage["withProfileEvidenceCount"] == 1
    assert stage["linkedToProfileRate"] == 1.0
    assert "proactive_consumption" not in report["failingStages"]


def test_proactive_without_personalization_breaks_loop():
    # 有主动消息但从未个性化（画像没被消费）→ 末端断裂。
    features = [_feature("u1")]
    profiles = [_profile("u1")]
    proactive = [_proactive("u1", personalized=False)]
    report = flywheel.evaluate_flywheel(
        features, profiles, learning_event_count=3, proactive_messages=proactive
    )
    stage = report["stages"]["proactive_consumption"]
    assert stage["ok"] is False
    assert stage["personalizedCount"] == 0
    assert "proactive_consumption" in report["failingStages"]
    assert report["verdict"] == "broken"


def test_proactive_personalized_but_no_profile_evidence_breaks_loop():
    # personalized 为真但无 interestProfile 派生证据(tags/segments)→ 视为空断言，不算闭合。
    features = [_feature("u1")]
    profiles = [_profile("u1")]
    proactive = [_proactive("u1", interest_tags=(), matched_segments=())]
    report = flywheel.evaluate_flywheel(
        features, profiles, learning_event_count=3, proactive_messages=proactive
    )
    stage = report["stages"]["proactive_consumption"]
    assert stage["ok"] is False
    assert stage["withProfileEvidenceCount"] == 0
    assert "proactive_consumption" in report["failingStages"]


def test_proactive_evidence_user_without_profile_lowers_linked_rate():
    # 主动消息带证据，但该用户在画像投影里不存在 → linkedToProfileRate 暴露断链。
    features = [_feature("u1")]
    profiles = [_profile("u1")]
    proactive = [_proactive("ghost_user")]
    report = flywheel.evaluate_flywheel(
        features, profiles, learning_event_count=3, proactive_messages=proactive
    )
    stage = report["stages"]["proactive_consumption"]
    # 仍有证据 → stage ok；但 linkedToProfileRate=0 暴露用户与画像未对齐。
    assert stage["ok"] is True
    assert stage["withProfileEvidenceCount"] == 1
    assert stage["linkedToProfileRate"] == 0.0
