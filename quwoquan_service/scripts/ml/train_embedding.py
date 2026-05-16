#!/usr/bin/env python3
"""
Dual-tower embedding training: user tower + item tower -> cosine similarity.

Reads training samples from rec_training_samples and produces user/item embedding
models that can be used for vector recall and dual-tower ranking.

Usage:
    python scripts/ml/train_embedding.py --scenario content_feed [--epochs 10]
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
    import numpy as np
except ImportError:
    np = None

EMBEDDING_DIM = 64
LEARNING_RATE = 0.001

USER_FEATURE_KEYS = [
    "engagementRate", "totalLikes", "totalFavorites", "totalShares", "totalEvents",
]
ITEM_FEATURE_KEYS = [
    "ageHours", "viewCount", "likeCount", "commentCount", "shareCount",
    "bodyLength", "tagCount", "qualityScore", "publishHour",
]
CONTENT_TYPE_MAP = {"photo": 0, "video": 1, "article": 2, "moment": 3}


def _build_user_vector(sample: dict) -> list[float]:
    user = sample.get("userFeatures") or {}
    ctx = sample.get("contextFeatures") or {}
    vec = []
    for k in USER_FEATURE_KEYS:
        vec.append(float(user.get(k, 0) or 0))
    vec.append(float(ctx.get("requestHour", 0) or 0))
    vec.append(float(ctx.get("requestDayOfWeek", 0) or 0))
    tag_aff = user.get("tagAffinities", {})
    sorted_tags = sorted(tag_aff.items(), key=lambda x: -x[1])[:10]
    for i in range(10):
        vec.append(sorted_tags[i][1] if i < len(sorted_tags) else 0.0)
    return vec


def _build_item_vector(sample: dict) -> list[float]:
    item = sample.get("itemFeatures") or {}
    vec = []
    for k in ITEM_FEATURE_KEYS:
        vec.append(float(item.get(k, 0) or 0))
    vec.append(float(CONTENT_TYPE_MAP.get(item.get("contentType", ""), -1)))
    vec.append(1.0 if item.get("hasCover") else 0.0)
    return vec


def _normalize_rows(X: "np.ndarray") -> "np.ndarray":
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return X / norms


class SimpleDualTower:
    """Minimal dual-tower model using linear projection + cosine similarity."""

    def __init__(self, user_dim: int, item_dim: int, embed_dim: int = EMBEDDING_DIM):
        self.embed_dim = embed_dim
        rng = np.random.default_rng(42)
        scale_u = np.sqrt(2.0 / (user_dim + embed_dim))
        scale_i = np.sqrt(2.0 / (item_dim + embed_dim))
        self.W_user = rng.normal(0, scale_u, (user_dim, embed_dim))
        self.W_item = rng.normal(0, scale_i, (item_dim, embed_dim))
        self.b_user = np.zeros(embed_dim)
        self.b_item = np.zeros(embed_dim)

    def user_embed(self, X: "np.ndarray") -> "np.ndarray":
        return _normalize_rows(np.tanh(X @ self.W_user + self.b_user))

    def item_embed(self, X: "np.ndarray") -> "np.ndarray":
        return _normalize_rows(np.tanh(X @ self.W_item + self.b_item))

    def predict(self, X_user: "np.ndarray", X_item: "np.ndarray") -> "np.ndarray":
        u_emb = self.user_embed(X_user)
        i_emb = self.item_embed(X_item)
        return np.sum(u_emb * i_emb, axis=1)

    def train_step(self, X_user, X_item, y, lr=LEARNING_RATE):
        """One gradient descent step with cosine embedding loss."""
        batch = len(y)
        u_raw = X_user @ self.W_user + self.b_user
        i_raw = X_item @ self.W_item + self.b_item
        u_emb = np.tanh(u_raw)
        i_emb = np.tanh(i_raw)
        u_norm = _normalize_rows(u_emb)
        i_norm = _normalize_rows(i_emb)

        cos_sim = np.sum(u_norm * i_norm, axis=1)
        # labels: 1 for positive, -1 for negative
        targets = 2.0 * y - 1.0
        margin = 0.1
        loss_per = np.maximum(0, margin - targets * cos_sim)
        loss = np.mean(loss_per)

        # Gradient (simplified: skip normalization jacobian for stability)
        active = (loss_per > 0).astype(float)
        d_cos = -targets * active / batch
        d_u_emb = (d_cos[:, None] * i_norm)
        d_i_emb = (d_cos[:, None] * u_norm)

        dtanh_u = 1 - u_emb ** 2
        dtanh_i = 1 - i_emb ** 2
        d_u_pre = d_u_emb * dtanh_u
        d_i_pre = d_i_emb * dtanh_i

        grad_Wu = X_user.T @ d_u_pre
        grad_Wi = X_item.T @ d_i_pre
        grad_bu = d_u_pre.sum(axis=0)
        grad_bi = d_i_pre.sum(axis=0)

        self.W_user -= lr * np.clip(grad_Wu, -1, 1)
        self.W_item -= lr * np.clip(grad_Wi, -1, 1)
        self.b_user -= lr * np.clip(grad_bu, -1, 1)
        self.b_item -= lr * np.clip(grad_bi, -1, 1)

        return loss

    def save(self, path: Path):
        np.savez(
            str(path),
            W_user=self.W_user,
            W_item=self.W_item,
            b_user=self.b_user,
            b_item=self.b_item,
            embed_dim=self.embed_dim,
        )

    @classmethod
    def load(cls, path: Path) -> "SimpleDualTower":
        data = np.load(str(path))
        user_dim = data["W_user"].shape[0]
        item_dim = data["W_item"].shape[0]
        embed_dim = int(data["embed_dim"])
        model = cls(user_dim, item_dim, embed_dim)
        model.W_user = data["W_user"]
        model.W_item = data["W_item"]
        model.b_user = data["b_user"]
        model.b_item = data["b_item"]
        return model


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="content_feed")
    p.add_argument("--mongodb-uri", default=os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
    p.add_argument("--db", default="quwoquan_content")
    p.add_argument("--out-dir", default=os.environ.get("MODEL_OUT_DIR", "/tmp/rec_models"))
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=256)
    p.add_argument("--embed-dim", type=int, default=EMBEDDING_DIM)
    p.add_argument("--production", action="store_true")
    args = p.parse_args()

    if np is None:
        print("pip install numpy", file=sys.stderr)
        return 1

    client = MongoClient(args.mongodb_uri)
    db = client[args.db]
    samples_coll = db["rec_training_samples"]

    rows = list(samples_coll.find({"scenario": args.scenario}).sort("ts", 1))
    if len(rows) < 100:
        print(f"Only {len(rows)} samples; need at least 100", file=sys.stderr)
        return 1

    n = len(rows)
    train_end = int(n * 0.80)

    X_user_all = np.array([_build_user_vector(r) for r in rows])
    X_item_all = np.array([_build_item_vector(r) for r in rows])
    y_all = np.array([float((r.get("labels") or {}).get("engaged", 0)) for r in rows])

    X_user_train, X_item_train, y_train = X_user_all[:train_end], X_item_all[:train_end], y_all[:train_end]
    X_user_test, X_item_test, y_test = X_user_all[train_end:], X_item_all[train_end:], y_all[train_end:]

    user_dim = X_user_train.shape[1]
    item_dim = X_item_train.shape[1]

    print(f"Training dual-tower: user_dim={user_dim}, item_dim={item_dim}, embed_dim={args.embed_dim}", file=sys.stderr)
    print(f"Train: {len(y_train)}, Test: {len(y_test)}", file=sys.stderr)

    model = SimpleDualTower(user_dim, item_dim, args.embed_dim)

    for epoch in range(args.epochs):
        indices = np.random.permutation(len(y_train))
        epoch_loss = 0.0
        n_batches = 0
        for start in range(0, len(y_train), args.batch_size):
            idx = indices[start:start + args.batch_size]
            loss = model.train_step(X_user_train[idx], X_item_train[idx], y_train[idx])
            epoch_loss += loss
            n_batches += 1
        avg_loss = epoch_loss / max(n_batches, 1)
        print(f"  Epoch {epoch+1}/{args.epochs}: loss={avg_loss:.4f}", file=sys.stderr)

    # Evaluate
    scores_test = model.predict(X_user_test, X_item_test)
    from sklearn.metrics import roc_auc_score
    test_auc = roc_auc_score(y_test, scores_test) if len(set(y_test)) > 1 else 0.5

    # Recall@K: for each positive, check if it's in top-K by score
    pos_mask = y_test == 1
    if pos_mask.sum() > 0:
        sorted_idx = np.argsort(-scores_test)
        top20 = set(sorted_idx[:20].tolist())
        pos_in_top20 = sum(1 for i in np.where(pos_mask)[0] if i in top20)
        recall_at_20 = pos_in_top20 / pos_mask.sum()
    else:
        recall_at_20 = 0.0

    metrics = {
        "auc": round(float(test_auc), 4),
        "recall_at_20": round(float(recall_at_20), 4),
        "train_size": len(y_train),
        "test_size": len(y_test),
        "embed_dim": args.embed_dim,
        "epochs": args.epochs,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    version = datetime.utcnow().strftime("emb_v%Y%m%d_%H%M%S")
    model_path = out_dir / f"{args.scenario}_{version}.npz"
    model.save(model_path)

    print(f"Embedding metrics: {json.dumps(metrics)}", file=sys.stderr)

    import model_registry as mr
    artifact_uri = ""
    try:
        import artifact_store
        artifact_uri = artifact_store.upload(str(model_path), args.scenario, version)
    except Exception as e:
        print(f"[train_embedding] artifact upload skipped: {e}", file=sys.stderr)

    mr.write_registry(
        db,
        scenario=f"{args.scenario}_embedding",
        version=version,
        metrics=metrics,
        artifact_path=str(model_path),
        artifact_uri=artifact_uri,
        model_type="dual_tower",
        production=args.production,
    )
    print(f"Saved embedding model to {model_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
