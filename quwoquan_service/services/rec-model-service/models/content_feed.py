"""
Content-feed scenario scorer.
Uses rule-based formula (placeholder); can load LightGBM model from ModelRegistry later.
"""
from __future__ import annotations

import math
from typing import Any

from generated.models.request_response import (
    CandidateScore,
    ModelScoreRequest,
    ModelScoreResponse,
)
from features.transformer import build_candidate_features


def score_candidate(features: dict[str, Any]) -> tuple[float, dict[str, float]]:
    """
    Rule-based score: popularity (log-scaled) + freshness (exp decay).
    Detail dict for explainability.
    """
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
    detail = {"popularity": popularity, "freshness": freshness, "total": total}
    return total, detail


class ContentFeedScorer:
    """Scorer for scenario=content_feed."""

    def score(self, req: ModelScoreRequest) -> ModelScoreResponse:
        rows = build_candidate_features(req)
        session = req.sessionSignals or {}
        tag_weights = session.get("tagWeights") or {}
        exposed_ids = set(session.get("exposedIds") or [])
        negative_ids = set(session.get("negativeIds") or [])
        scores_list: list[CandidateScore] = []
        for row in rows:
            sc, detail = score_candidate(row)
            content_id = row["contentId"]
            if content_id in exposed_ids or content_id in negative_ids:
                sc -= 1000.0
                detail["filtered"] = 1.0
            else:
                detail["filtered"] = 0.0

            # Session-level tag preference boost.
            boost = 0.0
            for tag in row.get("tags", []):
                try:
                    boost += float(tag_weights.get(tag, 0.0))
                except (TypeError, ValueError):
                    continue
            sc += boost
            detail["sessionTagBoost"] = boost
            detail["total"] = sc
            scores_list.append(
                CandidateScore(
                    contentId=content_id,
                    score=sc,
                    detail=detail,
                )
            )
        return ModelScoreResponse(scores=scores_list)
