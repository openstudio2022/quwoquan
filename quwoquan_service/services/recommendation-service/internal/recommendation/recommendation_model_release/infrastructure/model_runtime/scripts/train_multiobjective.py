#!/usr/bin/env python3
"""
Multi-objective ranking: train separate LightGBM models for click, dwell, like,
share, comment, follow — then combine with weighted fusion.

Usage: python services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/train_multiobjective.py --scenario content_feed [--production]
"""
import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
_MODEL_RUNTIME_ROOT = _SCRIPT_DIR.parent
if str(_MODEL_RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEL_RUNTIME_ROOT))

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

from diversity_metrics import compute_diversity_metrics
from features.intersection_feature_encoder import (
    append_intersection_features,
    matched_edge_categorical_features,
)
from privacy_guard import reject_closed_documents
from time_utils import utc_now
from training_sample_policy import (
    DEFAULT_MAX_FEATURE_LAG_SECONDS,
    filter_point_in_time_rows,
)

ITEM_NUMERIC_FEATURES = [
    "ageHours", "viewCount", "likeCount", "commentCount", "shareCount",
    # N3-3 特征偏斜收口：bodyLength/aspectRatio/hasCover 已退役（在线召回投影
    # 不携带、serving 恒 0，训练学到的分裂在线全失效；S1 召回投影补齐后再启用）。
    "tagCount", "qualityScore", "publishHour",
]
RECALL_PATH_MAP = {"tag_recall": 0, "hot_recall": 1, "social_friend": 2, "social_circle": 3, "explore_recall": 4}
USER_NUMERIC_FEATURES = [
    "engagementRate", "totalLikes", "totalShares", "totalEvents",
]
CONTEXT_NUMERIC_FEATURES = [
    "requestHour", "requestDayOfWeek",
]
CONTENT_TYPE_MAP = {"image": 0, "video": 1, "article": 2, "micro": 3}
# Multi-objective targets and their fusion weights
OBJECTIVES = {
    "click":    {"type": "binary",     "weight": 0.30},
    "dwell_s":  {"type": "regression", "weight": 0.25},
    "like":     {"type": "binary",     "weight": 0.15},
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
    # hasCover 已退役（N3-3）：在线不可得，双侧同步移除保持特征向量同构。
    features.append(float(RECALL_PATH_MAP.get(item.get("recallPath", ""), -1)))

    tag_affinities = user.get("tagAffinities", {})
    item_tags = item.get("tagRefs", [])
    tag_match_score = sum(tag_affinities.get(t, 0) for t in item_tags[:10])
    features.append(tag_match_score)

    author_affinities = user.get("authorAffinities", {})
    author_id = item.get("authorId", "")
    features.append(author_affinities.get(author_id, 0.0))

    topic_affinities = user.get("topicAffinities", {})
    audience_affinities = user.get("audienceAffinities", {})
    format_affinities = user.get("formatAffinities", {})
    entity_affinities = user.get("entityAffinities", {})
    entity_instance_affinities = user.get("entityInstanceAffinities", {})

    topic_match = sum(topic_affinities.get(t, 0) for t in item_tags[:10])
    audience_match = sum(audience_affinities.get(t, 0) for t in item_tags[:10])
    format_match = sum(format_affinities.get(t, 0) for t in item_tags[:10])
    entity_match = sum(entity_affinities.get(t, 0) for t in item_tags[:10])
    features.extend([topic_match, audience_match, format_match, entity_match])

    entity_refs = item.get("entityRefs", []) or []
    entity_instance_match = sum(entity_instance_affinities.get(r, 0) for r in entity_refs[:10])
    features.append(entity_instance_match)

    features.append(float(user.get("avgEngagementDepth", 0) or 0))
    depth_dist = user.get("depthDistribution", {}) or {}
    for level in ["L0", "L1", "L2", "L3", "L4"]:
        features.append(float(depth_dist.get(level, 0)))

    features.append(float(user.get("socialInterestScore", 0) or 0))
    circle_aff = user.get("circleTagAffinities", {}) or {}
    circle_match = sum(circle_aff.get(t, 0) for t in item_tags[:10])
    features.append(circle_match)

    type_ener = user.get("typeENER", {}) or {}
    content_type = item.get("contentType", "")
    features.append(float(type_ener.get(content_type, 0)))

    append_intersection_features(features, item, user, user)

    return features


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true"))
    p.add_argument("--db", default=os.environ.get("DB", "quwoquan_content"))
    p.add_argument("--out-dir", default=os.environ.get("MODEL_OUT_DIR", "/tmp/rec_models"))
    p.add_argument("--production", action="store_true")
    p.add_argument("--num-boost-round", type=int, default=100)
    p.add_argument("--min-samples", type=int, default=100, help="Minimum samples required to train")
    p.add_argument(
        "--max-feature-lag-seconds",
        type=float,
        default=DEFAULT_MAX_FEATURE_LAG_SECONDS,
        help="PIT 泄漏防护：featureLagSeconds 超过该阈值（或缺失）的样本剔除（N3-3）",
    )
    args = p.parse_args()

    if np is None or lgb is None:
        print("pip install numpy lightgbm scikit-learn", file=sys.stderr)
        return 1

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    samples_coll = db["rec_training_samples"]

    rows = list(samples_coll.find({"scenario": args.scenario}).sort("ts", 1))
    input_sample_count = len(rows)
    rows, _closed_subjects = reject_closed_documents(db, rows)
    privacy_dropped_samples = input_sample_count - len(rows)
    # N3-3 PIT 泄漏防护（featureLagSeconds=曝光时刻-在线快照时刻）：
    # 负值表示快照来自曝光之后（时间旅行），超阈值表示快照与曝光间隔异常；
    # 两者及缺 lag 的旧样本都按保守策略剔除。
    rows, dropped_lag_rows = filter_point_in_time_rows(
        rows,
        args.max_feature_lag_seconds,
    )
    if dropped_lag_rows:
        print(
            f"[pit] dropped {dropped_lag_rows} samples with missing/excessive "
            f"featureLagSeconds (> {args.max_feature_lag_seconds}s)",
            file=sys.stderr,
        )
    if len(rows) < args.min_samples:
        print(f"Only {len(rows)} samples; need at least {args.min_samples}", file=sys.stderr)
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
    version = utc_now().strftime("mo_v%Y%m%d_%H%M%S")

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

        categorical_features = matched_edge_categorical_features(X_train.shape[1])
        dtrain = lgb.Dataset(
            X_train,
            label=y_train,
            categorical_feature=categorical_features,
        )
        dval = lgb.Dataset(
            X_val,
            label=y_val,
            reference=dtrain,
            categorical_feature=categorical_features,
        )
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
    all_metrics["pit_input_samples"] = input_sample_count
    all_metrics["pit_accepted_samples"] = len(rows)
    all_metrics["pit_dropped_samples"] = dropped_lag_rows
    all_metrics["pit_max_feature_lag_seconds"] = args.max_feature_lag_seconds
    all_metrics["privacy_dropped_samples"] = privacy_dropped_samples
    all_metrics.update(compute_diversity_metrics(test_rows, list(fused_scores), top_k=20))

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
    # N0-5：子模型 .txt 必须与 fusion config 一起上传——serving 侧按 config 的
    # model_files 拉子模型；只传 config 会导致远端拉不到子模型恒回退。
    artifact_uri = ""
    sub_model_uris: dict[str, str] = {}
    try:
        import artifact_store
        for obj_name in models:
            sub_path = out_dir / f"{args.scenario}_{obj_name}_{version}.txt"
            sub_model_uris[obj_name] = artifact_store.upload(
                str(sub_path), args.scenario, version
            )
        # 子模型全部上传成功后，把 uri 写进 fusion config 再上传（config 是
        # serving 的入口 artifact，必须包含子模型的远端地址）。
        fusion_config["model_artifact_uris"] = sub_model_uris
        config_path.write_text(json.dumps(fusion_config, indent=2))
        artifact_uri = artifact_store.upload(str(config_path), args.scenario, version)
    except Exception as e:
        print(f"[train_multiobjective] artifact upload skipped: {e}", file=sys.stderr)
    if args.production and (not artifact_uri or len(sub_model_uris) != len(models)):
        print(
            f"[train_multiobjective] production registry write requires fusion config + all sub-model artifacts uploaded for scenario={args.scenario}",
            file=sys.stderr,
        )
        return 1

    mr.write_registry(
        db,
        scenario=f"{args.scenario}_multiobjective",
        version=version,
        metrics=all_metrics,
        artifact_path=str(config_path),
        artifact_uri=artifact_uri,
        model_type="lgb_multiobjective",
        production=args.production,
    )
    print(f"Registered multi-objective model version={version}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
