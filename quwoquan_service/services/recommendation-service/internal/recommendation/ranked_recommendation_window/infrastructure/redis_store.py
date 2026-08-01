from __future__ import annotations

import json
from datetime import datetime
from typing import Protocol

from ..domain.model import RankedRecommendationItem, RankedRecommendationWindow


class RedisClient(Protocol):
    def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool | None: ...

    def get(self, key: str) -> str | bytes | None: ...

    def sadd(self, key: str, *values: str) -> int: ...

    def srem(self, key: str, *values: str) -> int: ...

    def smembers(self, key: str) -> set[str] | set[bytes]: ...

    def expire(self, key: str, seconds: int) -> bool: ...

    def delete(self, *keys: str) -> int: ...


class RedisWindowStore:
    TTL_SECONDS = 900
    MAX_WINDOW_PAYLOAD_BYTES = 2 * 1024 * 1024

    def __init__(self, client: RedisClient) -> None:
        self._client = client

    @staticmethod
    def _key(window_id: str) -> str:
        return f"recommendation:ranked-window:{window_id}"

    @staticmethod
    def _subject_key(subject_id: str) -> str:
        return f"recommendation:ranked-window-subject:{subject_id}"

    def create_or_get(self, window: RankedRecommendationWindow) -> RankedRecommendationWindow:
        payload = json.dumps(
            {
                "windowId": window.window_id,
                "subjectId": window.subject_id,
                "scenario": window.scenario,
                "modelBucket": window.model_bucket,
                "modelChannel": window.model_channel,
                "modelReleaseId": window.model_release_id,
                "policyDigest": window.policy_digest,
                "requestDigest": window.request_digest,
                "rankingSnapshotDigest": window.ranking_snapshot_digest,
                "featureSnapshotAt": window.feature_snapshot_at.isoformat(),
                "userFeatureSnapshot": window.user_feature_snapshot,
                "createdAt": window.created_at.isoformat(),
                "expiresAt": window.expires_at.isoformat(),
                "items": [
                    {
                        "ordinal": item.ordinal,
                        "contentId": item.content_id,
                        "score": item.score,
                        "featureSnapshotDigest": item.feature_snapshot_digest,
                        "itemFeatureSnapshot": item.item_feature_snapshot,
                    }
                    for item in window.items
                ],
            },
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(payload.encode("utf-8")) > self.MAX_WINDOW_PAYLOAD_BYTES:
            raise ValueError("ranked recommendation window exceeds 2 MiB")
        subject_key = self._subject_key(window.subject_id)
        self._client.sadd(subject_key, window.window_id)
        self._client.expire(subject_key, self.TTL_SECONDS)
        try:
            created = self._client.set(
                self._key(window.window_id),
                payload,
                ex=self.TTL_SECONDS,
                nx=True,
            )
        except Exception:
            self._client.srem(subject_key, window.window_id)
            raise
        if created:
            return window
        existing = self.get(window.window_id)
        if existing is None:
            self._client.srem(subject_key, window.window_id)
            raise RuntimeError("ranked recommendation window identity raced with expiry")
        if existing.subject_id != window.subject_id:
            self._client.srem(subject_key, window.window_id)
        return existing

    def get(self, window_id: str) -> RankedRecommendationWindow | None:
        raw = self._client.get(self._key(window_id))
        if raw is None:
            return None
        document = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        return RankedRecommendationWindow(
            window_id=document["windowId"],
            subject_id=document["subjectId"],
            scenario=document["scenario"],
            model_bucket=document["modelBucket"],
            model_channel=document.get("modelChannel"),
            model_release_id=document.get("modelReleaseId"),
            policy_digest=document["policyDigest"],
            request_digest=document["requestDigest"],
            ranking_snapshot_digest=document["rankingSnapshotDigest"],
            feature_snapshot_at=datetime.fromisoformat(document["featureSnapshotAt"]),
            user_feature_snapshot=dict(document["userFeatureSnapshot"]),
            items=tuple(
                RankedRecommendationItem(
                    ordinal=int(item["ordinal"]),
                    content_id=item["contentId"],
                    score=float(item["score"]),
                    feature_snapshot_digest=item["featureSnapshotDigest"],
                    item_feature_snapshot=dict(item["itemFeatureSnapshot"]),
                )
                for item in document["items"]
            ),
            created_at=datetime.fromisoformat(document["createdAt"]),
            expires_at=datetime.fromisoformat(document["expiresAt"]),
        )

    def erase_subject(self, subject_id: str) -> int:
        normalized = subject_id.strip()
        if not normalized:
            raise ValueError("subjectId is required")
        subject_key = self._subject_key(normalized)
        raw_window_ids = self._client.smembers(subject_key)
        window_ids = [
            value.decode("utf-8") if isinstance(value, bytes) else str(value)
            for value in raw_window_ids
        ]
        deleted = 0
        for window_id in window_ids:
            deleted += int(self._client.delete(self._key(window_id)))
        self._client.delete(subject_key)
        return deleted
