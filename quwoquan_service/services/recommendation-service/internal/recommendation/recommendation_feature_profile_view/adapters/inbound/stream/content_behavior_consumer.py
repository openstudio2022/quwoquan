from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .durable_projection_consumer import DurableProjectionConsumer


CONTENT_BEHAVIOR_STREAM = "events.content.behavior_facts"
CONTENT_BEHAVIOR_DLQ = "events.content.behavior_facts.recommendation-feature.dlq"
CONSUMER_GROUP = "recommendation-feature-content-behavior"


@dataclass(frozen=True, slots=True)
class ContentBehaviorEvent:
    event_id: str
    persona_id: str
    target_id: str
    target_type: str
    action: str
    entity_refs: tuple[str, ...]
    display_name: str
    occurred_at: datetime
    event_digest: str


def _time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("ContentBehaviorRecorded occurredAt must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _strings(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"ContentBehaviorRecorded {field} must be an array")
    result = tuple(str(item).strip() for item in value)
    if any(not item for item in result) or len(set(result)) != len(result):
        raise ValueError(f"ContentBehaviorRecorded {field} must be unique and non-empty")
    return result


def decode_content_behavior(values: dict[str, str]) -> ContentBehaviorEvent | None:
    if values.get("eventName", "").strip() != "ContentBehaviorRecorded":
        return None
    try:
        payload: Any = json.loads(values.get("payload", ""))
    except json.JSONDecodeError as error:
        raise ValueError("ContentBehaviorRecorded payload is invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("ContentBehaviorRecorded payload must be an object")
    subject_id = values.get("subjectId", "").strip()
    persona_id = str(payload.get("personaId") or "").strip()
    client_event_id = str(payload.get("clientEventId") or "").strip()
    event_id = values.get("eventId", "").strip()
    expected_id = hashlib.sha256(
        f"ContentBehaviorRecorded:{subject_id}:{client_event_id}".encode()
    ).hexdigest()
    if not subject_id or not client_event_id or event_id != expected_id:
        raise ValueError("ContentBehaviorRecorded identity is invalid")
    occurred_at = _time(values.get("occurredAt", ""))
    if occurred_at != _time(payload.get("occurredAt")):
        raise ValueError("ContentBehaviorRecorded occurredAt mismatch")
    target_id = str(payload.get("objectId") or payload.get("contentId") or "").strip()
    outer_target = values.get("targetId", "").strip()
    content_id = str(payload.get("contentId") or "").strip()
    if outer_target != content_id:
        raise ValueError("ContentBehaviorRecorded targetId mismatch")
    target_type = str(
        payload.get("objectKind") or payload.get("contentType") or "post"
    ).strip()
    action = str(payload.get("action") or "").strip()
    entity_refs = _strings(payload.get("entityRefs"), field="entityRefs")
    if not target_id or not target_type or not action:
        raise ValueError("ContentBehaviorRecorded projection fields are incomplete")
    canonical = {
        "action": action,
        "clientEventId": client_event_id,
        "displayName": str(payload.get("displayName") or "").strip(),
        "entityRefs": entity_refs,
        "eventId": event_id,
        "occurredAt": occurred_at.isoformat(),
        "personaId": persona_id,
        "subjectId": subject_id,
        "targetId": target_id,
        "targetType": target_type,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return ContentBehaviorEvent(
        event_id=event_id,
        persona_id=persona_id,
        target_id=target_id,
        target_type=target_type,
        action=action,
        entity_refs=entity_refs,
        display_name=str(payload.get("displayName") or "").strip(),
        occurred_at=occurred_at,
        event_digest=digest,
    )


class ContentBehaviorConsumer(DurableProjectionConsumer):
    def __init__(self, *, redis_client, feature_store, projector, consumer: str) -> None:
        def apply(values: dict[str, str]) -> None:
            event = decode_content_behavior(values)
            if event is not None and event.persona_id:
                projector.project_behavior(
                    event_id=event.event_id,
                    event_digest=event.event_digest,
                    persona_id=event.persona_id,
                    target_id=event.target_id,
                    target_type=event.target_type,
                    action=event.action,
                    entity_refs=event.entity_refs,
                    display_name=event.display_name,
                    occurred_at=event.occurred_at,
                )

        super().__init__(
            redis_client=redis_client,
            feature_store=feature_store,
            stream=CONTENT_BEHAVIOR_STREAM,
            dead_letter_stream=CONTENT_BEHAVIOR_DLQ,
            consumer_group=CONSUMER_GROUP,
            consumer=consumer,
            handler=apply,
            thread_name="recommendation-feature-content-behavior",
        )
