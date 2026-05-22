"""
Request validation, scenario routing, and model lifecycle for POST /v1/score.
Supports hot-reload of models via POST /v1/model/reload and periodic background refresh.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from api.metrics import (
    observe_score_duration,
    record_rec_request,
    refresh_rec_model_loaded_gauges,
)
from generated.models.request_response import (
    ModelScoreRequest,
    ModelScoreResponse,
)

_scorers: dict[str, Any] | None = None
_scorers_lock = threading.Lock()
_reload_interval_s = 300
_last_reload: datetime | None = None


def _init_scorers() -> dict[str, Any]:
    from models.content_feed import ContentFeedScorer
    from models.multiobjective_scorer import MultiObjectiveScorer

    content_feed = ContentFeedScorer()
    multi_obj = MultiObjectiveScorer()
    canary_obj = MultiObjectiveScorer()

    active_content = multi_obj if multi_obj.model_version != "rule" else content_feed

    return {
        "content_feed": active_content,
        "_content_feed_lgb": content_feed,
        "_content_feed_multi": multi_obj,
        "_content_feed_canary": canary_obj,
    }


def _get_scorers() -> dict[str, Any]:
    global _scorers, _last_reload
    if _scorers is None:
        with _scorers_lock:
            if _scorers is None:
                _scorers = _init_scorers()
                _last_reload = datetime.utcnow()
    return _scorers


def _reload_scorers():
    """Reload all scorers from registry. Thread-safe."""
    global _scorers, _last_reload
    new_scorers = _init_scorers()
    with _scorers_lock:
        _scorers = new_scorers
        _last_reload = datetime.utcnow()


def _background_reload():
    """Periodically check for new model versions."""
    while True:
        time.sleep(_reload_interval_s)
        try:
            _reload_scorers()
            refresh_rec_model_loaded_gauges()
        except Exception:
            pass


_reload_thread = threading.Thread(target=_background_reload, daemon=True)
_reload_thread.start()

router = APIRouter()


@router.post("/v1/score", response_model=ModelScoreResponse)
def score(body: ModelScoreRequest) -> ModelScoreResponse:
    score_path = "/v1/score"
    if not body.candidates:
        record_rec_request(score_path, "200")
        return ModelScoreResponse(scores=[])
    scorers = _get_scorers()

    model_version = (body.context or {}).get("modelVersion", "champion") if body.context else "champion"
    if model_version == "challenger":
        scorer = scorers.get(f"_{body.scenario}_canary")
        if scorer is None or getattr(scorer, "model_version", "rule") == "rule":
            scorer = scorers.get(body.scenario)
    else:
        scorer = scorers.get(body.scenario)
    if scorer is None:
        record_rec_request(score_path, "400")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported scenario: {body.scenario}. Supported: {[k for k in scorers if not k.startswith('_')]}",
        )
    t0 = time.perf_counter()
    try:
        result = scorer.score(body)
    except Exception:
        record_rec_request(score_path, "500")
        raise
    elapsed = time.perf_counter() - t0
    mv = getattr(scorer, "model_version", getattr(scorer, "_model_version", "unknown"))
    observe_score_duration(str(mv), elapsed)
    record_rec_request(score_path, "200")
    return result


@router.post("/v1/model/reload")
def reload_models() -> dict[str, Any]:
    """Trigger immediate model reload from registry."""
    _reload_scorers()
    refresh_rec_model_loaded_gauges()
    scorers = _get_scorers()
    versions = {}
    for key, s in scorers.items():
        if key.startswith("_"):
            continue
        v = getattr(s, "_model_version", getattr(s, "model_version", "unknown"))
        versions[key] = v
    return {"status": "reloaded", "versions": versions, "reloaded_at": datetime.utcnow().isoformat()}


@router.get("/v1/model/status")
def model_status() -> dict[str, Any]:
    """Return current model versions and reload status."""
    scorers = _get_scorers()
    versions = {}
    for key, s in scorers.items():
        if key.startswith("_"):
            continue
        v = getattr(s, "_model_version", getattr(s, "model_version", "unknown"))
        versions[key] = v
    return {
        "versions": versions,
        "last_reload": _last_reload.isoformat() if _last_reload else None,
        "reload_interval_s": _reload_interval_s,
    }


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
