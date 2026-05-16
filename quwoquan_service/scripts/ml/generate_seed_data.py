#!/usr/bin/env python3
"""
Bootstrap seed data for ML training pipeline dry-run.

Generates synthetic but realistic data:
- 200+ posts in rm_discovery_feed (varied contentType, tags, entityRefs)
- 500+ learning events in rec_learning_events (impression + engagement)
- 5-10 user profiles in rm_recommend_feature

Uses data engineering baselines (tag taxonomy, entity types, content types)
to ensure diversity and downstream pipeline compatibility.

Usage:
    python scripts/ml/generate_seed_data.py --mongodb-uri mongodb://localhost:27017
    python scripts/ml/generate_seed_data.py --clean  # wipe + regenerate
"""
import argparse
import hashlib
import os
import random
import sys
from datetime import datetime, timedelta

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

SEED_MARKER = "__ml_seed__"

CONTENT_TYPES = ["photo", "video", "article", "moment"]
CONTENT_TYPE_WEIGHTS = [0.35, 0.25, 0.25, 0.15]

RECALL_PATHS = ["tag_recall", "hot_recall", "social_friend", "social_circle", "explore_recall"]
REFERRAL_SOURCES = [
    "organic_feed", "friend_share", "chat_link",
    "circle_post", "author_profile", "entity_page", "search",
]

TAG_POOL = [
    "Topic/旅行/旅行主题/雪山探险", "Topic/旅行/玩法/观光游览",
    "Topic/旅行/出行方式/徒步穿越", "Topic/旅行/出行方式/自驾",
    "Topic/旅行/旅行主题/古镇探访", "Topic/旅行/季节/秋季",
    "Topic/美食/川菜/火锅", "Topic/美食/小吃/串串",
    "Topic/摄影/风光摄影", "Topic/摄影/人文纪实",
    "Topic/地理/行政区/中国/四川省/成都市",
    "Topic/地理/行政区/中国/四川省/阿坝州",
    "Topic/地理/行政区/中国/四川省/甘孜州",
    "Topic/地理/行政区/中国/云南省/丽江市",
    "Topic/地理/行政区/中国/浙江省/杭州市",
    "Audience/亲子/学龄前", "Audience/亲子/小学生",
    "Audience/情侣/蜜月", "Audience/银发/退休",
    "Audience/独行/背包客",
    "Format/内容角度/攻略", "Format/内容角度/体验",
    "Format/内容角度/科普", "Format/内容角度/日记",
    "Format/内容角度/探店",
    "Entity/地点/景区", "Entity/地点/古镇",
    "Entity/地点/餐厅", "Entity/地点/住宿",
]

ENTITY_REFS = [
    "entity/地点/景区/峨眉山", "entity/地点/景区/九寨沟",
    "entity/地点/景区/稻城亚丁", "entity/地点/景区/黄龙",
    "entity/地点/景区/都江堰", "entity/地点/古镇/黄龙溪",
    "entity/地点/古镇/洛带", "entity/地点/餐厅/龙抄手",
    "entity/地点/住宿/锦江宾馆", "entity/地点/景区/西湖",
    "entity/地点/景区/清迈古城", "entity/地点/景区/巴黎铁塔",
]

AUTHOR_IDS = [f"author_{i:03d}" for i in range(20)]

POSITIVE_ACTIONS = ["click", "like", "favorite", "share", "comment", "follow"]
NEGATIVE_ACTIONS = ["dislike", "skip"]
ALL_ENGAGEMENT_ACTIONS = POSITIVE_ACTIONS + NEGATIVE_ACTIONS


def _deterministic_id(prefix: str, idx: int) -> str:
    raw = f"{prefix}_{idx}_{SEED_MARKER}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _random_tags(rng: random.Random, min_n=2, max_n=6) -> list[str]:
    n = rng.randint(min_n, max_n)
    return rng.sample(TAG_POOL, min(n, len(TAG_POOL)))


def _random_entity_refs(rng: random.Random) -> list[str]:
    n = rng.randint(0, 3)
    return rng.sample(ENTITY_REFS, min(n, len(ENTITY_REFS)))


