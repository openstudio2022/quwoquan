from datetime import datetime, timezone

import pytest

from internal.recommendation.ranked_recommendation_window.application.facade import (
    Facade,
    IdempotencyConflictError,
    SubjectClosedError,
)
from internal.recommendation.ranked_recommendation_window.domain.model import (
    MAX_WINDOW_OBJECT_CARDS,
    MAX_WINDOW_ITEMS,
    WINDOW_TTL,
    RecommendationObjectCard,
    RankedCandidate,
    RankedRecommendationWindow,
    RankingResult,
)


class _Store:
    def __init__(self) -> None:
        self.window = None

    def create_or_get(self, window):
        if self.window is None:
            self.window = window
        return self.window

    def get(self, subject_id, window_id):
        if (
            self.window
            and self.window.subject_id == subject_id
            and self.window.window_id == window_id
        ):
            return self.window
        return None

    def erase_subject(self, subject_id):
        if self.window and self.window.subject_id == subject_id:
            self.window = None
            return 1
        return 0


def _ranking(count: int = 5) -> RankingResult:
    return RankingResult(
        experiment_bucket="model",
        model_bucket="model",
        model_channel="champion",
        model_release_id="release-001",
        policy_digest="sha256:2f8a57089882835170b77224eb7ef2db78c5d5d26ae4637b210dbe195713f094",
        feature_snapshot_at=datetime(2020, 7, 31, 11, tzinfo=timezone.utc),
        ranking_snapshot_digest="ranking-digest-001",
        user_feature_snapshot={"engagement": 0.7},
        candidates=tuple(
            RankedCandidate(
                content_id=f"post-{index}",
                score=float(count - index),
                feature_snapshot_digest=f"feature-digest-{index}",
                item_feature_snapshot={"quality": index / 10},
            )
            for index in range(count)
        ),
    )


class _Ranker:
    def __init__(self) -> None:
        self.calls = 0

    def rank(self, *, subject_id: str, scenario: str, session_id: str, limit: int):
        self.calls += 1
        return _ranking()


class _Closures:
    def __init__(self, *closed: str) -> None:
        self.closed = set(closed)

    def exists(self, account_id: str) -> bool:
        return account_id in self.closed


class _ExclusionProfiles:
    """Typed stand-in for the subject's current strong-feedback profile."""

    def __init__(self) -> None:
        self.profiles: dict[str, dict] = {}

    def read_for_scoring(self, subject_id: str) -> dict:
        return dict(self.profiles.get(subject_id, {}))


def test_ranked_window_has_fixed_expiry_and_stable_ordinals() -> None:
    now = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)
    window = RankedRecommendationWindow.create(
        window_id="window-001",
        subject_id="persona-001",
        scenario="content_feed",
        request_digest="request-digest-001",
        ranking=RankingResult(
            experiment_bucket="model",
            model_bucket="model",
            model_channel="champion",
            model_release_id="release-001",
            policy_digest="sha256:2f8a57089882835170b77224eb7ef2db78c5d5d26ae4637b210dbe195713f094",
            feature_snapshot_at=now,
            ranking_snapshot_digest="ranking-digest-001",
            user_feature_snapshot={"engagement": 0.7},
            candidates=(
                RankedCandidate("post-a", 4.0, "digest-a", {"quality": 0.8}),
                RankedCandidate("post-b", 3.0, "digest-b", {"quality": 0.7}),
                RankedCandidate("post-c", 2.0, "digest-c", {"quality": 0.6}),
            ),
        ),
        now=now,
    )
    first, next_ordinal = window.page(from_ordinal=0, limit=2)
    second, terminal = window.page(from_ordinal=next_ordinal, limit=2)
    assert window.expires_at == now + WINDOW_TTL
    assert [(item.ordinal, item.content_id) for item in first] == [(0, "post-a"), (1, "post-b")]
    assert [(item.ordinal, item.content_id) for item in second] == [(2, "post-c")]
    assert terminal is None
    assert window.expires_at == now + WINDOW_TTL


