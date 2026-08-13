from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Protocol
from uuid import NAMESPACE_URL, uuid5

from ..domain.model import (
    MAX_WINDOW_ITEMS,
    RankingResult,
    RankedRecommendationItem,
    RecommendationObjectCard,
    RankedRecommendationWindow,
)


class WindowStore(Protocol):
    def create_or_get(self, window: RankedRecommendationWindow) -> RankedRecommendationWindow: ...

    def get(
        self,
        subject_id: str,
        window_id: str,
    ) -> RankedRecommendationWindow | None: ...

    def erase_subject(self, subject_id: str) -> int: ...


class CandidateRanker(Protocol):
    def rank(
        self,
        *,
        subject_id: str,
        scenario: str,
        session_id: str,
        limit: int,
    ) -> RankingResult: ...


class SubjectClosureReader(Protocol):
    def exists(self, account_id: str) -> bool: ...


class ExclusionProfileReader(Protocol):
    """Reads the subject's current strong negative-feedback profile.

    Windows stay immutable, but every page served from an existing window must
    project out content the subject has since disliked/hidden ("强反馈只影响
    未来窗口"): already-delivered client history is untouched, while any page
    read after the feedback excludes the offending items.
    """

    def read_for_scoring(self, subject_id: str) -> dict: ...


class IdempotencyConflictError(RuntimeError):
    pass


class SubjectClosedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RankedRecommendationPage:
    window_id: str
    scenario: str
    model_bucket: str
    model_channel: str | None
    model_release_id: str | None
    policy_digest: str
    ranking_snapshot_digest: str
    feature_snapshot_at: str
    user_feature_snapshot: dict
    items: tuple[RankedRecommendationItem, ...]
    next_ordinal: int | None
    expires_at: str
    object_cards: tuple[RecommendationObjectCard, ...] = ()


class Facade:
    def __init__(
        self,
        *,
        store: WindowStore,
        ranker: CandidateRanker,
        subject_closures: SubjectClosureReader,
        exclusion_profiles: ExclusionProfileReader,
        window_id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._store = store
        self._ranker = ranker
        self._subject_closures = subject_closures
        self._exclusion_profiles = exclusion_profiles
        self._window_id_factory = window_id_factory or (
            lambda idempotency_key: str(
                uuid5(NAMESPACE_URL, f"quwoquan:recommendation-window:{idempotency_key}")
            )
        )

    def create_window(
        self,
        *,
        idempotency_key: str,
        subject_id: str,
        scenario: str,
        limit: int,
    ) -> RankedRecommendationPage:
        if limit <= 0 or limit > 100:
            raise ValueError("limit must be in 1..100")
        normalized_key = idempotency_key.strip()
        if not normalized_key or len(normalized_key.encode("utf-8")) > 256:
            raise ValueError("Idempotency-Key is required and must not exceed 256 bytes")
        normalized_subject = subject_id.strip()
        if not normalized_subject:
            raise ValueError("subjectId is required")
        normalized_scenario = scenario.strip()
        if not normalized_scenario:
            raise ValueError("scenario is required")
        if self._subject_closures.exists(normalized_subject):
            raise SubjectClosedError("closed subjects cannot create recommendation windows")
        request_digest = hashlib.sha256(
            json.dumps(
                {
                    "subjectId": normalized_subject,
                    "scenario": normalized_scenario,
                    "limit": limit,
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        window_id = self._window_id_factory(normalized_key)
        existing = self._store.get(normalized_subject, window_id)
        if existing is not None:
            if existing.request_digest != request_digest:
                raise IdempotencyConflictError(
                    "Idempotency-Key was already used with another request"
                )
            return self._page(existing, from_ordinal=0, limit=limit)

        ranking = self._ranker.rank(
            subject_id=normalized_subject,
            scenario=normalized_scenario,
            session_id=window_id,
            limit=MAX_WINDOW_ITEMS,
        )
        window = RankedRecommendationWindow.create(
            window_id=window_id,
            subject_id=normalized_subject,
            scenario=normalized_scenario,
            request_digest=request_digest,
            ranking=ranking,
        )
        persisted = self._store.create_or_get(window)
        if persisted.request_digest != request_digest:
            raise IdempotencyConflictError(
                "Idempotency-Key was concurrently used with another request"
            )
        if self._subject_closures.exists(normalized_subject):
            self._store.erase_subject(normalized_subject)
            raise SubjectClosedError("closed subjects cannot create recommendation windows")
        return self._page(persisted, from_ordinal=0, limit=limit)

    def read_page(
        self,
        *,
        subject_id: str,
        window_id: str,
        from_ordinal: int,
        limit: int,
    ) -> RankedRecommendationPage:
        normalized_subject = subject_id.strip()
        normalized_window = window_id.strip()
        if not normalized_subject or not normalized_window:
            raise ValueError("subjectId and windowId are required")
        window = self._store.get(normalized_subject, normalized_window)
        if window is None:
            raise LookupError("ranked recommendation window not found or expired")
        if self._subject_closures.exists(normalized_subject):
            self._store.erase_subject(normalized_subject)
            raise SubjectClosedError("closed subjects cannot read recommendation windows")
        return self._page(window, from_ordinal=from_ordinal, limit=limit)

    def _current_hard_exclusions(
        self,
        subject_id: str,
    ) -> tuple[set[str], set[str], set[str]]:
        profile = self._exclusion_profiles.read_for_scoring(subject_id)
        def _normalized(field: str) -> set[str]:
            return {
                str(value).strip()
                for value in profile.get(field) or []
                if str(value).strip()
            }
        return (
            _normalized("negativeContentIds"),
            _normalized("hiddenAuthorIds"),
            _normalized("hiddenContentTypes"),
        )

    def _page(self, window: RankedRecommendationWindow, *, from_ordinal: int, limit: int) -> RankedRecommendationPage:
        items, next_ordinal = window.page(from_ordinal=from_ordinal, limit=limit)
        # 未来窗口精确过滤：窗口本体与 ordinal 保持不可变，但每次读取都按
        # subject 当前强负反馈投影过滤；页因此可以变短，next_ordinal 不受影响。
        negative, hidden_authors, hidden_types = self._current_hard_exclusions(
            window.subject_id
        )
        if negative or hidden_authors or hidden_types:
            items = tuple(
                item
                for item in items
                if item.content_id not in negative
                and str(item.item_feature_snapshot.get("authorId") or "").strip()
                not in hidden_authors
                and str(item.item_feature_snapshot.get("contentType") or "").strip()
                not in hidden_types
            )
        return RankedRecommendationPage(
            window_id=window.window_id,
            scenario=window.scenario,
            model_bucket=window.model_bucket,
            model_channel=window.model_channel,
            model_release_id=window.model_release_id,
            policy_digest=window.policy_digest,
            ranking_snapshot_digest=window.ranking_snapshot_digest,
            feature_snapshot_at=window.feature_snapshot_at.isoformat(),
            user_feature_snapshot=dict(window.user_feature_snapshot),
            items=items,
            next_ordinal=next_ordinal,
            expires_at=window.expires_at.isoformat(),
            object_cards=window.object_cards,
        )
