# spec_ref: specs/feature-tree/recommendation-platform/rec-model-service/spec.md#sit-001
# readiness_case: score-candidates-local
# readiness_case: batch-score-candidates-local
from generated.recommendation.recommendation_model_release.models.request_response import (
    BatchModelScoreRequest,
    CandidateInput,
    CandidateScore,
    ModelScoreRequest,
    ModelScoreResponse,
)
from internal.recommendation.recommendation_model_release.application.scoring_facade import (
    RecommendationScoringQueryFacade,
)
from internal.recommendation.recommendation_model_release.adapters.inbound.http.scoring_router import (
    build_scoring_router,
)


class _Scorer:
    scorer_kind = "typed-double"

    def score(self, request: ModelScoreRequest) -> ModelScoreResponse:
        return ModelScoreResponse(
            modelReleaseId="release-001",
            scores=[
                CandidateScore(contentId=item.contentId, score=float(index + 1))
                for index, item in enumerate(request.candidates)
            ],
        )


class _Registry:
    def resolve(self, scenario: str, release: str):
        assert release == "champion"
        if scenario != "content_feed":
            return None
        return _Scorer()

    def supported_scenarios(self) -> tuple[str, ...]:
        return ("content_feed",)


def _request(content_id: str) -> ModelScoreRequest:
    return ModelScoreRequest(
        scenario="content_feed",
        userId="persona-001",
        sessionId="session-001",
        candidates=[CandidateInput(contentId=content_id)],
    )


def test_scoring_facade_uses_the_typed_reader_and_capacity_port() -> None:
    capacity_calls: list[tuple[str, str]] = []

    def capacity_score(request, scorer_kind, invoke):
        capacity_calls.append((request.scenario, scorer_kind))
        return invoke()

    facade = RecommendationScoringQueryFacade(_Registry(), capacity_score)
    response = facade.score(_request("post-001"))

    assert response.modelReleaseId == "release-001"
    assert response.scores[0].contentId == "post-001"
    assert capacity_calls == [("content_feed", "typed-double")]


def test_batch_scoring_preserves_request_order_and_single_query_semantics() -> None:
    facade = RecommendationScoringQueryFacade(
        _Registry(), lambda _request, _kind, invoke: invoke()
    )

    response = facade.batch_score(
        BatchModelScoreRequest(requests=[_request("post-a"), _request("post-b")])
    )

    assert [item.scores[0].contentId for item in response.results] == [
        "post-a",
        "post-b",
    ]


class _TokenVerifier:
    def verify(self, authorization, *, required_scope):
        assert authorization == "Bearer local-contract"
        assert required_scope == "recommendation.model.score"
        return {"sub": "service:local-contract"}


def test_scoring_http_adapter_decodes_both_operations_and_uses_runtime_boundary() -> None:
    requests: list[tuple[str, str]] = []
    durations: list[tuple[str, float]] = []
    facade = RecommendationScoringQueryFacade(
        _Registry(), lambda _request, _kind, invoke: invoke()
    )
    app = FastAPI()
    app.include_router(
        build_scoring_router(
            facade=facade,
            token_verifier=_TokenVerifier(),
            record_request=lambda path, outcome: requests.append((path, outcome)),
            observe_duration=lambda release, duration: durations.append((release, duration)),
        )
    )
    client = TestClient(app)
    headers = {"Authorization": "Bearer local-contract"}
    single = client.post(
        SCORE_RECOMMENDATION_CANDIDATES_PATH,
        headers=headers,
        json=_request("post-http").model_dump(by_alias=True),
    )
    assert single.status_code == 200
    assert single.json()["scores"][0]["contentId"] == "post-http"

    batch = client.post(
        BATCH_SCORE_RECOMMENDATION_CANDIDATES_PATH,
        headers=headers,
        json={"requests": [_request("post-batch").model_dump(by_alias=True)]},
    )
    assert batch.status_code == 200
    assert batch.json()["results"][0]["scores"][0]["contentId"] == "post-batch"
    assert requests == [
        (SCORE_RECOMMENDATION_CANDIDATES_PATH, "200"),
        (BATCH_SCORE_RECOMMENDATION_CANDIDATES_PATH, "200"),
    ]
    assert len(durations) == 2


def test_scoring_http_adapter_maps_unknown_scenario_to_canonical_error() -> None:
    facade = RecommendationScoringQueryFacade(
        _Registry(), lambda _request, _kind, invoke: invoke()
    )
    app = FastAPI()
    app.include_router(
        build_scoring_router(
            facade=facade,
            token_verifier=_TokenVerifier(),
            record_request=lambda _path, _outcome: None,
            observe_duration=lambda _release, _duration: None,
        )
    )
    response = TestClient(app).post(
        SCORE_RECOMMENDATION_CANDIDATES_PATH,
        headers={"Authorization": "Bearer local-contract"},
        json={
            "scenario": "unknown",
            "userId": "persona-001",
            "sessionId": "session-001",
            "candidates": [{"contentId": "post-unknown"}],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "RECOMMENDATION.USER.invalid_argument"
from fastapi import FastAPI
from fastapi.testclient import TestClient

from generated.recommendation.recommendation_model_release.api.operations import (
    BATCH_SCORE_RECOMMENDATION_CANDIDATES_PATH,
    SCORE_RECOMMENDATION_CANDIDATES_PATH,
)
