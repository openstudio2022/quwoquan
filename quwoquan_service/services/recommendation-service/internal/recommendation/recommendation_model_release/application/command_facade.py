from __future__ import annotations

from typing import Protocol

from generated.recommendation.recommendation_model_release.models.request_response import (
    ActivateRecommendationModelReleaseCommand,
    RecommendationModelReleaseCommandResult,
    StageRecommendationModelReleaseCommand,
)

from ..domain.model import ActivateRelease, CommandResult, StageRelease


class ReleaseStore(Protocol):
    def stage(self, command: StageRelease) -> CommandResult: ...

    def activate(self, command: ActivateRelease) -> CommandResult: ...


class RecommendationModelReleaseCommandFacade:
    def __init__(self, store: ReleaseStore) -> None:
        self._store = store

    @staticmethod
    def _wire(result: CommandResult) -> RecommendationModelReleaseCommandResult:
        return RecommendationModelReleaseCommandResult(**result.as_document())

    def stage(
        self, command: StageRecommendationModelReleaseCommand
    ) -> RecommendationModelReleaseCommandResult:
        result = self._store.stage(
            StageRelease.create(
                release_id=command.releaseId,
                scenario=command.scenario,
                model_digest=command.modelDigest,
                feature_contract_digest=command.featureContractDigest,
                artifact_uri=command.artifactUri,
                verification_digest=command.verificationDigest,
                evaluation_metrics=command.evaluationMetrics,
                idempotency_key=command.idempotencyKey,
            )
        )
        return self._wire(result)

    def activate(
        self, command: ActivateRecommendationModelReleaseCommand
    ) -> RecommendationModelReleaseCommandResult:
        result = self._store.activate(
            ActivateRelease.create(
                release_id=command.releaseId,
                scenario=command.scenario,
                expected_active_release_id=command.expectedActiveReleaseId,
                idempotency_key=command.idempotencyKey,
            )
        )
        return self._wire(result)
