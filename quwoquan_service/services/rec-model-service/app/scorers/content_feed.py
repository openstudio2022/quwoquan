"""
content_feed scenario scorer.
Rule-based placeholder; can be replaced by LightGBM when model is loaded from ModelRegistry.
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


def score(req: ModelScoreRequest) -> list[CandidateScore]:
    """Return one CandidateScore per candidate, same order."""
    out: list[CandidateScore] = []
    for c in req.candidates:
        s = _rule_score(c)
        content_id = c.contentId or ""
        out.append(
            CandidateScore(contentId=content_id, score=s, detail={"rule": s})
        )
    return out


# For scenario router
content_feed_scorer = type("ContentFeedScorer", (), {"score": staticmethod(score)})()
