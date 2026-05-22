"""
Prometheus metrics for rec-model-service (custom business metrics).

HTTP 指标由 prometheus_fastapi_instrumentator 注册；本模块仅包含推荐业务相关指标。
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

rec_score_duration = Histogram(
    "rec_score_duration_seconds",
    "Recommendation scoring latency in seconds",
    ["model_version"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

rec_score_value = Histogram(
    "rec_score_value",
    "Recommendation score distribution before final ranking penalties",
    ["model_version"],
    buckets=[0.0, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0],
)

rec_requests_total = Counter(
    "rec_requests_total",
    "Total recommendation requests (business counter)",
    ["endpoint", "status"],
)

rec_model_loaded = Gauge(
    "rec_model_loaded",
    "Whether the recommendation model is loaded (1=yes, 0=no)",
    ["model_version"],
)


def observe_score_duration(model_version: str, seconds: float) -> None:
    mv = model_version if model_version else "unknown"
    rec_score_duration.labels(model_version=mv).observe(seconds)


def observe_score_value(model_version: str, score: float) -> None:
    mv = model_version if model_version else "unknown"
    rec_score_value.labels(model_version=mv).observe(score)


def record_rec_request(endpoint: str, status: str) -> None:
    rec_requests_total.labels(endpoint=endpoint, status=status).inc()


def refresh_rec_model_loaded_gauges() -> None:
    """根据当前 scorer 刷新各 model_version 的加载态（ML≠rule 视为已加载）。"""
    from api.score import _get_scorers

    scorers = _get_scorers()
    for key, s in scorers.items():
        if key.startswith("_"):
            continue
        ver = str(
            getattr(s, "model_version", getattr(s, "_model_version", "unknown"))
        )
        loaded = 1.0 if ver != "rule" else 0.0
        rec_model_loaded.labels(model_version=ver).set(loaded)
