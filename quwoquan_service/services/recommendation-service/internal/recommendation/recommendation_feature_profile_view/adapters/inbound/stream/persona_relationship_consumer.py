from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json

from .durable_projection_consumer import DurableProjectionConsumer


PERSONA_RELATIONSHIP_STREAM = "events.user.persona_relationship"
PERSONA_RELATIONSHIP_DLQ = "events.user.persona_relationship.recommendation-feature.dlq"
CONSUMER_GROUP = "recommendation-feature-persona-relationship"
SUPPORTED_EVENTS = {
    "PersonaFollowStateChanged",
    "PersonaBlocked",
    "PersonaUnblocked",
}


@dataclass(frozen=True, slots=True)
class PersonaRelationshipEvent:
    event_id: str
    event_name: str
    source_persona_id: str
    target_persona_id: str
    following: bool
    source_follow_cleared: bool
    target_follow_cleared: bool
    version: int
    occurred_at: datetime
    event_digest: str


def _boolean(value: str, *, field: str, default: bool | None = None) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    if default is not None and not normalized:
        return default
    raise ValueError(f"persona relationship {field} is invalid")


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("persona relationship occurredAt must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_persona_relationship(values: dict[str, str]) -> PersonaRelationshipEvent | None:
    event_name = values.get("eventName", "").strip()
    if event_name not in SUPPORTED_EVENTS:
        return None
    event_id = values.get("eventId", "").strip()
    source = values.get("sourcePersonaId", "").strip()
    target = values.get("targetPersonaId", "").strip()
    following = _boolean(values.get("following", ""), field="following")
    source_cleared = _boolean(
        values.get("sourceFollowCleared", ""),
        field="sourceFollowCleared",
        default=False,
    )
    target_cleared = _boolean(
        values.get("targetFollowCleared", ""),
        field="targetFollowCleared",
        default=False,
    )
    try:
        version = int(values.get("version", ""))
    except ValueError as error:
        raise ValueError("persona relationship version is invalid") from error
    occurred_at = _time(values.get("occurredAt", ""))
    if not event_id or not source or not target or source == target or version <= 0:
        raise ValueError("persona relationship identity is invalid")
    if event_name in {"PersonaBlocked", "PersonaUnblocked"} and following:
        raise ValueError("block lifecycle event cannot retain following=true")
    canonical = {
        "eventId": event_id,
        "eventName": event_name,
        "following": following,
        "occurredAt": occurred_at.isoformat(),
        "sourceFollowCleared": source_cleared,
        "sourcePersonaId": source,
        "targetFollowCleared": target_cleared,
        "targetPersonaId": target,
        "version": version,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return PersonaRelationshipEvent(
        event_id=event_id,
        event_name=event_name,
        source_persona_id=source,
        target_persona_id=target,
        following=following,
        source_follow_cleared=source_cleared,
        target_follow_cleared=target_cleared,
        version=version,
        occurred_at=occurred_at,
        event_digest=digest,
    )


class PersonaRelationshipConsumer(DurableProjectionConsumer):
    def __init__(self, *, redis_client, feature_store, projector, consumer: str) -> None:
        def apply(values: dict[str, str]) -> None:
            event = decode_persona_relationship(values)
            if event is not None:
                projector.project_persona_relationship(
                    event_id=event.event_id,
                    event_digest=event.event_digest,
                    event_name=event.event_name,
                    source_persona_id=event.source_persona_id,
                    target_persona_id=event.target_persona_id,
                    following=event.following,
                    source_follow_cleared=event.source_follow_cleared,
                    target_follow_cleared=event.target_follow_cleared,
                    version=event.version,
                    occurred_at=event.occurred_at,
                )

        super().__init__(
            redis_client=redis_client,
            feature_store=feature_store,
            stream=PERSONA_RELATIONSHIP_STREAM,
            dead_letter_stream=PERSONA_RELATIONSHIP_DLQ,
            consumer_group=CONSUMER_GROUP,
            consumer=consumer,
            handler=apply,
            thread_name="recommendation-feature-persona-relationship",
        )
