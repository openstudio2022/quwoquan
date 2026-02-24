"""Request validation and scenario routing to per-scenario scorers."""
from generated.api.schemas import (
    CandidateScore,
    ModelScoreRequest,
    ModelScoreResponse,
)

from app.scorers.content_feed import content_feed_scorer

# Scenario -> scorer callable: (request) -> list[CandidateScore]
_SCORERS: dict[str, callable] = {
    "content_feed": content_feed_scorer.score,
    # Optional placeholders for future:
    # "circle_discovery": circle_discovery_scorer.score,
    # "friend_suggestion": friend_suggestion_scorer.score,
}

DEFAULT_SCENARIO = "content_feed"


def score_request(req: ModelScoreRequest) -> ModelScoreResponse:
    """Validate and route by scenario; return scores."""
    if not req.candidates:
        return ModelScoreResponse(scores=[])
    scenario = (req.scenario or "").strip() or DEFAULT_SCENARIO
    scorer = _SCORERS.get(scenario)
    if scorer is None:
        # Fallback to content_feed for unknown scenario
        scorer = _SCORERS[DEFAULT_SCENARIO]
    scores = scorer(req)
    return ModelScoreResponse(scores=scores)
