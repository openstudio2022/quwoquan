from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Callable, Protocol

from ..domain.model import (
    RankedCandidate,
    RankedRecommendationItem,
    RecommendationObjectCard,
    RankedRecommendationWindow,
    RankingResult,
    WINDOW_TTL,
)


class RedisClient(Protocol):
    def get(self, key: str) -> str | bytes | None: ...

    def zrange(self, key: str, start: int, end: int) -> list[str] | list[bytes]: ...

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str | bytes | int,
    ) -> Any: ...


class WindowStoreError(RuntimeError):
    """Base failure for the canonical bounded Redis window store."""


class WindowIdentityConflictError(WindowStoreError):
    """The immutable winner for one identity differs from the contender."""


class WindowShardRecordQuotaError(WindowStoreError):
    """The fixed per-shard live-record ceiling rejected the contender."""


class WindowShardByteQuotaError(WindowStoreError):
    """The fixed per-shard live-byte ceiling rejected the contender."""


class WindowRepairBoundError(WindowStoreError):
    """The bounded index/metadata state cannot be repaired inside its cap."""


class WindowConcurrentIndexError(WindowStoreError):
    """The quota index changed on every bounded atomic retry."""


_ATOMIC_CREATE_SCRIPT = r"""
local ttl_ms = tonumber(ARGV[2])
local owner_digest = ARGV[3]
local max_owner = tonumber(ARGV[4])
local max_shard_records = tonumber(ARGV[5])
local max_shard_bytes = tonumber(ARGV[6])
local payload_bytes = tonumber(ARGV[7])
if not ttl_ms or ttl_ms <= 0 or not max_owner or max_owner <= 0
  or not max_shard_records or max_shard_records <= 0
  or not max_shard_bytes or max_shard_bytes <= 0
  or not payload_bytes or payload_bytes <= 0
  or max_owner > max_shard_records then
  return redis.error_reply('bounded immutable record policy is invalid')
end

local server_time = redis.call('TIME')
local now_us = tonumber(server_time[1]) * 1000000 + tonumber(server_time[2])
local expires_at_us = now_us + ttl_ms * 1000

local declared = {[KEYS[1]] = true}
for position = 4, #KEYS do
  declared[KEYS[position]] = true
end

local indexed = redis.call('ZRANGE', KEYS[2], 0, max_shard_records)
if #indexed > max_shard_records then
  return {'', -4, 0, #indexed, 0}
end
for position = 1, #indexed do
  if not declared[indexed[position]] then
    return {'', -1, 0, #indexed, 0}
  end
end

for position = 1, #indexed do
  local candidate = indexed[position]
  local expiry = redis.call('ZSCORE', KEYS[2], candidate)
  local exists = redis.call('EXISTS', candidate)
  if not expiry or tonumber(expiry) <= now_us or exists == 0 then
    redis.call('ZREM', KEYS[2], candidate)
    redis.call('HDEL', KEYS[3], candidate)
    if expiry and tonumber(expiry) <= now_us then
      redis.call('DEL', candidate)
    end
  end
end

indexed = redis.call('ZRANGE', KEYS[2], 0, max_shard_records)
local live_records = 0
local live_bytes = 0
local owner_records = {}
for position = 1, #indexed do
  local candidate = indexed[position]
  local metadata = redis.call('HGET', KEYS[3], candidate)
  if not metadata then
    return {'', -4, 0, #indexed, live_bytes}
  end
  local candidate_owner, candidate_bytes_text =
    string.match(metadata, '^([0-9a-f]+):([0-9]+)$')
  local candidate_bytes = tonumber(candidate_bytes_text)
  if not candidate_owner or not candidate_bytes or candidate_bytes <= 0 then
    return {'', -4, 0, #indexed, live_bytes}
  end
  live_records = live_records + 1
  live_bytes = live_bytes + candidate_bytes
  if candidate_owner == owner_digest then
    owner_records[#owner_records + 1] = {
      key = candidate,
      bytes = candidate_bytes,
    }
  end
end

local existing = redis.call('GET', KEYS[1])
if existing then
  local metadata = redis.call('HGET', KEYS[3], KEYS[1])
  local indexed_expiry = redis.call('ZSCORE', KEYS[2], KEYS[1])
  if not metadata or not indexed_expiry then
    return {'', -4, 0, live_records, live_bytes}
  end
  local existing_owner, existing_bytes_text =
    string.match(metadata, '^([0-9a-f]+):([0-9]+)$')
  local existing_bytes = tonumber(existing_bytes_text)
  if existing_owner ~= owner_digest or existing_bytes ~= string.len(existing) then
    return {'', -4, 0, live_records, live_bytes}
  end
  return {existing, 0, 0, live_records, live_bytes}
end

local owner_eviction_count = #owner_records - max_owner + 1
if owner_eviction_count < 0 then
  owner_eviction_count = 0
end
local owner_eviction_bytes = 0
for position = 1, owner_eviction_count do
  owner_eviction_bytes = owner_eviction_bytes + owner_records[position].bytes
end

local projected_records = live_records - owner_eviction_count + 1
local projected_bytes = live_bytes - owner_eviction_bytes + payload_bytes
if projected_records > max_shard_records then
  return {'', -2, 0, live_records, live_bytes}
end
if projected_bytes > max_shard_bytes then
  return {'', -3, 0, live_records, live_bytes}
end

for position = 1, owner_eviction_count do
  local victim = owner_records[position].key
  redis.call('DEL', victim)
  redis.call('ZREM', KEYS[2], victim)
  redis.call('HDEL', KEYS[3], victim)
end

local persisted = redis.call('SET', KEYS[1], ARGV[1], 'NX', 'PX', ttl_ms)
if not persisted then
  return redis.error_reply('bounded immutable record atomic SET NX did not persist')
end
redis.call('ZADD', KEYS[2], expires_at_us, KEYS[1])
redis.call('HSET', KEYS[3], KEYS[1], owner_digest .. ':' .. payload_bytes)
local index_ttl_ms = redis.call('PTTL', KEYS[2])
if index_ttl_ms < ttl_ms then
  redis.call('PEXPIRE', KEYS[2], ttl_ms)
end
local metadata_ttl_ms = redis.call('PTTL', KEYS[3])
if metadata_ttl_ms < ttl_ms then
  redis.call('PEXPIRE', KEYS[3], ttl_ms)
end
return {'', 1, owner_eviction_count, projected_records, projected_bytes}
"""


