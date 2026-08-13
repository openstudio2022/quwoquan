from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Callable, Mapping, Protocol

from prometheus_client import Counter

from generated.recommendation.recommendation_model_release.models.request_response import (
    CandidateInput,
    ModelScoreRequest,
    ModelScoreResponse,
)
from internal.recommendation.ranked_recommendation_window.domain.discovery_tuning import (
    DiscoveryRankingTuning,
    NEW_CONTENT_BOOST_MAX_AGE_HOURS,
    WHITELIST_SUPPLY_SOURCE,
)
from internal.recommendation.ranked_recommendation_window.domain.model import (
    RecommendationObjectCard,
    RankedCandidate,
    RankingResult,
)
from internal.recommendation.ranked_recommendation_window.domain.experiment_policy import (
    ExperimentAssignments,
)
from internal.recommendation.recommendation_model_release.application.rule_scoring import (
    rule_score,
)

# Model-bucket scoring failures degrade to the deterministic rule scorer
# instead of failing the window request (same semantics as the content-side
# CascadeScorer, see rec-model-service/go-integration REQ-002). The fallback
# is observable so AB evaluation can exclude or separately bucket the sample.
model_score_fallback_total = Counter(
    "rec_ranked_window_model_score_fallback_total",
    "Model-bucket scoring failures degraded to the deterministic rule scorer.",
    ["reason"],
)


class CandidateReader(Protocol):
    def list_for_ranking(
        self,
        *,
        subject_id: str,
        scenario: str,
        limit: int,
    ) -> list[dict[str, Any]]: ...

    def list_for_ranking_by_content_ids(
        self,
        *,
        scenario: str,
        content_ids: tuple[str, ...],
        limit: int,
    ) -> list[dict[str, Any]]: ...

    def list_object_card_candidates(self, *, limit: int) -> list[dict[str, Any]]: ...


class FeatureProfileReader(Protocol):
    def read_for_scoring(self, subject_id: str) -> dict[str, Any]: ...


class ScoringFacade(Protocol):
    def score(self, request: ModelScoreRequest) -> ModelScoreResponse: ...


