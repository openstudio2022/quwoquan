#!/usr/bin/env python3
"""
SampleJoiner: read immutable online feature snapshots from rec_learning_events,
write multi-label training samples to rec_training_samples.

Event schema (MongoSink):
  eventType: "rec_impression" | "rec_engagement"
  scenario:  "content_feed"
  occurredAt: BSON datetime（MongoSink 由 RFC3339 事件边界规范化）
  createdAt:  datetime (Mongo server time)
  userId / targetId: string
  labels:  {sessionId, contentType, recallPath, action}
  context: {score, feedRequestId, featureSnapshotAt,
            userFeatureSnapshot, itemFeatureSnapshot, ...}

Labels output: click, dwell_s, like, share, comment, follow, dislike, engaged
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime

from time_utils import as_utc
from privacy_guard import closed_subject_ids, reject_closed_documents

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

POSITIVE_ACTIONS = {"click", "like", "share", "comment", "follow"}
NEGATIVE_ACTIONS = {"dislike", "report", "skip"}
IMPRESSION_WINDOW_SEC = 10


def _extract_action(event: dict) -> str:
    """Extract the user action from an event document.

    rec_engagement stores the real action in labels.action;
    rec_impression has no explicit action (it represents an exposure).
    """
    event_type = event.get("eventType", "")
    if event_type == "rec_impression":
        return "impression"
    labels = event.get("labels") or {}
    return labels.get("action", "unknown")


def _extract_duration(event: dict) -> float:
    """Extract dwell duration (seconds) from event context."""
    ctx = event.get("context") or {}
    return float(ctx.get("duration", 0) or 0)


def _parse_time(value) -> datetime | None:
    if isinstance(value, datetime):
        return as_utc(value)
    if isinstance(value, str) and value:
        try:
            return as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except (ValueError, TypeError):
            return None
    return None


def _extract_occurred_at(event: dict) -> datetime | None:
    """Parse occurredAt or createdAt; invalid facts fail closed."""
    return _parse_time(event.get("occurredAt")) or _parse_time(event.get("createdAt"))


def _extract_request_id(event: dict) -> str:
    context = event.get("context") or {}
    labels = event.get("labels") or {}
    return str(context.get("feedRequestId") or labels.get("feedRequestId") or "").strip()


def _extract_online_snapshot(event: dict) -> tuple[dict, dict, datetime] | None:
    """Read the immutable features captured by the online scoring request."""
    if event.get("eventType") != "rec_impression":
        return None
    context = event.get("context") or {}
    user = context.get("userFeatureSnapshot")
    item = context.get("itemFeatureSnapshot")
    captured_at = _parse_time(context.get("featureSnapshotAt"))
    if not isinstance(user, dict) or not isinstance(item, dict) or captured_at is None:
        return None
    return dict(user), dict(item), captured_at


def build_training_samples(
    events: list[dict],
    scenario: str,
) -> tuple[list[dict], int, int]:
    """Build samples only from immutable, request-correlated exposure facts."""
    grouped = defaultdict(list)
    rejected_missing_identity = 0
    for event in events:
        user_id = str(event.get("userId") or "").strip()
        target_id = str(event.get("targetId") or "").strip()
        request_id = _extract_request_id(event)
        if not user_id or not target_id or not request_id:
            rejected_missing_identity += 1
            continue
        # rec_model/fields.yaml 的关联身份是 requestId+targetId；禁止把同一用户
        # 对同一内容的多次独立曝光合成一个样本。
        grouped[(user_id, target_id, request_id)].append(event)

    docs = []
    rejected_missing_snapshot = 0
    for (user_id, target_id, request_id), group_events in grouped.items():
        impressions = []
        for event in group_events:
            occurred_at = _extract_occurred_at(event)
            snapshot = _extract_online_snapshot(event)
            if occurred_at is not None and snapshot is not None:
                impressions.append((occurred_at, event, snapshot))
        if not impressions:
            rejected_missing_snapshot += 1
            continue
        impression_at, impression_event, snapshot = min(
            impressions,
            key=lambda row: row[0],
        )
        user_features, item_features, snapshot_at = snapshot

        actions = set()
        max_dwell = 0.0
        for event in group_events:
            actions.add(_extract_action(event))
            max_dwell = max(max_dwell, _extract_duration(event))

        has_positive = bool(actions & POSITIVE_ACTIONS) or max_dwell > IMPRESSION_WINDOW_SEC
        has_negative = bool(actions & NEGATIVE_ACTIONS)
        labels = {
            "click": 1.0 if "click" in actions else 0.0,
            "dwell_s": float(max_dwell),
            "like": 1.0 if "like" in actions else 0.0,
            "share": 1.0 if "share" in actions else 0.0,
            "comment": 1.0 if "comment" in actions else 0.0,
            "follow": 1.0 if "follow" in actions else 0.0,
            "dislike": 1.0 if "dislike" in actions else 0.0,
            "engaged": 1.0 if has_positive and not has_negative else 0.0,
        }

        impression_context = impression_event.get("context") or {}
        # 在线特征必须在曝光事实之前或同一时刻完成快照。保留有符号差值，
        # 让训练准入策略对“快照晚于曝光”的时间旅行样本按负值 fail-closed；
        # 禁止 clamp 到 0，否则非法未来快照会伪装成零延迟样本。
        feature_lag_seconds = (impression_at - snapshot_at).total_seconds()
        docs.append({
            "scenario": scenario,
            "userId": user_id,
            "targetId": target_id,
            "requestId": request_id,
            "userFeatures": user_features,
            "itemFeatures": item_features,
            "contextFeatures": {
                # 与 RemoteModelScorer 发送给在线模型的评分时刻同源；禁止用
                # 稍后的下发事实时刻重算，以免跨小时/跨日时产生训练-在线偏斜。
                "requestHour": snapshot_at.hour,
                "requestDayOfWeek": snapshot_at.weekday(),
                "referralSource": impression_context.get("referralSource", ""),
                "contentType": item_features.get("contentType", ""),
            },
            "labels": labels,
            "ts": impression_at,
            "featureSnapshotAt": snapshot_at,
            "featureLagSeconds": round(feature_lag_seconds, 3),
        })
    return docs, rejected_missing_identity, rejected_missing_snapshot


def main():
    p = argparse.ArgumentParser(description="Join learning events into multi-label training samples")
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"))
    p.add_argument("--limit", type=int, default=50000)
    p.add_argument("--db", default=os.environ.get("DB", "quwoquan_content"))
    p.add_argument("--clean", action="store_true", help="Drop existing samples for this scenario before writing")
    args = p.parse_args()

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    events_coll = db["rec_learning_events"]
    samples_coll = db["rec_training_samples"]

    if args.clean:
        result = samples_coll.delete_many({"scenario": args.scenario})
        print(f"Cleaned {result.deleted_count} old samples for scenario={args.scenario}", file=sys.stderr)

    query = {
        "scenario": args.scenario,
        "eventType": {"$in": ["rec_impression", "rec_engagement"]},
    }
    events = list(
        events_coll.find(query)
        .sort("createdAt", -1)
        .limit(args.limit)
    )
    events, closed_event_subjects = reject_closed_documents(db, events)
    if not events:
        print(
            "No open-subject learning events found "
            f"(closed_subjects={len(closed_event_subjects)})",
            file=sys.stderr,
        )
        return 1

    docs, rejected_missing_identity, rejected_missing_snapshot = (
        build_training_samples(events, args.scenario)
    )

    if not docs:
        print(
            "No admissible samples: impressions must carry requestId and immutable "
            "online feature snapshots",
            file=sys.stderr,
        )
        return 1
    docs, closed_sample_subjects = reject_closed_documents(db, docs)
    if not docs:
        print(
            "No admissible open-subject samples "
            f"(closed_subjects={len(closed_sample_subjects)})",
            file=sys.stderr,
        )
        return 1
    samples_coll.insert_many(docs)
    late_closed = closed_subject_ids(
        db,
        (doc["userId"] for doc in docs),
    )
    if late_closed:
        inserted_ids = [
            doc["_id"]
            for doc in docs
            if doc["userId"] in late_closed
        ]
        if inserted_ids:
            samples_coll.delete_many({"_id": {"$in": inserted_ids}})
        docs = [doc for doc in docs if doc["userId"] not in late_closed]
    if not docs:
        print(
            "All samples were rejected by a concurrent account closure",
            file=sys.stderr,
        )
        return 1
    lags = sorted(d["featureLagSeconds"] for d in docs)
    if lags:
        p50 = lags[len(lags) // 2]
        p95 = lags[min(len(lags) - 1, int(len(lags) * 0.95))]
        stale_share = sum(1 for lag in lags if lag > 24 * 3600) / len(lags)
        print(
            f"Feature snapshot lag: p50={p50:.0f}s p95={p95:.0f}s "
            f"share(lag>24h)={stale_share:.2%} "
            f"rejected_identity={rejected_missing_identity} "
            f"rejected_snapshot={rejected_missing_snapshot}",
            file=sys.stderr,
        )
    print(f"Wrote {len(docs)} samples for scenario={args.scenario}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
