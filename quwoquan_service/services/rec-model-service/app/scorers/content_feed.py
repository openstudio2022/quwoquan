"""
content_feed scenario scorer.
Rule-based baseline with sessionSignals integration:
- tagWeights: per-session interest boost
- exposedIds / negativeIds: hard penalty (de-prioritize)
Can be replaced by LightGBM when model is loaded from ModelRegistry.
"""
import math

from generated.api.schemas import CandidateInput, CandidateScore, ModelScoreRequest


def _rule_score(c: CandidateInput) -> float:
    """Simple rule: popularity (log-scaled) + freshness. Aligns with Go RuleScorer semantics."""
    like = c.likeCount or 0
    view = c.viewCount or 0
    comment = c.commentCount or 0
    share = c.shareCount or 0
    pop = math.log1p(float(view) * 0.1 + float(like) + float(comment) * 1.5 + float(share) * 2.0)
    age = max(0.0, c.ageHours or 0)
    fresh = math.exp(-age / 24.0)
    return pop * 0.6 + fresh * 0.4


def _session_boost(c: CandidateInput, session_signals: dict) -> tuple[float, bool]:
    if not session_signals:
        return 0.0, False

    content_id = c.contentId or ""
    exposed = set(session_signals.get("exposedIds") or [])
    negative = set(session_signals.get("negativeIds") or [])
    if content_id in negative or content_id in exposed:
        return -1000.0, True

    tag_weights = session_signals.get("tagWeights") or {}
    tags = c.tags or []
    boost = 0.0
    for tag in tags:
        w = tag_weights.get(tag, 0.0)
        try:
            boost += float(w)
        except (TypeError, ValueError):
            continue
    return boost, False


def score(req: ModelScoreRequest) -> list[CandidateScore]:
    """Return one CandidateScore per candidate, same order."""
    out: list[CandidateScore] = []
    session_signals = req.sessionSignals or {}
    for c in req.candidates:
        base = _rule_score(c)
        boost, filtered = _session_boost(c, session_signals)
        s = base + boost
        content_id = c.contentId or ""
        out.append(
            CandidateScore(
                contentId=content_id,
                score=s,
                detail={
                    "rule_base": base,
                    "session_boost": boost,
                    "filtered": 1.0 if filtered else 0.0,
                },
            )
        )
    return out


# For scenario router
content_feed_scorer = type("ContentFeedScorer", (), {"score": staticmethod(score)})()
