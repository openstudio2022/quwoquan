from __future__ import annotations

import datetime as dt
from typing import Any

from ..api import BusinessObjectRef, CapabilityRequest
from ..capabilities.common import AcceptanceActorSet, ImmutableReleaseHandle
from ..capabilities.content_service import (
    ACTIVE_REFERENCE_RELEASE,
    POST_COMMENTS,
    POST_FOOTPRINT,
    POST_REACTIONS,
    ActiveReleaseParams,
    PostCommentsParams,
    PostCommentsResult,
    PostFootprintParams,
    PostFootprintResult,
    PostReactionParams,
    PostReactionResult,
)
from ..model import (
    CapabilityDefinition,
    CleanupResult,
    PartialProvisioningError,
    ProviderPlan,
    ProvisionedCapability,
    ReadbackResult,
    TestDataContext,
)
from ..operations import PublicOperationExecutor, TestDataRuntime
from .support import items, plan_for, required_id


_RELEASE = CapabilityDefinition(
    capability=ACTIVE_REFERENCE_RELEASE,
    operations=(),
)
_COMMENTS = CapabilityDefinition(
    capability=POST_COMMENTS,
    operations=(
        "content.comment.CreateComment",
        "content.comment.ListComments",
        "content.comment.DeleteComment",
    ),
)
_REACTIONS = CapabilityDefinition(
    capability=POST_REACTIONS,
    operations=(
        "content.content_reaction.LikePost",
        "content.content_reaction.GetContentReactionState",
        "content.content_reaction.UnlikePost",
    ),
)
_FOOTPRINT = CapabilityDefinition(
    capability=POST_FOOTPRINT,
    operations=(
        "content.content_behavior_fact.ReportBehaviors",
        "content.post.GetMyFootprint",
    ),
)


