"""RecommendationModelRelease scoring query use cases.

HTTP, model loading and capacity enforcement stay behind injected ports. This
module owns scenario/release selection and the single/batch query semantics.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from generated.recommendation.recommendation_model_release.models.request_response import (
    BatchModelScoreRequest,
    BatchModelScoreResponse,
    ModelScoreRequest,
    ModelScoreResponse,
)


class ScorerPort(Protocol):
    model_version: str

    def score(self, request: ModelScoreRequest) -> ModelScoreResponse: ...


class ScorerRegistryPort(Protocol):
    def resolve(self, scenario: str, release: str) -> ScorerPort | None: ...

    def supported_scenarios(self) -> tuple[str, ...]: ...


CapacityScore = Callable[
    [ModelScoreRequest, str, Callable[[], ModelScoreResponse]],
    ModelScoreResponse,
]


class UnsupportedScenarioError(ValueError):
    def __init__(self, scenario: str, supported: tuple[str, ...]) -> None:
        self.scenario = scenario
        self.supported = supported
        super().__init__(
            f"Unsupported scenario: {scenario}. Supported: {list(supported)}"
        )


class RecommendationScoringQueryFacade:
    """Object-owned query facade for active RecommendationModelRelease scoring."""

    def __init__(
        self,
        registry: ScorerRegistryPort,
        capacity_score: CapacityScore,
    ) -> None:
        self._registry = registry
        self._capacity_score = capacity_score

    def score(self, request: ModelScoreRequest) -> ModelScoreResponse:
        if not request.candidates:
            return ModelScoreResponse(scores=[])

        context: dict[str, Any] = request.context or {}
        release = str(context.get("modelVersion", "champion"))
        scorer = self._registry.resolve(request.scenario, release)
        if scorer is None:
            raise UnsupportedScenarioError(
                request.scenario,
                self._registry.supported_scenarios(),
            )

        model_version = str(
            getattr(scorer, "model_version", getattr(scorer, "_model_version", "unknown"))
        )
        return self._capacity_score(
            request,
            model_version,
            lambda: scorer.score(request),
        )

    def batch_score(self, request: BatchModelScoreRequest) -> BatchModelScoreResponse:
        return BatchModelScoreResponse(
            results=[self.score(item) for item in request.requests]
        )
