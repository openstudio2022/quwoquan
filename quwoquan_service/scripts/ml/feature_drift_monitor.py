#!/usr/bin/env python3
"""
Feature drift monitor: computes Population Stability Index (PSI) between
baseline feature distributions (from training data) and current production
feature distributions (from rm_recommend_feature).

PSI < 0.1: no significant change
0.1 <= PSI < 0.2: moderate drift (warning)
PSI >= 0.2: significant drift (alert)

Usage:
  python feature_drift_monitor.py --scenario content_feed
  python feature_drift_monitor.py --scenario content_feed --baseline-date 2026-05-01
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    np = None

PSI_WARNING_THRESHOLD = 0.1
PSI_ALERT_THRESHOLD = 0.2

MONITORED_FEATURES = [
    "engagementRate",
    "totalLikes",
    "totalFavorites",
    "totalShares",
    "totalEvents",
    "avgEngagementDepth",
    "socialInterestScore",
]

NUM_BINS = 10


def _parse_baseline_date(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _compute_histogram(
    values: list[float],
    bins: int = NUM_BINS,
    bin_edges: list[float] | None = None,
) -> list[float]:
    """Compute a normalized histogram (probabilities) for a list of values."""
    if not values:
        return [1.0 / bins] * bins

    if np is not None:
        counts, _ = np.histogram(values, bins=bin_edges if bin_edges is not None else bins)
        total = sum(counts)
        if total == 0:
            return [1.0 / bins] * bins
        return [(c + 0.0001) / (total + 0.0001 * bins) for c in counts]

    if bin_edges is not None:
        if len(bin_edges) < 2:
            return [1.0 / bins] * bins
        min_val = float(bin_edges[0])
        max_val = float(bin_edges[-1])
        if min_val == max_val:
            result = [0.0001] * bins
            result[0] = 1.0
            total = sum(result)
            return [r / total for r in result]
        counts = [0] * bins
        for v in values:
            idx = bins - 1
            for i in range(bins):
                upper = float(bin_edges[i + 1])
                if v <= upper:
                    idx = i
                    break
            counts[idx] += 1
        total = sum(counts)
        return [(c + 0.0001) / (total + 0.0001 * bins) for c in counts]

    min_val = min(values)
    max_val = max(values)
    if min_val == max_val:
        result = [0.0001] * bins
        result[0] = 1.0
        total = sum(result)
        return [r / total for r in result]

    bin_width = (max_val - min_val) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - min_val) / bin_width), bins - 1)
        counts[idx] += 1
    total = sum(counts)
    return [(c + 0.0001) / (total + 0.0001 * bins) for c in counts]


def compute_psi(baseline: list[float], current: list[float]) -> float:
    """Compute Population Stability Index between two distributions."""
    if len(baseline) != len(current):
        raise ValueError("Distributions must have same number of bins")

    psi = 0.0
    for b, c in zip(baseline, current):
        b = max(b, 0.0001)
        c = max(c, 0.0001)
        psi += (c - b) * math.log(c / b)
    return psi


def extract_feature_values(db, feature_name: str, limit: int = 10000) -> list[float]:
    """Extract a feature's values from rm_recommend_feature collection."""
    coll = db["rm_recommend_feature"]
    values = []
    cursor = coll.find(
        {f"userFeatures.{feature_name}": {"$exists": True}},
        {f"userFeatures.{feature_name}": 1},
    ).limit(limit)
    for doc in cursor:
        uf = doc.get("userFeatures", {})
        val = uf.get(feature_name, 0)
        if isinstance(val, (int, float)):
            values.append(float(val))
    return values


def extract_training_feature_values(
    db,
    scenario: str,
    feature_name: str,
    limit: int = 10000,
    baseline_date: datetime | None = None,
) -> list[float]:
    """Extract baseline feature values from training samples."""
    coll = db["rec_training_samples"]
    query = {"scenario": scenario, f"userFeatures.{feature_name}": {"$exists": True}}
    if baseline_date is not None:
        query["ts"] = {"$lt": baseline_date}
    values = []
    cursor = coll.find(
        query,
        {f"userFeatures.{feature_name}": 1},
    ).sort("ts", -1).limit(limit)
    for doc in cursor:
        uf = doc.get("userFeatures", {})
        val = uf.get(feature_name, 0)
        if isinstance(val, (int, float)):
            values.append(float(val))
    return values


def main():
    p = argparse.ArgumentParser(description="Feature drift monitor (PSI)")
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    p.add_argument("--db", default=os.environ.get("DB", "quwoquan_content"))
    p.add_argument("--limit", type=int, default=10000)
    p.add_argument("--baseline-date", default="", help="Only compare training samples strictly earlier than this ISO date")
    p.add_argument("--out", default="", help="Write result JSON")
    args = p.parse_args()

    client = MongoClient(args.mongodb_uri, serverSelectionTimeoutMS=5000)
    db = client[args.db]
    baseline_date = _parse_baseline_date(args.baseline_date)

    results = {}
    alerts = []
    warnings = []

    for feature in MONITORED_FEATURES:
        print(f"[drift] Analyzing feature: {feature}")

        baseline_values = extract_training_feature_values(
            db,
            args.scenario,
            feature,
            args.limit,
            baseline_date=baseline_date,
        )
        current_values = extract_feature_values(db, feature, args.limit)

        if len(baseline_values) < 50 or len(current_values) < 50:
            print(f"  SKIP: insufficient data (baseline={len(baseline_values)}, current={len(current_values)})")
            results[feature] = {"status": "skip", "baseline_count": len(baseline_values), "current_count": len(current_values)}
            continue

        shared_min = min(min(baseline_values), min(current_values))
        shared_max = max(max(baseline_values), max(current_values))
        shared_edges = None
        if shared_min != shared_max:
            if np is not None:
                shared_edges = list(np.linspace(shared_min, shared_max, NUM_BINS + 1))
            else:
                step = (shared_max - shared_min) / NUM_BINS
                shared_edges = [shared_min + step * i for i in range(NUM_BINS + 1)]
                shared_edges[-1] = shared_max

        baseline_hist = _compute_histogram(baseline_values, bin_edges=shared_edges)
        current_hist = _compute_histogram(current_values, bin_edges=shared_edges)
        psi = compute_psi(baseline_hist, current_hist)

        status = "stable"
        if psi >= PSI_ALERT_THRESHOLD:
            status = "alert"
            alerts.append(feature)
        elif psi >= PSI_WARNING_THRESHOLD:
            status = "warning"
            warnings.append(feature)

        results[feature] = {
            "psi": round(psi, 6),
            "status": status,
            "baseline_count": len(baseline_values),
            "current_count": len(current_values),
            "baseline_mean": round(sum(baseline_values) / len(baseline_values), 4),
            "current_mean": round(sum(current_values) / len(current_values), 4),
        }
        print(f"  PSI={psi:.6f} status={status} (baseline={len(baseline_values)}, current={len(current_values)})")

    print(f"\n{'='*50}")
    print(f"Feature drift summary:")
    print(f"  Alerts: {alerts or 'none'}")
    print(f"  Warnings: {warnings or 'none'}")
    print(f"{'='*50}")

    report = {
        "scenario": args.scenario,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_date": baseline_date.isoformat() if baseline_date else None,
        "features": results,
        "alert_features": alerts,
        "warning_features": warnings,
        "overall_status": "alert" if alerts else ("warning" if warnings else "stable"),
    }

    if args.out:
        with open(args.out, "w") as f:
            json.dump(report, f, indent=2)
        print(f"[drift] Report written to {args.out}")

    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
