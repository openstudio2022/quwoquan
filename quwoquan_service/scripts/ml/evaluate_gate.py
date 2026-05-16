#!/usr/bin/env python3
"""
evaluate_gate.py — Model quality gate for the training pipeline.

Reads the latest model version from rec_model_registry and compares
its metrics against absolute thresholds and relative deltas vs production.

Exit 0 = PASS, Exit 1 = BLOCKED.
Outputs eval_report.json for CI consumption.
"""
import argparse
import json
import os
import sys
from datetime import datetime

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

AUC_ABSOLUTE_MIN = 0.65
NDCG_ABSOLUTE_MIN = 0.15
FUSED_AUC_ABSOLUTE_MIN = 0.60
AUC_RELATIVE_DROP_MAX = 0.02
NDCG_RELATIVE_DROP_MAX = 0.03

DRY_RUN_AUC_MIN = 0.50
DRY_RUN_NDCG_MIN = 0.05
DRY_RUN_FUSED_AUC_MIN = 0.45


def main():
    p = argparse.ArgumentParser(description="Model quality gate")
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"))
    p.add_argument("--db", default="quwoquan_content")
    p.add_argument("--out", default="eval_report.json")
    p.add_argument("--dry-run", action="store_true", help="Lower thresholds for seed/dry-run data")
    p.add_argument("--allow-bootstrap", action="store_true", help="Allow empty registry to pass for initial bootstrap only")
    args = p.parse_args()

    auc_min = DRY_RUN_AUC_MIN if args.dry_run else AUC_ABSOLUTE_MIN
    ndcg_min = DRY_RUN_NDCG_MIN if args.dry_run else NDCG_ABSOLUTE_MIN
    fused_min = DRY_RUN_FUSED_AUC_MIN if args.dry_run else FUSED_AUC_ABSOLUTE_MIN

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    coll = db["rec_model_registry"]

    latest = coll.find_one(
        {"scenario": args.scenario},
        sort=[("createdAt", -1)],
    )
    if not latest:
        reason = "no model found"
        if args.allow_bootstrap:
            print("[evaluate_gate] No model found — SKIP (bootstrap allowed)")
            _write_report(args.out, "skip", reason, {}, {})
            return 0
        print(f"[evaluate_gate] BLOCKED: {reason}")
        _write_report(args.out, "blocked", reason, {}, {})
        return 1

    new_metrics = latest.get("metrics", {})
    version = latest.get("version", "unknown")

    prod = coll.find_one(
        {"scenario": args.scenario, "production": True},
        sort=[("createdAt", -1)],
    )
    prod_metrics = prod.get("metrics", {}) if prod else {}

    failures = []

    new_auc = new_metrics.get("auc", 0)
    new_ndcg = new_metrics.get("ndcg_20", 0)
    new_fused = new_metrics.get("fused_auc", 0)
    prod_auc = prod_metrics.get("auc", 0)
    prod_ndcg = prod_metrics.get("ndcg_20", 0)
    prod_fused = prod_metrics.get("fused_auc", 0)
    is_multiobjective = args.scenario.endswith("_multiobjective") or ("fused_auc" in new_metrics and "auc" not in new_metrics)
    diversity_keys = [
        "item_coverage_at_20",
        "author_repeat_rate_at_20",
        "topic_entropy_at_20",
        "author_hhi_at_20",
        "geo_coverage_at_20",
        "distinct_authors_at_20",
        "distinct_topics_at_20",
        "distinct_geo_buckets_at_20",
    ]
    diversity_metrics = {k: new_metrics[k] for k in diversity_keys if k in new_metrics}

    if new_auc == 0 and new_ndcg == 0 and new_fused == 0:
        failures.append("All metrics are zero — invalid training result")

    if new_auc < auc_min and new_auc > 0:
        failures.append(f"AUC {new_auc:.4f} < absolute min {auc_min}")

    if new_ndcg < ndcg_min and new_ndcg > 0:
        failures.append(f"NDCG@20 {new_ndcg:.4f} < absolute min {ndcg_min}")

    if new_fused > 0 and new_fused < fused_min:
        failures.append(f"fused_auc {new_fused:.4f} < absolute min {fused_min}")

    if is_multiobjective:
        if prod_fused > 0 and new_fused > 0:
            drop = prod_fused - new_fused
            if drop > AUC_RELATIVE_DROP_MAX:
                failures.append(
                    f"fused_auc dropped {drop:.4f} vs production (max {AUC_RELATIVE_DROP_MAX})"
                )
    elif prod_auc > 0 and new_auc > 0:
        drop = prod_auc - new_auc
        if drop > AUC_RELATIVE_DROP_MAX:
            failures.append(f"AUC dropped {drop:.4f} vs production (max {AUC_RELATIVE_DROP_MAX})")

    if prod_ndcg > 0 and new_ndcg > 0:
        drop = prod_ndcg - new_ndcg
        if drop > NDCG_RELATIVE_DROP_MAX:
            failures.append(f"NDCG@20 dropped {drop:.4f} vs production (max {NDCG_RELATIVE_DROP_MAX})")

    status = "pass" if not failures else "blocked"
    if failures:
        reason = "; ".join(failures)
    elif is_multiobjective:
        reason = f"v={version} fused_auc={new_fused:.4f}"
    else:
        reason = f"v={version} AUC={new_auc:.4f} NDCG={new_ndcg:.4f}"

    _write_report(args.out, status, reason, new_metrics, prod_metrics, diversity_metrics)

    if failures:
        print(f"[evaluate_gate] BLOCKED: {reason}")
        if diversity_metrics:
            print(f"[evaluate_gate] Diversity: {json.dumps(diversity_metrics, ensure_ascii=False)}")
        return 1

    print(f"[evaluate_gate] PASS: {reason}")
    if diversity_metrics:
        print(f"[evaluate_gate] Diversity: {json.dumps(diversity_metrics, ensure_ascii=False)}")
    return 0


def _write_report(path: str, status: str, reason: str, new_metrics: dict, prod_metrics: dict, diversity_metrics: dict):
    report = {
        "status": status,
        "reason": reason,
        "new_metrics": new_metrics,
        "prod_metrics": prod_metrics,
        "diversity_metrics": diversity_metrics,
        "evaluated_at": datetime.utcnow().isoformat(),
    }
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[evaluate_gate] Report written to {path}")


if __name__ == "__main__":
    sys.exit(main() or 0)
