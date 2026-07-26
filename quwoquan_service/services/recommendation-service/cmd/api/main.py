"""recommendation-service composition root."""

from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request
from prometheus_client import Counter, Histogram, make_asgi_app

from api.capacity import refresh_capacity_metrics
from api.metrics import refresh_rec_model_loaded_gauges
from runtime_contract import bootstrap_runtime_contract_or_die


bootstrap_runtime_contract_or_die()

from api.score import router as score_router  # noqa: E402


http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests served by recommendation-service.",
    ["handler", "method", "status"],
)

http_request_duration_highr_seconds = Histogram(
    "http_request_duration_highr_seconds",
    "HTTP request latency with high-resolution buckets.",
    ["handler", "method", "status"],
    buckets=[0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    refresh_rec_model_loaded_gauges()
    refresh_capacity_metrics()
    yield


app = FastAPI(
    title="quwoquan recommendation-service",
    lifespan=lifespan,
    description="Recommendation model scoring through the ModelRelease Reader contract.",
)


def _handler_label(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if route_path:
        return str(route_path)
    return request.url.path or "unknown"


@app.middleware("http")
async def observe_http(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        handler = _handler_label(request)
        elapsed = time.perf_counter() - started
        http_requests_total.labels(
            handler=handler,
            method=request.method,
            status="5xx",
        ).inc()
        http_request_duration_highr_seconds.labels(
            handler=handler,
            method=request.method,
            status="5xx",
        ).observe(elapsed)
        raise

    handler = _handler_label(request)
    status_group = f"{response.status_code // 100}xx"
    elapsed = time.perf_counter() - started
    http_requests_total.labels(
        handler=handler,
        method=request.method,
        status=status_group,
    ).inc()
    http_request_duration_highr_seconds.labels(
        handler=handler,
        method=request.method,
        status=status_group,
    ).observe(elapsed)
    return response


app.include_router(score_router)
app.mount("/metrics", make_asgi_app())
