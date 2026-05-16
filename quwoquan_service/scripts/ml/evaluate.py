#!/usr/bin/env python3
"""
Offline evaluation: load model from registry (or explicit path) and test samples,
compute AUC/GAUC/NDCG@20/logloss.

Usage:
    python scripts/ml/evaluate.py --scenario content_feed
    python scripts/ml/evaluate.py --scenario content_feed --model-path /tmp/model.txt
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

from diversity_metrics import compute_diversity_metrics


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


def _resolve_model_path(db, scenario: str, explicit_path: str | None) -> str | None:
    """Resolve model path: explicit > registry artifactUri > registry artifactPath."""
    if explicit_path:
        if os.path.exists(explicit_path):
            return explicit_path
        print(f"[evaluate] Explicit model path not found: {explicit_path}", file=sys.stderr)
        return None

    coll = db["rec_model_registry"]
    doc = coll.find_one({"scenario": scenario}, sort=[("createdAt", -1)])
    if not doc:
        print(f"[evaluate] No model in registry for scenario={scenario}", file=sys.stderr)
        return None

    version = doc.get("version", "unknown")

    artifact_uri = doc.get("artifactUri", "")
    if artifact_uri:
        try:
            import artifact_store
            local = artifact_store.download(artifact_uri)
            print(f"[evaluate] Downloaded model v={version} from {artifact_uri}", file=sys.stderr)
            return local
        except Exception as e:
            print(f"[evaluate] artifact download failed: {e}", file=sys.stderr)

    artifact_path = doc.get("artifactPath", "")
    if artifact_path and os.path.exists(artifact_path):
        print(f"[evaluate] Using local model v={version} at {artifact_path}", file=sys.stderr)
        return artifact_path

    print(f"[evaluate] Model v={version} registered but artifact not accessible", file=sys.stderr)
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--model-path", default=None, help="Explicit path to LightGBM model (optional; defaults to registry)")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"))
    p.add_argument("--db", default="quwoquan_content")
    p.add_argument("--split", default="test", choices=["test", "val", "all"])
    args = p.parse_args()

    if np is None or roc_auc_score is None:
        print("pip install numpy scikit-learn", file=sys.stderr)
        return 1
    if lgb is None:
        print("pip install lightgbm", file=sys.stderr)
        return 1

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]

    model_path = _resolve_model_path(db, args.scenario, args.model_path)
    if not model_path:
        print("[evaluate] No model available — skipping evaluation", file=sys.stderr)
        return 1

    if model_path.endswith(".json"):
        print(f"[evaluate] Skipping evaluation for fusion config JSON: {model_path}", file=sys.stderr)
        print("[evaluate] Multi-objective models are evaluated inline during training", file=sys.stderr)
        return 0

    model = lgb.Booster(model_file=model_path)

    samples_coll = db["rec_training_samples"]

    sample_scenario = args.scenario
    rows = list(samples_coll.find({"scenario": sample_scenario}).sort("ts", 1))
    if not rows and args.scenario.endswith("_multiobjective"):
        sample_scenario = args.scenario.removesuffix("_multiobjective")
        rows = list(samples_coll.find({"scenario": sample_scenario}).sort("ts", 1))
    if not rows:
        print("No samples found", file=sys.stderr)
        return 1
    if sample_scenario != args.scenario:
        print(f"[evaluate] using samples from scenario={sample_scenario} for registry scenario={args.scenario}", file=sys.stderr)

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

    metrics.update(compute_diversity_metrics(eval_rows, list(y_pred), top_k=20))

    metrics["eval_size"] = len(eval_rows)
    metrics["positive_rate"] = round(float(y_true.mean()), 4)

    y_dislike = np.array([float((r.get("labels") or {}).get("dislike", 0)) for r in eval_rows])
    if y_dislike.sum() > 0:
        dislike_pred = 1 - y_pred
        dislike_auc = roc_auc_score(y_dislike, dislike_pred) if len(set(y_dislike)) > 1 else 0.5
        metrics["dislike_auc"] = round(float(dislike_auc), 4)

    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
