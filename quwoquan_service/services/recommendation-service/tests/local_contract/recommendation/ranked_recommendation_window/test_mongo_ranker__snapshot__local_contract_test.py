from datetime import datetime, timezone
import hashlib
import json

import pytest
from tests.support.presentation import presentation_contract
from generated.recommendation.ranked_recommendation_window.models.request_response import ReleasePinnedQueryFence
from internal.recommendation.ranked_recommendation_window.domain.model import RecommendationRequestContext

from generated.recommendation.recommendation_model_release.models.request_response import (
    CandidateScore,
    ModelScoreResponse,
)
from internal.recommendation.ranked_recommendation_window.domain.discovery_tuning import (
    DiscoveryRankingTuning,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.mongo_ranker import (
    MongoCandidateRanker,
)
from internal.recommendation.ranked_recommendation_window.domain.experiment_policy import (
    ExperimentAssignments,
    ExperimentPolicy,
    PolicyVariant,
)


class _Candidates:
    def __init__(
        self,
        expected_scenario: str = "content_feed",
        object_card_candidates: list[dict] | None = None,
    ) -> None:
        self.expected_scenario = expected_scenario
        self.object_card_candidates = object_card_candidates or []

    def list_for_ranking(self, *, subject_id: str, scenario: str, limit: int, eligible_content_types):
        assert subject_id == "persona-viewer"
        assert scenario == self.expected_scenario
        assert limit == 300
        return [
            {
                "contentId": "post-b",
                "contentType": "article",
                "authorId": "persona-b",
                "tagRefs": ["Topic/旅行"],
                "entityRefs": ["地点/景区/色达"],
                "publishedAt": datetime(2026, 7, 31, 10, tzinfo=timezone.utc),
                "viewCount": 20,
                "likeCount": 5,
                "commentCount": 2,
                "shareCount": 1,
                "qualityScore": 0.8,
                "premiumEligible": True,
                "intersectionFeatures": {"intersectionEdgeWeight": 0.4},
                "sourceSequence": 2,
            },
            {
                "contentId": "post-a",
                "contentType": "video",
                "authorId": "persona-a",
                "tagRefs": [],
                "entityRefs": [],
                "publishedAt": datetime(2026, 7, 31, 11, tzinfo=timezone.utc),
                "viewCount": 10,
                "likeCount": 2,
                "commentCount": 1,
                "shareCount": 0,
                "qualityScore": 0.6,
                "premiumEligible": False,
                "intersectionFeatures": {},
                "sourceSequence": 3,
            },
        ]

    def list_for_ranking_by_content_ids(
        self, *, scenario: str, content_ids: tuple, limit: int, eligible_content_types
    ):
        return []

    def list_homepage_candidates(self, *, limit: int):
        assert limit == 400
        return list(self.object_card_candidates)


class _Features:
    def read_for_scoring(self, subject_id: str):
        assert subject_id == "persona-viewer"
        return {
            "checkpoint": 8,
            "sparseFeatures": {"engagementRate": 0.7, "action:view": 1.0},
            "influenceScore": 0.2,
            "collaborativeFeatures": {"post-a": 0.3},
            "intersectionFeatures": {"strength": 0.4},
            "negativeContentIds": [],
            "hiddenAuthorIds": [],
            "hiddenContentTypes": [],
        }


class _HardExclusionFeatures(_Features):
    def read_for_scoring(self, subject_id: str):
        result = super().read_for_scoring(subject_id)
        result["negativeContentIds"] = ["post-b"]
        result["hiddenContentTypes"] = ["video"]
        return result


class _Scoring:
    def __init__(self, *, incomplete: bool = False) -> None:
        self.incomplete = incomplete
        self.requests = []

    def score(self, request):
        self.requests.append(request)
        score_by_id = {"post-a": 0.8, "post-b": 0.5}
        scores = [
            CandidateScore(contentId=candidate.contentId, score=score_by_id[candidate.contentId])
            for candidate in request.candidates
        ]
        if self.incomplete and scores:
            scores = scores[:1]
        return ModelScoreResponse(scores=scores, modelReleaseId="release-001")


class _AssignmentPublisher:
    def __init__(self) -> None:
        self.assignments = []

    def publish(self, assignment) -> None:
        self.assignments.append(assignment)


def _ranker(
    scoring: _Scoring,
    *,
    candidates: _Candidates | None = None,
    features: _Features | None = None,
    tuning: DiscoveryRankingTuning | None = None,
) -> MongoCandidateRanker:
    experiment_publisher = _AssignmentPublisher()
    experiments = ExperimentAssignments(experiment_publisher)
    experiments.apply_policy(
        ExperimentPolicy(
            experiment_id="rec_model_vs_rule",
            revision=4,
            status="running",
            variants=(
                PolicyVariant("model", 9999),
                PolicyVariant("rule", 1),
            ),
            starts_at=None,
            ends_at=None,
            updated_at=datetime(2026, 7, 31, 11, tzinfo=timezone.utc),
            digest="",
        )
    )
    return MongoCandidateRanker(
        candidates=candidates or _Candidates(),
        feature_profiles=features or _Features(),
        scoring=scoring,
        experiments=experiments,
        snapshot_digester=lambda user, item: hashlib.sha256(
            json.dumps(
                {"item": item, "user": user},
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        tuning=tuning or DiscoveryRankingTuning.neutral(),
        now=lambda: datetime(2026, 7, 31, 12, tzinfo=timezone.utc),
    )


def test_ranker_freezes_feature_snapshot_and_stable_score_order() -> None:
    scoring = _Scoring()
    result = _ranker(scoring).rank(
        content_fence=ReleasePinnedQueryFence(release=None, revision=0),
        client_presentation_contract=presentation_contract(),
        subject_id="persona-viewer",
        scenario="content_feed",
        session_id="window-001",
        limit=300,
        request_context=RecommendationRequestContext("unknown", "unknown", "unknown", "h12", "unknown"),
    )
    assert result.model_release_id == "release-001"
    assert result.model_bucket == "model"
    assert len(result.ranking_snapshot_digest) == 64
    assert [(item.envelope.post.postId, item.score) for item in result.candidates] == [
        ("post-a", 0.8),
        ("post-b", 0.5),
    ]
    assert result.feature_snapshot_at == datetime(2026, 7, 31, 12, tzinfo=timezone.utc)
    assert result.candidates[0].item_feature_snapshot["contentId"] == "post-a"
    assert len(result.candidates[0].feature_snapshot_digest) == 64
    request = scoring.requests[0]
    assert request.userFeatures["engagementRate"] == 0.7
    assert request.candidates[0].ageHours == 2.0
    assert request.candidates[0].recallPath == "premium_pool"


def test_ranker_filters_capabilities_before_scoring():
    scoring = _Scoring()
    class AdmissionCandidates(_Candidates):
        def list_for_ranking(self, **kwargs):
            assert kwargs["eligible_content_types"] == ("article",)
            return super().list_for_ranking(**kwargs)
    result = _ranker(scoring, candidates=AdmissionCandidates()).rank(
        content_fence=ReleasePinnedQueryFence(release=None, revision=0),
        client_presentation_contract=presentation_contract(openSurfaces=["article_reader"]),
        subject_id="persona-viewer", scenario="content_feed", session_id="filtered", limit=300,
        request_context=RecommendationRequestContext("unknown", "unknown", "unknown", "h12", "unknown"),
    )
    assert [candidate.contentId for candidate in scoring.requests[0].candidates] == ["post-b"]
    assert [candidate.envelope.post.postId for candidate in result.candidates] == ["post-b"]


def test_ranker_keeps_audience_selection_separate_from_model_scenario() -> None:
    scoring = _Scoring()
    result = _ranker(
        scoring,
        candidates=_Candidates(expected_scenario="premium_stream"),
    ).rank(
        content_fence=ReleasePinnedQueryFence(release=None, revision=0),
        client_presentation_contract=presentation_contract(),
        subject_id="persona-viewer",
        scenario="premium_stream",
        session_id="window-premium",
        limit=300,
        request_context=RecommendationRequestContext("unknown", "unknown", "unknown", "h12", "unknown"),
    )
    assert result.model_release_id == "release-001"
    assert scoring.requests[0].scenario == "content_feed"


def test_ranker_fails_closed_when_scoring_omits_candidate() -> None:
    with pytest.raises(RuntimeError, match="does not match"):
        _ranker(_Scoring(incomplete=True)).rank(
        content_fence=ReleasePinnedQueryFence(release=None, revision=0),
        client_presentation_contract=presentation_contract(),
            subject_id="persona-viewer",
            scenario="content_feed",
            session_id="window-001",
            limit=300,
            request_context=RecommendationRequestContext("unknown", "unknown", "unknown", "h12", "unknown"),
        )


def test_ranker_applies_profile_hard_exclusions_before_scoring() -> None:
    scoring = _Scoring()
    result = _ranker(scoring, features=_HardExclusionFeatures()).rank(
        content_fence=ReleasePinnedQueryFence(release=None, revision=0),
        client_presentation_contract=presentation_contract(),
        subject_id="persona-viewer",
        scenario="content_feed",
        session_id="window-excluded",
        limit=300,
        request_context=RecommendationRequestContext("unknown", "unknown", "unknown", "h12", "unknown"),
    )
    assert result.candidates == ()
    assert scoring.requests == []


def test_ranker_freezes_object_cards_from_candidate_snapshot_and_entity_affinity() -> None:
    class _ObjectCardFeatures(_Features):
        def read_for_scoring(self, subject_id: str):
            result = super().read_for_scoring(subject_id)
            result["sparseFeatures"].update(
                {
                    "entity:entity-a": 0.7,
                    "entity:entity-b": 0.9,
                    "entity:entity-negative": -1.0,
                }
            )
            return result

    candidates = _Candidates(
        object_card_candidates=[
            {"objectKind": "gathering", "sourceKey": "unsupported-gathering"},
            {"objectKind": "future_kind", "sourceKey": "unsupported-future"},
            {
                "objectKind": "entity_homepage",
                "primaryHomepageId": "homepage-a",
                "primaryHomepageSnapshot": {
                    "homepageId": "homepage-a",
                    "canonicalEntityId": "entity-a",
                    "title": "对象 A",
                    "subtitle": "公开副标题",
                    "coverUrl": "https://cdn.example/a.jpg",
                    "tagRefs": ["旅行", "旅行", "摄影"],
                },
            },
            {
                "objectKind": "entity_homepage",
                "primaryHomepageId": "homepage-b",
                "primaryHomepageSnapshot": {
                    "homepageId": "homepage-b",
                    "canonicalEntityId": "entity-b",
                    "title": "对象 B",
                    "tagRefs": [],
                },
            },
            {
                "objectKind": "entity_homepage",
                "primaryHomepageId": "homepage-negative",
                "primaryHomepageSnapshot": {
                    "homepageId": "homepage-negative",
                    "canonicalEntityId": "entity-negative",
                    "title": "不得进入窗口",
                    "tagRefs": [],
                },
            },
        ]
    )

    result = _ranker(
        _Scoring(),
        candidates=candidates,
        features=_ObjectCardFeatures(),
    ).rank(
        content_fence=ReleasePinnedQueryFence(release=None, revision=0),
        client_presentation_contract=presentation_contract(),
        subject_id="persona-viewer",
        scenario="content_feed",
        session_id="window-object-cards",
        limit=300,
        request_context=RecommendationRequestContext("unknown", "unknown", "unknown", "h12", "unknown"),
    )

    homepages = [item for item in result.candidates if item.envelope.homepage]
    assert [item.envelope.homepage.homepageId for item in homepages] == ["homepage-b", "homepage-a"]
    assert result.candidates[0] == homepages[0]
    assert homepages[1].item_feature_snapshot["homepageSnapshot"]["title"] == "对象 A"
    assert {item.item_feature_snapshot["recallPath"] for item in homepages} == {"entity_card_affinity"}


def test_ranker_isolates_unsupported_gathering_without_losing_legal_posts() -> None:
    candidates = _Candidates(
        object_card_candidates=[
            {
                "objectKind": "gathering",
                "sourceKey": "gathering-001",
                "sourceVersion": 7,
                "cardDigest": "a" * 64,
                "title": "周末山野徒步",
                "summary": "公开摘要",
                "tagRefs": ["Topic/徒步", "Topic/徒步"],
            }
        ]
    )

    result = _ranker(_Scoring(), candidates=candidates).rank(
        content_fence=ReleasePinnedQueryFence(release=None, revision=0),
        client_presentation_contract=presentation_contract(),
        subject_id="persona-viewer",
        scenario="content_feed",
        session_id="window-gathering-card",
        limit=300,
        request_context=RecommendationRequestContext("unknown", "unknown", "unknown", "h12", "unknown"),
    )
    assert [item.envelope.post.postId for item in result.candidates] == ["post-a", "post-b"]
