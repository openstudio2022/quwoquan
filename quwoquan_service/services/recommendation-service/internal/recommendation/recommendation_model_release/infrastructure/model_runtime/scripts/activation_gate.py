#!/usr/bin/env python3
"""
Automatic activation gate: compares active vs candidate shadow scores
from rec_learning_events and activates a staged release if metrics are better.

Usage:
  python activation_gate.py --scenario content_feed --days 3 --min-samples 500 --release-id <id> --expected-active-release-id <id>
  python activation_gate.py --scenario content_feed --dry-run
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import timedelta

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

import model_release_client
from time_utils import utc_now


PROMOTION_THRESHOLDS = {
    "ctr_lift_min": 0.0,
    "engagement_score_lift_min": 0.0,
    "shadow_score_mean_lift_min": 0.005,
}


def collect_shadow_metrics(db, scenario: str, days: int) -> dict:
    """Collect shadow scoring events and compute comparison metrics."""
    coll = db["rec_learning_events"]
    since = utc_now() - timedelta(days=days)

    shadow_events = list(coll.find({
        "eventType": "rec_shadow",
        "scenario": scenario,
        "createdAt": {"$gte": since},
    }).limit(100000))

    impression_events = list(coll.find({
        "eventType": "rec_impression",
        "scenario": scenario,
        "createdAt": {"$gte": since},
    }).limit(100000))

    engagement_events = list(coll.find({
        "eventType": "rec_engagement",
        "scenario": scenario,
        "createdAt": {"$gte": since},
    }).limit(100000))

    champion_scores = {}
    for ev in impression_events:
        ctx = ev.get("context") or {}
        score = ctx.get("score", 0)
        content_id = ev.get("targetId", "")
        if content_id:
            champion_scores[content_id] = score

    challenger_scores = {}
    for ev in shadow_events:
        ctx = ev.get("context") or {}
        score = ctx.get("shadowScore", 0)
        content_id = ev.get("targetId", "")
        if content_id:
            challenger_scores[content_id] = score

    engaged_ids = set()
    clicked_ids = set()
    for ev in engagement_events:
        labels = ev.get("labels") or {}
        action = labels.get("action", "")
        content_id = ev.get("targetId", "")
        if action == "click":
            clicked_ids.add(content_id)
        if action in ("click", "like", "share", "comment", "follow"):
            engaged_ids.add(content_id)

    common_ids = set(champion_scores.keys()) & set(challenger_scores.keys())

    if not common_ids:
        return {"sample_count": 0}

    champ_mean = sum(champion_scores[cid] for cid in common_ids) / len(common_ids)
    chall_mean = sum(challenger_scores[cid] for cid in common_ids) / len(common_ids)

    impression_count = len(impression_events)
    ctr = len(clicked_ids) / max(impression_count, 1)
    engagement_rate = len(engaged_ids) / max(impression_count, 1)

    return {
        "sample_count": len(common_ids),
        "champion_score_mean": champ_mean,
        "challenger_score_mean": chall_mean,
        "score_lift": chall_mean - champ_mean,
        "impression_count": impression_count,
        "ctr": ctr,
        "engagement_rate": engagement_rate,
    }


def evaluate_gate(metrics: dict) -> tuple[bool, str]:
    """Evaluate whether the candidate is eligible for activation."""
    sample_count = metrics.get("sample_count", 0)
    if sample_count == 0:
        return False, "no shadow samples available"

    score_lift = metrics.get("score_lift", 0)
    min_lift = PROMOTION_THRESHOLDS["shadow_score_mean_lift_min"]
    if score_lift < min_lift:
        return False, f"score_lift {score_lift:.6f} < threshold {min_lift}"

    return True, f"score_lift={score_lift:.6f} (samples={sample_count})"


def main():
    p = argparse.ArgumentParser(description="Automatic model activation gate")
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--days", type=int, default=3, help="Days of shadow data to analyze")
    p.add_argument("--min-samples", type=int, default=500, help="Minimum shadow samples required")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    p.add_argument("--db", default=os.environ.get("DB", "quwoquan_recommendation"))
    p.add_argument("--dry-run", action="store_true", help="Analyze only, do not activate")
    p.add_argument("--release-id", default="", help="Staged release to activate")
    p.add_argument(
        "--expected-active-release-id",
        default=None,
        help="Exact current active release for CAS; omit only when no active release exists",
    )
    p.add_argument("--out", default="", help="Write result JSON to file")
    args = p.parse_args()

    client = MongoClient(args.mongodb_uri, serverSelectionTimeoutMS=5000)
    db = client[args.db]

    print(f"[activation_gate] Collecting shadow metrics for {args.scenario} (last {args.days} days)...")
    metrics = collect_shadow_metrics(db, args.scenario, args.days)

    print(f"[activation_gate] Metrics: {json.dumps(metrics, indent=2, default=str)}")

    if metrics.get("sample_count", 0) < args.min_samples:
        result = {"status": "SKIP", "reason": f"insufficient samples: {metrics.get('sample_count', 0)} < {args.min_samples}", "metrics": metrics}
        print(f"[activation_gate] {result['status']}: {result['reason']}")
    else:
        passed, reason = evaluate_gate(metrics)
        if passed and not args.dry_run and not args.release_id.strip():
            result = {
                "status": "BLOCKED",
                "reason": "release-id is required for activation",
                "metrics": metrics,
            }
            print(f"[activation_gate] BLOCKED: {result['reason']}")
        elif passed and not args.dry_run:
            release_scenario = f"{args.scenario}_multiobjective"
            print(f"[activation_gate] PASS: {reason} — activating staged release")
            activation = model_release_client.activate_release(
                release_id=args.release_id,
                scenario=release_scenario,
                expected_active_release_id=args.expected_active_release_id,
            )
            result = {
                "status": "ACTIVATED",
                "reason": reason,
                "metrics": metrics,
                "release": activation,
            }
        elif passed:
            result = {"status": "PASS_DRYRUN", "reason": reason, "metrics": metrics}
            print(f"[activation_gate] PASS (dry-run): {reason}")
        else:
            result = {"status": "BLOCKED", "reason": reason, "metrics": metrics}
            print(f"[activation_gate] BLOCKED: {reason}")

    if args.out:
        import json as _json
        with open(args.out, "w") as f:
            _json.dump(result, f, indent=2, default=str)
        print(f"[activation_gate] Report written to {args.out}")


if __name__ == "__main__":
    main()
