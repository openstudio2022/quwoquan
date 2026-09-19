# spec_ref: specs/feature-tree/discovery-content/content-type-framework/unified-presentation-model/spec.md
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from generated.recommendation.ranked_recommendation_window.models.request_response import ReleasePinnedQueryFence
from internal.recommendation.ranked_recommendation_window.application.facade import Facade, IdempotencyConflictError, SubjectClosedError
from internal.recommendation.ranked_recommendation_window.domain.model import (
    RankedCandidate, RankedRecommendationWindow, RankingResult, WINDOW_TTL,
    validate_presentation_contract, validate_envelope,
)
from tests.support.presentation import presentation_contract, post_envelope, homepage_envelope

NOW = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)
FENCE = ReleasePinnedQueryFence(release=None, revision=0)


class _Store:
    window = None

    def create_or_get(self, window):
        if self.window is None:
            self.window = window
        return self.window

    def get(self, subject_id, window_id):
        if self.window and self.window.subject_id == subject_id and self.window.window_id == window_id:
            return self.window
        return None

    def erase_subject(self, subject_id):
        self.window = None
        return 1


class _Closures:
    closed = False

    def exists(self, account_id):
        return self.closed


class _Profiles:
    profile = {}

    def read_for_scoring(self, subject_id):
        return self.profile


def _ranking():
    return RankingResult(
        experiment_bucket="rule", model_bucket="rule", model_channel=None, model_release_id=None,
        policy_digest="policy", feature_snapshot_at=NOW, ranking_snapshot_digest="ranking",
        user_feature_snapshot={}, candidates=(
            RankedCandidate(post_envelope("post-a", "image"), 3, "a", {"authorId": "author"}),
            RankedCandidate(homepage_envelope("homepage-a"), 2, "b", {}),
            RankedCandidate(post_envelope("post-b", "article"), 1, "c", {}),
        ),
    )


class _Ranker:
    calls = 0

    def rank(self, **kwargs):
        self.calls += 1
        assert kwargs["client_presentation_contract"] == validate_presentation_contract(presentation_contract())
        return _ranking()


def _window(ranking=None, contract=None):
    return RankedRecommendationWindow.create(
        content_fence=FENCE, client_presentation_contract=contract or presentation_contract(),
        window_id="window", subject_id="subject", scenario="content_feed", request_digest="request",
        ranking=ranking or _ranking(), now=NOW,
    )


# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
def test_ordinary_query_requires_explicit_partition_and_data_events_are_not_ordinary():
    from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store_ranking_reads import MongoCandidateRankingReadOps
    from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.post_lifecycle_consumer import PostLifecycleEvent, lifecycle_snapshot
    assert MongoCandidateRankingReadOps.ranking_query("content_feed")["sourcePartition"] == "ordinary"
    for payload in ({}, {"sourceOwner": "qwq_data"}):
        event = PostLifecycleEvent("event", "PostPublished", "p", 1, payload, NOW)
        with pytest.raises(ValueError):
            lifecycle_snapshot(event)


def test_unified_items_have_stable_ordinals_and_fixed_expiry():
    window = _window()
    page, next_ordinal = window.page(from_ordinal=0, limit=2)
    assert [item.ordinal for item in page] == [0, 1]
    assert page[1].envelope.homepage.homepageId == "homepage-a"
    assert next_ordinal == 2
    assert window.page(from_ordinal=2, limit=2)[1] is None
    assert window.expires_at == NOW + WINDOW_TTL
    assert not hasattr(window, "object_cards")


@pytest.mark.parametrize("changes", [
    {"contentTypes": ["article"]}, {"listObjectKinds": ["entity_homepage"]},
    {"presentationRecipes": ["homepage_summary_card"]}, {"openSurfaces": ["homepage_detail"]},
])
def test_four_sets_filter_before_assigning_ordinals(changes):
    window = _window(contract=presentation_contract(**changes))
    assert len(window.items) < 3
    assert [item.ordinal for item in window.items] == list(range(len(window.items)))
    assert all(item.envelope.post is None or item.envelope.post.postId != "post-a" for item in window.items)