def generate_posts(rng: random.Random, count: int = 220) -> list[dict]:
    now = datetime.utcnow()
    posts = []
    for i in range(count):
        ct = rng.choices(CONTENT_TYPES, weights=CONTENT_TYPE_WEIGHTS, k=1)[0]
        published_at = now - timedelta(hours=rng.randint(1, 720))
        post_id = _deterministic_id("post", i)
        tags = _random_tags(rng)
        entity_refs = _random_entity_refs(rng)
        author_id = rng.choice(AUTHOR_IDS)
        quality = round(rng.uniform(0.3, 1.0), 2)

        cover_url = f"https://cdn.example.com/cover/{post_id}.jpg" if rng.random() > 0.2 else ""
        doc = {
            "postId": post_id,
            "contentType": ct,
            "authorId": author_id,
            "tags": tags,
            "entityRefs": entity_refs,
            "publishedAt": published_at,
            "viewCount": rng.randint(0, 5000),
            "likeCount": rng.randint(0, 500),
            "commentCount": rng.randint(0, 100),
            "shareCount": rng.randint(0, 50),
            "bodyLength": rng.randint(50, 3000),
            "coverUrl": cover_url,
            "hasCover": bool(cover_url),
            "tagCount": len(tags),
            "publishHour": published_at.hour,
            "aspectRatio": rng.choice([0.75, 1.0, 1.33, 1.78]),
            "qualityScore": quality,
            "recallPath": rng.choice(RECALL_PATHS),
            "status": "published",
            "_seedMarker": SEED_MARKER,
        }
        posts.append(doc)
    return posts


def generate_users(rng: random.Random, count: int = 8) -> list[dict]:
    users = []
    for i in range(count):
        user_id = f"seed_user_{i:03d}"
        tag_aff = {}
        for t in rng.sample(TAG_POOL, min(15, len(TAG_POOL))):
            tag_aff[t] = rng.randint(1, 50)

        topic_aff = {k: v for k, v in tag_aff.items() if k.startswith("Topic/")}
        audience_aff = {k: v for k, v in tag_aff.items() if k.startswith("Audience/")}
        format_aff = {k: v for k, v in tag_aff.items() if k.startswith("Format/")}
        entity_aff = {k: v for k, v in tag_aff.items() if k.startswith("Entity/")}

        author_aff = {}
        for a in rng.sample(AUTHOR_IDS, rng.randint(3, 8)):
            author_aff[a] = rng.randint(1, 30)

        entity_inst_aff = {}
        for e in rng.sample(ENTITY_REFS, rng.randint(2, 6)):
            entity_inst_aff[e] = round(rng.uniform(0.1, 1.0), 3)

        circle_aff = {}
        for t in rng.sample(TAG_POOL, rng.randint(3, 8)):
            circle_aff[t] = round(rng.uniform(0.05, 0.5), 3)

        depth_dist = {
            "L0": round(rng.uniform(0.05, 0.3), 3),
            "L1": round(rng.uniform(0.1, 0.3), 3),
            "L2": round(rng.uniform(0.1, 0.3), 3),
            "L3": round(rng.uniform(0.05, 0.2), 3),
            "L4": round(rng.uniform(0.01, 0.1), 3),
        }

        type_imps = {ct: rng.randint(10, 200) for ct in CONTENT_TYPES}
        type_engs = {ct: rng.randint(1, imp) for ct, imp in type_imps.items()}

        doc = {
            "userId": user_id,
            "userFeatures": {
                "tagInteraction": tag_aff,
                "authorInteraction": author_aff,
                "topicAffinities": topic_aff,
                "audienceAffinities": audience_aff,
                "formatAffinities": format_aff,
                "entityAffinities": entity_aff,
                "entityInstanceAffinities": entity_inst_aff,
                "engagementRate": round(rng.uniform(0.1, 0.6), 3),
                "totalLikes": rng.randint(10, 500),
                "totalFavorites": rng.randint(5, 200),
                "totalShares": rng.randint(0, 50),
                "totalEvents": rng.randint(100, 5000),
                "avgEngagementDepth": round(rng.uniform(1.0, 3.5), 2),
                "depthDistribution": depth_dist,
                "circleTagAffinities": circle_aff,
                "socialInterestScore": round(rng.uniform(0.0, 1.0), 3),
                "typeImpressions": type_imps,
                "typeEngagements": type_engs,
                "sourceDistribution": {
                    "organic_feed": round(rng.uniform(0.4, 0.7), 2),
                    "friend_share": round(rng.uniform(0.05, 0.2), 2),
                    "search": round(rng.uniform(0.05, 0.15), 2),
                },
            },
            "_seedMarker": SEED_MARKER,
        }
        users.append(doc)
    return users


