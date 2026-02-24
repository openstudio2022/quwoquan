"""HTTP routes: POST /v1/score, GET /health. Uses generated schemas."""
from fastapi import APIRouter, HTTPException

from generated.api.schemas import ModelScoreRequest, ModelScoreResponse

from app.score import score_request

router = APIRouter()


@router.post("/v1/score", response_model=ModelScoreResponse)
def score(body: ModelScoreRequest) -> ModelScoreResponse:
    """Multi-scenario recommendation scoring."""
    return score_request(body)


@router.get("/health")
def health() -> dict:
    """Health check."""
    return {"status": "ok"}
