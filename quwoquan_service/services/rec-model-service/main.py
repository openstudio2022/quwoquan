"""
rec-model-service: recommendation model inference API.
POST /v1/score (multi-scenario), GET /health.
"""
from fastapi import FastAPI

from api.score import router as score_router
from runtime_contract import bootstrap_runtime_contract_or_die

bootstrap_runtime_contract_or_die()

app = FastAPI(
    title="quwoquan recommendation-service",
    version="v1",
    description="Recommendation model scoring (content_feed / circle_discovery / friend_suggestion).",
)
app.include_router(score_router)
