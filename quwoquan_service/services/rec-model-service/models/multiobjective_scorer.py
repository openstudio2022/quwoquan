"""
Multi-objective scorer for content_feed scenario.
Loads per-objective LightGBM models and fuses predictions with weighted sum.
Falls back to single-model ContentFeedScorer if multi-obj models unavailable.
"""
from __future__ import annotations

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
from models.content_feed import _extract_feature_vector, rule_score

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

OBJECTIVES = {
    "click":    {"weight": 0.30},
    "dwell_s":  {"weight": 0.25},
    "like":     {"weight": 0.15},
    "favorite": {"weight": 0.10},
    "share":    {"weight": 0.08},
    "comment":  {"weight": 0.07},
    "follow":   {"weight": 0.05},
}


def _resolve_cached_artifact_path(artifact_path: str) -> Path | None:
    if not artifact_path:
        return None
    candidate = Path(artifact_path)
    cache_dir = Path(os.environ.get("MODEL_CACHE_DIR", "/app/cache"))
    candidates = [candidate, cache_dir / candidate.name]
    if not candidate.is_absolute():
        candidates.append(cache_dir / candidate)
    for path in candidates:
        if path.exists():
            return path
    return None


def _load_multiobjective_models() -> tuple[dict[str, Any] | None, dict[str, float] | None]:
    """Load multi-objective models and optional fusion weights from registry."""
    if lgb is None or MongoClient is None:
        return None, None
    uri = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/?directConnection=true")
    db_name = os.environ.get("MONGODB_DATABASE", "quwoquan_content")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        db = client[db_name]
        doc = db["rec_model_registry"].find_one(
            {"scenario": "content_feed_multiobjective", "modelType": "lgb_multiobjective", "production": True},
            sort=[("createdAt", -1)],
        )
        if not doc:
            doc = db["rec_model_registry"].find_one(
                {"scenario": "content_feed_multiobjective"},
                sort=[("createdAt", -1)],
            )
        if not doc:
            return None, None

        artifact_uri = doc.get("artifactUri", "")
        artifact_path = doc.get("artifactPath", "")

        load_path = None
        if artifact_uri:
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ml"))
                sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "ml"))
                import artifact_store
                load_path = artifact_store.download(artifact_uri)
            except Exception:
                pass
        if not load_path:
            resolved_path = _resolve_cached_artifact_path(artifact_path)
            if resolved_path:
                load_path = str(resolved_path)

        if not load_path:
            return None, None

        load_path = Path(load_path)
        load_dir = load_path.parent if load_path.is_file() else load_path

        fusion_config = None
        if load_path.is_file() and load_path.suffix == ".json":
            try:
                import json as _json
                fusion_config = _json.loads(load_path.read_text())
            except Exception:
                pass

        model_files_map = fusion_config.get("model_files", {}) if fusion_config else {}

        models = {}
        for obj_name in OBJECTIVES:
            candidates = [
                load_dir / model_files_map.get(obj_name, ""),
                load_dir / f"{obj_name}_model.txt",
            ]
            for candidate in candidates:
                if candidate.name and candidate.exists():
                    models[obj_name] = lgb.Booster(model_file=str(candidate))
                    break

        fusion_weights = None
        if fusion_config:
            obj_cfgs = fusion_config.get("objectives", {})
            fusion_weights = {k: v.get("weight", OBJECTIVES.get(k, {}).get("weight", 0)) for k, v in obj_cfgs.items()}

        return (models, fusion_weights) if models else (None, None)
    except Exception:
        return None, None


class MultiObjectiveScorer:
    """Scorer that fuses per-objective LightGBM predictions."""

    def __init__(self):
        self._models, self._fusion_weights = _load_multiobjective_models()
        self._model_version = "multi_obj" if self._models else "rule"

    @property
    def model_version(self) -> str:
        return self._model_version

    def _get_weight(self, obj_name: str) -> float:
        if self._fusion_weights and obj_name in self._fusion_weights:
            return self._fusion_weights[obj_name]
        return OBJECTIVES.get(obj_name, {}).get("weight", 0)

    def reload(self):
        self._models, self._fusion_weights = _load_multiobjective_models()
        self._model_version = "multi_obj" if self._models else "rule"

    def score(self, req: ModelScoreRequest) -> ModelScoreResponse:
        rows = build_candidate_features(req)
        session = req.sessionSignals or {}
        tag_weights = session.get("tagWeights") or {}
        exposed_ids = set(session.get("exposedIds") or [])
        negative_ids = set(session.get("negativeIds") or [])
        user_feat = req.userFeatures or {}
        ctx_feat = req.context or {}

        scores_list: list[CandidateScore] = []

        if self._models and np is not None:
            X = np.array([_extract_feature_vector(r, user_feat, ctx_feat) for r in rows])
            fused_scores = np.zeros(len(rows))
            detail_maps = [{} for _ in rows]

            for obj_name in OBJECTIVES:
                if obj_name in self._models:
                    preds = self._models[obj_name].predict(X)
                    weight = self._get_weight(obj_name)
                    fused_scores += preds * weight
                    for i in range(len(rows)):
                        detail_maps[i][f"obj_{obj_name}"] = float(preds[i])

            for i, row in enumerate(rows):
                sc = float(fused_scores[i])
                detail = detail_maps[i].copy()
                detail["model"] = "multi_obj"
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