_ERASE_SUBJECT_SCRIPT = r"""
local max_shard_records = tonumber(ARGV[1])
local owner_digest = ARGV[2]
if not max_shard_records or max_shard_records <= 0
  or not string.match(owner_digest, '^[0-9a-f]+$') then
  return redis.error_reply('bounded subject erase policy is invalid')
end

local declared = {}
for position = 3, #KEYS do
  declared[KEYS[position]] = true
end
local indexed = redis.call('ZRANGE', KEYS[1], 0, max_shard_records)
if #indexed > max_shard_records then
  return {-4, 0}
end
for position = 1, #indexed do
  if not declared[indexed[position]] then
    return {-1, 0}
  end
end

local server_time = redis.call('TIME')
local now_us = tonumber(server_time[1]) * 1000000 + tonumber(server_time[2])
local deleted = 0
for position = 1, #indexed do
  local candidate = indexed[position]
  local expiry = redis.call('ZSCORE', KEYS[1], candidate)
  local exists = redis.call('EXISTS', candidate)
  if not expiry or tonumber(expiry) <= now_us or exists == 0 then
    redis.call('ZREM', KEYS[1], candidate)
    redis.call('HDEL', KEYS[2], candidate)
    if expiry and tonumber(expiry) <= now_us then
      redis.call('DEL', candidate)
    end
  else
    local metadata = redis.call('HGET', KEYS[2], candidate)
    if not metadata then
      return {-4, deleted}
    end
    local candidate_owner, candidate_bytes_text =
      string.match(metadata, '^([0-9a-f]+):([0-9]+)$')
    local candidate_bytes = tonumber(candidate_bytes_text)
    if not candidate_owner or not candidate_bytes or candidate_bytes <= 0 then
      return {-4, deleted}
    end
    if candidate_owner == owner_digest then
      deleted = deleted + redis.call('DEL', candidate)
      redis.call('ZREM', KEYS[1], candidate)
      redis.call('HDEL', KEYS[2], candidate)
    end
  end
end
return {0, deleted}
"""


