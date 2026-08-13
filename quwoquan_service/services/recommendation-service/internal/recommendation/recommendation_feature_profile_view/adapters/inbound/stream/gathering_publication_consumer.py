from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .durable_projection_consumer import DurableProjectionConsumer


GATHERING_PUBLICATION_STREAM = "events.circle.gatherings"
GATHERING_PUBLICATION_DLQ = (
    "events.circle.gatherings.recommendation-social-proof.dlq"
)
CONSUMER_GROUP = "recommendation-feature-gathering-publication"
SUPPORTED_EVENTS = {"GatheringPublished"}


@dataclass(frozen=True, slots=True)
class GatheringPublicationEvent:
    event_id: str
    gathering_id: str
    organizer_id: str
    source_refs: tuple[tuple[str, str], ...]
    max_participants: int
    admission_policy: str
    version: int
    occurred_at: datetime
    event_digest: str


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("GatheringPublication occurredAt must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_gathering_publication(
    values: dict[str, str],
) -> GatheringPublicationEvent | None:
    """GatheringPublished → 发起级社会证明证据（organizer + 溯源引用）。

    诚实口径：只接受 owner outbox 的 published 事实；身份漂移（payload
    gatheringId 与 aggregateId 不一致）、缺 organizer 一律拒收进 DLQ；
    sourceRefs 可为空（无溯源的行动只进发起人锚点，不进实体/内容锚点）。
    """
    event_type = values.get("eventType", "").strip()
    if event_type not in SUPPORTED_EVENTS:
        return None
    if values.get("aggregateType", "").strip() != "Gathering":
        raise ValueError("GatheringPublication aggregateType is invalid")
    try:
        version = int(values.get("aggregateVersion", ""))
    except ValueError as error:
        raise ValueError("GatheringPublication aggregateVersion is invalid") from error
    try:
        payload: Any = json.loads(values.get("payload", ""))
    except json.JSONDecodeError as error:
        raise ValueError("GatheringPublication payload is invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("GatheringPublication payload must be an object")
    event_id = values.get("eventId", "").strip()
    gathering_id = values.get("aggregateId", "").strip()
    payload_gathering = str(payload.get("gatheringId") or "").strip()
    organizer_id = str(payload.get("actorPersonaId") or "").strip()
    lifecycle = str(payload.get("lifecycleStatus") or "").strip()
    if (
        not event_id
        or not gathering_id
        or payload_gathering != gathering_id
        or not organizer_id
        or lifecycle != "published"
        or version <= 0
    ):
        raise ValueError("GatheringPublication identity or lifecycle is invalid")
    raw_refs = payload.get("sourceRefs") or []
    if not isinstance(raw_refs, list):
        raise ValueError("GatheringPublication sourceRefs must be a list")
    source_refs: list[tuple[str, str]] = []
    for raw in raw_refs:
        if not isinstance(raw, dict):
            raise ValueError("GatheringPublication sourceRef must be an object")
        object_kind = str(raw.get("objectKind") or "").strip()
        object_id = str(raw.get("objectId") or "").strip()
        if not object_kind or not object_id:
            raise ValueError("GatheringPublication sourceRef identity is incomplete")
        source_refs.append((object_kind, object_id))
    # 发布时冻结的公开政策维度事实；旧事件缺字段按空处理（切片归 unclassified）。
    try:
        max_participants = int(payload.get("maxParticipants") or 0)
    except (TypeError, ValueError):
        max_participants = 0
    admission_policy = str(payload.get("admissionPolicy") or "").strip()
    occurred_at = _time(values.get("occurredAt", ""))
    canonical = {
        "admissionPolicy": admission_policy,
        "aggregateVersion": version,
        "eventId": event_id,
        "eventType": event_type,
        "gatheringId": gathering_id,
        "maxParticipants": max_participants,
        "occurredAt": occurred_at.isoformat(),
        "organizerPersonaId": organizer_id,
        "sourceRefs": [
            {"objectKind": kind, "objectId": object_id}
            for kind, object_id in source_refs
        ],
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
    ).hexdigest()
    return GatheringPublicationEvent(
        event_id=event_id,
        gathering_id=gathering_id,
        organizer_id=organizer_id,
        source_refs=tuple(source_refs),
        max_participants=max_participants,
        admission_policy=admission_policy,
        version=version,
        occurred_at=occurred_at,
        event_digest=digest,
    )


class GatheringPublicationConsumer(DurableProjectionConsumer):
    """四锚点社会证明的发起级事实来源（circle.gathering outbox）。

    只投影「gatheringId → organizer + 溯源引用」的最小事实；成形/经历两级
    由 participation 与公开回顾证据在读时聚合，本 consumer 不做任何计数。
    """

    def __init__(self, *, redis_client, feature_store, projector, consumer: str) -> None:
        def apply(values: dict[str, str]) -> None:
            event = decode_gathering_publication(values)
            if event is not None:
                projector.project_gathering_publication(
                    event_id=event.event_id,
                    event_digest=event.event_digest,
                    gathering_id=event.gathering_id,
                    organizer_id=event.organizer_id,
                    source_refs=event.source_refs,
                    max_participants=event.max_participants,
                    admission_policy=event.admission_policy,
                    version=event.version,
                    occurred_at=event.occurred_at,
                )

        super().__init__(
            redis_client=redis_client,
            feature_store=feature_store,
            stream=GATHERING_PUBLICATION_STREAM,
            dead_letter_stream=GATHERING_PUBLICATION_DLQ,
            consumer_group=CONSUMER_GROUP,
            consumer=consumer,
            handler=apply,
            thread_name="recommendation-feature-gathering-publication",
        )
