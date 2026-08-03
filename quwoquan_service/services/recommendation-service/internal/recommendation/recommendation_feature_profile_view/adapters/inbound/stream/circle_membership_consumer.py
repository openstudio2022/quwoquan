from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .durable_projection_consumer import DurableProjectionConsumer


CIRCLE_MEMBERSHIP_STREAM = "events.circle.memberships"
CIRCLE_MEMBERSHIP_DLQ = "events.circle.memberships.recommendation-feature.dlq"
CONSUMER_GROUP = "recommendation-feature-circle-membership"
SUPPORTED_EVENTS = {
    "CircleMembershipRequested",
    "CircleMembershipJoined",
    "CircleMembershipApproved",
    "CircleMembershipLeft",
    "CircleMembershipRoleChanged",
    "CircleMembershipRejected",
}


@dataclass(frozen=True, slots=True)
class CircleMembershipEvent:
    event_id: str
    membership_id: str
    circle_id: str
    persona_id: str
    state: str
    version: int
    occurred_at: datetime
    event_digest: str


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("CircleMembership occurredAt must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_circle_membership(values: dict[str, str]) -> CircleMembershipEvent | None:
    event_type = values.get("eventType", "").strip()
    if event_type not in SUPPORTED_EVENTS:
        return None
    if values.get("aggregateType", "").strip() != "CircleMembership":
        raise ValueError("CircleMembership aggregateType is invalid")
    try:
        version = int(values.get("aggregateVersion", ""))
    except ValueError as error:
        raise ValueError("CircleMembership aggregateVersion is invalid") from error
    try:
        payload: Any = json.loads(values.get("payload", ""))
    except json.JSONDecodeError as error:
        raise ValueError("CircleMembership payload is invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("CircleMembership payload must be an object")
    event_id = values.get("eventId", "").strip()
    membership_id = values.get("aggregateId", "").strip()
    circle_id = str(payload.get("circleId") or "").strip()
    persona_id = str(payload.get("personaId") or "").strip()
    state = str(payload.get("state") or "").strip()
    payload_id = str(payload.get("id") or "").strip()
    payload_version = int(payload.get("version") or 0)
    occurred_at = _time(values.get("occurredAt", ""))
    if (
        not event_id
        or not membership_id
        or payload_id != membership_id
        or payload_version != version
        or not circle_id
        or not persona_id
        or state not in {"pending", "active", "rejected", "left", "removed"}
        or version <= 0
    ):
        raise ValueError("CircleMembership identity or lifecycle is invalid")
    canonical = {
        "aggregateId": membership_id,
        "aggregateVersion": version,
        "circleId": circle_id,
        "eventId": event_id,
        "eventType": event_type,
        "occurredAt": occurred_at.isoformat(),
        "personaId": persona_id,
        "state": state,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return CircleMembershipEvent(
        event_id=event_id,
        membership_id=membership_id,
        circle_id=circle_id,
        persona_id=persona_id,
        state=state,
        version=version,
        occurred_at=occurred_at,
        event_digest=digest,
    )


class CircleMembershipConsumer(DurableProjectionConsumer):
    def __init__(self, *, redis_client, feature_store, projector, consumer: str) -> None:
        def apply(values: dict[str, str]) -> None:
            event = decode_circle_membership(values)
            if event is not None:
                projector.project_circle_membership(
                    event_id=event.event_id,
                    event_digest=event.event_digest,
                    membership_id=event.membership_id,
                    circle_id=event.circle_id,
                    persona_id=event.persona_id,
                    state=event.state,
                    version=event.version,
                    occurred_at=event.occurred_at,
                )

        super().__init__(
            redis_client=redis_client,
            feature_store=feature_store,
            stream=CIRCLE_MEMBERSHIP_STREAM,
            dead_letter_stream=CIRCLE_MEMBERSHIP_DLQ,
            consumer_group=CONSUMER_GROUP,
            consumer=consumer,
            handler=apply,
            thread_name="recommendation-feature-circle-membership",
        )
