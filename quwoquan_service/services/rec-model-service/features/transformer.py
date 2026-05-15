"""
Feature transformer aligned with feature_registry v2.
Maps request payload to a feature matrix for scoring.
"""
from __future__ import annotations

from typing import Any

from generated.models.request_response import ModelScoreRequest


def build_candidate_features(req: ModelScoreRequest) -> list[dict[str, Any]]:
    """Build per-candidate feature dicts for scoring, aligned with feature_registry v2."""
    rows = []
    for c in req.candidates:
        tags = c.tags or []
        rows.append({
            "contentId": c.contentId or "",
            "contentType": c.contentType or "",
            "authorId": c.authorId or "",
            "tags": tags,
            "entityRefs": getattr(c, "entityRefs", None) or [],
            "ageHours": c.ageHours or 0.0,
            "viewCount": c.viewCount or 0,
            "likeCount": c.likeCount or 0,
            "commentCount": c.commentCount or 0,
            "shareCount": c.shareCount or 0,
            "bodyLength": getattr(c, "bodyLength", 0) or 0,
            "hasCover": bool(getattr(c, "hasCover", False)),
            "tagCount": len(tags),
            "qualityScore": getattr(c, "qualityScore", 0.0) or 0.0,
            "publishHour": getattr(c, "publishHour", 0) or 0,
            "recallPath": c.recallPath or "",
        })
    return rows


def transform_user_features(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize user features from request."""
    if not raw:
        return {}
    return {
        "tagAffinities": raw.get("tagAffinities", {}),
        "authorAffinities": raw.get("authorAffinities", {}),
        "engagementRate": float(raw.get("engagementRate", 0)),
        "totalLikes": int(raw.get("totalLikes", 0)),
        "totalFavorites": int(raw.get("totalFavorites", 0)),
        "totalShares": int(raw.get("totalShares", 0)),
        "totalEvents": int(raw.get("totalEvents", 0)),
    }


def transform_session_signals(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize session signals."""
    if not raw:
        return {}
    return {
        "tagWeights": raw.get("tagWeights", {}),
        "exposedIds": list(raw.get("exposedIds", [])),
        "negativeIds": list(raw.get("negativeIds", [])),
        "realtimeInterest": raw.get("realtimeInterest"),
    }
