from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from generated.recommendation.ranked_recommendation_window.models.client_presentation_contract import (
    validate_client_content_presentation_contract,
)
import hashlib
import json
import math
from typing import Any, Mapping

from generated.recommendation.ranked_recommendation_window.models.request_response import (
    ClientContentPresentationContract,
    ListItemHomepageRef,
    ListItemPostRef,
    ListItemPresentationEnvelope,
    ReleasePinnedQueryFence,
)


def validate_content_fence(fence: ReleasePinnedQueryFence) -> ReleasePinnedQueryFence:
    if not isinstance(fence, ReleasePinnedQueryFence):
        raise ValueError("typed Content fence is required")
    if fence.release is None:
        if fence.revision != 0:
            raise ValueError("empty Content fence must have zero revision")
    else:
        release = fence.release
        if (fence.revision <= 0 or release.environment not in {"alpha", "beta", "gamma", "prod"}
                or release.sourceOwner != "qwq_data" or not release.releaseId.strip()
                or len(release.manifestDigest) != 71 or not release.manifestDigest.startswith("sha256:")
                or any(c not in "0123456789abcdef" for c in release.manifestDigest[7:])):
            raise ValueError("Content fence identity is invalid")
    return fence.model_copy(deep=True)


def validate_presentation_contract(
    contract: ClientContentPresentationContract,
) -> ClientContentPresentationContract:
    """由生成助手唯一拥有闭集、canonical 编码与摘要校验。"""
    if not isinstance(contract, ClientContentPresentationContract):
        raise ValueError("typed client presentation contract is required")
    normalized = validate_client_content_presentation_contract(contract.model_dump(mode="json"))
    return ClientContentPresentationContract.model_validate(normalized)


def validate_envelope(envelope: ListItemPresentationEnvelope) -> ListItemPresentationEnvelope:
    if not isinstance(envelope, ListItemPresentationEnvelope):
        raise ValueError("typed presentation envelope is required")
    envelope = ListItemPresentationEnvelope.model_validate(envelope.model_dump(mode="json"))
    if envelope.objectKind == "post":
        if envelope.post is None or envelope.homepage is not None or envelope.contentType is None:
            raise ValueError("post envelope requires only a post reference and contentType")
        identity = envelope.post.postId
    elif envelope.objectKind == "entity_homepage":
        if envelope.homepage is None or envelope.post is not None or envelope.contentType is not None:
            raise ValueError("homepage envelope requires only a homepage reference")
        identity = envelope.homepage.homepageId
    else:
        raise ValueError("unsupported presentation object kind")
    if not identity.strip() or identity != identity.strip():
        raise ValueError("presentation identity must be canonical")
    return envelope


def supports_presentation(
    contract: ClientContentPresentationContract, envelope: ListItemPresentationEnvelope,
) -> bool:
    return (
        envelope.objectKind in contract.listObjectKinds
        and (envelope.contentType is None or envelope.contentType in contract.contentTypes)
        and (envelope.presentationRecipe is None or envelope.presentationRecipe in contract.presentationRecipes)
        and envelope.openSurface in contract.openSurfaces
    )


def post_envelope(post_id: str, content_type: str) -> ListItemPresentationEnvelope:
    # 赋值属于推荐 writer；生成模型负责值域，不从媒体附件嗅探卡型。
    if content_type == "article":
        recipe, surface = "article_excerpt_card", "article_reader"
    elif content_type == "image" or content_type == "video":
        recipe, surface = "cover_media_card", "media_immersive"
    else:
        raise ValueError("candidate contentType has no presentation assignment")
    return validate_envelope(ListItemPresentationEnvelope(
        objectKind="post", contentType=content_type, presentationRecipe=recipe,
        openSurface=surface, post=ListItemPostRef(postId=post_id),
    ))


def homepage_envelope(homepage_id: str) -> ListItemPresentationEnvelope:
    return validate_envelope(ListItemPresentationEnvelope(
        objectKind="entity_homepage", presentationRecipe="homepage_summary_card",
        openSurface="homepage_detail", homepage=ListItemHomepageRef(homepageId=homepage_id),
    ))


def envelope_identity(envelope: ListItemPresentationEnvelope) -> tuple[str, str]:
    reference = envelope.post.postId if envelope.post is not None else envelope.homepage.homepageId
    return envelope.objectKind, reference


WINDOW_TTL = timedelta(minutes=10)
MAX_WINDOW_ITEMS = 300


@dataclass(frozen=True, slots=True)
class RankedRecommendationItem:
    ordinal: int
    envelope: ListItemPresentationEnvelope
    score: float
    feature_snapshot_digest: str
    item_feature_snapshot: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    envelope: ListItemPresentationEnvelope
    score: float
    feature_snapshot_digest: str
    item_feature_snapshot: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RecommendationRequestContext:
    viewport_profile: str
    device_class: str
    coarse_region: str
    time_bucket: str
    profile_revision: str

    def canonical_document(self) -> dict[str, str]:
        return {
            "coarseRegion": self.coarse_region,
            "deviceClass": self.device_class,
            "profileRevision": self.profile_revision,
            "timeBucket": self.time_bucket,
            "viewportProfile": self.viewport_profile,
        }


@dataclass(frozen=True, slots=True)
class RankingResult:
    experiment_bucket: str
    model_bucket: str
    model_channel: str | None
    model_release_id: str | None
    policy_digest: str
    feature_snapshot_at: datetime
    ranking_snapshot_digest: str
    user_feature_snapshot: Mapping[str, Any]
    candidates: tuple[RankedCandidate, ...]
    profile_revision: str = "unknown"


