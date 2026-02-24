"""
Feature transformer aligned with feature_registry.
Maps request payload to a feature matrix for scoring (placeholder: pass-through).
"""
from __future__ import annotations

from typing import Any

from generated.models.request_response import ModelScoreRequest


def build_candidate_features(req: ModelScoreRequest) -> list[dict[str, Any]]:
    """
    Build per-candidate feature dicts for scoring.
    Aligned with feature_registry; currently uses request fields as-is.
    """
    rows = []
    for c in req.candidates:
        rows.append({
            "contentId": c.contentId or "",
            "contentType": c.contentType or "",
            "authorId": c.authorId or "",
            "tags": c.tags or [],
            "ageHours": c.ageHours or 0.0,
            "viewCount": c.viewCount or 0,
            "likeCount": c.likeCount or 0,
            "commentCount": c.commentCount or 0,
            "shareCount": c.shareCount or 0,
            "recallPath": c.recallPath or "",
        })
    return rows


def transform_user_features(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize user features from request. Placeholder."""
    return dict(raw) if raw else {}


def transform_session_signals(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize session signals. Placeholder."""
    return dict(raw) if raw else {}
