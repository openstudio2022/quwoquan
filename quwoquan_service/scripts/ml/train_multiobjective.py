#!/usr/bin/env python3
"""
Multi-objective ranking: train separate LightGBM models for click, dwell, like,
favorite, share, comment, follow — then combine with weighted fusion.

Usage: python scripts/ml/train_multiobjective.py --scenario content_feed [--production]
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
    from sklearn.metrics import roc_auc_score, log_loss
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

# Multi-objective targets and their fusion weights
OBJECTIVES = {
    "click":    {"type": "binary",     "weight": 0.30},
    "dwell_s":  {"type": "regression", "weight": 0.25},
    "like":     {"type": "binary",     "weight": 0.15},
    "favorite": {"type": "binary",     "weight": 0.10},
    "share":    {"type": "binary",     "weight": 0.08},
    "comment":  {"type": "binary",     "weight": 0.07},
    "follow":   {"type": "binary",     "weight": 0.05},
}


def _extract_features(sample: dict) -> list[float]:
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    p.add_argument("--db", default="quwoquan_content")
    p.add_argument("--out-dir", default=os.environ.get("MODEL_OUT_DIR", "/tmp/rec_models"))
    p.add_argument("--production", action="store_true")
    p.add_argument("--num-boost-round", type=int, default=100)
    args = p.parse_args()

    if np is None or lgb is None:
        print("pip install numpy lightgbm scikit-learn", file=sys.stderr)
        return 1

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    samples_coll = db["rec_training_samples"]

    rows = list(samples_coll.find({"scenario": args.scenario}).sort("ts", 1))
    if len(rows) < 100:
        print(f"Only {len(rows)} samples; need at least 100", file=sys.stderr)
        return 1

    n = len(rows)
    train_end = int(n * 0.70)
    val_end = int(n * 0.85)

    train_rows = rows[:train_end]
    val_rows = rows[train_end:val_end]
    test_rows = rows[val_end:]

    X_train = np.array([_extract_features(r) for r in train_rows])
    X_val = np.array([_extract_features(r) for r in val_rows])
    X_test = np.array([_extract_features(r) for r in test_rows])

    print(f"Train: {len(train_rows)}, Val: {len(val_rows)}, Test: {len(test_rows)}", file=sys.stderr)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    version = datetime.utcnow().strftime("mo_v%Y%m%d_%H%M%S")

    all_metrics = {}
    models = {}

    for obj_name, obj_cfg in OBJECTIVES.items():
        print(f"\n--- Training objective: {obj_name} ({obj_cfg['type']}) ---", file=sys.stderr)

        def get_label(row):
            labels = row.get("labels") or {}
            v = labels.get(obj_name, 0)
            return float(v if v is not None else 0)

        y_train = np.array([get_label(r) for r in train_rows])
        y_val = np.array([get_label(r) for r in val_rows])
        y_test = np.array([get_label(r) for r in test_rows])

        if obj_cfg["type"] == "binary":
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
        else:
            params = {
                "objective": "regression",
                "metric": ["rmse"],
                "learning_rate": 0.05,
                "num_leaves": 31,
                "verbosity": -1,
                "feature_fraction": 0.8,
                "bagging_fraction": 0.8,
                "bagging_freq": 5,
            }

        dtrain = lgb.Dataset(X_train, label=y_train)
        dval = lgb.Dataset(X_val, label=y_val, reference=dtrain)
        callbacks = [lgb.early_stopping(stopping_rounds=10, verbose=False)]
        model = lgb.train(
            params, dtrain,
            num_boost_round=args.num_boost_round,
            valid_sets=[dval],
            callbacks=callbacks,
        )

        model_path = out_dir / f"{args.scenario}_{obj_name}_{version}.txt"
        model.save_model(str(model_path))
        models[obj_name] = model

        y_pred = model.predict(X_test)
        obj_metrics = {"weight": obj_cfg["weight"]}
        if obj_cfg["type"] == "binary" and len(set(y_test)) > 1:
            obj_metrics["auc"] = round(float(roc_auc_score(y_test, y_pred)), 4)
            obj_metrics["logloss"] = round(float(log_loss(y_test, y_pred)), 4)
        elif obj_cfg["type"] == "regression":
            rmse = float(np.sqrt(np.mean((y_test - y_pred) ** 2)))
            obj_metrics["rmse"] = round(rmse, 4)

        all_metrics[obj_name] = obj_metrics
        print(f"  {obj_name}: {json.dumps(obj_metrics)}", file=sys.stderr)

    # Compute fused score on test set
    fused_scores = np.zeros(len(test_rows))
    for obj_name, model in models.items():
        pred = model.predict(X_test)
        if OBJECTIVES[obj_name]["type"] == "regression":
            pred = np.clip(pred / 60.0, 0, 1)  # normalize dwell to [0,1]
        fused_scores += pred * OBJECTIVES[obj_name]["weight"]

    # Evaluate fused ranking
    y_engaged = np.array([float((r.get("labels") or {}).get("engaged", 0)) for r in test_rows])
    if len(set(y_engaged)) > 1:
        fused_auc = float(roc_auc_score(y_engaged, fused_scores))
    else:
        fused_auc = 0.5

    all_metrics["fused_auc"] = round(fused_auc, 4)
    all_metrics["fusion_weights"] = {k: v["weight"] for k, v in OBJECTIVES.items()}

    # Save fusion config
    fusion_config = {
        "version": version,
        "scenario": args.scenario,
        "objectives": {k: {"weight": v["weight"], "type": v["type"]} for k, v in OBJECTIVES.items()},
        "model_files": {k: f"{args.scenario}_{k}_{version}.txt" for k in OBJECTIVES},
    }
    config_path = out_dir / f"{args.scenario}_fusion_{version}.json"
    config_path.write_text(json.dumps(fusion_config, indent=2))

    print(f"\nFused AUC (engaged): {fused_auc:.4f}", file=sys.stderr)
    print(f"All metrics: {json.dumps(all_metrics, indent=2)}", file=sys.stderr)

    import model_registry as mr
    mr.write_registry(
        db,
        scenario=f"{args.scenario}_multiobjective",
        version=version,
        metrics=all_metrics,
        artifact_path=str(config_path),
        production=args.production,
    )
    print(f"Registered multi-objective model version={version}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
