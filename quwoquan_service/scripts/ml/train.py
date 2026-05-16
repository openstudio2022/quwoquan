#!/usr/bin/env python3
"""
LightGBM train: read samples from rec_training_samples, train with 15+ features,
time-split validation, compute AUC/GAUC/NDCG, write model + ModelRegistry.

Usage: python scripts/ml/train.py --scenario content_feed [--production]
"""
import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    from pymongo import MongoClient
except ImportError:
    print("pip install pymongo", file=sys.stderr)
    sys.exit(1)

try:
    import lightgbm as lgb
except ImportError:
    lgb = None

try:
    import numpy as np
    from sklearn.metrics import roc_auc_score, log_loss, ndcg_score
except ImportError:
    np = None
    roc_auc_score = None

ITEM_NUMERIC_FEATURES = [
    "ageHours", "viewCount", "likeCount", "commentCount", "shareCount",
    "bodyLength", "tagCount", "qualityScore", "publishHour",
]
USER_NUMERIC_FEATURES = [
    "engagementRate", "totalLikes", "totalFavorites", "totalShares", "totalEvents",
]
CONTEXT_NUMERIC_FEATURES = [
    "requestHour", "requestDayOfWeek",
]
CONTENT_TYPE_MAP = {"image": 0, "video": 1, "article": 2, "moment": 3}


def _extract_features(sample: dict) -> list[float]:
    """Extract 15+ features from a training sample."""
    item = sample.get("itemFeatures") or {}
    user = sample.get("userFeatures") or {}
    ctx = sample.get("contextFeatures") or {}

    features = []
    for f in ITEM_NUMERIC_FEATURES:
        features.append(float(item.get(f, 0) or 0))
    for f in USER_NUMERIC_FEATURES:
        features.append(float(user.get(f, 0) or 0))
    for f in CONTEXT_NUMERIC_FEATURES:
        features.append(float(ctx.get(f, 0) or 0))

    features.append(float(CONTENT_TYPE_MAP.get(item.get("contentType", ""), -1)))
    features.append(1.0 if item.get("hasCover") else 0.0)

    tag_affinities = user.get("tagAffinities", {})
    item_tags = item.get("tags", [])
    tag_match_score = sum(tag_affinities.get(t, 0) for t in item_tags[:10])
    features.append(tag_match_score)

    author_affinities = user.get("authorAffinities", {})
    author_id = item.get("authorId", "")
    features.append(author_affinities.get(author_id, 0.0))

    return features


def _gauc(y_true, y_pred, user_ids):
    """Grouped AUC by userId."""
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    p.add_argument("--db", default="quwoquan_content")
    p.add_argument("--out-dir", default=os.environ.get("MODEL_OUT_DIR", "/tmp/rec_models"))
    p.add_argument("--production", action="store_true", help="Mark this version as production")
    p.add_argument("--num-boost-round", type=int, default=100)
    args = p.parse_args()

    if np is None or roc_auc_score is None:
        print("pip install numpy scikit-learn", file=sys.stderr)
        return 1

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    samples_coll = db["rec_training_samples"]

    rows = list(samples_coll.find({"scenario": args.scenario}).sort("ts", 1))
    if len(rows) < 100:
        print(f"Only {len(rows)} samples; need at least 100", file=sys.stderr)
        return 1

    # Time-split: 70% train, 15% val, 15% test (sorted by ts)
    n = len(rows)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    train_rows = rows[:train_end]
    val_rows = rows[train_end:val_end]
    test_rows = rows[val_end:]

    def to_dataset(row_list):
        X = [_extract_features(r) for r in row_list]
        y = [float((r.get("labels") or {}).get("engaged", 0)) for r in row_list]
        uids = [r.get("userId", "") for r in row_list]
        return np.array(X), np.array(y), uids

    X_train, y_train, uid_train = to_dataset(train_rows)
    X_val, y_val, uid_val = to_dataset(val_rows)
    X_test, y_test, uid_test = to_dataset(test_rows)

    print(f"Train: {len(train_rows)}, Val: {len(val_rows)}, Test: {len(test_rows)}", file=sys.stderr)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    version = datetime.utcnow().strftime("v%Y%m%d_%H%M%S")
    model_path = out_dir / f"{args.scenario}_{version}.txt"

    if lgb is not None:
        dtrain = lgb.Dataset(X_train, label=y_train)
        dval = lgb.Dataset(X_val, label=y_val, reference=dtrain)
        params = {
            "objective": "binary",
            "metric": ["auc", "binary_logloss"],
            "learning_rate": 0.05,
            "num_leaves": 31,
            "verbosity": -1,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
        }
        callbacks = [lgb.early_stopping(stopping_rounds=10, verbose=True)]
        model = lgb.train(
            params, dtrain,
            num_boost_round=args.num_boost_round,
            valid_sets=[dval],
            callbacks=callbacks,
        )
        model.save_model(str(model_path))

        # Evaluate on test set
        y_pred = model.predict(X_test)
        test_auc = roc_auc_score(y_test, y_pred) if len(set(y_test)) > 1 else 0.5
        test_gauc = _gauc(y_test, y_pred, uid_test)
        test_logloss = log_loss(y_test, y_pred) if len(set(y_test)) > 1 else 999
        try:
            test_ndcg = ndcg_score([y_test], [y_pred], k=20)
        except ValueError:
            test_ndcg = 0.0

        metrics = {
            "auc": round(test_auc, 4),
            "gauc": round(test_gauc, 4),
            "ndcg_20": round(test_ndcg, 4),
            "logloss": round(test_logloss, 4),
            "train_size": len(train_rows),
            "test_size": len(test_rows),
        }
    else:
        model_path.write_text("placeholder\n")
        metrics = {"auc": 0.0, "gauc": 0.0, "ndcg_20": 0.0, "logloss": 999}

    print(f"Test metrics: {json.dumps(metrics)}", file=sys.stderr)

    import model_registry as mr
    mr.write_registry(
        db,
        scenario=args.scenario,
        version=version,
        metrics=metrics,
        artifact_path=str(model_path),
        production=args.production,
    )
    print(f"Saved model to {model_path}; registered for scenario={args.scenario}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
