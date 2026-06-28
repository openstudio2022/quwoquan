"""Persona deduplication via token-set similarity (embedding proxy)."""
from __future__ import annotations

import re
from typing import Any


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[\W_]+", text.lower()) if len(t) >= 2}


def persona_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    profile_a = a.get("profile") or {}
    profile_b = b.get("profile") or {}
    text_a = " ".join(
        str(profile_a.get(k) or "") for k in ("displayName", "bio", "headline", "userHandle")
    )
    text_b = " ".join(
        str(profile_b.get(k) or "") for k in ("displayName", "bio", "headline", "userHandle")
    )
    ta, tb = _tokens(text_a), _tokens(text_b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def duplicate_persona_p95(bundles: list[dict[str, Any]]) -> float:
    if len(bundles) < 2:
        return 0.0
    scores: list[float] = []
    for i, left in enumerate(bundles):
        best = 0.0
        for j, right in enumerate(bundles):
            if i == j:
                continue
            best = max(best, persona_similarity(left, right))
        scores.append(best)
    scores.sort()
    idx = max(0, int(len(scores) * 0.95) - 1)
    return round(scores[idx], 4)
