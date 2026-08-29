from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import threading
from typing import Any

from prometheus_client import Counter

from internal.recommendation.recommendation_exposure_fact.application.appender import (
    Appender,
    ExposureFact,
)

# 契约 runtime_entrypoints[].telemetry.metric 同名计数器（outcome=ok|error）。
_INGEST_OUTCOMES = Counter(
    "recommendation_exposure_ingest",
    "Contract runtime entrypoint outcome counter (FeedPageDelivered ingest).",
    ["outcome"],
)


FEED_PAGE_DELIVERED_STREAM = "events.content.feed_page_delivered"
FEED_PAGE_DELIVERED_DLQ = (
    "events.content.feed_page_delivered.recommendation-exposure.dlq"
)
CONSUMER_GROUP = "recommendation-exposure-fact"
MAX_ATTEMPTS = 5
RETENTION_SECONDS = 7 * 24 * 60 * 60
MAX_DELIVERED_ITEMS = 20


@dataclass(frozen=True, slots=True)
class FeedPageDeliveredEvent:
    event_id: str
    delivery_page_id: str
    feed_request_id: str
    subject_id: str
    persona_id: str | None
    scenario: str
    window_id: str
    experiment_bucket: str
    model_bucket: str
    model_channel: str | None
    model_release_id: str | None
    ranking_snapshot_digest: str
    feature_snapshot_at: datetime
    user_feature_snapshot: dict[str, Any]
    items: tuple[dict[str, Any], ...]
    occurred_at: datetime


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _values(raw: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in raw.items()}


def _parse_time(value: Any, name: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"FeedPageDelivered {name} is required")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"FeedPageDelivered {name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_feed_page_delivered(values: dict[str, str]) -> FeedPageDeliveredEvent:
    if values.get("eventName", "").strip() != "FeedPageDelivered":
        raise ValueError("unsupported recommendation exposure source event")
    payload = json.loads(values.get("payload", ""))
    if not isinstance(payload, dict):
        raise ValueError("FeedPageDelivered payload must be an object")
    delivery_page_id = str(payload.get("deliveryPageId") or "").strip()
    event_id = values.get("eventId", "").strip()
    expected_event_id = hashlib.sha256(
        f"FeedPageDelivered:{delivery_page_id}".encode("utf-8")
    ).hexdigest()
    if (
        not delivery_page_id
        or values.get("deliveryPageId", "").strip() != delivery_page_id
        or event_id != expected_event_id
    ):
        raise ValueError("FeedPageDelivered identity is invalid")
    items = payload.get("items")
    if not isinstance(items, list) or not items or len(items) > MAX_DELIVERED_ITEMS:
        raise ValueError("FeedPageDelivered items must contain 1..20 entries")
    if any(not isinstance(item, dict) for item in items):
        raise ValueError("FeedPageDelivered item must be an object")
    ordinals = [item.get("ordinal") for item in items]
    content_ids = [str(item.get("contentId") or "").strip() for item in items]
    if (
        any(not isinstance(value, int) or value < 0 for value in ordinals)
        or len(set(ordinals)) != len(ordinals)
        or any(not value for value in content_ids)
        or len(set(content_ids)) != len(content_ids)
    ):
        raise ValueError("FeedPageDelivered item identity is invalid")
    experiment_bucket = str(payload.get("experimentBucket") or "").strip()
    model_bucket = str(payload.get("modelBucket") or "").strip()
    model_channel = str(payload.get("modelChannel") or "").strip() or None
    model_release_id = str(payload.get("modelReleaseId") or "").strip() or None
    if experiment_bucket not in {"model", "rule"}:
        raise ValueError("FeedPageDelivered experimentBucket is invalid")
    if model_bucket not in {"model", "rule"}:
        raise ValueError("FeedPageDelivered modelBucket is invalid")
    if model_bucket == "model" and (not model_channel or not model_release_id):
        raise ValueError("FeedPageDelivered model attribution is incomplete")
    if model_bucket == "rule" and (model_channel is not None or model_release_id is not None):
        raise ValueError("FeedPageDelivered rule attribution cannot claim a model release")
    occurred_at = _parse_time(payload.get("occurredAt"), "occurredAt")
    if occurred_at != _parse_time(values.get("occurredAt"), "occurredAt"):
        raise ValueError("FeedPageDelivered occurredAt mismatch")
    feature_snapshot_at = _parse_time(
        payload.get("featureSnapshotAt"),
        "featureSnapshotAt",
    )
    if feature_snapshot_at > occurred_at:
        raise ValueError("FeedPageDelivered feature snapshot is later than delivery")
    user_snapshot = payload.get("userFeatureSnapshot")
    if not isinstance(user_snapshot, dict):
        raise ValueError("FeedPageDelivered userFeatureSnapshot must be an object")
    required = {
        "feedRequestId": str(payload.get("feedRequestId") or "").strip(),
        "subjectId": str(payload.get("subjectId") or "").strip(),
        "scenario": str(payload.get("scenario") or "").strip(),
        "windowId": str(payload.get("windowId") or "").strip(),
        "rankingSnapshotDigest": str(payload.get("rankingSnapshotDigest") or "").strip(),
    }
    if not all(required.values()):
        raise ValueError("FeedPageDelivered attribution is incomplete")
    return FeedPageDeliveredEvent(
        event_id=event_id,
        delivery_page_id=delivery_page_id,
        feed_request_id=required["feedRequestId"],
        subject_id=required["subjectId"],
        persona_id=str(payload.get("personaId") or "").strip() or None,
        scenario=required["scenario"],
        window_id=required["windowId"],
        experiment_bucket=experiment_bucket,
        model_bucket=model_bucket,
        model_channel=model_channel,
        model_release_id=model_release_id,
        ranking_snapshot_digest=required["rankingSnapshotDigest"],
        feature_snapshot_at=feature_snapshot_at,
        user_feature_snapshot=user_snapshot,
        items=tuple(items),
        occurred_at=occurred_at,
    )


