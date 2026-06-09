#!/usr/bin/env python3
"""
内容飞轮大循环实证（端云数据面闭环校验）。

跨 content / user 两个 Mongo 库读取大循环各环节真相源，逐段断言"行为反馈 →
兴趣/人群画像派生 → 双路 CQRS 投影 → 引擎可定向"这条链路是否真实闭合，并产出
飞轮评估报告（JSON）。与 Prometheus dashboard 互补：dashboard 看实时吞吐/归因，
本脚本看存量数据的"闭环完整性 + 跨投影一致性"，供运营飞轮实证与回归对照。

校验的真相源集合：
  - content 库   rm_recommend_feature   行为归一后的 userFeatures + 顶层 segments($set 回写)
  - content 库   rec_learning_events    反馈事件（大循环燃料）
  - user 库      rm_user_profile_view   interestProfile + segments（对外画像单一真相源）
  - assistant 库 app_messages           主动触达消息 + 个性化归因(interestTags/matchedSegments)

闭环分段（loop stages）：
  1. behavior_to_features      行为 → rm_recommend_feature.userFeatures 已落库
  2. features_to_segments      content 派生后把 segments $set 回写宽表（segmentsUpdatedAt 标记）
  3. interest_projection       UserInterestRecomputed 投影出 user 域 interestProfile
  4. segment_cqrs_consistency  同一用户在宽表与画像两路投影的 segments 一致（单一 MatchSegments 计算源）
  5. feedback_events           反馈事件已记录（闭环可持续）
  6. proactive_consumption     画像被小艺主动消费：主动消息引用 interestProfile 派生 tags/segments 并落库可审计

用法：
  python3 scripts/recommendation/eval_content_flywheel_loop.py
  python3 scripts/recommendation/eval_content_flywheel_loop.py --output flywheel.json
  python3 scripts/recommendation/eval_content_flywheel_loop.py --require-closed-loop          # 闭环未闭合 exit 1
  python3 scripts/recommendation/eval_content_flywheel_loop.py --min-segment-consistency 0.99 # 跨投影一致性门禁
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

CONTENT_FEATURE_COLLECTION = "rm_recommend_feature"
CONTENT_LEARNING_COLLECTION = "rec_learning_events"
USER_PROFILE_COLLECTION = "rm_user_profile_view"
ASSISTANT_APP_MESSAGE_COLLECTION = "app_messages"

CRITICAL_STAGES = (
    "behavior_to_features",
    "features_to_segments",
    "interest_projection",
    "segment_cqrs_consistency",
    "feedback_events",
    "proactive_consumption",
)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def evaluate_flywheel(
    features: list[dict],
    profiles: list[dict],
    learning_event_count: int,
    *,
    proactive_messages: list[dict] | None = None,
    min_segment_consistency: float = 0.99,
) -> dict:
    """纯函数：对已抽取的扁平输入计算飞轮闭环报告。

    features: [{userId, hasFeatures(bool), segmentsUpdated(bool), segments:[str]}]
    profiles: [{userId, hasInterests(bool), lifecycleStage(str), segments:[str]}]
    proactive_messages: [{userId, personalized(bool), interestTags:[str],
                          matchedSegments:[str], lifecycleStage:str}]
    """
    now = datetime.now(timezone.utc)
    proactive_messages = proactive_messages or []

    feature_count = len(features)
    feature_with_features = sum(1 for f in features if f.get("hasFeatures"))
    feature_with_segments_updated = sum(1 for f in features if f.get("segmentsUpdated"))
    feature_with_segments = sum(1 for f in features if f.get("segments"))

    profile_count = len(profiles)
    profile_with_interests = sum(1 for p in profiles if p.get("hasInterests"))
    lifecycle = {"new": 0, "active": 0, "dormant": 0, "unknown": 0}
    for p in profiles:
        stage = p.get("lifecycleStage") or "unknown"
        lifecycle[stage] = lifecycle.get(stage, 0) + 1

    # 跨投影 segment 一致性：取两路投影都存在的用户交集，比较 segment 集合。
    feature_segments = {
        f["userId"]: set(f.get("segments") or [])
        for f in features
        if f.get("userId")
    }
    overlap = 0
    consistent = 0
    for p in profiles:
        uid = p.get("userId")
        if uid is None or uid not in feature_segments:
            continue
        overlap += 1
        if set(p.get("segments") or []) == feature_segments[uid]:
            consistent += 1
    consistency_rate = _rate(consistent, overlap) if overlap else 1.0

    interest_coverage = _rate(profile_with_interests, profile_count)

    # 飞轮末端：画像被小艺主动消费。主动消息须 personalized 且带 interestProfile
    # 派生证据(tags/segments)，且其用户确有画像投影（闭环可溯源）。
    profile_user_ids = {p["userId"] for p in profiles if p.get("userId")}
    proactive_count = len(proactive_messages)
    proactive_personalized = [m for m in proactive_messages if m.get("personalized")]
    proactive_with_evidence = [
        m
        for m in proactive_personalized
        if m.get("interestTags") or m.get("matchedSegments")
    ]
    proactive_linked = [
        m for m in proactive_with_evidence if m.get("userId") in profile_user_ids
    ]
    proactive_evidence_count = len(proactive_with_evidence)
    proactive_linked_rate = _rate(len(proactive_linked), proactive_evidence_count)

    stages = {
        "behavior_to_features": {
            "ok": feature_count > 0 and feature_with_features > 0,
            "featureCount": feature_count,
            "featureWithFeaturesRate": _rate(feature_with_features, feature_count),
        },
        "features_to_segments": {
            # 派生作业把 segments 回写宽表（segmentsUpdatedAt 标记其确已运行）。
            "ok": feature_with_segments_updated > 0,
            "segmentsBackfilledRate": _rate(feature_with_segments_updated, feature_count),
            "segmentsNonEmptyRate": _rate(feature_with_segments, feature_count),
        },
        "interest_projection": {
            "ok": profile_count > 0 and profile_with_interests > 0,
            "profileCount": profile_count,
            "interestCoverageRate": interest_coverage,
            "lifecycle": lifecycle,
        },
        "segment_cqrs_consistency": {
            # 交集为空视为"暂无可比对"，不判 broken；有交集则要求高一致。
            "ok": overlap == 0 or consistency_rate >= min_segment_consistency,
            "overlapUsers": overlap,
            "consistencyRate": consistency_rate,
        },
        "feedback_events": {
            "ok": learning_event_count > 0,
            "learningEventCount": learning_event_count,
        },
        "proactive_consumption": {
            # 画像被主动消费并落库：至少一条个性化主动消息带画像派生证据。
            "ok": proactive_evidence_count > 0,
            "proactiveMessageCount": proactive_count,
            "personalizedCount": len(proactive_personalized),
            "withProfileEvidenceCount": proactive_evidence_count,
            "linkedToProfileRate": proactive_linked_rate,
        },
    }

    failing = [name for name in CRITICAL_STAGES if not stages[name]["ok"]]
    verdict = "closed" if not failing else "broken"

    return {
        "generatedAt": now.isoformat(),
        "verdict": verdict,
        "failingStages": failing,
        "stages": stages,
        "summary": {
            "featureCount": feature_count,
            "profileCount": profile_count,
            "interestCoverageRate": interest_coverage,
            "segmentConsistencyRate": consistency_rate,
            "learningEventCount": learning_event_count,
            "proactiveMessageCount": proactive_count,
            "proactivePersonalizedCount": len(proactive_personalized),
            "proactiveProfileEvidenceCount": proactive_evidence_count,
        },
    }


def _extract_features(coll) -> list[dict]:
    out: list[dict] = []
    cursor = coll.find(
        {},
        {"userId": 1, "userFeatures": 1, "segments": 1, "segmentsUpdatedAt": 1},
    )
    for doc in cursor:
        out.append(
            {
                "userId": doc.get("userId"),
                "hasFeatures": bool(doc.get("userFeatures")),
                "segmentsUpdated": doc.get("segmentsUpdatedAt") is not None,
                "segments": list(doc.get("segments") or []),
            }
        )
    return out


def _extract_profiles(coll) -> list[dict]:
    out: list[dict] = []
    cursor = coll.find(
        {"interestProfile": {"$exists": True}},
        {"userId": 1, "interestProfile": 1, "segments": 1},
    )
    for doc in cursor:
        prof = doc.get("interestProfile") or {}
        out.append(
            {
                "userId": doc.get("userId"),
                "hasInterests": bool(prof.get("topInterests")),
                "lifecycleStage": prof.get("lifecycleStage") or "unknown",
                # segments 落在 rm_user_profile_view 顶层（与宽表对齐比对）。
                "segments": list(doc.get("segments") or []),
            }
        )
    return out


def _extract_proactive_messages(coll) -> list[dict]:
    out: list[dict] = []
    cursor = coll.find(
        {},
        {
            "userId": 1,
            "personalized": 1,
            "interestTags": 1,
            "matchedSegments": 1,
            "lifecycleStage": 1,
        },
    )
    for doc in cursor:
        out.append(
            {
                "userId": doc.get("userId"),
                "personalized": bool(doc.get("personalized")),
                "interestTags": list(doc.get("interestTags") or []),
                "matchedSegments": list(doc.get("matchedSegments") or []),
                "lifecycleStage": doc.get("lifecycleStage") or "",
            }
        )
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="内容飞轮大循环实证（数据面闭环校验）")
    p.add_argument(
        "--mongodb-uri",
        default=os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"),
    )
    p.add_argument(
        "--content-db",
        default=os.environ.get("MONGODB_CONTENT_DATABASE", "quwoquan_content"),
        help="content 服务库（rm_recommend_feature / rec_learning_events）",
    )
    p.add_argument(
        "--user-db",
        default=os.environ.get("MONGODB_USER_DATABASE", "quwoquan"),
        help="user 服务库（rm_user_profile_view）",
    )
    p.add_argument(
        "--assistant-db",
        default=os.environ.get("MONGODB_ASSISTANT_DATABASE", "quwoquan_assistant"),
        help="assistant 服务库（app_messages 主动触达消息）",
    )
    p.add_argument("--output", default="", help="报告写入路径（默认 stdout）")
    p.add_argument(
        "--require-closed-loop",
        action="store_true",
        help="任一关键闭环分段未闭合则 exit 1（门禁用）",
    )
    p.add_argument("--min-interest-coverage", type=float, default=-1.0)
    p.add_argument("--min-segment-consistency", type=float, default=0.99)
    p.add_argument(
        "--enforce-segment-consistency",
        action="store_true",
        help="跨投影 segment 一致性低于 --min-segment-consistency 时 exit 1",
    )
    args = p.parse_args()

    try:
        from pymongo import MongoClient
    except ImportError:  # pragma: no cover - operational dependency
        print("pip install pymongo", file=sys.stderr)
        return 2

    client = MongoClient(args.mongodb_uri, serverSelectionTimeoutMS=5000)
    try:
        content_db = client[args.content_db]
        user_db = client[args.user_db]
        assistant_db = client[args.assistant_db]
        features = _extract_features(content_db[CONTENT_FEATURE_COLLECTION])
        profiles = _extract_profiles(user_db[USER_PROFILE_COLLECTION])
        proactive_messages = _extract_proactive_messages(
            assistant_db[ASSISTANT_APP_MESSAGE_COLLECTION]
        )
        learning_event_count = content_db[CONTENT_LEARNING_COLLECTION].count_documents({})
    finally:
        client.close()

    report = evaluate_flywheel(
        features,
        profiles,
        learning_event_count,
        proactive_messages=proactive_messages,
        min_segment_consistency=args.min_segment_consistency,
    )
    report["contentDb"] = args.content_db
    report["userDb"] = args.user_db
    report["assistantDb"] = args.assistant_db

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
        print(f"content-flywheel report written to {args.output}", file=sys.stderr)
    else:
        print(payload)

    exit_code = 0
    if args.require_closed_loop and report["verdict"] != "closed":
        print(f"FAIL: flywheel loop not closed; failing={report['failingStages']}", file=sys.stderr)
        exit_code = 1
    if args.min_interest_coverage >= 0 and report["summary"]["interestCoverageRate"] < args.min_interest_coverage:
        print(
            f"FAIL: interestCoverageRate {report['summary']['interestCoverageRate']} < min {args.min_interest_coverage}",
            file=sys.stderr,
        )
        exit_code = 1
    if args.enforce_segment_consistency and report["summary"]["segmentConsistencyRate"] < args.min_segment_consistency:
        print(
            f"FAIL: segmentConsistencyRate {report['summary']['segmentConsistencyRate']} < min {args.min_segment_consistency}",
            file=sys.stderr,
        )
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
