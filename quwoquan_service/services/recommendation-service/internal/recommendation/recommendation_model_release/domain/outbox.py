from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


class OutboxClaimLostError(RuntimeError):
    pass


MODEL_RELEASE_EVENT_PAYLOAD_FIELDS: dict[str, tuple[str, ...]] = {
    "RecommendationModelReleaseStaged": (
        "id",
        "scenario",
        "modelDigest",
        "featureContractDigest",
        "status",
        "createdAt",
    ),
    "RecommendationModelReleaseActivated": (
        "id",
        "scenario",
        "modelDigest",
        "featureContractDigest",
        "status",
        "activatedAt",
    ),
    "RecommendationModelReleaseRetired": (
        "id",
        "scenario",
        "status",
        "retiredAt",
    ),
}

_EVENT_STATUS = {
    "RecommendationModelReleaseStaged": "staged",
    "RecommendationModelReleaseActivated": "active",
    "RecommendationModelReleaseRetired": "retired",
}
_EVENT_TIMESTAMP_FIELD = {
    "RecommendationModelReleaseStaged": "createdAt",
    "RecommendationModelReleaseActivated": "activatedAt",
    "RecommendationModelReleaseRetired": "retiredAt",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("model release event timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def build_model_release_event_payload(
    event_type: str,
    *,
    release_id: str,
    scenario: str,
    occurred_at: datetime,
    model_digest: str | None = None,
    feature_contract_digest: str | None = None,
) -> dict[str, Any]:
    if event_type not in MODEL_RELEASE_EVENT_PAYLOAD_FIELDS:
        raise ValueError("model release event type is not declared")
    identity = release_id.strip()
    normalized_scenario = scenario.strip()
    if not identity or not normalized_scenario:
        raise ValueError("model release event identity is incomplete")
    timestamp_field = _EVENT_TIMESTAMP_FIELD[event_type]
    payload: dict[str, Any] = {
        "id": identity,
        "scenario": normalized_scenario,
        "status": _EVENT_STATUS[event_type],
        timestamp_field: _canonical_timestamp(occurred_at),
    }
    if event_type != "RecommendationModelReleaseRetired":
        normalized_model_digest = (model_digest or "").strip()
        normalized_feature_digest = (feature_contract_digest or "").strip()
        if not _SHA256.fullmatch(normalized_model_digest) or not _SHA256.fullmatch(
            normalized_feature_digest
        ):
            raise ValueError("model release event digest is invalid")
        payload["modelDigest"] = normalized_model_digest
        payload["featureContractDigest"] = normalized_feature_digest
    validate_model_release_event_payload(event_type, payload)
    return payload


def validate_model_release_event_payload(
    event_type: str,
    payload: dict[str, Any],
) -> None:
    expected_fields = MODEL_RELEASE_EVENT_PAYLOAD_FIELDS.get(event_type)
    if expected_fields is None:
        raise ValueError("model release event type is not declared")
    if set(payload) != set(expected_fields):
        raise ValueError("model release event payload does not match its contract")
    if not str(payload["id"]).strip() or not str(payload["scenario"]).strip():
        raise ValueError("model release event identity is incomplete")
    if payload["status"] != _EVENT_STATUS[event_type]:
        raise ValueError("model release event status is invalid")
    if event_type != "RecommendationModelReleaseRetired" and (
        not _SHA256.fullmatch(str(payload["modelDigest"]))
        or not _SHA256.fullmatch(str(payload["featureContractDigest"]))
    ):
        raise ValueError("model release event digest is invalid")
    timestamp = payload[_EVENT_TIMESTAMP_FIELD[event_type]]
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ValueError("model release event timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise ValueError("model release event timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("model release event timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    event_id: str
    event_type: str
    aggregate_id: str
    aggregate_version: int
    payload: dict[str, Any]
    occurred_at: datetime
    attempt_count: int


class TransactionalOutbox(Protocol):
    def claim_pending_outbox(
        self,
        owner_id: str,
        now: datetime,
        lease_seconds: float,
    ) -> OutboxEvent | None: ...

    def mark_outbox_published(
        self,
        event_id: str,
        owner_id: str,
        published_at: datetime,
    ) -> None: ...

    def schedule_outbox_retry(
        self,
        event_id: str,
        owner_id: str,
        next_attempt_at: datetime,
        failure_code: str,
    ) -> None: ...