class _BoundedJSONWriter:
    def __init__(self, maximum_bytes: int) -> None:
        self._maximum_bytes = maximum_bytes
        self._encoded = bytearray()
        self._encoder = json.JSONEncoder(
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def raw(self, value: bytes) -> None:
        self._append(value)

    def value(self, value: Any) -> None:
        for chunk in self._encoder.iterencode(value):
            self._append(chunk.encode("utf-8"))

    def _append(self, value: bytes) -> None:
        if len(self._encoded) + len(value) > self._maximum_bytes:
            raise ValueError("ranked recommendation window exceeds 2 MiB")
        self._encoded.extend(value)

    def finish(self) -> bytes:
        return bytes(self._encoded)


class RedisWindowStore:
    TTL_SECONDS = int(WINDOW_TTL.total_seconds())
    MAX_WINDOW_PAYLOAD_BYTES = 2 * 1024 * 1024
    MAX_ACTIVE_WINDOWS_PER_SUBJECT = 8
    DEFAULT_QUOTA_SHARD_COUNT = 256
    DEFAULT_MAXIMUM_LIVE_RECORDS_PER_SHARD = 128
    DEFAULT_MAXIMUM_LIVE_BYTES_PER_SHARD = 128 * 1024 * 1024
    MAXIMUM_SHARD_COUNT = 4096
    MAX_ATOMIC_ATTEMPTS = 16

    def __init__(
        self,
        client: RedisClient,
        *,
        quota_shard_count: int = DEFAULT_QUOTA_SHARD_COUNT,
        maximum_live_records_per_shard: int = DEFAULT_MAXIMUM_LIVE_RECORDS_PER_SHARD,
        maximum_live_bytes_per_shard: int = DEFAULT_MAXIMUM_LIVE_BYTES_PER_SHARD,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if client is None:
            raise ValueError("Redis client is required")
        if (
            quota_shard_count <= 0
            or quota_shard_count > self.MAXIMUM_SHARD_COUNT
            or quota_shard_count & (quota_shard_count - 1) != 0
        ):
            raise ValueError("quota shard count must be a power of two in [1, 4096]")
        if (
            maximum_live_records_per_shard <= 0
            or maximum_live_bytes_per_shard <= 0
            or self.MAX_ACTIVE_WINDOWS_PER_SUBJECT
            > maximum_live_records_per_shard
        ):
            raise ValueError("ranked window live record/byte quota is invalid")
        self._client = client
        self._quota_shard_count = quota_shard_count
        self._maximum_live_records_per_shard = maximum_live_records_per_shard
        self._maximum_live_bytes_per_shard = maximum_live_bytes_per_shard
        self._now = now or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _subject_hash(subject_id: str) -> str:
        normalized = subject_id.strip()
        if not normalized:
            raise ValueError("subjectId is required")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]

    def _shard(self, subject_hash: str) -> str:
        shard = int(subject_hash[:16], 16) & (self._quota_shard_count - 1)
        return f"{shard:04x}"

    def _keys(self, subject_hash: str, window_id: str) -> tuple[str, str, str]:
        normalized_window = window_id.strip()
        if not normalized_window:
            raise ValueError("windowId is required")
        tag = f"{{rfw-{self._shard(subject_hash)}}}"
        return (
            f"rec:ranked_feed_window:{tag}:{subject_hash}:{normalized_window}",
            f"rec:ranked_feed_window_index:{tag}",
            f"rec:ranked_feed_window_metadata:{tag}",
        )

    @staticmethod
    def _text(value: str | bytes) -> str:
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    def _indexed_keys(self, index_key: str, value_prefix: str) -> list[str]:
        raw = self._client.zrange(
            index_key,
            0,
            self._maximum_live_records_per_shard,
        )
        indexed = [self._text(value) for value in raw]
        if len(indexed) > self._maximum_live_records_per_shard:
            raise WindowRepairBoundError(
                "ranked window quota index exceeds its bounded repair cap"
            )
        if any(not key.startswith(value_prefix) for key in indexed):
            raise WindowRepairBoundError(
                "ranked window quota index contains a key outside its shard"
            )
        return indexed

    @staticmethod
    def _script_int(value: Any, field: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise WindowStoreError(
                f"ranked window atomic result {field} is invalid"
            ) from error

    def create_or_get(
        self,
        window: RankedRecommendationWindow,
    ) -> RankedRecommendationWindow:
        payload = self._encode_window(window)
        subject_hash = self._subject_hash(window.subject_id)
        record_key, index_key, metadata_key = self._keys(
            subject_hash,
            window.window_id,
        )
        value_prefix = (
            f"rec:ranked_feed_window:{{rfw-{self._shard(subject_hash)}}}:"
        )
        for _attempt in range(self.MAX_ATOMIC_ATTEMPTS):
            indexed = self._indexed_keys(index_key, value_prefix)
            keys = [record_key, index_key, metadata_key]
            keys.extend(key for key in indexed if key != record_key)
            result = self._client.eval(
                _ATOMIC_CREATE_SCRIPT,
                len(keys),
                *keys,
                payload,
                self.TTL_SECONDS * 1000,
                subject_hash,
                self.MAX_ACTIVE_WINDOWS_PER_SUBJECT,
                self._maximum_live_records_per_shard,
                self._maximum_live_bytes_per_shard,
                len(payload),
            )
            if not isinstance(result, Sequence) or len(result) != 5:
                raise WindowStoreError("ranked window atomic result is invalid")
            status = self._script_int(result[1], "status")
            if status == -1:
                continue
            if status == -2:
                raise WindowShardRecordQuotaError(
                    "ranked window shard live-record quota exceeded"
                )
            if status == -3:
                raise WindowShardByteQuotaError(
                    "ranked window shard live-byte quota exceeded"
                )
            if status == -4:
                raise WindowRepairBoundError(
                    "ranked window quota metadata requires unbounded repair"
                )
            if status == 1:
                return window
            if status != 0:
                raise WindowStoreError(
                    f"ranked window atomic result status={status} is unsupported"
                )
            winner_raw = result[0]
            if not isinstance(winner_raw, (str, bytes)) or not winner_raw:
                raise WindowStoreError("ranked window atomic winner is missing")
            winner = self._decode_window(
                winner_raw,
                expected_subject_id=window.subject_id,
                expected_window_id=window.window_id,
            )
            if winner is None:
                raise WindowStoreError("ranked window atomic winner is expired")
            comparable = replace(
                window,
                created_at=winner.created_at,
                expires_at=winner.expires_at,
            )
            if winner != comparable:
                raise WindowIdentityConflictError(
                    "ranked window identity winner differs from contender"
                )
            return winner
        raise WindowConcurrentIndexError(
            "ranked window quota index changed during every atomic retry"
        )

    def get(
        self,
        subject_id: str,
        window_id: str,
    ) -> RankedRecommendationWindow | None:
        subject_hash = self._subject_hash(subject_id)
        record_key, _, _ = self._keys(subject_hash, window_id)
        raw = self._client.get(record_key)
        if raw is None:
            return None
        return self._decode_window(
            raw,
            expected_subject_id=subject_id,
            expected_window_id=window_id,
        )

    def erase_subject(self, subject_id: str) -> int:
        normalized = subject_id.strip()
        subject_hash = self._subject_hash(normalized)
        record_key, index_key, metadata_key = self._keys(
            subject_hash,
            "subject-erase-probe",
        )
        value_prefix = (
            f"rec:ranked_feed_window:{{rfw-{self._shard(subject_hash)}}}:"
        )
        for _attempt in range(self.MAX_ATOMIC_ATTEMPTS):
            indexed = self._indexed_keys(index_key, value_prefix)
            keys = [index_key, metadata_key, *indexed]
            result = self._client.eval(
                _ERASE_SUBJECT_SCRIPT,
                len(keys),
                *keys,
                self._maximum_live_records_per_shard,
                subject_hash,
            )
            if not isinstance(result, Sequence) or len(result) != 2:
                raise WindowStoreError("ranked window subject erase result is invalid")
            status = self._script_int(result[0], "erase status")
            if status == -1:
                continue
            if status == -4:
                raise WindowRepairBoundError(
                    "ranked window subject erase requires unbounded repair"
                )
            if status != 0:
                raise WindowStoreError(
                    f"ranked window subject erase status={status} is unsupported"
                )
            return self._script_int(result[1], "deleted count")
        raise WindowConcurrentIndexError(
            "ranked window quota index changed during every subject erase retry"
        )

    def _encode_window(self, window: RankedRecommendationWindow) -> bytes:
        self._preflight_text_bytes(window)
        writer = _BoundedJSONWriter(self.MAX_WINDOW_PAYLOAD_BYTES)
        writer.raw(b"{")
        fields: tuple[tuple[str, Any], ...] = (
            ("windowId", window.window_id),
            ("subjectId", window.subject_id),
            ("scenario", window.scenario),
            ("experimentBucket", window.experiment_bucket),
            ("modelBucket", window.model_bucket),
            ("modelChannel", window.model_channel),
            ("modelReleaseId", window.model_release_id),
            ("policyDigest", window.policy_digest),
            ("requestDigest", window.request_digest),
            ("rankingSnapshotDigest", window.ranking_snapshot_digest),
            ("featureSnapshotAt", window.feature_snapshot_at.isoformat()),
            ("userFeatureSnapshot", window.user_feature_snapshot),
            ("createdAt", window.created_at.isoformat()),
            ("expiresAt", window.expires_at.isoformat()),
        )
        first = True
        for key, value in fields:
            if not first:
                writer.raw(b",")
            first = False
            writer.value(key)
            writer.raw(b":")
            writer.value(value)
        writer.raw(b',"items":[')
        for index, item in enumerate(window.items):
            if index:
                writer.raw(b",")
            writer.value(
                {
                    "ordinal": item.ordinal,
                    "contentId": item.content_id,
                    "score": item.score,
                    "featureSnapshotDigest": item.feature_snapshot_digest,
                    "itemFeatureSnapshot": item.item_feature_snapshot,
                }
            )
        writer.raw(b'],"objectCards":[')
        for index, card in enumerate(window.object_cards):
            if index:
                writer.raw(b",")
            writer.value(
                {
                    "objectKind": card.object_kind,
                    "objectId": card.object_id,
                    "title": card.title,
                    "subtitle": card.subtitle,
                    "coverUrl": card.cover_url,
                    "tagRefs": card.tag_refs,
                    "reasonKey": card.reason_key,
                    "recallPath": card.recall_path,
                }
            )
        writer.raw(b"]}")
        return writer.finish()

    def _preflight_text_bytes(self, window: RankedRecommendationWindow) -> None:
        remaining = self.MAX_WINDOW_PAYLOAD_BYTES
        active: set[int] = set()

        def visit(value: Any) -> None:
            nonlocal remaining
            if isinstance(value, str):
                remaining -= len(value.encode("utf-8"))
                if remaining < 0:
                    raise ValueError("ranked recommendation window exceeds 2 MiB")
                return
            if isinstance(value, Mapping):
                identity = id(value)
                if identity in active:
                    raise ValueError("ranked recommendation window contains cyclic JSON")
                active.add(identity)
                try:
                    for key, child in value.items():
                        if not isinstance(key, str):
                            raise ValueError("ranked recommendation JSON keys must be strings")
                        visit(key)
                        visit(child)
                finally:
                    active.remove(identity)
                return
            if isinstance(value, Sequence) and not isinstance(
                value, (str, bytes, bytearray)
            ):
                identity = id(value)
                if identity in active:
                    raise ValueError("ranked recommendation window contains cyclic JSON")
                active.add(identity)
                try:
                    for child in value:
                        visit(child)
                finally:
                    active.remove(identity)

        visit(
            (
                window.window_id,
                window.subject_id,
                window.scenario,
                window.experiment_bucket,
                window.model_bucket,
                window.model_channel,
                window.model_release_id,
                window.policy_digest,
                window.request_digest,
                window.ranking_snapshot_digest,
                window.user_feature_snapshot,
                tuple(
                    (
                        item.content_id,
                        item.feature_snapshot_digest,
                        item.item_feature_snapshot,
                    )
                    for item in window.items
                ),
                tuple(
                    (
                        card.object_kind,
                        card.object_id,
                        card.title,
                        card.subtitle,
                        card.cover_url,
                        card.tag_refs,
                        card.reason_key,
                        card.recall_path,
                    )
                    for card in window.object_cards
                ),
            )
        )

    def _decode_window(
        self,
        raw: str | bytes,
        *,
        expected_subject_id: str,
        expected_window_id: str,
    ) -> RankedRecommendationWindow | None:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        if not encoded or len(encoded) > self.MAX_WINDOW_PAYLOAD_BYTES:
            raise WindowStoreError("ranked recommendation window payload is invalid")

        def reject_constant(value: str) -> None:
            raise ValueError(f"non-finite JSON constant {value}")

        try:
            document = json.loads(encoded, parse_constant=reject_constant)
            self._require_exact_fields(
                document,
                {
                    "windowId",
                    "subjectId",
                    "scenario",
                    "experimentBucket",
                    "modelBucket",
                    "modelChannel",
                    "modelReleaseId",
                    "policyDigest",
                    "requestDigest",
                    "rankingSnapshotDigest",
                    "featureSnapshotAt",
                    "userFeatureSnapshot",
                    "createdAt",
                    "expiresAt",
                    "items",
                    "objectCards",
                },
                "window",
            )
            if not isinstance(document["items"], list) or not isinstance(
                document["objectCards"], list
            ):
                raise ValueError("ranked window items and objectCards must be arrays")
            if not isinstance(document["userFeatureSnapshot"], dict):
                raise ValueError("ranked window userFeatureSnapshot must be an object")
            subject_id = self._required_text(document["subjectId"], "subjectId")
            window_id = self._required_text(document["windowId"], "windowId")
            if subject_id != expected_subject_id.strip() or window_id != expected_window_id.strip():
                raise WindowIdentityConflictError(
                    "ranked window payload does not match its subject/window key"
                )
            created_at = self._timestamp(document["createdAt"], "createdAt")
            expires_at = self._timestamp(document["expiresAt"], "expiresAt")
            if expires_at - created_at != WINDOW_TTL:
                raise ValueError("ranked window expiry does not match the fixed TTL")
            if expires_at <= self._now().astimezone(timezone.utc):
                return None
            candidates: list[RankedCandidate] = []
            for item in document["items"]:
                self._require_exact_fields(
                    item,
                    {
                        "ordinal",
                        "contentId",
                        "score",
                        "featureSnapshotDigest",
                        "itemFeatureSnapshot",
                    },
                    "item",
                )
                if not isinstance(item["ordinal"], int) or isinstance(
                    item["ordinal"], bool
                ):
                    raise ValueError("ranked window item ordinal must be an integer")
                if item["ordinal"] != len(candidates):
                    raise ValueError("ranked window item ordinals must be stable and contiguous")
                if (
                    not isinstance(item["score"], (int, float))
                    or isinstance(item["score"], bool)
                    or not math.isfinite(float(item["score"]))
                    or not isinstance(item["itemFeatureSnapshot"], dict)
                ):
                    raise ValueError("ranked window item snapshot is invalid")
                candidates.append(
                    RankedCandidate(
                        content_id=self._required_text(item["contentId"], "contentId"),
                        score=float(item["score"]),
                        feature_snapshot_digest=self._required_text(
                            item["featureSnapshotDigest"],
                            "featureSnapshotDigest",
                        ),
                        item_feature_snapshot=item["itemFeatureSnapshot"],
                    )
                )
            cards: list[RecommendationObjectCard] = []
            for card in document["objectCards"]:
                self._require_exact_fields(
                    card,
                    {
                        "objectKind",
                        "objectId",
                        "title",
                        "subtitle",
                        "coverUrl",
                        "tagRefs",
                        "reasonKey",
                        "recallPath",
                    },
                    "object card",
                )
                if not isinstance(card["tagRefs"], list) or any(
                    not isinstance(tag, str) for tag in card["tagRefs"]
                ):
                    raise ValueError("ranked window object card tagRefs are invalid")
                cards.append(
                    RecommendationObjectCard(
                        object_kind=self._required_text(card["objectKind"], "objectKind"),
                        object_id=self._required_text(card["objectId"], "objectId"),
                        title=self._required_text(card["title"], "title"),
                        subtitle=self._optional_text(card["subtitle"], "subtitle"),
                        cover_url=self._optional_text(card["coverUrl"], "coverUrl"),
                        tag_refs=tuple(card["tagRefs"]),
                        reason_key=self._required_text(card["reasonKey"], "reasonKey"),
                        recall_path=self._required_text(card["recallPath"], "recallPath"),
                    )
                )
            ranking = RankingResult(
                experiment_bucket=self._required_text(
                    document["experimentBucket"], "experimentBucket"
                ),
                model_bucket=self._required_text(document["modelBucket"], "modelBucket"),
                model_channel=self._optional_text(document["modelChannel"], "modelChannel"),
                model_release_id=self._optional_text(
                    document["modelReleaseId"], "modelReleaseId"
                ),
                policy_digest=self._required_text(document["policyDigest"], "policyDigest"),
                feature_snapshot_at=self._timestamp(
                    document["featureSnapshotAt"], "featureSnapshotAt"
                ),
                ranking_snapshot_digest=self._required_text(
                    document["rankingSnapshotDigest"], "rankingSnapshotDigest"
                ),
                user_feature_snapshot=document["userFeatureSnapshot"],
                candidates=tuple(candidates),
                object_cards=tuple(cards),
            )
            window = RankedRecommendationWindow.create(
                window_id=window_id,
                subject_id=subject_id,
                scenario=self._required_text(document["scenario"], "scenario"),
                request_digest=self._required_text(
                    document["requestDigest"], "requestDigest"
                ),
                ranking=ranking,
                now=created_at,
            )
            if window.expires_at != expires_at:
                raise ValueError("ranked window expiry is not canonical")
            return window
        except WindowIdentityConflictError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise WindowStoreError(
                f"ranked recommendation window payload is invalid: {error}"
            ) from error

    @staticmethod
    def _require_exact_fields(value: Any, expected: set[str], label: str) -> None:
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError(f"ranked window {label} fields are not canonical")

    @staticmethod
    def _required_text(value: Any, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"ranked window {field} must be non-blank text")
        return value.strip()

    @staticmethod
    def _optional_text(value: Any, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"ranked window {field} must be null or non-blank text")
        return value.strip()

    @staticmethod
    def _timestamp(value: Any, field: str) -> datetime:
        if not isinstance(value, str):
            raise ValueError(f"ranked window {field} must be a timestamp")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError(f"ranked window {field} must be timezone-aware")
        return parsed.astimezone(timezone.utc)
