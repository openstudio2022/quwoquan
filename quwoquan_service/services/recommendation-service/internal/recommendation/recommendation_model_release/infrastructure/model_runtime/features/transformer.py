"""
Feature transformer aligned with the canonical feature_registry (see
scripts/feature_registry.yaml). Maps request payload to a feature matrix for
scoring. Intersection features (W7): candidate-level fact strength/freshness
and the advisory affinity channel flow through to models/content_feed.py
_extract_feature_vector; the affinity score only counts when
intersectionConfidenceLabel is present (same semantics as Go ranking fusion).
"""
from __future__ import annotations

from typing import Any

from generated.recommendation.recommendation_model_release.models.request_response import (
    ModelScoreRequest,
)


def build_candidate_features(req: ModelScoreRequest) -> list[dict[str, Any]]:
    """Build per-candidate feature dicts for scoring, aligned with feature_registry."""
    rows = []
    for c in req.candidates:
        tags = c.tagRefs or []
        rows.append({
            "contentId": c.contentId or "",
            "contentType": c.contentType or "",
            "authorId": c.authorId or "",
            "tagRefs": tags,
            "entityRefs": getattr(c, "entityRefs", None) or [],
            # viewer-candidate pair features are projected once by Go through
            # StrongestIntersectionEdgeFor; Python must not receive or rematch
            # the original intersectionEdges map.
            "intersectionEdgeWeight": getattr(c, "intersectionEdgeWeight", 0.0) or 0.0,
            "intersectionEdgeFreshness": getattr(c, "intersectionEdgeFreshness", 0.0) or 0.0,
            "intersectionEdgeKind": getattr(c, "intersectionEdgeKind", "") or "",
            "ageHours": c.ageHours or 0.0,
            "viewCount": c.viewCount or 0,
            "likeCount": c.likeCount or 0,
            "commentCount": c.commentCount or 0,
            "shareCount": c.shareCount or 0,
            # N3-3：bodyLength/hasCover/aspectRatio 已退役（在线召回投影不携带，
            # 恒 0 造成训练-在线偏斜；registry 同步移除，S1 投影补齐后再启用）。
            "tagCount": len(tags),
            "qualityScore": getattr(c, "qualityScore", 0.0) or 0.0,
            # publishHour 由 Go 侧从 publishedAt 派生随请求下发（-1 表缺失）。
            "publishHour": getattr(c, "publishHour", 0) or 0,
            "recallPath": c.recallPath or "",
            # Intersection features (W7, canonical registry): candidate-level fact
            # channel + advisory affinity（confidenceLabel 缺失时抽取器归零）。
            "intersectionFactStrength": getattr(c, "intersectionFactStrength", 0.0) or 0.0,
            "intersectionFreshness": getattr(c, "intersectionFreshness", 0.0) or 0.0,
            "affinityIntersectionScore": getattr(c, "affinityIntersectionScore", 0.0) or 0.0,
            "intersectionSourceRefTop": getattr(c, "intersectionSourceRefTop", "") or "",
            "intersectionConfidenceLabel": getattr(c, "intersectionConfidenceLabel", "") or "",
            "intersectionClass": getattr(c, "intersectionClass", "") or "",
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
        "totalShares": int(raw.get("totalShares", 0)),
        "totalEvents": int(raw.get("totalEvents", 0)),
        # Intersection features (W7, canonical registry): viewer-level fact counts
        # derived by Go FeatureStore（kindCounts 直方图派生），wire 单点注入。
        "sharedFolloweesCount": int(raw.get("sharedFolloweesCount", 0) or 0),
        "sharedCircleCount": int(raw.get("sharedCircleCount", 0) or 0),
        "coCommentedCount": int(raw.get("coCommentedCount", 0) or 0),
        "coVisitedEntityCount": int(raw.get("coVisitedEntityCount", 0) or 0),
        "followeeInObjectActive": int(raw.get("followeeInObjectActive", 0) or 0),
        "followeeViewingActive": int(raw.get("followeeViewingActive", 0) or 0),
        "affinityIntersectionScore": float(
            raw.get("affinityIntersectionScore", 0.0) or 0.0
        ),
        "intersectionSourceRefTop": raw.get("intersectionSourceRefTop", "") or "",
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
