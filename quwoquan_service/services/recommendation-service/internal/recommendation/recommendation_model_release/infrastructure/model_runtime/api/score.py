"""Model-runtime implementation of the ModelRelease scoring application ports."""
from __future__ import annotations

import threading
import time
from typing import Any

from api.capacity import (
    clear_score_cache,
    refresh_capacity_metrics,
    score_with_capacity_controls,
)
from api.metrics import refresh_rec_model_loaded_gauges
from generated.recommendation.recommendation_model_release.models.request_response import ModelScoreRequest, ModelScoreResponse
from internal.recommendation.recommendation_model_release.application import RecommendationScoringQueryFacade

_scorers: dict[str, Any] | None = None
_scorers_lock = threading.Lock()
_reload_interval_s = 300


def _init_scorers() -> dict[str, Any]:
    from models.content_feed import ContentFeedScorer
    from models.multiobjective_scorer import MultiObjectiveScorer

    content_feed = ContentFeedScorer()
    multi_obj = MultiObjectiveScorer()
    canary_obj = MultiObjectiveScorer()

    active_content = multi_obj if multi_obj.scorer_kind != "rule" else content_feed

    return {
        "content_feed": active_content,
        "_content_feed_lgb": content_feed,
        "_content_feed_multi": multi_obj,
        "_content_feed_canary": canary_obj,
    }


def _get_scorers() -> dict[str, Any]:
    global _scorers
    if _scorers is None:
        with _scorers_lock:
            if _scorers is None:
                _scorers = _init_scorers()
    return _scorers


def reload_scorers():
    """Reload all scorers from registry. Thread-safe."""
    global _scorers
    new_scorers = _init_scorers()
    with _scorers_lock:
        _scorers = new_scorers
    clear_score_cache()


def _background_reload():
    """Periodically check for newly activated model releases."""
    while True:
        time.sleep(_reload_interval_s)
        try:
            reload_scorers()
            refresh_rec_model_loaded_gauges()
            refresh_capacity_metrics()
        except Exception as exc:
            print(f"[recommendation-service] background reload failed: {exc}", flush=True)


_reload_thread = threading.Thread(target=_background_reload, daemon=True)
_reload_thread.start()


class _RuntimeScorerRegistry:
    def resolve(self, scenario: str, release: str) -> Any | None:
        scorers = _get_scorers()
        if release == "challenger":
            challenger = scorers.get(f"_{scenario}_canary")
            if challenger is not None and getattr(challenger, "scorer_kind", "rule") != "rule":
                return challenger
        return scorers.get(scenario)

    def supported_scenarios(self) -> tuple[str, ...]:
        return tuple(sorted(key for key in _get_scorers() if not key.startswith("_")))


def _capacity_score(body: ModelScoreRequest, scorer_kind: str, compute: Any) -> ModelScoreResponse:
    return score_with_capacity_controls(
        body,
        scorer_kind=scorer_kind,
        compute=compute,
    )


_scoring_facade = RecommendationScoringQueryFacade(
    _RuntimeScorerRegistry(),
    _capacity_score,
)


def get_scoring_facade() -> RecommendationScoringQueryFacade:
    return _scoring_facade
