"""
Content-feed scenario scorer.
Loads LightGBM model from ModelRegistry; falls back to rule-based scoring.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any

from generated.models.request_response import (
    CandidateScore,
    ModelScoreRequest,
    ModelScoreResponse,
)
from api.metrics import observe_score_value
from features.transformer import build_candidate_features

try:
    import lightgbm as lgb
    import numpy as np
except ImportError:
    lgb = None
    np = None

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

CONTENT_TYPE_MAP = {"photo": 0, "video": 1, "article": 2, "moment": 3}

ITEM_NUMERIC = [
    "ageHours", "viewCount", "likeCount", "commentCount", "shareCount",
    "bodyLength", "tagCount", "qualityScore", "publishHour", "aspectRatio",
]
RECALL_PATH_MAP = {"tag_recall": 0, "hot_recall": 1, "social_friend": 2, "social_circle": 3, "explore_recall": 4}
USER_NUMERIC = [
    "engagementRate", "totalLikes", "totalFavorites", "totalShares", "totalEvents",
]
CONTEXT_NUMERIC = ["requestHour", "requestDayOfWeek"]


def _extract_feature_vector(row: dict, user_feat: dict, ctx_feat: dict) -> list[float]:
    """Must align with train.py _extract_features (34 dims)."""
    features: list[float] = []
    for f in ITEM_NUMERIC:
        features.append(float(row.get(f, 0) or 0))
    for f in USER_NUMERIC:
        features.append(float(user_feat.get(f, 0) or 0))
    for f in CONTEXT_NUMERIC:
        features.append(float(ctx_feat.get(f, 0) or 0))
    features.append(float(CONTENT_TYPE_MAP.get(row.get("contentType", ""), -1)))
    features.append(1.0 if row.get("hasCover") else 0.0)
    features.append(float(RECALL_PATH_MAP.get(row.get("recallPath", ""), -1)))

    tag_affinities = user_feat.get("tagAffinities", {})
    item_tags = row.get("tags", [])
    tag_match = sum(tag_affinities.get(t, 0) for t in item_tags[:10])
    features.append(tag_match)

    author_affinities = user_feat.get("authorAffinities", {})
    features.append(author_affinities.get(row.get("authorId", ""), 0.0))

    topic_affinities = user_feat.get("topicAffinities", {})
    audience_affinities = user_feat.get("audienceAffinities", {})
    format_affinities = user_feat.get("formatAffinities", {})
    entity_affinities = user_feat.get("entityAffinities", {})
    entity_instance_affinities = user_feat.get("entityInstanceAffinities", {})

    topic_match = sum(topic_affinities.get(t, 0) for t in item_tags[:10])
    audience_match = sum(audience_affinities.get(t, 0) for t in item_tags[:10])
    format_match = sum(format_affinities.get(t, 0) for t in item_tags[:10])
    entity_match = sum(entity_affinities.get(t, 0) for t in item_tags[:10])
    features.extend([topic_match, audience_match, format_match, entity_match])

    entity_refs = row.get("entityRefs", []) or []
    entity_instance_match = sum(entity_instance_affinities.get(r, 0) for r in entity_refs[:10])
    features.append(entity_instance_match)

    features.append(float(user_feat.get("avgEngagementDepth", 0) or 0))
    depth_dist = user_feat.get("depthDistribution", {}) or {}
    for level in ["L0", "L1", "L2", "L3", "L4"]:
        features.append(float(depth_dist.get(level, 0)))

    features.append(float(user_feat.get("socialInterestScore", 0) or 0))
    circle_aff = user_feat.get("circleTagAffinities", {}) or {}
    circle_match = sum(circle_aff.get(t, 0) for t in item_tags[:10])
    features.append(circle_match)

    type_ener = user_feat.get("typeENER", {}) or {}
    content_type = row.get("contentType", "")
    features.append(float(type_ener.get(content_type, 0)))

    return features


def rule_score(features: dict[str, Any]) -> tuple[float, dict[str, float]]:
    like = float(features.get("likeCount") or 0)
    comment = float(features.get("commentCount") or 0)
    share = float(features.get("shareCount") or 0)
    view = float(features.get("viewCount") or 0)
    age_hours = float(features.get("ageHours") or 0)
    if age_hours < 0:
        age_hours = 0
    popularity = math.log1p(view * 0.1 + like * 1.0 + comment * 1.5 + share * 2.0)
    freshness = math.exp(-age_hours / 24.0)
    total = popularity * 0.6 + freshness * 0.4
    return total, {"popularity": popularity, "freshness": freshness, "total": total}


def _resolve_cached_artifact_path(artifact_path: str) -> str | None:
    if not artifact_path:
        return None
    candidate = Path(artifact_path)
    cache_dir = Path(os.environ.get("MODEL_CACHE_DIR", "/app/cache"))
    candidates = [candidate, cache_dir / candidate.name]
    if not candidate.is_absolute():
        candidates.append(cache_dir / candidate)
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def _load_model_from_registry() -> Any:
    """Load production LightGBM model from MongoDB registry.

    Resolution order:
    1. artifactUri (S3/OSS) → download to local cache
    2. artifactPath (local filesystem) → direct load
    3. None → rule fallback
    """
    if lgb is None or MongoClient is None:
        return None
    uri = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true")
    db_name = os.environ.get("MONGODB_DATABASE", "quwoquan_content")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        db = client[db_name]
        doc = db["rec_model_registry"].find_one(
            {"scenario": "content_feed", "production": True},
            sort=[("createdAt", -1)],
        )
        if not doc:
            return None

        artifact_uri = doc.get("artifactUri", "")
        if artifact_uri:
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ml"))
                sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "ml"))
                import artifact_store
                local_path = artifact_store.download(artifact_uri)
                return lgb.Booster(model_file=local_path)
            except Exception:
                pass

        artifact_path = doc.get("artifactPath", "")
        resolved_path = _resolve_cached_artifact_path(artifact_path)
        if resolved_path:
            return lgb.Booster(model_file=resolved_path)
    except Exception:
        pass
    return None


class ContentFeedScorer:
    """Scorer for scenario=content_feed. Loads LightGBM model on init."""

    def __init__(self):
        self._model = _load_model_from_registry()
        self._model_version = "lgb" if self._model else "rule"

    @property
    def model_version(self) -> str:
        return self._model_version

    def reload(self):
        self._model = _load_model_from_registry()
        self._model_version = "lgb" if self._model else "rule"

    def score(self, req: ModelScoreRequest) -> ModelScoreResponse:
        rows = build_candidate_features(req)
        session = req.sessionSignals or {}
        tag_weights = session.get("tagWeights") or {}
        exposed_ids = set(session.get("exposedIds") or [])
        negative_ids = set(session.get("negativeIds") or [])
        user_feat = req.userFeatures or {}
        ctx_feat = req.context or {}

        scores_list: list[CandidateScore] = []

        if self._model is not None and np is not None:
            X = np.array([_extract_feature_vector(r, user_feat, ctx_feat) for r in rows])
            predictions = self._model.predict(X)
            for i, row in enumerate(rows):
                sc = float(predictions[i])
                detail = {"model": "lgb", "raw_score": sc}
                content_id = row["contentId"]
                boost = sum(float(tag_weights.get(t, 0)) for t in row.get("tags", []))
                sc += boost * 0.1
                detail["sessionTagBoost"] = boost
                observe_score_value(self._model_version, sc)
                if content_id in exposed_ids or content_id in negative_ids:
                    sc -= 1000.0
                    detail["filtered"] = 1.0
                detail["total"] = sc
                scores_list.append(CandidateScore(contentId=content_id, score=sc, detail=detail))
        else:
            for row in rows:
                sc, detail = rule_score(row)
                content_id = row["contentId"]
                boost = sum(float(tag_weights.get(t, 0)) for t in row.get("tags", []))
                sc += boost
                detail["sessionTagBoost"] = boost
                observe_score_value(self._model_version, sc)
                if content_id in exposed_ids or content_id in negative_ids:
                    sc -= 1000.0
                    detail["filtered"] = 1.0
                else:
                    detail["filtered"] = 0.0
                detail["total"] = sc
                scores_list.append(CandidateScore(contentId=content_id, score=sc, detail=detail))

        return ModelScoreResponse(scores=scores_list)