class FeedPageDeliveredConsumer:
    def __init__(
        self,
        *,
        redis_client: Any,
        exposure_store: Any,
        subject_closures: Any,
        feature_projector: Any,
        consumer: str,
    ) -> None:
        self._redis = redis_client
        self._store = exposure_store
        self._appender = Appender(exposure_store, subject_closures)
        self._feature_projector = feature_projector
        self._consumer = consumer.strip() or "recommendation-exposure-fact"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                FEED_PAGE_DELIVERED_STREAM,
                CONSUMER_GROUP,
                id="0-0",
                mkstream=True,
            )
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise

    @staticmethod
    def _messages(raw: Any) -> list[tuple[str, dict[str, str]]]:
        result: list[tuple[str, dict[str, str]]] = []
        for _stream, entries in raw or []:
            for stream_id, fields in entries:
                result.append((_text(stream_id), _values(fields)))
        return result

    def _claimed(self) -> list[tuple[str, dict[str, str]]]:
        result = self._redis.xautoclaim(
            FEED_PAGE_DELIVERED_STREAM,
            CONSUMER_GROUP,
            self._consumer,
            min_idle_time=30_000,
            start_id="0-0",
            count=50,
        )
        entries = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else []
        return [(_text(stream_id), _values(fields)) for stream_id, fields in entries]

    def _new(self) -> list[tuple[str, dict[str, str]]]:
        return self._messages(
            self._redis.xreadgroup(
                CONSUMER_GROUP,
                self._consumer,
                {FEED_PAGE_DELIVERED_STREAM: ">"},
                count=50,
            )
        )

    def _trim_and_expire(self, stream: str) -> None:
        server_time = self._redis.time()
        cutoff_ms = (int(server_time[0]) - RETENTION_SECONDS) * 1000
        self._redis.xtrim(stream, minid=f"{max(cutoff_ms, 0)}-0", approximate=False)
        self._redis.expire(stream, RETENTION_SECONDS)

    def _dead_letter(
        self,
        *,
        stream_id: str,
        values: dict[str, str],
        attempts: int,
        error: Exception,
    ) -> None:
        self._redis.xadd(
            FEED_PAGE_DELIVERED_DLQ,
            {
                "sourceStream": FEED_PAGE_DELIVERED_STREAM,
                "streamId": stream_id,
                "eventId": values.get("eventId", ""),
                "attempts": str(attempts),
                "error": str(error)[:1024],
                "deadLetteredAt": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._trim_and_expire(FEED_PAGE_DELIVERED_DLQ)

    def _process(self, stream_id: str, values: dict[str, str]) -> None:
        try:
            event = decode_feed_page_delivered(values)
            for item in event.items:
                content_id = str(item.get("contentId") or "").strip()
                item_snapshot = item.get("itemFeatureSnapshot")
                if not isinstance(item_snapshot, dict):
                    raise ValueError("FeedPageDelivered itemFeatureSnapshot must be an object")
                ordinal = int(item["ordinal"])
                exposure_id = hashlib.sha256(
                    (
                        "RecommendationExposureFact:"
                        f"{event.delivery_page_id}:{ordinal}:{content_id}"
                    ).encode("utf-8")
                ).hexdigest()
                exposure, _created = self._appender.append(
                    ExposureFact(
                        exposure_id=exposure_id,
                        source_event_id=event.event_id,
                        delivery_page_id=event.delivery_page_id,
                        feed_request_id=event.feed_request_id,
                        window_id=event.window_id,
                        subject_id=event.subject_id,
                        persona_id=event.persona_id,
                        scenario=event.scenario,
                        target_type=str(item.get("contentType") or "").strip(),
                        target_id=content_id,
                        ordinal=ordinal,
                        experiment_bucket=event.experiment_bucket,
                        model_bucket=event.model_bucket,
                        model_channel=event.model_channel,
                        model_release_id=event.model_release_id,
                        feature_snapshot_at=event.feature_snapshot_at,
                        feature_snapshot_digest=str(
                            item.get("featureSnapshotDigest") or ""
                        ).strip(),
                        ranking_snapshot_digest=event.ranking_snapshot_digest,
                        user_feature_snapshot=event.user_feature_snapshot,
                        item_feature_snapshot=item_snapshot,
                        exposed_at=event.occurred_at,
                        recorded_at=datetime.now(timezone.utc),
                    )
                )
                self._feature_projector.project_exposure(
                    exposure_fact_id=exposure.exposure_id,
                    subject_id=exposure.subject_id,
                    target_id=exposure.target_id,
                    occurred_at=exposure.exposed_at,
                )
        except Exception as error:
            attempts = self._store.record_failure(
                stream_id,
                values.get("eventId", ""),
                error,
            )
            if attempts < MAX_ATTEMPTS:
                raise
            self._dead_letter(
                stream_id=stream_id,
                values=values,
                attempts=attempts,
                error=error,
            )
            self._redis.xack(FEED_PAGE_DELIVERED_STREAM, CONSUMER_GROUP, stream_id)
            self._store.clear_failure(stream_id)
            return
        self._redis.xack(FEED_PAGE_DELIVERED_STREAM, CONSUMER_GROUP, stream_id)
        self._store.clear_failure(stream_id)

    def process_once(self) -> int:
        try:
            processed = self._process_once_inner()
        except Exception:
            _INGEST_OUTCOMES.labels(outcome="error").inc()
            raise
        _INGEST_OUTCOMES.labels(outcome="ok").inc()
        return processed

    def _process_once_inner(self) -> int:
        self.ensure_group()
        seen: set[str] = set()
        messages: list[tuple[str, dict[str, str]]] = []
        for stream_id, values in (*self._claimed(), *self._new()):
            if stream_id not in seen:
                seen.add(stream_id)
                messages.append((stream_id, values))
        first_error: Exception | None = None
        processed = 0
        for stream_id, values in messages:
            try:
                self._process(stream_id, values)
                processed += 1
            except Exception as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            self._last_failure = first_error
            raise first_error
        self._last_success = datetime.now(timezone.utc)
        self._last_failure = None
        return processed

    def healthy(self, *, max_staleness_seconds: float = 10.0) -> bool:
        if self._last_success is None or self._last_failure is not None:
            return False
        return (
            datetime.now(timezone.utc) - self._last_success
        ).total_seconds() <= max_staleness_seconds

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.process_once()
            except Exception:
                pass
            self._stop.wait(0.25)

    def start(self) -> None:
        self.ensure_group()
        if self._thread is not None:
            raise RuntimeError("FeedPageDelivered consumer is already started")
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-exposure-feed-page-delivered",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
