from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Callable, Mapping, Protocol

from generated.recommendation.recommendation_model_release.models.request_response import (
    CandidateInput,
    ModelScoreRequest,
    ModelScoreResponse,
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


class CandidateReader(Protocol):
    def list_for_ranking(
        self,
        *,
        subject_id: str,
        scenario: str,
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
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._candidates = candidates
        self._feature_profiles = feature_profiles
        self._scoring = scoring
        self._experiments = experiments
        self._snapshot_digester = snapshot_digester
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
            recallPath="premium_pool" if document.get("premiumEligible") else "explore_recall",
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
        if assignment.bucket == "model":
            response = (
                self._scoring.score(request)
                if candidates
                else ModelScoreResponse(scores=[], modelReleaseId=None)
            )
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
        else:
            scores = {
                str(candidate.contentId): rule_score(
                    candidate.model_dump(mode="python")
                )[0]
                for candidate in candidates
            }
        if set(scores) != set(candidate_ids):
            raise RuntimeError("model scoring result does not match the candidate snapshot")
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        model_bucket = assignment.bucket
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
            "modelChannel": model_channel,
            "modelReleaseId": model_release_id,
            "experimentId": assignment.experiment_id,
            "experimentRevision": assignment.experiment_revision,
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
