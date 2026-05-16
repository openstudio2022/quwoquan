#!/usr/bin/env python3
"""
SampleJoiner: read rec_learning_events + rm_recommend_feature + rm_discovery_feed,
write multi-label training samples to rec_training_samples.

Labels: click, dwell_s, like, favorite, share, comment, dislike
Negative: impression with no positive signal within 10s window
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

POSITIVE_ACTIONS = {"click", "like", "favorite", "share", "comment", "follow"}
NEGATIVE_ACTIONS = {"dislike", "report"}
IMPRESSION_WINDOW_SEC = 10


def _build_user_features(user_feat_doc: dict) -> dict:
    """Extract user features from rm_recommend_feature document."""
    if not user_feat_doc:
        return {}
    uf = user_feat_doc.get("userFeatures", {})
    tag_interaction = uf.get("tagInteraction", {})
    author_interaction = uf.get("authorInteraction", {})
    top_tags = sorted(tag_interaction.items(), key=lambda x: -x[1])[:50]
    top_authors = sorted(author_interaction.items(), key=lambda x: -x[1])[:20]
    return {
        "tagAffinities": dict(top_tags),
        "authorAffinities": dict(top_authors),
        "engagementRate": uf.get("engagementRate", 0.0),
        "totalLikes": uf.get("totalLikes", 0),
        "totalFavorites": uf.get("totalFavorites", 0),
        "totalShares": uf.get("totalShares", 0),
        "totalEvents": uf.get("totalEvents", 0),
    }


def _build_item_features(feed_doc: dict) -> dict:
    """Extract item features from rm_discovery_feed document."""
    if not feed_doc:
        return {}
    published_at = feed_doc.get("publishedAt", datetime.utcnow())
    age_hours = (datetime.utcnow() - published_at).total_seconds() / 3600 if isinstance(published_at, datetime) else 0
    tags = feed_doc.get("tags", [])
    return {
        "contentType": feed_doc.get("contentType", ""),
        "authorId": feed_doc.get("authorId", ""),
        "tags": tags,
        "entityRefs": feed_doc.get("entityRefs", []),
        "ageHours": round(age_hours, 2),
        "viewCount": feed_doc.get("viewCount", 0),
        "likeCount": feed_doc.get("likeCount", 0),
        "commentCount": feed_doc.get("commentCount", 0),
        "shareCount": feed_doc.get("shareCount", 0),
        "bodyLength": feed_doc.get("bodyLength", 0),
        "hasCover": bool(feed_doc.get("coverUrl")),
        "tagCount": len(tags),
        "qualityScore": feed_doc.get("qualityScore", 0.0),
        "publishHour": published_at.hour if isinstance(published_at, datetime) else 0,
        "recallPath": feed_doc.get("recallPath", ""),
    }


def main():
    p = argparse.ArgumentParser(description="Join learning events into multi-label training samples")
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    p.add_argument("--limit", type=int, default=50000)
    p.add_argument("--db", default="quwoquan_content")
    args = p.parse_args()

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    events_coll = db["rec_learning_events"]
    samples_coll = db["rec_training_samples"]
    feature_coll = db["rm_recommend_feature"]
    feed_coll = db["rm_discovery_feed"]

    events = list(
        events_coll.find({"scenario": args.scenario})
        .sort("ts", -1)
        .limit(args.limit)
    )
    if not events:
        print("No learning events found", file=sys.stderr)
        return 1

    user_ids = list({e.get("userId", "") for e in events if e.get("userId")})
    target_ids = list({e.get("targetId", "") for e in events if e.get("targetId")})

    user_features_map = {}
    for doc in feature_coll.find({"userId": {"$in": user_ids}}):
        user_features_map[doc["userId"]] = doc

    item_features_map = {}
    for doc in feed_coll.find({"contentId": {"$in": target_ids}}):
        item_features_map[doc["contentId"]] = doc

    # Group events by (userId, targetId) to compute multi-label
    from collections import defaultdict
    grouped = defaultdict(list)
    for e in events:
        key = (e.get("userId", ""), e.get("targetId", ""))
        grouped[key].append(e)

    now = datetime.utcnow()
    docs = []
    for (user_id, target_id), group_events in grouped.items():
        actions = {e.get("eventType", "") for e in group_events}
        max_dwell = max(
            (e.get("durationSec", 0) or 0 for e in group_events if e.get("eventType") == "dwell"),
            default=0,
        )

        has_positive = bool(actions & POSITIVE_ACTIONS) or max_dwell > IMPRESSION_WINDOW_SEC
        has_negative = bool(actions & NEGATIVE_ACTIONS)

        labels = {
            "click": 1.0 if "click" in actions else 0.0,
            "dwell_s": float(max_dwell),
            "like": 1.0 if "like" in actions else 0.0,
            "favorite": 1.0 if "favorite" in actions else 0.0,
            "share": 1.0 if "share" in actions else 0.0,
            "comment": 1.0 if "comment" in actions else 0.0,
            "dislike": 1.0 if "dislike" in actions else 0.0,
            "engaged": 1.0 if has_positive and not has_negative else 0.0,
        }

        earliest = min((e.get("ts", now) for e in group_events), default=now)

        doc = {
            "scenario": args.scenario,
            "userId": user_id,
            "targetId": target_id,
            "userFeatures": _build_user_features(user_features_map.get(user_id)),
            "itemFeatures": _build_item_features(item_features_map.get(target_id)),
            "contextFeatures": {
                "requestHour": earliest.hour if isinstance(earliest, datetime) else 0,
                "requestDayOfWeek": earliest.weekday() if isinstance(earliest, datetime) else 0,
            },
            "labels": labels,
            "ts": earliest,
        }
        docs.append(doc)

    if docs:
        samples_coll.insert_many(docs)
    print(f"Wrote {len(docs)} samples for scenario={args.scenario}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
