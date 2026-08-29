"""Discovery tuning knobs, model-bucket fallback and empty-candidate semantics.

Covers the ops.reco.discovery.* runtime knobs (prerank.new_content_boost,
rank.author_diversity_weight, recall.whitelist_enabled), the model-bucket
degrade-to-rule semantics, and the canonical empty-window behaviour when the
candidate pool or the post-filter set is empty.
"""
# spec_ref: specs/feature-tree/discovery-content/exposure-governance/ops-intervention-and-policy-ejection/spec.md#req-001
# spec_ref: specs/feature-tree/recommendation-platform/rec-model-service/go-integration/spec.md#req-002
from datetime import datetime, timezone
import hashlib
import json

import pytest
from prometheus_client import REGISTRY

from generated.recommendation.recommendation_model_release.models.request_response import (
    CandidateScore,
    ModelScoreResponse,
)
from internal.recommendation.ranked_recommendation_window.domain.discovery_tuning import (
    DiscoveryRankingTuning,
)
from internal.recommendation.ranked_recommendation_window.domain.experiment_policy import (
    ExperimentAssignments,
    ExperimentPolicy,
    PolicyVariant,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.mongo_ranker import (
    MongoCandidateRanker,
)

NOW = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)
SUBJECT = "persona-viewer"


def _document(
    content_id: str,
    *,
    author_id: str = "persona-author",
    age_hours: float = 2.0,
    supply_source: str | None = "ugc",
    content_type: str = "article",
) -> dict:
    published_at = datetime.fromtimestamp(
        NOW.timestamp() - age_hours * 3600.0, tz=timezone.utc
    )
    return {
        "contentId": content_id,
        "contentType": content_type,
        "authorId": author_id,
        "tagRefs": [],
        "entityRefs": [],
        "publishedAt": published_at,
        "viewCount": 10,
        "likeCount": 2,
        "commentCount": 1,
        "shareCount": 0,
        "qualityScore": 0.5,
        "premiumEligible": False,
        "intersectionFeatures": {},
        "sourceSequence": 1,
        "supplySource": supply_source,
    }


class _Candidates:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents

    def list_for_ranking(self, *, subject_id: str, scenario: str, limit: int):
        return list(self.documents)

    def list_for_ranking_by_content_ids(
        self, *, scenario: str, content_ids: tuple, limit: int
    ):
        return []

    def list_object_card_candidates(self, *, limit: int):
        return []


class _Features:
    def __init__(self, **overrides) -> None:
        self.overrides = overrides

    def read_for_scoring(self, subject_id: str):
        profile = {
            "checkpoint": 1,
            "sparseFeatures": {},
            "influenceScore": 0.0,
            "collaborativeFeatures": {},
            "intersectionFeatures": {},
            "negativeContentIds": [],
            "hiddenAuthorIds": [],
            "hiddenContentTypes": [],
        }
        profile.update(self.overrides)
        return profile


class _FixedScoring:
    """Deterministic model scorer with a per-content score table."""

    def __init__(self, score_by_id: dict[str, float]) -> None:
        self.score_by_id = score_by_id
        self.requests = []

    def score(self, request):
        self.requests.append(request)
        return ModelScoreResponse(
            scores=[
                CandidateScore(
                    contentId=candidate.contentId,
                    score=self.score_by_id[candidate.contentId],
                )
                for candidate in request.candidates
            ],
            modelReleaseId="release-001",
        )


class _FailingScoring:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def score(self, request):
        raise self.error


class _NoReleaseScoring:
    def score(self, request):
        return ModelScoreResponse(
            scores=[
                CandidateScore(contentId=candidate.contentId, score=0.5)
                for candidate in request.candidates
            ],
            modelReleaseId=None,
        )