@dataclass(frozen=True, slots=True)
class RankedRecommendationWindow:
    content_fence: ReleasePinnedQueryFence
    client_presentation_contract: ClientContentPresentationContract
    window_id: str
    subject_id: str
    scenario: str
    experiment_bucket: str
    model_bucket: str
    model_channel: str | None
    model_release_id: str | None
    policy_digest: str
    request_context: RecommendationRequestContext
    context_digest: str
    request_digest: str
    ranking_snapshot_digest: str
    feature_snapshot_at: datetime
    user_feature_snapshot: Mapping[str, Any]
    items: tuple[RankedRecommendationItem, ...]
    created_at: datetime
    expires_at: datetime

    @classmethod
    def create(
        cls,
        *,
        window_id: str,
        subject_id: str,
        scenario: str,
        request_digest: str,
        request_context: RecommendationRequestContext,
        context_digest: str,
        ranking: RankingResult,
        content_fence: ReleasePinnedQueryFence,
        client_presentation_contract: ClientContentPresentationContract,
        now: datetime | None = None,
    ) -> "RankedRecommendationWindow":
        created_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        contract = validate_presentation_contract(client_presentation_contract)
        normalized_subject = subject_id.strip()
        normalized_scenario = scenario.strip()
        if not all(
            value.strip()
            for value in (
                window_id,
                normalized_subject,
                normalized_scenario,
                ranking.experiment_bucket,
                request_digest,
                ranking.model_bucket,
                ranking.policy_digest,
                context_digest,
                ranking.ranking_snapshot_digest,
            )
        ):
            raise ValueError("windowId, subjectId, scenario and ranking snapshot digests are required")
        if request_context.coarse_region != "unknown":
            raise ValueError("coarseRegion must be unknown")
        if len(request_context.time_bucket) != 3 or request_context.time_bucket[0] != "h" or not request_context.time_bucket[1:].isdigit() or int(request_context.time_bucket[1:]) > 23:
            raise ValueError("timeBucket is invalid")
        revision = request_context.profile_revision
        if revision != "unknown" and revision != "0" and (not revision.isdigit() or revision.startswith("0")):
            raise ValueError("profileRevision is invalid")
        if request_context.viewport_profile not in {"landscape", "portrait", "unknown"}:
            raise ValueError("viewportProfile is invalid")
        if request_context.device_class not in {"phone", "tablet", "desktop", "unknown"}:
            raise ValueError("deviceClass is invalid")
        canonical_context_digest = hashlib.sha256(json.dumps(
            request_context.canonical_document(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")).hexdigest()
        if context_digest != canonical_context_digest:
            raise ValueError("contextDigest does not match canonical requestContext")
        if ranking.feature_snapshot_at.tzinfo is None:
            raise ValueError("featureSnapshotAt must be timezone-aware")
        if ranking.feature_snapshot_at.astimezone(timezone.utc) > created_at:
            raise ValueError("featureSnapshotAt cannot be later than window creation")
        bucket, experiment = ranking.model_bucket.strip(), ranking.experiment_bucket.strip()
        if bucket not in {"model", "rule"} or experiment not in {"model", "rule"}:
            raise ValueError("ranking buckets must be model or rule")
        if bucket == "model" and (not ranking.model_channel or not ranking.model_release_id):
            raise ValueError("model ranking requires modelChannel and modelReleaseId")
        if bucket == "rule" and (ranking.model_channel is not None or ranking.model_release_id is not None):
            raise ValueError("rule ranking cannot claim a model channel or release")
        if len(ranking.candidates) > MAX_WINDOW_ITEMS:
            raise ValueError("ranked window must contain at most 300 items")
        seen: set[tuple[str, str]] = set()
        items: list[RankedRecommendationItem] = []
        for candidate in ranking.candidates:
            envelope = validate_envelope(candidate.envelope)
            identity = envelope_identity(envelope)
            if identity in seen or not math.isfinite(float(candidate.score)) or not candidate.feature_snapshot_digest.strip():
                raise ValueError("ranked window candidate snapshot is invalid")
            seen.add(identity)
            if not supports_presentation(contract, envelope):
                continue
            items.append(RankedRecommendationItem(
                ordinal=len(items), envelope=envelope, score=float(candidate.score),
                feature_snapshot_digest=candidate.feature_snapshot_digest.strip(),
                item_feature_snapshot=dict(candidate.item_feature_snapshot),
            ))
        return cls(
            content_fence=validate_content_fence(content_fence), client_presentation_contract=contract,
            window_id=window_id.strip(), subject_id=normalized_subject, scenario=normalized_scenario,
            experiment_bucket=experiment, model_bucket=bucket,
            model_channel=ranking.model_channel.strip() if ranking.model_channel else None,
            model_release_id=ranking.model_release_id.strip() if ranking.model_release_id else None,
            policy_digest=ranking.policy_digest.strip(),
            request_context=request_context,
            context_digest=context_digest,
            request_digest=request_digest.strip(),
            ranking_snapshot_digest=ranking.ranking_snapshot_digest.strip(),
            feature_snapshot_at=ranking.feature_snapshot_at.astimezone(timezone.utc),
            user_feature_snapshot=dict(ranking.user_feature_snapshot), items=tuple(items),
            created_at=created_at, expires_at=created_at + WINDOW_TTL,
        )

    def page(self, *, from_ordinal: int, limit: int) -> tuple[tuple[RankedRecommendationItem, ...], int | None]:
        if from_ordinal < 0 or limit <= 0 or limit > 100:
            raise ValueError("fromOrdinal and limit are outside the accepted range")
        page_items = self.items[from_ordinal : from_ordinal + limit]
        next_ordinal = from_ordinal + len(page_items)
        if next_ordinal >= len(self.items):
            next_ordinal = None
        return page_items, next_ordinal
