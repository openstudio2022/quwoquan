"""
rec-model-service: recommendation model inference API.
POST /v1/score (multi-scenario), GET /health, GET /metrics (Prometheus).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from api.metrics import refresh_rec_model_loaded_gauges
from api.score import router as score_router
from runtime_contract import bootstrap_runtime_contract_or_die

bootstrap_runtime_contract_or_die()


@asynccontextmanager
async def lifespan(app: FastAPI):
    refresh_rec_model_loaded_gauges()
    yield


app = FastAPI(
    title="quwoquan recommendation-service",
    version="v1",
    lifespan=lifespan,
    description="Recommendation model scoring (content_feed / circle_discovery / friend_suggestion).",
)
app.include_router(score_router)

Instrumentator().instrument(app).expose(app)