class ContentAcceptanceDataProvider:
    def describe(self) -> tuple[CapabilityDefinition, ...]:
        return (_RELEASE, _COMMENTS, _REACTIONS, _FOOTPRINT)

    def plan(
        self,
        context: TestDataContext,
        request: CapabilityRequest[Any, Any],
        resolved_params: object,
    ) -> ProviderPlan:
        if request.capability == ACTIVE_REFERENCE_RELEASE:
            definition = _RELEASE
        elif request.capability == POST_REACTIONS:
            definition = _REACTIONS
        elif request.capability == POST_FOOTPRINT:
            definition = _FOOTPRINT
        else:
            definition = _COMMENTS
        return plan_for(definition, request, resolved_params)

    def provision(
        self,
        context: TestDataContext,
        plan: ProviderPlan,
    ) -> ProvisionedCapability:
        if isinstance(plan.resolved_params, ActiveReleaseParams):
            candidate = context.candidate
            if len(candidate.release_posts) < plan.resolved_params.minimum_posts:
                raise RuntimeError("active immutable release has too few posts")
            return ProvisionedCapability(
                value=ImmutableReleaseHandle(
                    release_id=candidate.release_id,
                    release_digest=candidate.release_digest,
                    import_run_id=candidate.import_run_id,
                    readiness_phase=candidate.readiness_phase,
                    readiness_receipt_digest=candidate.readiness_receipt_digest,
                    posts=candidate.release_posts,
                    creators=candidate.release_creators,
                    entities=candidate.release_entities,
                    homepages=candidate.release_homepages,
                    tags=candidate.release_tags,
                    media_assets=candidate.release_media_assets,
                )
            )
        if isinstance(plan.resolved_params, PostReactionParams):
            return self._provision_post_reaction(context, plan.resolved_params)
        if isinstance(plan.resolved_params, PostFootprintParams):
            return self._provision_post_footprint(context, plan.resolved_params)
        if not isinstance(plan.resolved_params, PostCommentsParams):
            raise TypeError("Content Provider received invalid resolved params")
        params = plan.resolved_params
        if not isinstance(params.release, ImmutableReleaseHandle):
            raise TypeError("release dependency was not resolved")
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        actor = params.actors.require(params.author_role)
        post = params.release.posts[0]
        executor = _executor(context, POST_COMMENTS.key.value)
        comments: list[BusinessObjectRef] = []
        try:
            for index in range(params.comment_count):
                response = executor.call(
                    "content.comment.CreateComment",
                    actor=actor,
                    step_id=f"comment-{index:03d}",
                    bindings={"postId": post.object_id},
                    body={
                        "content": f"验收评论 {index + 1}",
                        "replyToCommentId": None,
                        "attachmentMediaIds": [],
                        "mentions": [],
                    },
                )
                comments.append(
                    BusinessObjectRef(
                        "Comment",
                        required_id(response, "commentId", "id"),
                    )
                )
            for index in range(params.replies_per_comment):
                response = executor.call(
                    "content.comment.CreateComment",
                    actor=actor,
                    step_id=f"reply-{index:03d}",
                    bindings={"postId": post.object_id},
                    body={
                        "content": f"验收回复 {index + 1}",
                        "replyToCommentId": comments[0].object_id,
                        "attachmentMediaIds": [],
                        "mentions": [],
                    },
                )
                comments.append(
                    BusinessObjectRef(
                        "Comment",
                        required_id(response, "commentId", "id"),
                    )
                )
        except BaseException as error:
            if comments:
                raise PartialProvisioningError(
                    "Content Provider stopped after creating comments",
                    provisioned=ProvisionedCapability(
                        value=PostCommentsResult(
                            post=post,
                            comments=tuple(comments),
                        ),
                        cleanup_handle=tuple(comments),
                        cleanup_context=(actor, post),
                        operation_count=executor.operation_count,
                    ),
                ) from error
            raise
        return ProvisionedCapability(
            value=PostCommentsResult(post=post, comments=tuple(comments)),
            cleanup_handle=tuple(comments),
            cleanup_context=(actor, post),
            operation_count=executor.operation_count,
        )

    def _provision_post_reaction(
        self,
        context: TestDataContext,
        params: PostReactionParams,
    ) -> ProvisionedCapability:
        if not isinstance(params.release, ImmutableReleaseHandle):
            raise TypeError("release dependency was not resolved")
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        reactor = params.actors.require(params.reactor_role)
        post = params.release.posts[0]
        executor = _executor(context, POST_REACTIONS.key.value)
        executor.call(
            "content.content_reaction.LikePost",
            actor=reactor,
            step_id="like-post",
            bindings={"postId": post.object_id},
        )
        return ProvisionedCapability(
            value=PostReactionResult(post=post, reactor_role=params.reactor_role),
            cleanup_handle=(post,),
            cleanup_context=reactor,
            operation_count=executor.operation_count,
        )

    def _provision_post_footprint(
        self,
        context: TestDataContext,
        params: PostFootprintParams,
    ) -> ProvisionedCapability:
        if not isinstance(params.release, ImmutableReleaseHandle):
            raise TypeError("release dependency was not resolved")
        if not isinstance(params.actors, AcceptanceActorSet):
            raise TypeError("actors dependency was not resolved")
        viewer = params.actors.require(params.viewer_role)
        post = params.release.posts[0]
        executor = _executor(context, POST_FOOTPRINT.key.value)
        occurred_at = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
        executor.call(
            "content.content_behavior_fact.ReportBehaviors",
            actor=viewer,
            step_id="report-view-behavior",
            body={
                "events": [
                    {
                        "clientEventId": (
                            f"footprint-{context.test_data_instance_id}-000"
                        ),
                        "occurredAt": occurred_at,
                        "contentId": post.object_id,
                        "action": "click",
                        "contentType": "post",
                        "sourceSurface": "acceptance",
                    }
                ]
            },
        )
        return ProvisionedCapability(
            value=PostFootprintResult(post=post, viewer_role=params.viewer_role),
            cleanup_handle=(post,),
            cleanup_context=viewer,
            operation_count=executor.operation_count,
        )

    def readback(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> ReadbackResult:
        if isinstance(provisioned.value, PostFootprintResult):
            executor = _executor(context, POST_FOOTPRINT.key.value + ".readback")
            page = executor.call(
                "content.post.GetMyFootprint",
                actor=provisioned.cleanup_context,
                step_id="get-my-footprint",
                query={"type": "viewed", "limit": 50},
            )
            observed = {
                str(item.get("postId") or "").strip() for item in items(page)
            }
            return ReadbackResult(
                passed=provisioned.value.post.object_id in observed,
                operation_count=executor.operation_count,
                details={"footprintEntries": len(observed)},
            )
        if isinstance(provisioned.value, PostReactionResult):
            executor = _executor(context, POST_REACTIONS.key.value + ".readback")
            state = executor.call(
                "content.content_reaction.GetContentReactionState",
                actor=provisioned.cleanup_context,
                step_id="get-reaction-state",
                bindings={"postId": provisioned.value.post.object_id},
            )
            observed_post = str(state.get("postId") or "").strip()
            return ReadbackResult(
                passed=(
                    observed_post == provisioned.value.post.object_id
                    and state.get("liked") is True
                ),
                operation_count=executor.operation_count,
                details={"liked": bool(state.get("liked"))},
            )
        if isinstance(provisioned.value, ImmutableReleaseHandle):
            closure = {
                "posts": len(provisioned.value.posts),
                "creators": len(provisioned.value.creators),
                "entities": len(provisioned.value.entities),
                "homepages": len(provisioned.value.homepages),
                "tags": len(provisioned.value.tags),
                "mediaAssets": len(provisioned.value.media_assets),
            }
            return ReadbackResult(
                passed=all(closure.values()),
                details={
                    "releaseId": provisioned.value.release_id,
                    "readinessPhase": provisioned.value.readiness_phase,
                    "releaseClosure": closure,
                },
            )
        if not isinstance(provisioned.value, PostCommentsResult):
            return ReadbackResult(passed=False)
        actor, post = provisioned.cleanup_context  # type: ignore[misc]
        executor = _executor(context, POST_COMMENTS.key.value + ".readback")
        listed = executor.call(
            "content.comment.ListComments",
            actor=actor,
            step_id="list-comments",
            bindings={"postId": post.object_id},
            query={"limit": 100, "sort": "latest"},
        )
        observed = {
            str(item.get("commentId") or item.get("id") or "").strip()
            for item in items(listed)
        }
        expected = {comment.object_id for comment in provisioned.value.comments}
        return ReadbackResult(
            passed=expected.issubset(observed),
            operation_count=executor.operation_count,
            details={"expectedComments": len(expected), "observedComments": len(observed)},
        )

    def cleanup(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> CleanupResult:
        if isinstance(provisioned.value, PostFootprintResult):
            # ContentBehaviorFact 是 append-only 事实，无公开删除 command；
            # 足迹仅本人可见，viewer 是按 CaseResult 隔离的一次性 persona，
            # 不产生跨 case 可见残留。
            return CleanupResult(state="released")
        if isinstance(provisioned.value, PostReactionResult):
            executor = _executor(context, POST_REACTIONS.key.value + ".cleanup")
            executor.call(
                "content.content_reaction.UnlikePost",
                actor=provisioned.cleanup_context,
                step_id="unlike-post",
                bindings={"postId": provisioned.value.post.object_id},
            )
            return CleanupResult(
                state="released",
                operation_count=executor.operation_count,
            )
        if isinstance(provisioned.value, ImmutableReleaseHandle):
            return CleanupResult(state="released")
        if not isinstance(provisioned.value, PostCommentsResult):
            return CleanupResult(state="quarantined")
        actor, post = provisioned.cleanup_context  # type: ignore[misc]
        executor = _executor(context, POST_COMMENTS.key.value + ".cleanup")
        for index, comment in enumerate(reversed(provisioned.value.comments)):
            executor.call(
                "content.comment.DeleteComment",
                actor=actor,
                step_id=f"delete-comment-{index:03d}",
                bindings={
                    "postId": post.object_id,
                    "commentId": comment.object_id,
                },
            )
        return CleanupResult(state="released", operation_count=executor.operation_count)


def _executor(context: TestDataContext, capability_key: str) -> PublicOperationExecutor:
    if not isinstance(context.runtime, TestDataRuntime):
        raise TypeError("TestData runtime is unavailable")
    return PublicOperationExecutor(
        base_url=context.base_url,
        target=context.candidate.target,
        test_data_instance_id=context.test_data_instance_id,
        capability_key=capability_key,
        runtime=context.runtime,
    )


def build_provider() -> ContentAcceptanceDataProvider:
    return ContentAcceptanceDataProvider()
