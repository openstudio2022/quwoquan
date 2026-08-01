from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class InvalidCommandError(ValueError):
    pass


def _identity(value: str, name: str) -> str:
    normalized = value.strip()
    if not _IDENTITY.fullmatch(normalized):
        raise InvalidCommandError(f"{name} is not a canonical identity")
    return normalized


def _digest(value: str, name: str) -> str:
    normalized = value.strip()
    if not _SHA256.fullmatch(normalized):
        raise InvalidCommandError(f"{name} must be a lowercase SHA-256 digest")
    return normalized


def _artifact_uri(value: str) -> str:
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise InvalidCommandError("artifactUri must be an immutable s3 URI")
    if parsed.query or parsed.fragment:
        raise InvalidCommandError("artifactUri must not contain query or fragment")
    return normalized


def _idempotency_key(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized.encode("utf-8")) > 256:
        raise InvalidCommandError(
            "Idempotency-Key is required and must not exceed 256 bytes"
        )
    return normalized


def canonical_payload_digest(payload: dict[str, Any]) -> str:
    try:
        encoded = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise InvalidCommandError("evaluationMetrics must be canonical JSON") from error
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class StageRelease:
    release_id: str
    scenario: str
    model_digest: str
    feature_contract_digest: str
    artifact_uri: str
    verification_digest: str
    evaluation_metrics: dict[str, Any]
    idempotency_key: str

    @classmethod
    def create(
        cls,
        *,
        release_id: str,
        scenario: str,
        model_digest: str,
        feature_contract_digest: str,
        artifact_uri: str,
        verification_digest: str,
        evaluation_metrics: dict[str, Any],
        idempotency_key: str,
    ) -> "StageRelease":
        if not isinstance(evaluation_metrics, dict) or not evaluation_metrics:
            raise InvalidCommandError("evaluationMetrics must be a non-empty object")
        canonical_payload_digest(evaluation_metrics)
        return cls(
            release_id=_identity(release_id, "releaseId"),
            scenario=_identity(scenario, "scenario"),
            model_digest=_digest(model_digest, "modelDigest"),
            feature_contract_digest=_digest(
                feature_contract_digest, "featureContractDigest"
            ),
            artifact_uri=_artifact_uri(artifact_uri),
            verification_digest=_digest(verification_digest, "verificationDigest"),
            evaluation_metrics=dict(evaluation_metrics),
            idempotency_key=_idempotency_key(idempotency_key),
        )

    def command_digest(self) -> str:
        return canonical_payload_digest(
            {
                "operation": "StageRecommendationModelRelease",
                "releaseId": self.release_id,
                "scenario": self.scenario,
                "modelDigest": self.model_digest,
                "featureContractDigest": self.feature_contract_digest,
                "artifactUri": self.artifact_uri,
                "verificationDigest": self.verification_digest,
                "evaluationMetrics": self.evaluation_metrics,
            }
        )


@dataclass(frozen=True, slots=True)
class ActivateRelease:
    release_id: str
    scenario: str
    expected_active_release_id: str | None
    idempotency_key: str

    @classmethod
    def create(
        cls,
        *,
        release_id: str,
        scenario: str,
        expected_active_release_id: str | None,
        idempotency_key: str,
    ) -> "ActivateRelease":
        expected = (
            _identity(expected_active_release_id, "expectedActiveReleaseId")
            if expected_active_release_id is not None
            and expected_active_release_id.strip()
            else None
        )
        return cls(
            release_id=_identity(release_id, "releaseId"),
            scenario=_identity(scenario, "scenario"),
            expected_active_release_id=expected,
            idempotency_key=_idempotency_key(idempotency_key),
        )

    def command_digest(self) -> str:
        return canonical_payload_digest(
            {
                "operation": "ActivateRecommendationModelRelease",
                "releaseId": self.release_id,
                "scenario": self.scenario,
                "expectedActiveReleaseId": self.expected_active_release_id,
            }
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    release_id: str
    scenario: str
    status: str
    version: int
    active_release_id: str | None
    idempotent_replay: bool = False

    def as_document(self) -> dict[str, Any]:
        return {
            "releaseId": self.release_id,
            "scenario": self.scenario,
            "status": self.status,
            "version": self.version,
            "activeReleaseId": self.active_release_id,
            "idempotentReplay": self.idempotent_replay,
        }

    @classmethod
    def from_document(
        cls, document: dict[str, Any], *, replayed: bool = False
    ) -> "CommandResult":
        return cls(
            release_id=str(document["releaseId"]),
            scenario=str(document["scenario"]),
            status=str(document["status"]),
            version=int(document["version"]),
            active_release_id=(
                str(document["activeReleaseId"])
                if document.get("activeReleaseId") is not None
                else None
            ),
            idempotent_replay=replayed,
        )
