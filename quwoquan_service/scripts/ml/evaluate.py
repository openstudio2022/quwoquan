#!/usr/bin/env python3
"""
Offline evaluation: load model and test samples, compute AUC/GAUC/NDCG@20/logloss.

Usage: python scripts/ml/evaluate.py --model-path /tmp/rec_models/content_feed_v*.txt
"""
import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

try:
    import numpy as np
    from sklearn.metrics import roc_auc_score, log_loss, ndcg_score
except ImportError:
    np = None
    roc_auc_score = None

try:
    import lightgbm as lgb
except ImportError:
    lgb = None


def _gauc(y_true, y_pred, user_ids):
    from collections import defaultdict
    groups = defaultdict(lambda: ([], []))
    for yt, yp, uid in zip(y_true, y_pred, user_ids):
        groups[uid][0].append(yt)
        groups[uid][1].append(yp)

    total_weight = 0
    weighted_auc = 0
    for uid, (ys, ps) in groups.items():
        if len(set(ys)) < 2:
            continue
        try:
            auc = roc_auc_score(ys, ps)
            w = len(ys)
            weighted_auc += auc * w
            total_weight += w
        except ValueError:
            continue
    return weighted_auc / total_weight if total_weight > 0 else 0.5


def _extract_features(sample: dict) -> list[float]:
    """Must match train.py _extract_features exactly."""
    from train import _extract_features as _ef
    return _ef(sample)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--model-path", required=True, help="Path to LightGBM model file")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    p.add_argument("--db", default="quwoquan_content")
    p.add_argument("--split", default="test", choices=["test", "val", "all"])
    args = p.parse_args()

    if np is None or roc_auc_score is None:
        print("pip install numpy scikit-learn", file=sys.stderr)
        return 1
    if lgb is None:
        print("pip install lightgbm", file=sys.stderr)
        return 1

    model = lgb.Booster(model_file=args.model_path)

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    samples_coll = db["rec_training_samples"]

    rows = list(samples_coll.find({"scenario": args.scenario}).sort("ts", 1))
    if not rows:
        print("No samples found", file=sys.stderr)
        return 1

    # Time-split matching train.py
    n = len(rows)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    if args.split == "test":
        eval_rows = rows[val_end:]
    elif args.split == "val":
        eval_rows = rows[train_end:val_end]
    else:
        eval_rows = rows

    if len(eval_rows) < 10:
        print(f"Only {len(eval_rows)} eval samples", file=sys.stderr)
        return 1

    X = np.array([_extract_features(r) for r in eval_rows])
    y_true = np.array([float((r.get("labels") or {}).get("engaged", 0)) for r in eval_rows])
    user_ids = [r.get("userId", "") for r in eval_rows]

    y_pred = model.predict(X)

    metrics = {}
    if len(set(y_true)) > 1:
        metrics["auc"] = round(float(roc_auc_score(y_true, y_pred)), 4)
        metrics["logloss"] = round(float(log_loss(y_true, y_pred)), 4)
    else:
        metrics["auc"] = 0.5
        metrics["logloss"] = 999.0

    metrics["gauc"] = round(_gauc(y_true, y_pred, user_ids), 4)
    try:
        metrics["ndcg_20"] = round(float(ndcg_score([y_true], [y_pred], k=20)), 4)
    except ValueError:
        metrics["ndcg_20"] = 0.0

    metrics["eval_size"] = len(eval_rows)
    metrics["positive_rate"] = round(float(y_true.mean()), 4)

    # Dislike prediction accuracy
    y_dislike = np.array([float((r.get("labels") or {}).get("dislike", 0)) for r in eval_rows])
    if y_dislike.sum() > 0:
        dislike_pred = 1 - y_pred
        dislike_auc = roc_auc_score(y_dislike, dislike_pred) if len(set(y_dislike)) > 1 else 0.5
        metrics["dislike_auc"] = round(float(dislike_auc), 4)

    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
