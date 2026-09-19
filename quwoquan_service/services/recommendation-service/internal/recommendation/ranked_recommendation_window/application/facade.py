from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Callable, Protocol
from uuid import NAMESPACE_URL, uuid5

from ..domain.model import (
    MAX_WINDOW_ITEMS,
    ReleasePinnedQueryFence,
    validate_content_fence,
    RankingResult,
    RankedRecommendationItem,
    ClientContentPresentationContract,
    validate_presentation_contract,
    RecommendationRequestContext,
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
        content_fence: ReleasePinnedQueryFence,
        client_presentation_contract: ClientContentPresentationContract,
        request_context: RecommendationRequestContext,
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
    content_fence: ReleasePinnedQueryFence
    window_id: str
    scenario: str
    experiment_bucket: str
    model_bucket: str
    model_channel: str | None
    model_release_id: str | None
    policy_digest: str
    context_digest: str
    ranking_snapshot_digest: str
    feature_snapshot_at: str
    user_feature_snapshot: dict
    items: tuple[RankedRecommendationItem, ...]
    next_ordinal: int | None
    expires_at: str
    client_presentation_contract: ClientContentPresentationContract


class Facade:
    def __init__(
        self,
        *,
        store: WindowStore,
        ranker: CandidateRanker,
        subject_closures: SubjectClosureReader,
        exclusion_profiles: ExclusionProfileReader,
        window_id_factory: Callable[[str], str] | None = None,
        now: Callable[[], datetime] | None = None,
        release_readiness=None,
    ) -> None:
        self._release_readiness = release_readiness
        self._store = store
        self._ranker = ranker
        self._subject_closures = subject_closures
        self._exclusion_profiles = exclusion_profiles
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._window_id_factory = window_id_factory or (
            lambda idempotency_key: str(
                uuid5(NAMESPACE_URL, f"quwoquan:recommendation-window:{idempotency_key}")
            )
        )

    def read_release_readiness(self, query):
        from internal.recommendation.recommendation_candidate_index_view.application.release_candidate import ReleaseNotReady
        if self._release_readiness is None:
            raise ReleaseNotReady("release readiness reader is not configured")
        return self._release_readiness.read_release_readiness(query.binding, query.snapshotDigest)

    def create_window(
        self,
        *,
        idempotency_key: str,
        subject_id: str,
        scenario: str,
        limit: int,
        content_fence: ReleasePinnedQueryFence,
        client_presentation_contract: ClientContentPresentationContract,
        viewport_profile: str | None = None,
        device_class: str | None = None,
    ) -> RankedRecommendationPage:
        content_fence = validate_content_fence(content_fence)
        contract = validate_presentation_contract(client_presentation_contract)
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
        normalized_viewport = self._normalize_viewport(viewport_profile)
        normalized_device = self._normalize_device(device_class)
        window_id = self._window_id_factory(json.dumps([normalized_key, contract.contractDigest], separators=(",", ":")))
        existing = self._store.get(normalized_subject, window_id)
        if existing is not None:
            request_digest = self._request_digest(
                content_fence=content_fence,
                contract=contract,
                subject_id=normalized_subject,
                scenario=normalized_scenario,
                limit=limit,
                context_digest=self._context_digest(RecommendationRequestContext(
                    viewport_profile=normalized_viewport,
                    device_class=normalized_device,
                    coarse_region=existing.request_context.coarse_region,
                    time_bucket=existing.request_context.time_bucket,
                    profile_revision=existing.request_context.profile_revision,
                )),
            )
            if existing.request_digest != request_digest or existing.content_fence != content_fence:
                raise IdempotencyConflictError(
                    "Idempotency-Key was already used with another request"
                )
            return self._page(existing, from_ordinal=0, limit=limit)

        admitted_at = self._now().astimezone(timezone.utc)
        request_context = RecommendationRequestContext(
            viewport_profile=normalized_viewport,
            device_class=normalized_device,
            coarse_region="unknown",
            time_bucket=f"h{admitted_at.hour:02d}",
            profile_revision="unknown",
        )
        ranking = self._ranker.rank(
            subject_id=normalized_subject,
            scenario=normalized_scenario,
            session_id=window_id,
            limit=MAX_WINDOW_ITEMS,
            content_fence=content_fence.model_copy(deep=True),
            client_presentation_contract=contract.model_copy(deep=True),
            request_context=request_context,
        )
        admitted_at = max(admitted_at, ranking.feature_snapshot_at.astimezone(timezone.utc))
        request_context = RecommendationRequestContext(
            viewport_profile=request_context.viewport_profile,
            device_class=request_context.device_class,
            coarse_region=request_context.coarse_region,
            time_bucket=request_context.time_bucket,
            profile_revision=self._normalize_profile_revision(ranking.profile_revision),
        )
        context_digest = self._context_digest(request_context)
        request_digest = self._request_digest(
            content_fence=content_fence,
            contract=contract,
            subject_id=normalized_subject,
            scenario=normalized_scenario,
            limit=limit,
            context_digest=context_digest,
        )
        ranking = self._bind_ranking_context(ranking, context_digest)
        window = RankedRecommendationWindow.create(
            window_id=window_id,
            subject_id=normalized_subject,
            scenario=normalized_scenario,
            request_digest=request_digest,
            request_context=request_context,
            context_digest=context_digest,
            ranking=ranking,
            content_fence=content_fence,
            client_presentation_contract=contract,
            now=admitted_at,
        )
        persisted = self._store.create_or_get(window)
        if persisted.request_digest != request_digest or persisted.content_fence != content_fence:
            raise IdempotencyConflictError(
                "Idempotency-Key was concurrently used with another request"
            )
        if self._subject_closures.exists(normalized_subject):
            self._store.erase_subject(normalized_subject)
            raise SubjectClosedError("closed subjects cannot create recommendation windows")
        return self._page(persisted, from_ordinal=0, limit=limit)

    @staticmethod
    def _normalize_viewport(value: str | None) -> str:
        normalized = "unknown" if value is None else value
        if not isinstance(normalized, str) or normalized not in {"landscape", "portrait", "unknown"}:
            raise ValueError("viewportProfile is invalid")
        return normalized

    @staticmethod
    def _normalize_device(value: str | None) -> str:
        normalized = "unknown" if value is None else value
        if not isinstance(normalized, str) or normalized not in {"phone", "tablet", "desktop", "unknown"}:
            raise ValueError("deviceClass is invalid")
        return normalized

    @staticmethod
    def _normalize_profile_revision(value: str) -> str:
        normalized = str(value).strip()
        if normalized == "unknown" or normalized == "0" or (normalized.isdigit() and not normalized.startswith("0")):
            return normalized
        return "unknown"

    @staticmethod
    def _context_digest(context: RecommendationRequestContext) -> str:
        return hashlib.sha256(json.dumps(
            context.canonical_document(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")).hexdigest()

    @staticmethod
    def _request_digest(*, content_fence, contract, subject_id: str, scenario: str, limit: int, context_digest: str) -> str:
        return hashlib.sha256(json.dumps({
            "clientPresentationContract": contract.model_dump(mode="json"),
            "contentFence": content_fence.model_dump(mode="json"),
            "contextDigest": context_digest,
            "limit": limit,
            "scenario": scenario,
            "subjectId": subject_id,
        }, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _bind_ranking_context(ranking: RankingResult, context_digest: str) -> RankingResult:
        digest = hashlib.sha256(json.dumps({
            "contextDigest": context_digest,
            "featureSnapshotAt": ranking.feature_snapshot_at.astimezone(timezone.utc).isoformat(),
            "modelBucket": ranking.model_bucket,
            "modelChannel": ranking.model_channel,
            "modelReleaseId": ranking.model_release_id,
            "policyDigest": ranking.policy_digest,
            "rankerSnapshotDigest": ranking.ranking_snapshot_digest,
            "ranked": [
                {
                    "envelope": item.envelope.model_dump(mode="json"),
                    "featureSnapshotDigest": item.feature_snapshot_digest,
                    "score": item.score,
                }
                for item in ranking.candidates
            ],
        }, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
        return RankingResult(
            experiment_bucket=ranking.experiment_bucket, model_bucket=ranking.model_bucket,
            model_channel=ranking.model_channel, model_release_id=ranking.model_release_id,
            policy_digest=ranking.policy_digest, feature_snapshot_at=ranking.feature_snapshot_at,
            ranking_snapshot_digest=digest, user_feature_snapshot=ranking.user_feature_snapshot,
            candidates=ranking.candidates, profile_revision=ranking.profile_revision,
        )

    def read_page(
        self,
        *,
        subject_id: str,
        window_id: str,
        from_ordinal: int,
        limit: int,
        content_fence: ReleasePinnedQueryFence,
        client_presentation_contract: ClientContentPresentationContract,
    ) -> RankedRecommendationPage:
        content_fence = validate_content_fence(content_fence)
        contract = validate_presentation_contract(client_presentation_contract)
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
        if window.content_fence != content_fence or window.client_presentation_contract != contract:
            raise IdempotencyConflictError("Window fence or presentation contract changed; restart from first page")
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
                if item.envelope.post is None or (
                    item.envelope.post.postId not in negative
                    and str(item.item_feature_snapshot.get("authorId") or "").strip() not in hidden_authors
                    and item.envelope.contentType not in hidden_types
                )
            )
        return RankedRecommendationPage(
            content_fence=window.content_fence.model_copy(deep=True),
            window_id=window.window_id,
            scenario=window.scenario,
            experiment_bucket=window.experiment_bucket,
            model_bucket=window.model_bucket,
            model_channel=window.model_channel,
            model_release_id=window.model_release_id,
            policy_digest=window.policy_digest,
            context_digest=window.context_digest,
            ranking_snapshot_digest=window.ranking_snapshot_digest,
            feature_snapshot_at=window.feature_snapshot_at.isoformat(),
            user_feature_snapshot=dict(window.user_feature_snapshot),
            items=items,
            next_ordinal=next_ordinal,
            expires_at=window.expires_at.isoformat(),
            client_presentation_contract=window.client_presentation_contract.model_copy(deep=True),
        )
