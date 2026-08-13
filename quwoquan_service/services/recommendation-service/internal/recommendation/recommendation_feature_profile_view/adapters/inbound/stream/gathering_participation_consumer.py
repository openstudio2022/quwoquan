from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .durable_projection_consumer import DurableProjectionConsumer


GATHERING_STREAM = "events.circle.gatherings"
GATHERING_DLQ = "events.circle.gatherings.recommendation-feature.dlq"
CONSUMER_GROUP = "recommendation-feature-gathering-participation"
SUPPORTED_EVENTS = {"GatheringParticipationChanged"}
PARTICIPATION_STATES = {
    "invited_pending",
    "application_pending",
    "active",
    "closed",
}


@dataclass(frozen=True, slots=True)
class GatheringParticipationEvent:
    event_id: str
    gathering_id: str
    persona_id: str
    state: str
    version: int
    occurred_at: datetime
    event_digest: str


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("GatheringParticipation occurredAt must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_gathering_participation(
    values: dict[str, str],
) -> GatheringParticipationEvent | None:
    event_type = values.get("eventType", "").strip()
    if event_type not in SUPPORTED_EVENTS:
        return None
    if values.get("aggregateType", "").strip() != "Gathering":
        raise ValueError("GatheringParticipation aggregateType is invalid")
    try:
        version = int(values.get("aggregateVersion", ""))
    except ValueError as error:
        raise ValueError("GatheringParticipation aggregateVersion is invalid") from error
    try:
        payload: Any = json.loads(values.get("payload", ""))
    except json.JSONDecodeError as error:
        raise ValueError("GatheringParticipation payload is invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("GatheringParticipation payload must be an object")
    event_id = values.get("eventId", "").strip()
    gathering_id = values.get("aggregateId", "").strip()
    payload_gathering = str(payload.get("gatheringId") or "").strip()
    persona_id = str(payload.get("participantPersonaId") or "").strip()
    state = str(payload.get("participationState") or "").strip()
    if (
        not event_id
        or not gathering_id
        or payload_gathering != gathering_id
        or not persona_id
        or state not in PARTICIPATION_STATES
        or version <= 0
    ):
        raise ValueError("GatheringParticipation identity or lifecycle is invalid")
    occurred_at = _time(values.get("occurredAt", ""))
    canonical = {
        "aggregateVersion": version,
        "eventId": event_id,
        "eventType": event_type,
        "gatheringId": gathering_id,
        "occurredAt": occurred_at.isoformat(),
        "participantPersonaId": persona_id,
        "participationState": state,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return GatheringParticipationEvent(
        event_id=event_id,
        gathering_id=gathering_id,
        persona_id=persona_id,
        state=state,
        version=version,
        occurred_at=occurred_at,
        event_digest=digest,
    )


class GatheringParticipationConsumer(DurableProjectionConsumer):
    """coExperiencedGathering 经历交集的参与事实来源（circle.gathering outbox）。

    只投影「gatheringId × personaId → 当前参与状态」的最小断言；名单、申请答案与
    私密事实不进入本投影。经历交集的另一半事实（公开回顾）由 Post 生命周期
    consumer 的 gatheringRef 证据承载，两者缺一不可。
    """

    def __init__(self, *, redis_client, feature_store, projector, consumer: str) -> None:
        def apply(values: dict[str, str]) -> None:
            event = decode_gathering_participation(values)
            if event is not None:
                projector.project_gathering_participation(
                    event_id=event.event_id,
                    event_digest=event.event_digest,
                    gathering_id=event.gathering_id,
                    persona_id=event.persona_id,
                    state=event.state,
                    version=event.version,
                    occurred_at=event.occurred_at,
                )

        super().__init__(
            redis_client=redis_client,
            feature_store=feature_store,
            stream=GATHERING_STREAM,
            dead_letter_stream=GATHERING_DLQ,
            consumer_group=CONSUMER_GROUP,
            consumer=consumer,
            handler=apply,
            thread_name="recommendation-feature-gathering-participation",
        )
