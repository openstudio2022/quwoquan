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
    ClientContentPresentationContract,
    post_envelope,
    homepage_envelope,
    envelope_identity,
    supports_presentation,
    validate_presentation_contract,
    RankedCandidate,
    RankingResult,
    ReleasePinnedQueryFence,
    RecommendationRequestContext,
    validate_content_fence,
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
        eligible_content_types: tuple[str, ...],
    ) -> list[dict[str, Any]]: ...

    def list_for_ranking_by_content_ids(
        self,
        *,
        scenario: str,
        content_ids: tuple[str, ...],
        limit: int,
        eligible_content_types: tuple[str, ...],
    ) -> list[dict[str, Any]]: ...

    def list_homepage_candidates(self, *, limit: int) -> list[dict[str, Any]]: ...

    def list_release_for_ranking(
        self, fence: ReleasePinnedQueryFence, *, scenario: str, subject_id: str,
        limit: int, eligible_content_types: tuple[str, ...],
    ) -> list[dict[str, Any]]: ...


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
        content_fence: ReleasePinnedQueryFence,
        client_presentation_contract: ClientContentPresentationContract,
        request_context: RecommendationRequestContext,
    ) -> RankingResult:
        content_fence = validate_content_fence(content_fence)
        contract = validate_presentation_contract(client_presentation_contract)
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
        eligible_content_types = self._eligible_post_types(contract)
        profile = self._feature_profiles.read_for_scoring(subject_id.strip())
        behavior_count = self._behavior_count(profile)
        cold_start = behavior_count <= self._tuning.cold_start_max_behavior_count
        if content_fence.release is not None:
            documents = self._candidates.list_release_for_ranking(content_fence, subject_id=subject_id.strip(), scenario=normalized_scenario, limit=limit, eligible_content_types=eligible_content_types)
        else:
            documents = self._candidates.list_for_ranking(subject_id=subject_id.strip(), scenario=normalized_scenario, limit=limit, eligible_content_types=eligible_content_types)
            documents = self._merge_collaborative_lane(documents, profile=profile, scenario=normalized_scenario, limit=limit, eligible_content_types=eligible_content_types)
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
        documents = self._supported_documents(documents, contract)
        homepage_candidates = self._homepage_candidates(profile, contract)
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
                "viewportProfile": request_context.viewport_profile,
                "deviceClass": request_context.device_class,
                "coarseRegion": request_context.coarse_region,
                "timeBucket": request_context.time_bucket,
                "coldStart": cold_start,
                "behaviorCount": behavior_count,
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
        if cold_start:
            scores = self._apply_quality_prior(scores, candidates)
        scores = self._apply_new_content_boost(scores, candidates)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        ranked = self._apply_author_diversity(ranked, candidates)
        model_bucket = applied_bucket
        model_channel = "champion" if model_release_id else None
        ranked_candidates = tuple(
            RankedCandidate(
                envelope=post_envelope(content_id, item_snapshots[content_id]["contentType"]),
                score=score,
                feature_snapshot_digest=self._snapshot_digester(
                    user_snapshot,
                    item_snapshots[content_id],
                ),
                item_feature_snapshot=item_snapshots[content_id],
            )
            for content_id, score in ranked
        )
        ranked_candidates = tuple(sorted(
            (*ranked_candidates, *homepage_candidates),
            key=lambda candidate: (-candidate.score, envelope_identity(candidate.envelope)),
        )[:limit])
        ranking_snapshot = {
            "clientPresentationContract": contract.model_dump(mode="json"),
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
            "requestContext": request_context.canonical_document(),
            "coldStart": {
                "active": cold_start,
                "behaviorCount": behavior_count,
                "maximumBehaviorCount": self._tuning.cold_start_max_behavior_count,
            },
            "ranked": [
                {
                    "envelope": candidate.envelope.model_dump(mode="json"),
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
            experiment_bucket=assignment.bucket,
            model_bucket=model_bucket,
            model_channel=model_channel,
            model_release_id=model_release_id,
            policy_digest=assignment.policy_digest,
            feature_snapshot_at=now,
            ranking_snapshot_digest=ranking_snapshot_digest,
            user_feature_snapshot=user_snapshot,
            candidates=ranked_candidates,
            profile_revision=(
                str(profile["checkpoint"])
                if "checkpoint" in profile and isinstance(profile["checkpoint"], int)
                and not isinstance(profile["checkpoint"], bool) and profile["checkpoint"] >= 0
                else "unknown"
            ),
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
        eligible_content_types: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        if any((scenario != "content_feed", len(documents) >= limit)):
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
            eligible_content_types=eligible_content_types,
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

    @staticmethod
    def _behavior_count(profile: Mapping[str, Any]) -> int:
        sparse = profile.get("sparseFeatures") or {}
        if not isinstance(sparse, Mapping):
            raise RuntimeError("feature profile sparseFeatures must be a mapping")
        total = 0.0
        for key, value in sparse.items():
            if not str(key).startswith(("action:", "state:")):
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) < 0:
                raise RuntimeError("feature profile behavior count is invalid")
            total += float(value)
        return int(total)

    @staticmethod
    def _apply_quality_prior(
        scores: dict[str, float],
        candidates: list[CandidateInput],
    ) -> dict[str, float]:
        quality_by_content = {
            str(candidate.contentId): float(candidate.qualityScore or 0.0)
            for candidate in candidates
        }
        return {
            content_id: score + quality_by_content[content_id]
            for content_id, score in scores.items()
        }

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

    @staticmethod
    def _eligible_post_types(contract):
        return tuple(
            content_type for content_type in contract.contentTypes
            if supports_presentation(contract, post_envelope("admission", content_type))
        )

    @staticmethod
    def _supported_documents(documents, contract):
        supported = []
        for document in documents:
            envelope = post_envelope(
                str(document.get("contentId") or "").strip(),
                str(document.get("contentType") or "").strip(),
            )
            if supports_presentation(contract, envelope):
                supported.append(document)
        return supported

    @staticmethod
    def _entity_affinities(profile):
        return {
            key.removeprefix("entity:"): float(value)
            for key, value in (profile.get("sparseFeatures") or {}).items()
            if key.startswith("entity:") and key.removeprefix("entity:").strip()
            and isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) > 0
        }

    def _homepage_candidates(
        self, profile: Mapping[str, Any], contract: ClientContentPresentationContract,
    ) -> tuple[RankedCandidate, ...]:
        if not supports_presentation(contract, homepage_envelope("admission")):
            return ()
        sparse = dict(profile.get("sparseFeatures") or {})
        affinities = self._entity_affinities(profile)
        selected: dict[str, RankedCandidate] = {}
        for document in self._candidates.list_homepage_candidates(limit=400):
            # 窄 reader 只产出主页；污染/未来未知对象逐项隔离，不中断合法候选。
            if document.get("objectKind") != "entity_homepage":
                continue
            snapshot = document.get("primaryHomepageSnapshot")
            if not isinstance(snapshot, Mapping):
                continue
            homepage_id = str(document.get("primaryHomepageId") or snapshot.get("homepageId") or "").strip()
            entity_id = str(snapshot.get("canonicalEntityId") or "").strip()
            score = affinities.get(entity_id, 0.0)
            if not all((homepage_id, entity_id, str(snapshot.get("title") or "").strip(), score > 0)):
                continue
            envelope = homepage_envelope(homepage_id)
            if not supports_presentation(contract, envelope):
                continue
            item_snapshot = {
                "homepageSnapshot": dict(snapshot), "reasonKey": "affinity",
                "recallPath": "entity_card_affinity",
            }
            candidate = RankedCandidate(
                envelope=envelope, score=score,
                feature_snapshot_digest=self._snapshot_digester(sparse, item_snapshot),
                item_feature_snapshot=item_snapshot,
            )
            previous = selected.get(homepage_id)
            if previous is None or score > previous.score:
                selected[homepage_id] = candidate
        return tuple(sorted(selected.values(), key=lambda item: (-item.score, item.envelope.homepage.homepageId))[:20])
