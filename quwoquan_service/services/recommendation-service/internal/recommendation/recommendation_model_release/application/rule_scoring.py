from __future__ import annotations

import math
from typing import Any


def rule_score(features: dict[str, Any]) -> tuple[float, dict[str, float]]:
    """Canonical deterministic fallback used by every content-feed ranker."""

    like = float(features.get("likeCount") or 0)
    comment = float(features.get("commentCount") or 0)
    share = float(features.get("shareCount") or 0)
    view = float(features.get("viewCount") or 0)
    age_hours = max(float(features.get("ageHours") or 0), 0.0)
    popularity = math.log1p(view * 0.1 + like + comment * 1.5 + share * 2.0)
    freshness = math.exp(-age_hours / 24.0)
    total = popularity * 0.6 + freshness * 0.4
    return total, {
        "popularity": popularity,
        "freshness": freshness,
        "total": total,
    }