def test_digest_canonical_order_and_tampering():
    contract = presentation_contract()
    reversed_contract = contract.model_copy(deep=True)
    reversed_contract.contentTypes.reverse()
    assert validate_presentation_contract(contract) == validate_presentation_contract(reversed_contract)
    with pytest.raises(ValueError, match="digest"):
        validate_presentation_contract(contract.model_copy(update={"contractDigest": "sha256:" + "0" * 64}))
    with pytest.raises(ValueError, match="duplicate"):
        validate_presentation_contract(contract.model_copy(update={"contentTypes": ["image", "image"]}))
    with pytest.raises(ValueError):
        validate_presentation_contract(presentation_contract(contentTypes=["unknown"]))


def test_default_window_identity_is_isolated_by_canonical_digest():
    # 相同幂等键，不同客户端代际，不复用窗口 identity。
    first_store, second_store = _Store(), _Store()
    class Ranker:
        def rank(self, **kwargs):
            return _ranking()
    kwargs = dict(idempotency_key="same", subject_id="subject", scenario="content_feed", limit=2, content_fence=FENCE)
    def create(store, contract):
        facade = Facade(store=store, ranker=Ranker(), subject_closures=_Closures(), exclusion_profiles=_Profiles())
        return facade.create_window(**kwargs, client_presentation_contract=contract)
    first = create(first_store, presentation_contract())
    second = create(second_store, presentation_contract(listObjectKinds=["post"]))
    assert first.window_id != second.window_id


def test_empty_capabilities_do_not_expand_and_invalid_envelope_is_rejected():
    assert _window(contract=presentation_contract(listObjectKinds=[])).items == ()
    with pytest.raises(ValueError):
        validate_envelope(homepage_envelope("h").model_copy(update={"contentType": "image"}))


def test_duplicate_unbounded_and_invalid_fence_rejected():
    ranking = _ranking()
    for candidates in ((ranking.candidates[0],) * 2, (ranking.candidates[0],) * 301):
        with pytest.raises(ValueError):
            _window(replace(ranking, candidates=candidates))
    from internal.recommendation.ranked_recommendation_window.domain.model import validate_content_fence
    with pytest.raises(ValueError):
        validate_content_fence(ReleasePinnedQueryFence(release=None, revision=1))


def test_replay_capability_conflict_and_feedback_preserve_homepage_and_ordinal():
    store, ranker, profiles, closures = _Store(), _Ranker(), _Profiles(), _Closures()
    facade = Facade(store=store, ranker=ranker, subject_closures=closures, exclusion_profiles=profiles, window_id_factory=lambda _: "window")
    create = dict(idempotency_key="key", subject_id="subject", scenario="content_feed", limit=2, content_fence=FENCE, client_presentation_contract=presentation_contract())
    first = facade.create_window(**create)
    assert facade.create_window(**create) == first
    assert ranker.calls == 1
    read = dict(subject_id="subject", window_id="window", from_ordinal=0, limit=2, content_fence=FENCE, client_presentation_contract=presentation_contract())
    profiles.profile = {"negativeContentIds": ["post-a"]}
    filtered = facade.read_page(**read)
    assert [item.ordinal for item in filtered.items] == [1]
    assert filtered.next_ordinal == 2
    assert len(store.window.items) == 3
    changed = presentation_contract(openSurfaces=["article_reader"])
    with pytest.raises(IdempotencyConflictError):
        facade.create_window(**{**create, "client_presentation_contract": changed})
    with pytest.raises(IdempotencyConflictError):
        facade.read_page(**{**read, "client_presentation_contract": changed})
    closures.closed = True
    with pytest.raises(SubjectClosedError):
        facade.read_page(**read)
    with pytest.raises(SubjectClosedError):
        facade.create_window(**create)
