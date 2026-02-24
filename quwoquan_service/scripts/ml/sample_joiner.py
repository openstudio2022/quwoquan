#!/usr/bin/env python3
"""
SampleJoiner: read rec_learning_events, write rec_training_samples.
Schema per contracts/metadata/_projections/learning_events.yaml and training_samples.yaml.
"""
import argparse
import os
import sys
from datetime import datetime

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="Join learning events into training samples")
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    p.add_argument("--limit", type=int, default=10000)
    args = p.parse_args()

    client = MongoClient(args.mongodb_uri)
    db = client.get_database()
    events = db["rec_learning_events"]
    samples = db["rec_training_samples"]

    # Simple join: one event -> one sample row (impression/click as label placeholder)
    cursor = events.find({"scenario": args.scenario}).sort("ts", -1).limit(args.limit)
    now = datetime.utcnow()
    docs = []
    for e in cursor:
        doc = {
            "scenario": e.get("scenario", args.scenario),
            "userId": e.get("userId", ""),
            "targetId": e.get("targetId", ""),
            "userFeatures": {},
            "itemFeatures": {},
            "contextFeatures": {},
            "labels": {"click": 1.0 if e.get("eventType") == "click" else 0.0},
            "ts": e.get("ts", now),
        }
        docs.append(doc)
    if docs:
        samples.insert_many(docs)
    print(f"Wrote {len(docs)} samples for scenario={args.scenario}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