def test_ranked_window_facade_persists_one_bounded_identity() -> None:
    store = _Store()
    ranker = _Ranker()
    facade = Facade(
        store=store,
        ranker=ranker,
        subject_closures=_Closures(),
        exclusion_profiles=_ExclusionProfiles(),
        window_id_factory=lambda _key: "window-fixed",
    )
    page = facade.create_window(
        idempotency_key="request-001",
        subject_id="persona-001",
        scenario="content_feed",
        limit=3,
    )
    assert page.window_id == "window-fixed"
    assert [item.content_id for item in page.items] == ["post-0", "post-1", "post-2"]
    assert page.next_ordinal == 3
    assert facade.read_page(
        subject_id="persona-001",
        window_id="window-fixed",
        from_ordinal=3,
        limit=2,
    ).next_ordinal is None

    replay = facade.create_window(
        idempotency_key="request-001",
        subject_id="persona-001",
        scenario="content_feed",
        limit=3,
    )
    assert replay == page
    assert ranker.calls == 1

    with pytest.raises(IdempotencyConflictError):
        facade.create_window(
            idempotency_key="request-001",
            subject_id="persona-001",
            scenario="content_feed_other",
            limit=3,
        )


def test_ranked_window_future_pages_filter_current_strong_feedback() -> None:
    store = _Store()
    profiles = _ExclusionProfiles()
    facade = Facade(
        store=store,
        ranker=_Ranker(),
        subject_closures=_Closures(),
        exclusion_profiles=profiles,
        window_id_factory=lambda _key: "window-fixed",
    )
    first = facade.create_window(
        idempotency_key="request-001",
        subject_id="persona-001",
        scenario="content_feed",
        limit=2,
    )
    assert [item.content_id for item in first.items] == ["post-0", "post-1"]
    assert first.next_ordinal == 2

    # 强负反馈只影响未来窗口：窗口本体不可变，但反馈后的每次页读取都必须
    # 过滤被 dislike 的内容；ordinal 与 next_ordinal 保持窗口原值。
    profiles.profiles["persona-001"] = {"negativeContentIds": ["post-2"]}
    filtered = facade.read_page(
        subject_id="persona-001",
        window_id="window-fixed",
        from_ordinal=2,
        limit=2,
    )
    assert [item.content_id for item in filtered.items] == ["post-3"]
    assert filtered.next_ordinal == 4

    stored_items, _ = store.window.page(from_ordinal=2, limit=2)
    assert [item.content_id for item in stored_items] == ["post-2", "post-3"]


def test_ranked_window_blocks_closed_subject_creation_and_existing_window_reads() -> None:
    store = _Store()
    ranker = _Ranker()
    closures = _Closures()
    facade = Facade(
        store=store,
        ranker=ranker,
        subject_closures=closures,
        exclusion_profiles=_ExclusionProfiles(),
        window_id_factory=lambda _key: "window-fixed",
    )
    facade.create_window(
        idempotency_key="request-001",
        subject_id="account-001",
        scenario="content_feed",
        limit=3,
    )
    closures.closed.add("account-001")
    with pytest.raises(SubjectClosedError):
        facade.read_page(
            subject_id="account-001",
            window_id="window-fixed",
            from_ordinal=0,
            limit=3,
        )
    with pytest.raises(SubjectClosedError):
        facade.create_window(
            idempotency_key="request-002",
            subject_id="account-001",
            scenario="content_feed",
            limit=3,
        )