def generate_events(
    rng: random.Random, posts: list[dict], users: list[dict],
    count: int = 600, scenario: str = "content_feed",
) -> list[dict]:
    now = datetime.utcnow()
    events = []
    user_ids = [u["userId"] for u in users]

    for i in range(count):
        user_id = rng.choice(user_ids)
        post = rng.choice(posts)
        occurred_at = now - timedelta(minutes=rng.randint(1, 10080))

        is_impression = rng.random() < 0.45
        if is_impression:
            event = {
                "eventType": "rec_impression",
                "scenario": scenario,
                "userId": user_id,
                "targetId": post["postId"],
                "occurredAt": occurred_at.isoformat() + "Z",
                "createdAt": occurred_at,
                "labels": {
                    "sessionId": f"sess_{rng.randint(1, 100):03d}",
                    "contentType": post["contentType"],
                    "recallPath": post.get("recallPath", ""),
                },
                "context": {
                    "score": round(rng.uniform(0.1, 1.0), 4),
                    "authorId": post["authorId"],
                    "tags": post["tags"][:5],
                    "feedRequestId": f"req_{i:05d}",
                    "referralSource": rng.choice(REFERRAL_SOURCES),
                    "contentType": post["contentType"],
                },
                "_seedMarker": SEED_MARKER,
            }
        else:
            action = rng.choices(
                ALL_ENGAGEMENT_ACTIONS,
                weights=[0.35, 0.15, 0.10, 0.08, 0.08, 0.04, 0.10, 0.10],
                k=1,
            )[0]
            duration = 0.0
            if action == "click":
                duration = round(rng.uniform(1, 120), 1)
            elif action in ("like", "favorite", "share", "comment"):
                duration = round(rng.uniform(5, 180), 1)

            event = {
                "eventType": "rec_engagement",
                "scenario": scenario,
                "userId": user_id,
                "targetId": post["postId"],
                "occurredAt": occurred_at.isoformat() + "Z",
                "createdAt": occurred_at,
                "labels": {
                    "sessionId": f"sess_{rng.randint(1, 100):03d}",
                    "contentType": post["contentType"],
                    "recallPath": post.get("recallPath", ""),
                    "action": action,
                },
                "context": {
                    "score": round(rng.uniform(0.1, 1.0), 4),
                    "authorId": post["authorId"],
                    "tags": post["tags"][:5],
                    "duration": duration,
                    "feedRequestId": f"req_{i:05d}",
                    "referralSource": rng.choice(REFERRAL_SOURCES),
                    "contentType": post["contentType"],
                },
                "_seedMarker": SEED_MARKER,
            }
        events.append(event)
    return events


def clean_seed_data(db):
    """Remove all seed-generated documents."""
    marker = {"_seedMarker": SEED_MARKER}
    for coll_name in ["rm_discovery_feed", "rec_learning_events", "rm_recommend_feature"]:
        result = db[coll_name].delete_many(marker)
        print(f"  Cleaned {result.deleted_count} seed docs from {coll_name}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="Generate ML training seed data")
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"))
    p.add_argument("--db", default="quwoquan_content")
    p.add_argument("--post-count", type=int, default=220)
    p.add_argument("--event-count", type=int, default=600)
    p.add_argument("--user-count", type=int, default=8)
    p.add_argument("--clean", action="store_true", help="Remove old seed data before generating")
    p.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = p.parse_args()

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]

    if args.clean:
        print("[seed] Cleaning old seed data...", file=sys.stderr)
        clean_seed_data(db)

    rng = random.Random(args.seed)

    print(f"[seed] Generating {args.post_count} posts...", file=sys.stderr)
    posts = generate_posts(rng, args.post_count)
    if posts:
        db["rm_discovery_feed"].insert_many(posts)

    print(f"[seed] Generating {args.user_count} user profiles...", file=sys.stderr)
    users = generate_users(rng, args.user_count)
    if users:
        db["rm_recommend_feature"].insert_many(users)

    print(f"[seed] Generating {args.event_count} learning events...", file=sys.stderr)
    events = generate_events(rng, posts, users, args.event_count, args.scenario)
    if events:
        db["rec_learning_events"].insert_many(events)

    print(f"[seed] Done: {len(posts)} posts, {len(users)} users, {len(events)} events", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
