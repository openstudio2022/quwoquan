#!/usr/bin/env python3
"""Build immutable training samples from canonical exposure and feedback facts."""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime

from privacy_guard import closed_subject_ids, reject_closed_documents
from time_utils import as_utc

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)


POSITIVE_ACTIONS = {"click", "like", "share", "comment", "follow"}
NEGATIVE_ACTIONS = {"dislike", "report", "skip"}
IMPRESSION_WINDOW_SEC = 10


def _parse_time(value) -> datetime | None:
    if isinstance(value, datetime):
        return as_utc(value)
    if isinstance(value, str) and value:
        try:
            return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except (ValueError, TypeError):
            return None
    return None


def _feedback_duration(fact: dict) -> float:
    value = fact.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def build_training_samples(
    exposures: list[dict],
    feedbacks: list[dict],
    scenario: str,
) -> tuple[list[dict], int, int]:
    """Join feedback to exact immutable exposures without mutable projection reads."""
    feedback_by_exposure: dict[str, list[dict]] = defaultdict(list)
    for fact in feedbacks:
        exposure_id = str(fact.get("exposureId") or "").strip()
        if exposure_id:
            feedback_by_exposure[exposure_id].append(fact)

    docs: list[dict] = []
    rejected_missing_identity = 0
    rejected_missing_snapshot = 0
    for exposure in exposures:
        exposure_id = str(exposure.get("_id") or exposure.get("id") or "").strip()
        user_id = str(exposure.get("userId") or "").strip()
        target_id = str(exposure.get("targetId") or "").strip()
        request_id = str(exposure.get("requestId") or "").strip()
        if not exposure_id or not user_id or not target_id or not request_id:
            rejected_missing_identity += 1
            continue

        exposed_at = _parse_time(exposure.get("exposedAt"))
        snapshot_at = _parse_time(exposure.get("featureSnapshotAt"))
        user_features = exposure.get("userFeatureSnapshot")
        item_features = exposure.get("itemFeatureSnapshot")
        if (
            exposed_at is None
            or snapshot_at is None
            or not isinstance(user_features, dict)
            or not isinstance(item_features, dict)
        ):
            rejected_missing_snapshot += 1
            continue

        actions: set[str] = set()
        max_dwell = 0.0
        for feedback in feedback_by_exposure.get(exposure_id, []):
            action = str(feedback.get("feedbackType") or "").strip()
            if action:
                actions.add(action)
            max_dwell = max(max_dwell, _feedback_duration(feedback))

        has_positive = bool(actions & POSITIVE_ACTIONS) or max_dwell > IMPRESSION_WINDOW_SEC
        has_negative = bool(actions & NEGATIVE_ACTIONS)
        labels = {
            "click": 1.0 if "click" in actions else 0.0,
            "dwell_s": max_dwell,
            "like": 1.0 if "like" in actions else 0.0,
            "share": 1.0 if "share" in actions else 0.0,
            "comment": 1.0 if "comment" in actions else 0.0,
            "follow": 1.0 if "follow" in actions else 0.0,
            "dislike": 1.0 if "dislike" in actions else 0.0,
            "engaged": 1.0 if has_positive and not has_negative else 0.0,
        }
        feature_lag_seconds = (exposed_at - snapshot_at).total_seconds()
        docs.append(
            {
                "sourceSampleId": exposure_id,
                "scenario": scenario,
                "userId": user_id,
                "targetId": target_id,
                "requestId": request_id,
                "userFeatures": dict(user_features),
                "itemFeatures": dict(item_features),
                "contextFeatures": {
                    "requestHour": snapshot_at.hour,
                    "requestDayOfWeek": snapshot_at.weekday(),
                    "referralSource": item_features.get("referralSource", ""),
                    "contentType": item_features.get(
                        "contentType", exposure.get("targetType", "")
                    ),
                },
                "labels": labels,
                "ts": exposed_at,
                "featureSnapshotAt": snapshot_at,
                "featureLagSeconds": round(feature_lag_seconds, 3),
            }
        )
    return docs, rejected_missing_identity, rejected_missing_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Join canonical recommendation facts into training samples"
    )
    parser.add_argument("--scenario", default="content_feed")
    parser.add_argument(
        "--mongodb-uri",
        default=os.environ.get(
            "MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"
        ),
    )
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument(
        "--db", default=os.environ.get("DB", "quwoquan_recommendation")
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete current scenario samples before rebuilding",
    )
    args = parser.parse_args()

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    exposures_collection = db["recommendation_exposure_facts"]
    feedback_collection = db["recommendation_feedback_facts"]
    samples_collection = db["rec_training_samples"]

    if args.clean:
        result = samples_collection.delete_many({"scenario": args.scenario})
        print(
            f"Cleaned {result.deleted_count} old samples for scenario={args.scenario}",
            file=sys.stderr,
        )

    exposures = list(
        exposures_collection.find({"scenario": args.scenario})
        .sort("exposedAt", -1)
        .limit(args.limit)
    )
    exposures, closed_exposure_subjects = reject_closed_documents(db, exposures)
    if not exposures:
        print(
            "No open-subject exposure facts found "
            f"(closed_subjects={len(closed_exposure_subjects)})",
            file=sys.stderr,
        )
        return 1

    exposure_ids = [str(exposure.get("_id") or "").strip() for exposure in exposures]
    feedbacks = list(
        feedback_collection.find({"exposureId": {"$in": exposure_ids}}).limit(
            args.limit * 4
        )
    )
    feedbacks, _closed_feedback_subjects = reject_closed_documents(db, feedbacks)
    docs, rejected_identity, rejected_snapshot = build_training_samples(
        exposures,
        feedbacks,
        args.scenario,
    )
    docs, closed_sample_subjects = reject_closed_documents(db, docs)
    if not docs:
        print(
            "No admissible open-subject samples: exposures must carry canonical "
            "request identity and immutable feature snapshots "
            f"(closed_subjects={len(closed_sample_subjects)})",
            file=sys.stderr,
        )
        return 1

    samples_collection.insert_many(docs)
    late_closed = closed_subject_ids(db, (doc["userId"] for doc in docs))
    if late_closed:
        inserted_ids = [doc["_id"] for doc in docs if doc["userId"] in late_closed]
        if inserted_ids:
            samples_collection.delete_many({"_id": {"$in": inserted_ids}})
        docs = [doc for doc in docs if doc["userId"] not in late_closed]
    if not docs:
        print("All samples were rejected by a concurrent account closure", file=sys.stderr)
        return 1

    lags = sorted(doc["featureLagSeconds"] for doc in docs)
    p50 = lags[len(lags) // 2]
    p95 = lags[min(len(lags) - 1, int(len(lags) * 0.95))]
    stale_share = sum(1 for lag in lags if lag > 24 * 3600) / len(lags)
    print(
        f"Feature snapshot lag: p50={p50:.0f}s p95={p95:.0f}s "
        f"share(lag>24h)={stale_share:.2%} "
        f"rejected_identity={rejected_identity} rejected_snapshot={rejected_snapshot}",
        file=sys.stderr,
    )
    print(f"Wrote {len(docs)} samples for scenario={args.scenario}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
