from datetime import datetime, timezone
import hashlib
import json

import pytest

from generated.recommendation.recommendation_model_release.models.request_response import (
    CandidateScore,
    ModelScoreResponse,
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
    def __init__(self, expected_scenario: str = "content_feed") -> None:
        self.expected_scenario = expected_scenario

    def list_for_ranking(self, *, scenario: str, limit: int):
        assert scenario == self.expected_scenario
        assert limit == 500
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


class _Features:
    def read_for_scoring(self, subject_id: str):
        assert subject_id == "persona-viewer"
        return {
            "checkpoint": 8,
            "sparseFeatures": {"engagementRate": 0.7},
            "influenceScore": 0.2,
            "collaborativeFeatures": {"post-a": 0.3},
            "intersectionFeatures": {"strength": 0.4},
        }


class _Scoring:
    def __init__(self, *, incomplete: bool = False) -> None:
        self.incomplete = incomplete
        self.requests = []

    def score(self, request):
        self.requests.append(request)
        scores = [CandidateScore(contentId="post-b", score=0.5)]
        if not self.incomplete:
            scores.append(CandidateScore(contentId="post-a", score=0.8))
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
        feature_profiles=_Features(),
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
        now=lambda: datetime(2026, 7, 31, 12, tzinfo=timezone.utc),
    )


def test_ranker_freezes_feature_snapshot_and_stable_score_order() -> None:
    scoring = _Scoring()
    result = _ranker(scoring).rank(
        subject_id="persona-viewer",
        scenario="content_feed",
        session_id="window-001",
        limit=500,
    )
    assert result.model_release_id == "release-001"
    assert result.model_bucket == "model"
    assert len(result.ranking_snapshot_digest) == 64
    assert [(item.content_id, item.score) for item in result.candidates] == [
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


def test_ranker_keeps_audience_selection_separate_from_model_scenario() -> None:
    scoring = _Scoring()
    result = _ranker(
        scoring,
        candidates=_Candidates(expected_scenario="premium_stream"),
    ).rank(
        subject_id="persona-viewer",
        scenario="premium_stream",
        session_id="window-premium",
        limit=500,
    )
    assert result.model_release_id == "release-001"
    assert scoring.requests[0].scenario == "content_feed"


def test_ranker_fails_closed_when_scoring_omits_candidate() -> None:
    with pytest.raises(RuntimeError, match="does not match"):
        _ranker(_Scoring(incomplete=True)).rank(
            subject_id="persona-viewer",
            scenario="content_feed",
            session_id="window-001",
            limit=500,
        )
