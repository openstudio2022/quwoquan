#!/usr/bin/env python3
"""
SampleJoiner: read rec_learning_events + rm_recommend_feature + rm_discovery_feed,
write multi-label training samples to rec_training_samples.

Event schema (MongoSink):
  eventType: "rec_impression" | "rec_engagement"
  scenario:  "content_feed"
  occurredAt: RFC3339 string
  createdAt:  datetime (Mongo server time)
  userId / targetId: string
  labels:  {sessionId, contentType, recallPath, action}
  context: {score, authorId, tags, duration, recScore, feedRequestId, referralSource, ...}

Labels output: click, dwell_s, like, favorite, share, comment, follow, dislike, engaged
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

POSITIVE_ACTIONS = {"click", "like", "favorite", "share", "comment", "follow"}
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


def _extract_occurred_at(event: dict) -> datetime:
    """Parse occurredAt (RFC3339) or fall back to createdAt."""
    occurred = event.get("occurredAt", "")
    if occurred:
        try:
            return datetime.fromisoformat(occurred.replace("Z", "+00:00")).replace(tzinfo=None)
        except (ValueError, TypeError):
            pass
    created = event.get("createdAt")
    if isinstance(created, datetime):
        return created
    return datetime.utcnow()


def _build_user_features(user_feat_doc: dict) -> dict:
    """Extract user features from rm_recommend_feature document."""
    if not user_feat_doc:
        return {}
    uf = user_feat_doc.get("userFeatures", {})
    tag_interaction = uf.get("tagInteraction", {})
    author_interaction = uf.get("authorInteraction", {})
    top_tags = sorted(tag_interaction.items(), key=lambda x: -x[1])[:50]
    top_authors = sorted(author_interaction.items(), key=lambda x: -x[1])[:20]

    topic_affinities = uf.get("topicAffinities", {})
    audience_affinities = uf.get("audienceAffinities", {})
    format_affinities = uf.get("formatAffinities", {})
    entity_affinities = uf.get("entityAffinities", {})
    entity_instance_affinities = uf.get("entityInstanceAffinities", {})

    return {
        "tagAffinities": dict(sorted(tag_interaction.items(), key=lambda x: -x[1])[:50]),
        "authorAffinities": dict(top_authors),
        "engagementRate": uf.get("engagementRate", 0.0),
        "totalLikes": uf.get("totalLikes", 0),
        "totalFavorites": uf.get("totalFavorites", 0),
        "totalShares": uf.get("totalShares", 0),
        "totalEvents": uf.get("totalEvents", 0),
        "topicAffinities": dict(sorted(topic_affinities.items(), key=lambda x: -x[1])[:20]),
        "audienceAffinities": dict(sorted(audience_affinities.items(), key=lambda x: -x[1])[:10]),
        "formatAffinities": dict(sorted(format_affinities.items(), key=lambda x: -x[1])[:5]),
        "entityAffinities": dict(sorted(entity_affinities.items(), key=lambda x: -x[1])[:20]),
        "entityInstanceAffinities": dict(sorted(entity_instance_affinities.items(), key=lambda x: -x[1])[:20]),
        "avgEngagementDepth": uf.get("avgEngagementDepth", 0.0),
        "depthDistribution": uf.get("depthDistribution", {}),
        "sourceDistribution": uf.get("sourceDistribution", {}),
        "circleTagAffinities": dict(sorted(
            uf.get("circleTagAffinities", {}).items(),
            key=lambda x: -x[1],
        )[:20]),
        "socialInterestScore": uf.get("socialInterestScore", 0.0),
        "typeENER": _compute_type_ener(uf),
    }


def _compute_type_ener(uf: dict) -> dict:
    imps = uf.get("typeImpressions", {})
    engs = uf.get("typeEngagements", {})
    result = {}
    for ct, imp in imps.items():
        if imp > 0:
            result[ct] = engs.get(ct, 0) / imp
    return result


def _build_item_features(feed_doc: dict) -> dict:
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
        "geoTagRef": feed_doc.get("geoTagRef", ""),
        "ageHours": round(age_hours, 2),
        "viewCount": feed_doc.get("viewCount", 0),
        "likeCount": feed_doc.get("likeCount", 0),
        "commentCount": feed_doc.get("commentCount", 0),
        "shareCount": feed_doc.get("shareCount", 0),
        "bodyLength": feed_doc.get("bodyLength", 0),
        "hasCover": bool(feed_doc.get("coverUrl")),
        "aspectRatio": feed_doc.get("aspectRatio", 0.0),
        "tagCount": len(tags),
        "qualityScore": feed_doc.get("qualityScore", 0.0),
        "publishHour": published_at.hour if isinstance(published_at, datetime) else 0,
        "recallPath": feed_doc.get("recallPath", ""),
    }


def main():
    p = argparse.ArgumentParser(description="Join learning events into multi-label training samples")
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"))
    p.add_argument("--limit", type=int, default=50000)
    p.add_argument("--db", default="quwoquan_content")
    p.add_argument("--clean", action="store_true", help="Drop existing samples for this scenario before writing")
    args = p.parse_args()

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    events_coll = db["rec_learning_events"]
    samples_coll = db["rec_training_samples"]
    feature_coll = db["rm_recommend_feature"]
    feed_coll = db["rm_discovery_feed"]

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
    if not events:
        print("No learning events found", file=sys.stderr)
        return 1

    user_ids = list({e.get("userId", "") for e in events if e.get("userId")})
    target_ids = list({e.get("targetId", "") for e in events if e.get("targetId")})

    user_features_map = {}
    for doc in feature_coll.find({"userId": {"$in": user_ids}}):
        user_features_map[doc["userId"]] = doc

    item_features_map = {}
    for doc in feed_coll.find({"postId": {"$in": target_ids}}):
        item_features_map[doc["postId"]] = doc

    grouped = defaultdict(list)
    for e in events:
        key = (e.get("userId", ""), e.get("targetId", ""))
        grouped[key].append(e)

    docs = []
    for (user_id, target_id), group_events in grouped.items():
        actions = set()
        max_dwell = 0.0
        earliest = None

        for e in group_events:
            action = _extract_action(e)
            actions.add(action)
            dwell = _extract_duration(e)
            if dwell > max_dwell:
                max_dwell = dwell
            ts = _extract_occurred_at(e)
            if earliest is None or ts < earliest:
                earliest = ts

        if earliest is None:
            earliest = datetime.utcnow()

        has_positive = bool(actions & POSITIVE_ACTIONS) or max_dwell > IMPRESSION_WINDOW_SEC
        has_negative = bool(actions & NEGATIVE_ACTIONS)

        labels = {
            "click": 1.0 if "click" in actions else 0.0,
            "dwell_s": float(max_dwell),
            "like": 1.0 if "like" in actions else 0.0,
            "favorite": 1.0 if "favorite" in actions else 0.0,
            "share": 1.0 if "share" in actions else 0.0,
            "comment": 1.0 if "comment" in actions else 0.0,
            "follow": 1.0 if "follow" in actions else 0.0,
            "dislike": 1.0 if "dislike" in actions else 0.0,
            "engaged": 1.0 if has_positive and not has_negative else 0.0,
        }

        ctx_event = group_events[0].get("context") or {}
        doc = {
            "scenario": args.scenario,
            "userId": user_id,
            "targetId": target_id,
            "userFeatures": _build_user_features(user_features_map.get(user_id)),
            "itemFeatures": _build_item_features(item_features_map.get(target_id)),
            "contextFeatures": {
                "requestHour": earliest.hour,
                "requestDayOfWeek": earliest.weekday(),
                "referralSource": ctx_event.get("referralSource", ""),
                "contentType": ctx_event.get("contentType", ""),
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