def _ranker(
    scoring,
    documents: list[dict],
    *,
    tuning: DiscoveryRankingTuning,
    features: _Features | None = None,
) -> MongoCandidateRanker:
    class _Publisher:
        def publish(self, assignment) -> None:
            pass

    experiments = ExperimentAssignments(_Publisher())
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
        candidates=_Candidates(documents),
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
        tuning=tuning,
        now=lambda: NOW,
    )


def _rank(ranker: MongoCandidateRanker):
    return ranker.rank(
        subject_id=SUBJECT,
        scenario="content_feed",
        session_id="window-tuning",
        limit=300,
    )


def _fallback_count(reason: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "rec_ranked_window_model_score_fallback_total",
            {"reason": reason},
        )
        or 0.0
    )


def test_new_content_boost_promotes_fresh_candidates() -> None:
    documents = [
        _document("post-old", age_hours=48.0),
        _document("post-fresh", age_hours=2.0, author_id="persona-other"),
    ]
    scoring = _FixedScoring({"post-old": 0.6, "post-fresh": 0.5})

    neutral = _rank(_ranker(scoring, documents, tuning=DiscoveryRankingTuning.neutral()))
    assert [item.content_id for item in neutral.candidates] == ["post-old", "post-fresh"]

    boosted = _rank(
        _ranker(
            _FixedScoring({"post-old": 0.6, "post-fresh": 0.5}),
            documents,
            tuning=DiscoveryRankingTuning(
                new_content_boost=1.5,
                author_diversity_weight=1.0,
                whitelist_enabled=False,
            ),
        )
    )
    assert [item.content_id for item in boosted.candidates] == ["post-fresh", "post-old"]
    assert boosted.candidates[0].score == pytest.approx(0.75)
    assert boosted.candidates[1].score == pytest.approx(0.6)


def test_author_diversity_weight_demotes_repeat_authors() -> None:
    documents = [
        _document("post-a1", author_id="persona-a"),
        _document("post-a2", author_id="persona-a"),
        _document("post-b1", author_id="persona-b"),
    ]
    scoring = _FixedScoring({"post-a1": 0.9, "post-a2": 0.8, "post-b1": 0.5})

    result = _rank(
        _ranker(
            scoring,
            documents,
            tuning=DiscoveryRankingTuning(
                new_content_boost=1.0,
                author_diversity_weight=0.5,
                whitelist_enabled=False,
            ),
        )
    )
    # Second post-a item decays to 0.8 * 0.5 = 0.4 and falls behind post-b1.
    assert [item.content_id for item in result.candidates] == [
        "post-a1",
        "post-b1",
        "post-a2",
    ]
    assert [item.score for item in result.candidates] == pytest.approx([0.9, 0.5, 0.4])


def test_whitelist_keeps_canonical_release_supply_only() -> None:
    documents = [
        _document("post-ugc", supply_source="ugc"),
        _document("post-canonical", supply_source="data_engineering"),
    ]
    scoring = _FixedScoring({"post-canonical": 0.7, "post-ugc": 0.9})

    result = _rank(
        _ranker(
            scoring,
            documents,
            tuning=DiscoveryRankingTuning(
                new_content_boost=1.0,
                author_diversity_weight=1.0,
                whitelist_enabled=True,
            ),
        )
    )
    assert [item.content_id for item in result.candidates] == ["post-canonical"]


def test_whitelist_never_bypasses_hard_filters() -> None:
    documents = [
        _document("post-canonical", supply_source="data_engineering"),
    ]
    scoring = _FixedScoring({"post-canonical": 0.7})

    result = _rank(
        _ranker(
            scoring,
            documents,
            tuning=DiscoveryRankingTuning(
                new_content_boost=1.0,
                author_diversity_weight=1.0,
                whitelist_enabled=True,
            ),
            features=_Features(negativeContentIds=["post-canonical"]),
        )
    )
    assert result.candidates == ()