class MongoCandidateRanker:
    """Ranks the object-owned candidate projection through the active model facade."""

    def __init__(
        self,
        *,
        candidates: CandidateReader,
        feature_profiles: FeatureProfileReader,
        scoring: ScoringFacade,
        experiments: ExperimentAssignments,
        snapshot_digester: Callable[[Mapping[str, Any], Mapping[str, Any]], str],
        tuning: DiscoveryRankingTuning,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._candidates = candidates
        self._feature_profiles = feature_profiles
        self._scoring = scoring
        self._experiments = experiments
        self._snapshot_digester = snapshot_digester
        self._tuning = tuning
        self._now = now or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _candidate(document: dict[str, Any], now: datetime) -> CandidateInput:
        published_at = document.get("publishedAt")
        if not isinstance(published_at, datetime) or published_at.tzinfo is None:
            raise RuntimeError("candidate projection publishedAt must be timezone-aware")
        intersection = dict(document.get("intersectionFeatures") or {})
        published_utc = published_at.astimezone(timezone.utc)
        age_hours = max(
            (now - published_utc).total_seconds() / 3600.0,
            0.0,
        )
        recall_path = str(document.get("recallPath") or "").strip() or (
            "premium_pool" if document.get("premiumEligible") else "explore_recall"
        )
        return CandidateInput(
            contentId=str(document.get("contentId") or "").strip(),
            contentType=str(document.get("contentType") or "").strip(),
            authorId=str(document.get("authorId") or "").strip(),
            tagRefs=list(document.get("tagRefs") or []),
            entityRefs=list(document.get("entityRefs") or []),
            ageHours=age_hours,
            publishHour=published_utc.hour,
            viewCount=int(document.get("viewCount") or 0),
            likeCount=int(document.get("likeCount") or 0),
            commentCount=int(document.get("commentCount") or 0),
            shareCount=int(document.get("shareCount") or 0),
            recallPath=recall_path,
            qualityScore=float(document.get("qualityScore") or 0.0),
            contentVertical=document.get("contentVertical"),
            supplySource=document.get("supplySource"),
            intersectionEdgeWeight=intersection.get("intersectionEdgeWeight"),
            intersectionEdgeFreshness=intersection.get("intersectionEdgeFreshness"),
            intersectionEdgeKind=intersection.get("intersectionEdgeKind"),
            intersectionFactStrength=intersection.get("intersectionFactStrength"),
            intersectionFreshness=intersection.get("intersectionFreshness"),
            affinityIntersectionScore=intersection.get("affinityIntersectionScore"),
            intersectionSourceRefTop=intersection.get("intersectionSourceRefTop"),
            intersectionConfidenceLabel=intersection.get("intersectionConfidenceLabel"),
            intersectionClass=intersection.get("intersectionClass"),
        )

    def rank(
        self,
        *,
        subject_id: str,
        scenario: str,
        session_id: str,
        limit: int,
    ) -> RankingResult:
        now = self._now().astimezone(timezone.utc)
        # RankedWindowSubjectID uses '\x00' as an internal namespace separator.
        # ExperimentAssignmentObserved crosses into Product Ops Postgres text
        # columns, so bucketing/publish must use a wire-safe subject identity.
        assignment = self._experiments.assign(
            subject_id.replace("\x00", ":"),
            now=now,
        )
        normalized_scenario = scenario.strip()
        if normalized_scenario not in {
            "content_feed",
            "following",
            "premium_stream",
            "travel_photography",
        }:
            raise ValueError("unsupported recommendation ranking scenario")
        profile = self._feature_profiles.read_for_scoring(subject_id.strip())
        documents = self._candidates.list_for_ranking(
            subject_id=subject_id.strip(),
            scenario=normalized_scenario,
            limit=limit,
        )
        documents = self._merge_collaborative_lane(
            documents,
            profile=profile,
            scenario=normalized_scenario,
            limit=limit,
        )
        negative_content_ids = {
            str(value).strip()
            for value in profile.get("negativeContentIds") or []
            if str(value).strip()
        }
        hidden_author_ids = {
            str(value).strip()
            for value in profile.get("hiddenAuthorIds") or []
            if str(value).strip()
        }
        hidden_content_types = {
            str(value).strip()
            for value in profile.get("hiddenContentTypes") or []
            if str(value).strip()
        }
        if self._tuning.whitelist_enabled:
            # Ops safety switch: only canonical-release supply stays eligible.
            # It narrows recall and never bypasses the hard filters below.
            documents = [
                document
                for document in documents
                if str(document.get("supplySource") or "").strip()
                == WHITELIST_SUPPLY_SOURCE
            ]
        documents = [
            document
            for document in documents
            if str(document.get("contentId") or "").strip()
            not in negative_content_ids
            and str(document.get("authorId") or "").strip()
            not in hidden_author_ids
            and str(document.get("contentType") or "").strip()
            not in hidden_content_types
        ]
        object_cards = self._object_cards(profile)
        candidates = [self._candidate(document, now) for document in documents]
        candidate_ids = [str(candidate.contentId or "").strip() for candidate in candidates]
        if any(not content_id for content_id in candidate_ids) or len(set(candidate_ids)) != len(candidate_ids):
            raise RuntimeError("candidate projection returned empty or duplicate contentId")

        user_features = dict(profile.get("sparseFeatures") or {})
        user_features.update(
            {
                "influenceScore": float(profile.get("influenceScore") or 0.0),
                "collaborativeFeatures": dict(profile.get("collaborativeFeatures") or {}),
                "intersectionFeatures": dict(profile.get("intersectionFeatures") or {}),
                "searchTermAffinities": dict(profile.get("searchTermAffinities") or {}),
            }
        )
        request = ModelScoreRequest(
            # All three delivery audiences share the one content-feed model
            # contract. Audience selection belongs to CandidateIndex; model
            # release identity therefore remains canonical content_feed.
            scenario="content_feed",
            userId=subject_id.strip(),
            sessionId=session_id.strip(),
            modelChannel="champion",
            userFeatures=user_features,
            sessionSignals={},
            candidates=candidates,
            context={
                "requestHour": now.hour,
                "requestDayOfWeek": now.weekday(),
            },
        )
        user_snapshot = dict(request.userFeatures or {})
        item_snapshots = {
            str(candidate.contentId): candidate.model_dump(mode="json")
            for candidate in candidates
        }
        scores: dict[str, float] = {}
        model_release_id: str | None = None
        applied_bucket = assignment.bucket
        model_score_fallback_reason: str | None = None
        if assignment.bucket == "model":
            if not candidates:
                # No scorer ran; an empty window must not claim a model release
                # (the window invariant requires model windows to carry one).
                applied_bucket = "rule"
            else:
                try:
                    scores, model_release_id = self._model_scores(request, candidates)
                except Exception as error:  # noqa: BLE001 - degrade, observe, never fail the window
                    model_score_fallback_reason = type(error).__name__
                    model_score_fallback_total.labels(
                        reason=model_score_fallback_reason
                    ).inc()
                    applied_bucket = "rule"
                    model_release_id = None
                    scores = {}
        if applied_bucket == "rule":
            scores = {
                str(candidate.contentId): rule_score(
                    candidate.model_dump(mode="python")
                )[0]
                for candidate in candidates
            }
        if set(scores) != set(candidate_ids):
            raise RuntimeError("model scoring result does not match the candidate snapshot")
        scores = self._apply_new_content_boost(scores, candidates)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        ranked = self._apply_author_diversity(ranked, candidates)
        model_bucket = applied_bucket
        model_channel = "champion" if model_release_id else None
        ranked_candidates = tuple(
            RankedCandidate(
                content_id=content_id,
                score=score,
                feature_snapshot_digest=self._snapshot_digester(
                    user_snapshot,
                    item_snapshots[content_id],
                ),
                item_feature_snapshot=item_snapshots[content_id],
            )
            for content_id, score in ranked
        )
        ranking_snapshot = {
            "candidateSequences": [
                int(document.get("sourceSequence") or 0) for document in documents
            ],
            "featureSnapshotAt": now.isoformat(),
            "modelBucket": model_bucket,
            "assignedBucket": assignment.bucket,
            "modelScoreFallbackReason": model_score_fallback_reason,
            "modelChannel": model_channel,
            "modelReleaseId": model_release_id,
            "experimentId": assignment.experiment_id,
            "experimentRevision": assignment.experiment_revision,
            "discoveryTuning": {
                "newContentBoost": self._tuning.new_content_boost,
                "authorDiversityWeight": self._tuning.author_diversity_weight,
                "whitelistEnabled": self._tuning.whitelist_enabled,
            },
            "profileCheckpoint": int(profile.get("checkpoint") or 0),
            "ranked": [
                {
                    "contentId": candidate.content_id,
                    "featureSnapshotDigest": candidate.feature_snapshot_digest,
                    "score": candidate.score,
                }
                for candidate in ranked_candidates
            ],
            "request": request.model_dump(mode="json"),
        }
        ranking_snapshot_digest = hashlib.sha256(
            json.dumps(
                ranking_snapshot,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return RankingResult(
            model_bucket=model_bucket,
            model_channel=model_channel,
            model_release_id=model_release_id,
            policy_digest=assignment.policy_digest,
            feature_snapshot_at=now,
            ranking_snapshot_digest=ranking_snapshot_digest,
            user_feature_snapshot=user_snapshot,
            candidates=ranked_candidates,
            object_cards=object_cards,
        )

    # 协同召回路的点查上限：collaborativeFeatures 是离线物化的 per-subject
    # 相似内容分数，取分数最高的前 N 个做候选池点查（全部走 Mongo 索引）。
    COLLABORATIVE_RECALL_LIMIT = 50

    def _merge_collaborative_lane(
        self,
        documents: list[dict[str, Any]],
        *,
        profile: Mapping[str, Any],
        scenario: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if scenario != "content_feed":
            return documents
        collaborative = {
            str(key).strip(): float(value)
            for key, value in (profile.get("collaborativeFeatures") or {}).items()
            if str(key).strip()
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            and float(value) > 0
        }
        if not collaborative:
            return documents
        seen = {
            str(document.get("contentId") or "").strip() for document in documents
        }
        wanted = tuple(
            content_id
            for content_id, _score in sorted(
                collaborative.items(), key=lambda item: (-item[1], item[0])
            )
            if content_id not in seen
        )[: self.COLLABORATIVE_RECALL_LIMIT]
        if not wanted:
            return documents
        extra = self._candidates.list_for_ranking_by_content_ids(
            scenario=scenario,
            content_ids=wanted,
            limit=self.COLLABORATIVE_RECALL_LIMIT,
        )
        merged = list(documents)
        for document in extra:
            content_id = str(document.get("contentId") or "").strip()
            if not content_id or content_id in seen:
                continue
            seen.add(content_id)
            merged.append(document)
            if len(merged) >= limit:
                break
        return merged

    def _model_scores(
        self,
        request: ModelScoreRequest,
        candidates: list[CandidateInput],
    ) -> tuple[dict[str, float], str | None]:
        response = self._scoring.score(request)
        scores: dict[str, float] = {}
        for item in response.scores:
            content_id = str(item.contentId or "").strip()
            if (
                not content_id
                or item.score is None
                or not math.isfinite(float(item.score))
                or content_id in scores
            ):
                raise RuntimeError("model scoring returned invalid or duplicate candidate score")
            scores[content_id] = float(item.score)
        model_release_id = (
            str(response.modelReleaseId).strip() if response.modelReleaseId else None
        )
        if candidates and not model_release_id:
            raise RuntimeError("model experiment bucket requires an active model release")
        return scores, model_release_id

    def _apply_new_content_boost(
        self,
        scores: dict[str, float],
        candidates: list[CandidateInput],
    ) -> dict[str, float]:
        boost = self._tuning.new_content_boost
        if boost == 1.0:
            return scores
        fresh_ids = {
            str(candidate.contentId)
            for candidate in candidates
            if float(candidate.ageHours or 0.0) <= NEW_CONTENT_BOOST_MAX_AGE_HOURS
        }
        return {
            content_id: score * boost if content_id in fresh_ids else score
            for content_id, score in scores.items()
        }

    def _apply_author_diversity(
        self,
        ranked: list[tuple[str, float]],
        candidates: list[CandidateInput],
    ) -> list[tuple[str, float]]:
        weight = self._tuning.author_diversity_weight
        if weight == 1.0:
            return ranked
        author_by_content = {
            str(candidate.contentId): str(candidate.authorId or "").strip()
            for candidate in candidates
        }
        seen_by_author: dict[str, int] = {}
        adjusted: list[tuple[str, float]] = []
        for content_id, score in ranked:
            author = author_by_content.get(content_id, "")
            occurrence = seen_by_author.get(author, 0) if author else 0
            if author:
                seen_by_author[author] = occurrence + 1
            adjusted.append((content_id, score * (weight**occurrence)))
        return sorted(adjusted, key=lambda item: (-item[1], item[0]))

    def _object_cards(
        self,
        profile: Mapping[str, Any],
    ) -> tuple[RecommendationObjectCard, ...]:
        sparse = dict(profile.get("sparseFeatures") or {})
        affinities = {
            key.removeprefix("entity:"): float(value)
            for key, value in sparse.items()
            if key.startswith("entity:")
            and key.removeprefix("entity:").strip()
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            and float(value) > 0
        }
        selected: dict[tuple[str, str], tuple[float, RecommendationObjectCard]] = {}
        for ordinal, document in enumerate(
            self._candidates.list_object_card_candidates(limit=400)
        ):
            object_kind = str(document.get("objectKind") or "").strip()
            if object_kind == "gathering":
                gathering_id = str(document.get("sourceKey") or "").strip()
                title = str(document.get("title") or "").strip()
                card_digest = str(document.get("cardDigest") or "").strip()
                source_version = int(document.get("sourceVersion") or 0)
                if (
                    not gathering_id
                    or not title
                    or source_version <= 0
                    or len(card_digest) != 64
                ):
                    continue
                tags = tuple(
                    dict.fromkeys(
                        str(tag).strip()
                        for tag in document.get("tagRefs") or []
                        if str(tag).strip()
                    )
                )
                gathering_card = RecommendationObjectCard(
                    object_kind="gathering",
                    object_id=gathering_id,
                    title=title,
                    subtitle=(
                        str(document.get("summary") or "").strip() or None
                    ),
                    # Circle signs a canonical cover reference. Recommendation
                    # must not turn that reference into a fabricated media URL.
                    cover_url=None,
                    tag_refs=tags,
                    reason_key="public_gathering",
                    recall_path="gathering_candidate_index",
                )
                selected[("gathering", gathering_id)] = (
                    0.25 / float(ordinal + 1),
                    gathering_card,
                )
                continue
            snapshot = document.get("primaryHomepageSnapshot")
            if not isinstance(snapshot, Mapping):
                continue
            homepage_id = str(
                document.get("primaryHomepageId") or snapshot.get("homepageId") or ""
            ).strip()
            entity_id = str(snapshot.get("canonicalEntityId") or "").strip()
            title = str(snapshot.get("title") or "").strip()
            score = affinities.get(entity_id, 0.0)
            if not homepage_id or not entity_id or not title or score <= 0:
                continue
            tags = tuple(
                dict.fromkeys(
                    str(tag).strip()
                    for tag in snapshot.get("tagRefs") or []
                    if str(tag).strip()
                )
            )
            card = RecommendationObjectCard(
                object_kind="entity_homepage",
                object_id=homepage_id,
                title=title,
                subtitle=(str(snapshot.get("subtitle") or "").strip() or None),
                cover_url=(str(snapshot.get("coverUrl") or "").strip() or None),
                tag_refs=tags,
                reason_key="affinity",
                recall_path="entity_card_affinity",
            )
            identity = ("entity_homepage", homepage_id)
            previous = selected.get(identity)
            if previous is None or score > previous[0]:
                selected[identity] = (score, card)
        return tuple(
            card
            for _, card in sorted(
                selected.values(),
                key=lambda item: (-item[0], item[1].object_id),
            )[:20]
        )
