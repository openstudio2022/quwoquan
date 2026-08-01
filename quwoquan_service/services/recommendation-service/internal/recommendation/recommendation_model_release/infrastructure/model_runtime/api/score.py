"""Request validation and scenario routing for the ModelRelease scoring Reader."""
from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from api.capacity import (
    clear_score_cache,
    refresh_capacity_metrics,
    score_with_capacity_controls,
)
from api.metrics import (
    observe_score_duration,
    record_rec_request,
    refresh_rec_model_loaded_gauges,
)
from generated.recommendation.recommendation_model_release.models.request_response import (
    BatchModelScoreRequest,
    BatchModelScoreResponse,
    ModelScoreRequest,
    ModelScoreResponse,
)
from generated.recommendation.recommendation_model_release.api.operations import (
    BATCH_SCORE_RECOMMENDATION_CANDIDATES_PATH,
    SCORE_RECOMMENDATION_CANDIDATES_PATH,
)
from internal.recommendation.recommendation_model_release.application import (
    RecommendationScoringQueryFacade,
    UnsupportedScenarioError,
)
from security.service_authorization import AuthorizationFailure, ServiceTokenVerifier

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


def _reload_scorers():
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
            _reload_scorers()
            refresh_rec_model_loaded_gauges()
            refresh_capacity_metrics()
        except Exception as exc:
            print(f"[recommendation-service] background reload failed: {exc}", flush=True)


_reload_thread = threading.Thread(target=_background_reload, daemon=True)
_reload_thread.start()

router = APIRouter()
_service_token_verifier = ServiceTokenVerifier.from_env()


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


def require_scoring_service(request: Request) -> dict[str, Any]:
    try:
        return _service_token_verifier.verify(request.headers.get("Authorization"))
    except AuthorizationFailure as failure:
        raise HTTPException(
            status_code=failure.status_code,
            detail={"code": failure.code, "context": {"attributes": {}}},
        ) from None


@router.post(SCORE_RECOMMENDATION_CANDIDATES_PATH, response_model=ModelScoreResponse)
def score(
    body: ModelScoreRequest,
    _principal: dict[str, Any] = Depends(require_scoring_service),
) -> ModelScoreResponse:
    score_path = SCORE_RECOMMENDATION_CANDIDATES_PATH
    if not body.candidates:
        record_rec_request(score_path, "200")
        return _scoring_facade.score(body)
    t0 = time.perf_counter()
    try:
        result = _scoring_facade.score(body)
    except UnsupportedScenarioError as error:
        record_rec_request(score_path, "400")
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )
    except Exception:
        record_rec_request(score_path, "500")
        raise
    elapsed = time.perf_counter() - t0
    observe_score_duration(str(result.modelReleaseId or "rule"), elapsed)
    record_rec_request(score_path, "200")
    return result


@router.post(
    BATCH_SCORE_RECOMMENDATION_CANDIDATES_PATH,
    response_model=BatchModelScoreResponse,
)
def batch_score(
    body: BatchModelScoreRequest,
    _principal: dict[str, Any] = Depends(require_scoring_service),
) -> BatchModelScoreResponse:
    return _scoring_facade.batch_score(body)


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    candidate_consumer = getattr(
        request.app.state,
        "candidate_post_lifecycle_consumer",
        None,
    )
    premium_consumer = getattr(
        request.app.state,
        "candidate_premium_pool_consumer",
        None,
    )
    experiment_policy_consumer = getattr(
        request.app.state,
        "experiment_policy_consumer",
        None,
    )
    closure_consumer = getattr(
        request.app.state,
        "user_account_closed_consumer",
        None,
    )
    feedback_consumer = getattr(
        request.app.state,
        "content_behavior_consumer",
        None,
    )
    exposure_consumer = getattr(
        request.app.state,
        "feed_page_delivered_consumer",
        None,
    )
    ranked_window_facade = getattr(request.app.state, "ranked_window_facade", None)
    model_release_facade = getattr(
        request.app.state,
        "model_release_command_facade",
        None,
    )
    common_runtime_unready = (
        model_release_facade is None
        or candidate_consumer is None
        or premium_consumer is None
        or closure_consumer is None
        or feedback_consumer is None
        or exposure_consumer is None
        or not candidate_consumer.healthy()
        or not premium_consumer.healthy()
        or not closure_consumer.healthy()
        or not feedback_consumer.healthy()
        or not exposure_consumer.healthy()
    )
    content_release_only = (
        getattr(request.app.state, "runtime_workload", "full") == "content-release"
    )
    scoring_runtime_unready = (
        ranked_window_facade is None
        or experiment_policy_consumer is None
        or not experiment_policy_consumer.healthy()
    )
    if common_runtime_unready:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready"},
        )
    if scoring_runtime_unready and content_release_only:
        return {"status": "content_release_only"}
    if scoring_runtime_unready:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready"},
        )
    return {"status": "ok"}
