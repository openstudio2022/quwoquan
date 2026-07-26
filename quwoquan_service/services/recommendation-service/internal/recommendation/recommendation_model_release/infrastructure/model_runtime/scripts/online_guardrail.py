#!/usr/bin/env python3
"""
Online business metric guardrail: monitors CTR and engagement rate from
rec_learning_events. If metrics deviate significantly from baseline it emits
a fail-closed evidence record; the Ops rollout controller owns any rollback.

Usage:
  python online_guardrail.py --scenario content_feed --window-hours 4
  python online_guardrail.py --scenario content_feed --dry-run
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

BASELINE_CTR = 0.08
BASELINE_ENGAGEMENT_RATE = 0.15
CTR_DROP_THRESHOLD = 0.5
ENGAGEMENT_DROP_THRESHOLD = 0.4
MIN_IMPRESSIONS = 200


def compute_online_metrics(db, scenario: str, window_hours: int) -> dict:
    """Compute real-time CTR and engagement rate from learning events."""
    coll = db["rec_learning_events"]
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    impression_count = coll.count_documents({
        "eventType": "rec_impression",
        "scenario": scenario,
        "createdAt": {"$gte": since},
    })

    engagement_pipeline = [
        {"$match": {
            "eventType": "rec_engagement",
            "scenario": scenario,
            "createdAt": {"$gte": since},
        }},
        {"$group": {
            "_id": "$labels.action",
            "count": {"$sum": 1},
        }},
    ]
    action_counts = {}
    for doc in coll.aggregate(engagement_pipeline):
        action_counts[doc["_id"]] = doc["count"]

    click_count = action_counts.get("click", 0)
    total_engagement = sum(
        action_counts.get(a, 0)
        for a in ("click", "like", "share", "comment", "follow")
    )

    ctr = click_count / max(impression_count, 1)
    engagement_rate = total_engagement / max(impression_count, 1)

    model_pipeline = [
        {"$match": {
            "eventType": "rec_impression",
            "scenario": scenario,
            "createdAt": {"$gte": since},
            "context.score": {"$exists": True, "$gt": 0},
        }},
        {"$group": {
            "_id": None,
            "count": {"$sum": 1},
        }},
    ]
    model_imp_result = list(coll.aggregate(model_pipeline))
    model_impression_count = model_imp_result[0]["count"] if model_imp_result else 0

    return {
        "window_hours": window_hours,
        "impression_count": impression_count,
        "click_count": click_count,
        "total_engagement": total_engagement,
        "ctr": ctr,
        "engagement_rate": engagement_rate,
        "model_impression_count": model_impression_count,
        "model_ratio": model_impression_count / max(impression_count, 1),
    }


def evaluate_guardrail(metrics: dict) -> tuple[bool, str]:
    """Returns (safe, reason). safe=True means metrics are acceptable."""
    impression_count = metrics.get("impression_count", 0)
    if impression_count < MIN_IMPRESSIONS:
        return True, f"insufficient data ({impression_count} < {MIN_IMPRESSIONS})"

    ctr = metrics.get("ctr", 0)
    engagement_rate = metrics.get("engagement_rate", 0)

    violations = []
    if ctr < BASELINE_CTR * CTR_DROP_THRESHOLD:
        violations.append(f"CTR={ctr:.4f} < baseline*{CTR_DROP_THRESHOLD}={BASELINE_CTR * CTR_DROP_THRESHOLD:.4f}")

    if engagement_rate < BASELINE_ENGAGEMENT_RATE * ENGAGEMENT_DROP_THRESHOLD:
        violations.append(
            f"EngagementRate={engagement_rate:.4f} < baseline*{ENGAGEMENT_DROP_THRESHOLD}="
            f"{BASELINE_ENGAGEMENT_RATE * ENGAGEMENT_DROP_THRESHOLD:.4f}"
        )

    if violations:
        return False, "; ".join(violations)
    return True, f"CTR={ctr:.4f} EngagementRate={engagement_rate:.4f} within safe range"


def main():
    p = argparse.ArgumentParser(description="Online business metric guardrail")
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--window-hours", type=int, default=4)
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    p.add_argument("--db", default=os.environ.get("DB", "quwoquan_content"))
    p.add_argument("--env", default="gamma", choices=("alpha", "beta", "gamma", "prod"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out", default="", help="Write result JSON")
    args = p.parse_args()

    client = MongoClient(args.mongodb_uri, serverSelectionTimeoutMS=5000)
    db = client[args.db]

    print(f"[guardrail] Computing online metrics for {args.scenario} (last {args.window_hours}h)...")
    metrics = compute_online_metrics(db, args.scenario, args.window_hours)
    print(f"[guardrail] Metrics: {json.dumps(metrics, indent=2, default=str)}")

    safe, reason = evaluate_guardrail(metrics)

    if safe:
        result = {"status": "SAFE", "reason": reason, "metrics": metrics, "action": "monitor_only"}
        print(f"[guardrail] SAFE: {reason}")
    else:
        print(f"[guardrail] VIOLATION: {reason}")
        status = "GATE_BLOCK_DRYRUN" if args.dry_run else "GATE_BLOCK"
        print(
            "[guardrail] Ops rollout action required; service code does not mutate "
            "environment config or release state"
        )
        result = {
            "status": status,
            "reason": reason,
            "metrics": metrics,
            "action": "ops_rollout_required",
            "environment": args.env,
        }

    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"[guardrail] Report written to {args.out}")

    return 0 if safe else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