def test_model_bucket_scoring_failure_degrades_to_rule_and_is_observable() -> None:
    documents = [
        _document("post-a", author_id="persona-a"),
        _document("post-b", author_id="persona-b"),
    ]
    before = _fallback_count("RuntimeError")

    result = _rank(
        _ranker(
            _FailingScoring(RuntimeError("model artifact unavailable")),
            documents,
            tuning=DiscoveryRankingTuning.neutral(),
        )
    )

    # Assignment attribution stays intent-to-treat even when the actual scorer
    # degrades to the rule track.
    assert result.experiment_bucket == "model"
    assert result.model_bucket == "rule"
    assert result.model_release_id is None
    assert result.model_channel is None
    assert len(result.candidates) == 2
    assert _fallback_count("RuntimeError") == before + 1


def test_model_bucket_without_active_release_degrades_to_rule() -> None:
    documents = [_document("post-a")]
    before = _fallback_count("RuntimeError")

    result = _rank(
        _ranker(
            _NoReleaseScoring(),
            documents,
            tuning=DiscoveryRankingTuning.neutral(),
        )
    )
    assert result.experiment_bucket == "model"
    assert result.model_bucket == "rule"
    assert result.model_release_id is None
    assert len(result.candidates) == 1
    assert _fallback_count("RuntimeError") == before + 1


def test_empty_candidate_pool_returns_canonical_empty_window() -> None:
    result = _rank(
        _ranker(
            _FixedScoring({}),
            [],
            tuning=DiscoveryRankingTuning.neutral(),
        )
    )
    # exposure-governance REQ-002: filtered-out or empty pools must not be
    # force-refilled; the canonical outcome is an empty, valid window. An empty
    # window never claims a model release, so it is persisted as rule-ranked.
    assert result.candidates == ()
    assert result.model_bucket == "rule"
    assert result.model_release_id is None


def test_whitelist_filtering_everything_returns_empty_window_not_fallback() -> None:
    documents = [_document("post-ugc", supply_source="ugc")]
    result = _rank(
        _ranker(
            _FixedScoring({}),
            documents,
            tuning=DiscoveryRankingTuning(
                new_content_boost=1.0,
                author_diversity_weight=1.0,
                whitelist_enabled=True,
            ),
        )
    )
    assert result.candidates == ()


def test_tuning_validation_fails_fast() -> None:
    with pytest.raises(ValueError):
        DiscoveryRankingTuning(
            new_content_boost=0.0,
            author_diversity_weight=1.0,
            whitelist_enabled=False,
        )
    with pytest.raises(ValueError):
        DiscoveryRankingTuning(
            new_content_boost=1.0,
            author_diversity_weight=1.5,
            whitelist_enabled=False,
        )


def test_tuning_parses_rendered_runtime_config_shape() -> None:
    tuning = DiscoveryRankingTuning.from_runtime_config(
        {
            "ops": {
                "reco": {
                    "discovery": {
                        "prerank": {"new_content_boost": 1.08},
                        "rank": {"author_diversity_weight": 0.42},
                        "recall": {"whitelist_enabled": False},
                    }
                }
            }
        }
    )
    assert tuning.new_content_boost == pytest.approx(1.08)
    assert tuning.author_diversity_weight == pytest.approx(0.42)
    assert tuning.whitelist_enabled is False


def test_tuning_missing_tree_fails_fast() -> None:
    with pytest.raises(RuntimeError):
        DiscoveryRankingTuning.from_runtime_config({"ops": {}})


def test_snapshot_records_tuning_and_fallback_attribution() -> None:
    documents = [_document("post-a")]
    result = _rank(
        _ranker(
            _FailingScoring(RuntimeError("model artifact unavailable")),
            documents,
            tuning=DiscoveryRankingTuning(
                new_content_boost=1.08,
                author_diversity_weight=0.42,
                whitelist_enabled=False,
            ),
        )
    )
    # The digest is bound to a snapshot that carries the assigned bucket, the
    # fallback reason and the tuning values; consumers can audit the window.
    assert result.model_bucket == "rule"
    assert len(result.ranking_snapshot_digest) == 64
