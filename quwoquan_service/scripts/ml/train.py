#!/usr/bin/env python3
"""
LightGBM train: read samples from rec_training_samples, train, write model + ModelRegistry.
Usage: python scripts/ml/train.py --scenario content_feed [--datasetId ...]
"""
import argparse
import os
import sys
from pathlib import Path

# Allow import of model_registry when run from repo root or from this dir
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--datasetId", default="")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    p.add_argument("--out-dir", default=os.environ.get("MODEL_OUT_DIR", "/tmp/rec_models"))
    p.add_argument("--production", action="store_true", help="Mark this version as production")
    args = p.parse_args()

    client = MongoClient(args.mongodb_uri)
    db = client.get_database()
    samples_coll = db["rec_training_samples"]

    cursor = samples_coll.find({"scenario": args.scenario}).limit(5000)
    rows = list(cursor)
    if not rows:
        print("No samples; run sample_joiner first or seed rec_training_samples", file=sys.stderr)
        return 1

    # Minimal feature vector from labels/itemFeatures
    X = []
    y = []
    for r in rows:
        labels = r.get("labels") or {}
        feat = r.get("itemFeatures") or r.get("userFeatures") or {}
        # Placeholder: use likeCount/viewCount if present else zeros
        x = [
            float(feat.get("likeCount", 0)),
            float(feat.get("viewCount", 0)),
            float(feat.get("ageHours", 0)),
        ]
        X.append(x)
        y.append(float(labels.get("click", 0)))

    if not X:
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    version = "v1"
    model_path = out_dir / f"{args.scenario}_{version}.txt"

    if lgb is not None:
        dtrain = lgb.Dataset(X, label=y)
        params = {"objective": "binary", "metric": "auc", "verbosity": -1}
        model = lgb.train(params, dtrain, num_boost_round=10)
        model.save_model(str(model_path))
        metrics = {"auc": 0.5}  # placeholder; run evaluate.py for real
    else:
        # No LightGBM: write placeholder file so registry can point to it
        model_path.write_text("placeholder\n")
        metrics = {"auc": 0.0}

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
