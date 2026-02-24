"""
Request validation and scenario routing for POST /v1/score.
Delegates to scenario-specific scorers (content_feed required; others optional placeholder).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from generated.models.request_response import (
    ModelScoreRequest,
    ModelScoreResponse,
)

# Lazy import to avoid circular deps and allow optional scenario modules
_scorers: dict[str, object] | None = None


def _get_scorers() -> dict[str, object]:
    global _scorers
    if _scorers is None:
        from models.content_feed import ContentFeedScorer
        _scorers = {
            "content_feed": ContentFeedScorer(),
            # Optional: "circle_discovery": ..., "friend_suggestion": ...
        }
    return _scorers


router = APIRouter()


@router.post("/v1/score", response_model=ModelScoreResponse)
def score(body: ModelScoreRequest) -> ModelScoreResponse:
    """Validate request and route by scenario to the appropriate scorer."""
    if not body.candidates:
        return ModelScoreResponse(scores=[])
    scorers = _get_scorers()
    scorer = scorers.get(body.scenario)
    if scorer is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported scenario: {body.scenario}. Supported: {list(scorers.keys())}",
        )
    # All scorers implement .score(req) -> ModelScoreResponse
    return scorer.score(body)


@router.get("/health")
def health() -> dict[str, str]:
    """Health check for load balancer and readiness probes."""
    return {"status": "ok"}