def test_ranked_window_rejects_duplicate_or_unbounded_candidates() -> None:
    with pytest.raises(ValueError):
        RankedRecommendationWindow.create(
            window_id="window-duplicate",
            subject_id="persona-001",
            scenario="content_feed",
            request_digest="request-digest-001",
            ranking=RankingResult(
                experiment_bucket="rule",
                model_bucket="rule",
                model_channel=None,
                model_release_id=None,
                policy_digest="sha256:2f8a57089882835170b77224eb7ef2db78c5d5d26ae4637b210dbe195713f094",
                feature_snapshot_at=datetime.now(timezone.utc),
                ranking_snapshot_digest="ranking-digest-001",
                user_feature_snapshot={},
                candidates=(
                    RankedCandidate("post-a", 1.0, "digest-a", {}),
                    RankedCandidate("post-a", 0.5, "digest-a", {}),
                ),
            ),
        )
    with pytest.raises(ValueError):
        RankedRecommendationWindow.create(
            window_id="window-unbounded",
            subject_id="persona-001",
            scenario="content_feed",
            request_digest="request-digest-001",
            ranking=_ranking(MAX_WINDOW_ITEMS + 1),
        )


def test_ranked_window_freezes_bounded_unique_object_cards() -> None:
    ranking = _ranking()
    card = RecommendationObjectCard(
        object_kind="entity_homepage",
        object_id="homepage-001",
        title="公开对象页",
        subtitle=None,
        cover_url=None,
        tag_refs=("旅行",),
        reason_key="affinity",
        recall_path="entity_card_affinity",
    )
    window = RankedRecommendationWindow.create(
        window_id="window-object-card",
        subject_id="persona-001",
        scenario="content_feed",
        request_digest="request-object-card",
        ranking=RankingResult(
            experiment_bucket=ranking.experiment_bucket,
            model_bucket=ranking.model_bucket,
            model_channel=ranking.model_channel,
            model_release_id=ranking.model_release_id,
            policy_digest=ranking.policy_digest,
            feature_snapshot_at=ranking.feature_snapshot_at,
            ranking_snapshot_digest=ranking.ranking_snapshot_digest,
            user_feature_snapshot=ranking.user_feature_snapshot,
            candidates=ranking.candidates,
            object_cards=(card,),
        ),
    )
    assert window.object_cards == (card,)
    gathering_card = RecommendationObjectCard(
        object_kind="gathering",
        object_id="gathering-001",
        title="周末山野徒步",
        subtitle="公开摘要",
        cover_url=None,
        tag_refs=("徒步",),
        reason_key="public_gathering",
        recall_path="gathering_candidate_index",
    )
    gathering_window = RankedRecommendationWindow.create(
        window_id="window-gathering-card",
        subject_id="persona-001",
        scenario="content_feed",
        request_digest="request-gathering-card",
        ranking=RankingResult(
            experiment_bucket=ranking.experiment_bucket,
            model_bucket=ranking.model_bucket,
            model_channel=ranking.model_channel,
            model_release_id=ranking.model_release_id,
            policy_digest=ranking.policy_digest,
            feature_snapshot_at=ranking.feature_snapshot_at,
            ranking_snapshot_digest=ranking.ranking_snapshot_digest,
            user_feature_snapshot=ranking.user_feature_snapshot,
            candidates=ranking.candidates,
            object_cards=(gathering_card,),
        ),
    )
    assert gathering_window.object_cards == (gathering_card,)

    for invalid_cards in (
        (card, card),
        tuple(card for _ in range(MAX_WINDOW_OBJECT_CARDS + 1)),
    ):
        with pytest.raises(ValueError):
            RankedRecommendationWindow.create(
                window_id="window-invalid-object-card",
                subject_id="persona-001",
                scenario="content_feed",
                request_digest="request-invalid-object-card",
                ranking=RankingResult(
                    experiment_bucket=ranking.experiment_bucket,
                    model_bucket=ranking.model_bucket,
                    model_channel=ranking.model_channel,
                    model_release_id=ranking.model_release_id,
                    policy_digest=ranking.policy_digest,
                    feature_snapshot_at=ranking.feature_snapshot_at,
                    ranking_snapshot_digest=ranking.ranking_snapshot_digest,
                    user_feature_snapshot=ranking.user_feature_snapshot,
                    candidates=ranking.candidates,
                    object_cards=invalid_cards,
                ),
            )
