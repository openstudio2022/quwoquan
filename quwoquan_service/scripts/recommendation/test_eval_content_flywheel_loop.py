#!/usr/bin/env python3
"""Unit tests for eval_content_flywheel_loop.evaluate_flywheel (pure, no Mongo).

Run: python3 -m pytest quwoquan_service/scripts/recommendation/test_eval_content_flywheel_loop.py
"""
from __future__ import annotations

import importlib.util
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "eval_content_flywheel_loop", os.path.join(_HERE, "eval_content_flywheel_loop.py")
)
flywheel = importlib.util.module_from_spec(_SPEC)
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


def test_fully_closed_loop_is_closed():
    features = [_feature("u1"), _feature("u2", segments=("foodie", "traveler"))]
    profiles = [_profile("u1"), _profile("u2", segments=("foodie", "traveler"))]
    report = flywheel.evaluate_flywheel(features, profiles, learning_event_count=42)

    assert report["verdict"] == "closed"
    assert report["failingStages"] == []
    assert report["summary"]["interestCoverageRate"] == 1.0
    assert report["summary"]["segmentConsistencyRate"] == 1.0
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
