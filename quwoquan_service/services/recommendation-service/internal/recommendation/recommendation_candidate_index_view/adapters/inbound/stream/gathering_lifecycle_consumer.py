from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import threading
import time
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ....application.gathering_projector import (
    GatheringCandidateProjection,
    GatheringCandidateSnapshot,
)


GATHERING_LIFECYCLE_STREAM = "events.circle.gatherings"
CONSUMER_GROUP = "recommendation-gathering-candidate-v1"
DEAD_LETTER_STREAM = "events.circle.gathering.recommendation_candidate.dlq"
GATHERING_STREAM_POLL_BLOCK_MS = 100
UPSERT_EVENTS = frozenset(
    {
        "GatheringPublished",
        "GatheringRevisionAppended",
        "GatheringParticipationChanged",
        "GatheringAdmissionControlChanged",
    }
)
REMOVAL_EVENTS = frozenset({"GatheringCancelled", "GatheringCompleted"})
SUPPORTED_EVENTS = UPSERT_EVENTS | REMOVAL_EVENTS


class GatheringPublicCardReader(Protocol):
    def read_public_card(self, gathering_id: str) -> Mapping[str, Any] | None: ...


class CircleGatheringPublicReader:
    """Reads Circle's public contract; never reaches Circle storage."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 3.0) -> None:
        normalized = base_url.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("circle service base URL must be http(s)")
        if timeout_seconds <= 0:
            raise ValueError("circle public card timeout must be positive")
        self._base_url = normalized
        self._timeout_seconds = timeout_seconds

    def read_public_card(self, gathering_id: str) -> Mapping[str, Any] | None:
        normalized = gathering_id.strip()
        if not normalized:
            raise ValueError("gatheringId is required")
        request = Request(
            f"{self._base_url}/public/gatherings/{quote(normalized, safe='')}",
            method="GET",
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code in {403, 404, 410}:
                return None
            raise RuntimeError(
                f"circle public Gathering read failed with HTTP {error.code}"
            ) from error
        if not isinstance(payload, Mapping):
            raise ValueError("circle public Gathering response must be an object")
        return payload


@dataclass(frozen=True)
class GatheringLifecycleEvent:
    event_id: str
    event_name: str
    gathering_id: str
    source_version: int
    occurred_at: datetime
    event_digest: str


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if value is None:
        return ""
    return str(value)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _optional_mapping(value: Any, field: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return _mapping(value, field)


def _parse_timestamp(value: Any, field: str) -> datetime:
    normalized = _text(value).strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"{field} must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _optional_timestamp(value: Any, field: str) -> datetime | None:
    if value is None or not _text(value).strip():
        return None
    return _parse_timestamp(value, field)


def _required_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an integer") from error


def _required_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _decode_payload(fields: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = fields.get("payload", fields.get(b"payload"))
    if raw is None:
        raw = fields.get("payloadJson", fields.get(b"payloadJson"))
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        return raw
    parsed = json.loads(_text(raw))
    if not isinstance(parsed, Mapping):
        raise ValueError("Gathering lifecycle payload must be an object")
    return parsed


def decode_gathering_lifecycle(
    fields: Mapping[str, Any],
) -> GatheringLifecycleEvent:
    normalized = {_text(key): value for key, value in fields.items()}
    payload = _decode_payload(normalized)
    event_name = _text(
        normalized.get("eventName", normalized.get("eventType"))
    ).strip()
    event_id = _text(normalized.get("eventId")).strip()
    gathering_id = _text(
        normalized.get(
            "aggregateId",
            normalized.get("gatheringId", payload.get("gatheringId")),
        )
    ).strip()
    aggregate_type = _text(normalized.get("aggregateType", "Gathering")).strip()
    try:
        source_version = int(
            normalized.get(
                "aggregateVersion",
                normalized.get("sourceVersion", payload.get("aggregateVersion")),
            )
        )
    except (TypeError, ValueError) as error:
        raise ValueError("Gathering aggregateVersion must be positive") from error
    occurred_at = _parse_timestamp(
        normalized.get("occurredAt", payload.get("occurredAt")),
        "occurredAt",
    )
    if (
        not event_id
        or event_name not in SUPPORTED_EVENTS
        or aggregate_type != "Gathering"
        or not gathering_id
        or source_version <= 0
    ):
        raise ValueError("Gathering lifecycle event envelope is incomplete")
    payload_id = _text(payload.get("gatheringId")).strip()
    if payload_id and payload_id != gathering_id:
        raise ValueError("Gathering lifecycle aggregate identity drift")
    payload_version = payload.get("aggregateVersion")
    if payload_version is not None and int(payload_version) != source_version:
        raise ValueError("Gathering lifecycle aggregate version drift")
    event_digest = hashlib.sha256(
        json.dumps(
            {
                "eventId": event_id,
                "eventName": event_name,
                "gatheringId": gathering_id,
                "sourceVersion": source_version,
                "occurredAt": occurred_at.isoformat(),
                "payload": payload,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return GatheringLifecycleEvent(
        event_id=event_id,
        event_name=event_name,
        gathering_id=gathering_id,
        source_version=source_version,
        occurred_at=occurred_at,
        event_digest=event_digest,
    )


def gathering_candidate_snapshot(
    *,
    event: GatheringLifecycleEvent,
    public_detail: Mapping[str, Any],
) -> GatheringCandidateSnapshot | None:
    audience = _text(public_detail.get("audiencePolicy")).strip()
    card = _mapping(public_detail.get("card"), "card")
    lifecycle_status = _text(card.get("lifecycleStatus")).strip()
    if audience != "public" or lifecycle_status != "published":
        return None

    gathering_id = _text(card.get("gatheringId")).strip()
    try:
        source_version = int(card.get("aggregateVersion"))
    except (TypeError, ValueError) as error:
        raise ValueError("Gathering PublicCard aggregateVersion is invalid") from error
    if gathering_id != event.gathering_id:
        raise ValueError("Gathering PublicCard identity drift")
    if source_version < event.source_version:
        raise RuntimeError("Gathering PublicCard has not reached event sourceVersion")

    host = _mapping(card.get("host"), "card.host")
    purpose = _mapping(card.get("purpose"), "card.purpose")
    schedule = _mapping(card.get("schedule"), "card.schedule")
    place = _mapping(card.get("place"), "card.place")
    capacity = _mapping(card.get("capacity"), "card.capacity")
    admission = _mapping(card.get("admission"), "card.admission")
    cover = _optional_mapping(purpose.get("coverRef"), "card.purpose.coverRef")
    coarse_place = _optional_mapping(
        place.get("coarsePlaceRef"),
        "card.place.coarsePlaceRef",
    )
    tag_refs = tuple(
        dict.fromkeys(
            value.strip()
            for value in (
                *(_text(item) for item in purpose.get("topicRefs") or ()),
                *(_text(item) for item in purpose.get("requirementRefs") or ()),
            )
            if value.strip()
        )
    )
    return GatheringCandidateSnapshot(
        gathering_id=gathering_id,
        source_version=source_version,
        card_digest=_text(card.get("cardDigest")).strip().lower(),
        host_subject_kind=_text(host.get("hostSubjectKind")).strip(),
        host_subject_id=_text(host.get("hostSubjectId")).strip(),
        title=_text(purpose.get("title")).strip(),
        summary=_text(purpose.get("summary")).strip() or None,
        cover_object_type_ref=(
            _text(cover.get("objectTypeRef")).strip() if cover else None
        ),
        cover_object_id=_text(cover.get("objectId")).strip() if cover else None,
        tag_refs=tag_refs,
        start_at=_optional_timestamp(schedule.get("startAt"), "card.schedule.startAt"),
        end_at=_optional_timestamp(schedule.get("endAt"), "card.schedule.endAt"),
        date_label=_text(schedule.get("dateLabel")).strip() or None,
        place_mode=_text(place.get("mode")).strip(),
        coarse_place_object_type_ref=(
            _text(coarse_place.get("objectTypeRef")).strip() if coarse_place else None
        ),
        coarse_place_object_id=(
            _text(coarse_place.get("objectId")).strip() if coarse_place else None
        ),
        coarse_place_label=_text(place.get("coarsePlaceLabel")).strip() or None,
        max_participants=_required_int(
            capacity.get("maxParticipants"),
            "card.capacity.maxParticipants",
        ),
        occupied_seats=_required_int(
            capacity.get("occupiedSeats"),
            "card.capacity.occupiedSeats",
        ),
        remaining_seats=_required_int(
            capacity.get("remainingSeats"),
            "card.capacity.remainingSeats",
        ),
        full=_required_bool(capacity.get("full"), "card.capacity.full"),
        admission_state=_text(admission.get("admissionState")).strip(),
        lifecycle_status=lifecycle_status,
        updated_at=_parse_timestamp(card.get("updatedAt"), "card.updatedAt"),
    )


class GatheringLifecycleConsumer:
    def __init__(
        self,
        *,
        redis_client: Any,
        projection: GatheringCandidateProjection,
        public_cards: GatheringPublicCardReader,
        consumer: str,
        max_attempts: int = 5,
    ) -> None:
        if not consumer.strip() or max_attempts <= 0:
            raise ValueError("Gathering lifecycle consumer configuration is invalid")
        self._redis = redis_client
        self._projection = projection
        self._public_cards = public_cards
        self._consumer = consumer.strip()
        self._max_attempts = max_attempts
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._healthy = False
        self._ensure_group()

    def healthy(self) -> bool:
        return self._healthy

    def _ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                GATHERING_LIFECYCLE_STREAM,
                CONSUMER_GROUP,
                id="0-0",
                mkstream=True,
            )
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise

    def process_once(self, *, block_ms: int = 0) -> int:
        records = self._redis.xreadgroup(
            CONSUMER_GROUP,
            self._consumer,
            {GATHERING_LIFECYCLE_STREAM: ">"},
            count=20,
            block=block_ms,
        )
        processed = 0
        for _stream, messages in records:
            for stream_id, fields in messages:
                source_stream_id = _text(stream_id)
                failure_key = f"{GATHERING_LIFECYCLE_STREAM}\x1f{source_stream_id}"
                event_id = ""
                try:
                    event = decode_gathering_lifecycle(fields)
                    event_id = event.event_id
                    if event.event_name in REMOVAL_EVENTS:
                        self._projection.apply_gathering_source_event(
                            event_id=event.event_id,
                            event_digest=event.event_digest,
                            snapshot=None,
                            removal=(event.gathering_id, event.source_version),
                        )
                    else:
                        public_detail = self._public_cards.read_public_card(
                            event.gathering_id
                        )
                        snapshot = (
                            gathering_candidate_snapshot(
                                event=event,
                                public_detail=public_detail,
                            )
                            if public_detail is not None
                            else None
                        )
                        self._projection.apply_gathering_source_event(
                            event_id=event.event_id,
                            event_digest=event.event_digest,
                            snapshot=snapshot,
                            removal=(
                                (event.gathering_id, event.source_version)
                                if snapshot is None
                                else None
                            ),
                        )
                    self._projection.clear_source_failure(failure_key)
                    self._redis.xack(
                        GATHERING_LIFECYCLE_STREAM,
                        CONSUMER_GROUP,
                        stream_id,
                    )
                    processed += 1
                except Exception as error:
                    attempts = self._projection.record_source_failure(
                        failure_key,
                        event_id,
                        error,
                    )
                    if attempts >= self._max_attempts:
                        self._redis.xadd(
                            DEAD_LETTER_STREAM,
                            {
                                "sourceStreamId": source_stream_id,
                                "eventId": event_id,
                                "errorType": type(error).__name__,
                            },
                        )
                        self._redis.xack(
                            GATHERING_LIFECYCLE_STREAM,
                            CONSUMER_GROUP,
                            stream_id,
                        )
        self._healthy = True
        return processed

    def start(self) -> None:
        if self._thread is not None:
            return

        def run() -> None:
            while not self._stop.is_set():
                try:
                    self.process_once(block_ms=GATHERING_STREAM_POLL_BLOCK_MS)
                except Exception:
                    self._healthy = False
                    time.sleep(0.25)

        self._thread = threading.Thread(
            target=run,
            name="recommendation-gathering-candidate",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(3.0)
            self._thread = None
