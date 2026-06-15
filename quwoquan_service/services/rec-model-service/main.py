"""
rec-model-service: recommendation model inference API.
POST /v1/score (multi-scenario), GET /health, GET /metrics (Prometheus).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator import routing as instrumentator_routing
from starlette.routing import Match

from api.metrics import refresh_rec_model_loaded_gauges
from api.score import router as score_router
from runtime_contract import bootstrap_runtime_contract_or_die

bootstrap_runtime_contract_or_die()


@asynccontextmanager
async def lifespan(app: FastAPI):
    refresh_rec_model_loaded_gauges()
    yield


def _patch_instrumentator_route_name() -> None:
    """兼容 FastAPI 新路由包装对象，避免 metrics 中间件在测试时崩溃。"""

    def _safe_get_route_name(scope, routes, route_name=None):
        for route in routes:
            match, child_scope = route.matches(scope)
            if match == Match.FULL:
                current_name = getattr(route, "path", route_name)
                child_routes = getattr(route, "routes", None)
                if child_routes:
                    nested_name = _safe_get_route_name(child_scope, child_routes, current_name)
                    if nested_name is not None:
                        return nested_name
                if current_name is not None:
                    return current_name
            elif match == Match.PARTIAL and route_name is None:
                current_name = getattr(route, "path", None)
                child_routes = getattr(route, "routes", None)
                if child_routes:
                    nested_name = _safe_get_route_name(child_scope, child_routes, current_name)
                    if nested_name is not None:
                        return nested_name
                if current_name is not None:
                    return current_name
        return route_name

    instrumentator_routing._get_route_name = _safe_get_route_name


_patch_instrumentator_route_name()


app = FastAPI(
    title="quwoquan recommendation-service",
    version="v1",
    lifespan=lifespan,
    description="Recommendation model scoring (content_feed / circle_discovery / friend_suggestion).",
)
app.include_router(score_router)

Instrumentator().instrument(app).expose(app)
