"""搜推联动：消费 search.RecommendationSignalFact 短期意图流。

search-service 把搜索请求/点击的本地终态归并成 RecommendationSignalFact 并
发布到 `events.search.recommendation_signals`（signalId 幂等、retention 86400s，
契约声明「原始查询词不进入日志或 DLQ」）。本 consumer 把 query 信号归并进
FeatureProfile 的有界衰减 searchTermAffinities；click 信号仅推进幂等收据。

隐私约束的实现形态：DLQ 条目与错误信息只携带 signalId/attempts/固定文案，
绝不透传 normalizedQuery/relatedTerms 原文。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import threading
from typing import Any


SEARCH_SIGNAL_STREAM = "events.search.recommendation_signals"
SEARCH_SIGNAL_DLQ = "events.search.recommendation_signals.recommendation-feature.dlq"
CONSUMER_GROUP = "recommendation-feature-search-signal"
MAX_ATTEMPTS = 5
RETENTION_SECONDS = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class SearchRecommendationSignal:
    signal_id: str
    subject_id: str
    signal_type: str
    terms: tuple[str, ...]
    created_at: datetime


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _values(raw: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in raw.items()}


def _parse_time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("search signal createdAt must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _json_terms(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("search signal term list must be a JSON array")
    return tuple(
        dict.fromkeys(str(term).strip() for term in parsed if str(term).strip())
    )


def decode_search_signal(values: dict[str, str]) -> SearchRecommendationSignal:
    # 错误信息保持固定文案：本流的 payload 携带原始查询词，不得回显进异常。
    if values.get("eventType", "").strip() != "SearchRecommendationSignalPublished":
        raise ValueError("unsupported search recommendation signal source event")
    signal_id = values.get("signalId", "").strip()
    signal_type = values.get("signalType", "").strip()
    subject_id = values.get("userId", "").strip()
    if not signal_id or signal_type not in {"query", "click"}:
        raise ValueError("search recommendation signal identity is invalid")
    if not subject_id:
        # 无身份的公开搜索没有可归属主体：按合法空事件处理由调用方决定，
        # 这里显式拒绝以便 consumer 直接 ack 跳过（不是解码失败）。
        raise _AnonymousSignal()
    terms: tuple[str, ...] = ()
    if signal_type == "query":
        query = values.get("normalizedQuery", "").strip()
        related = _json_terms(values.get("relatedTerms", ""))
        terms = tuple(dict.fromkeys((query, *related))) if query else related
        if not terms:
            raise ValueError("search query signal carries no usable terms")
    return SearchRecommendationSignal(
        signal_id=signal_id,
        subject_id=subject_id,
        signal_type=signal_type,
        terms=terms,
        created_at=_parse_time(values.get("createdAt")),
    )


class _AnonymousSignal(Exception):
    """无 userId 的信号没有可归属的 FeatureProfile 主体，直接跳过。"""


class SearchSignalConsumer:
    def __init__(
        self,
        *,
        redis_client: Any,
        feature_store: Any,
        feature_projector: Any,
        subject_closures: Any,
        consumer: str,
    ) -> None:
        self._redis = redis_client
        self._store = feature_store
        self._projector = feature_projector
        self._subject_closures = subject_closures
        self._consumer = consumer.strip() or "recommendation-feature-search-signal"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                SEARCH_SIGNAL_STREAM,
                CONSUMER_GROUP,
                id="0-0",
                mkstream=True,
            )
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise

    @staticmethod
    def _messages(raw: Any) -> list[tuple[str, dict[str, str]]]:
        messages: list[tuple[str, dict[str, str]]] = []
        for _stream, entries in raw or []:
            for stream_id, fields in entries:
                messages.append((_text(stream_id), _values(fields)))
        return messages

    def _claimed(self) -> list[tuple[str, dict[str, str]]]:
        result = self._redis.xautoclaim(
            SEARCH_SIGNAL_STREAM,
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
                {SEARCH_SIGNAL_STREAM: ">"},
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
        # 隐私约束：DLQ 只携带 signalId 与固定错误类别，不落原始查询词。
        self._redis.xadd(
            SEARCH_SIGNAL_DLQ,
            {
                "sourceStream": SEARCH_SIGNAL_STREAM,
                "streamId": stream_id,
                "signalId": values.get("signalId", ""),
                "attempts": str(attempts),
                "error": type(error).__name__,
                "deadLetteredAt": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._trim_and_expire(SEARCH_SIGNAL_DLQ)

    def _process(self, stream_id: str, values: dict[str, str]) -> None:
        try:
            try:
                signal = decode_search_signal(values)
            except _AnonymousSignal:
                self._redis.xack(SEARCH_SIGNAL_STREAM, CONSUMER_GROUP, stream_id)
                self._store.clear_source_failure(stream_id)
                return
            if self._subject_closures.exists(signal.subject_id):
                raise ValueError("search signal subject is closed")
            self._projector.project_search_signal(
                signal_id=signal.signal_id,
                subject_id=signal.subject_id,
                signal_type=signal.signal_type,
                terms=signal.terms,
                created_at=signal.created_at,
            )
        except Exception as error:
            attempts = self._store.record_source_failure(
                stream_id,
                values.get("signalId", ""),
                # record_source_failure 落 Mongo 失败表：同样只给固定文案。
                ValueError(type(error).__name__),
            )
            if attempts < MAX_ATTEMPTS:
                raise
            self._dead_letter(
                stream_id=stream_id,
                values=values,
                attempts=attempts,
                error=error,
            )
            self._redis.xack(SEARCH_SIGNAL_STREAM, CONSUMER_GROUP, stream_id)
            self._store.clear_source_failure(stream_id)
            return
        self._redis.xack(SEARCH_SIGNAL_STREAM, CONSUMER_GROUP, stream_id)
        self._store.clear_source_failure(stream_id)

    def process_once(self) -> int:
        self.ensure_group()
        seen: set[str] = set()
        messages: list[tuple[str, dict[str, str]]] = []
        for stream_id, values in (*self._claimed(), *self._new()):
            if stream_id in seen:
                continue
            seen.add(stream_id)
            messages.append((stream_id, values))
        processed = 0
        first_error: Exception | None = None
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
            raise RuntimeError("search signal consumer is already started")
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-feature-search-signal",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
