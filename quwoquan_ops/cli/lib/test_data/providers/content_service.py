from __future__ import annotations

from typing import Any

from ..api import BusinessObjectRef, CapabilityRequest
from ..capabilities.common import AcceptanceActorSet, ImmutableReleaseHandle
from ..capabilities.content_service import (
    ACTIVE_REFERENCE_RELEASE,
    POST_COMMENTS,
    ActiveReleaseParams,
    PostCommentsParams,
    PostCommentsResult,
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


class ContentAcceptanceDataProvider:
    def describe(self) -> tuple[CapabilityDefinition, ...]:
        return (_RELEASE, _COMMENTS)

    def plan(
        self,
        context: TestDataContext,
        request: CapabilityRequest[Any, Any],
        resolved_params: object,
    ) -> ProviderPlan:
        definition = _RELEASE if request.capability == ACTIVE_REFERENCE_RELEASE else _COMMENTS
        return plan_for(definition, request, resolved_params)

    def provision(
        self,
        context: TestDataContext,
        plan: ProviderPlan,
    ) -> ProvisionedCapability:
        if isinstance(plan.resolved_params, ActiveReleaseParams):
            candidate = context.candidate
            if len(candidate.release_post_ids) < plan.resolved_params.minimum_posts:
                raise RuntimeError("active immutable release has too few posts")
            return ProvisionedCapability(
                value=ImmutableReleaseHandle(
                    release_id=candidate.release_id,
                    release_digest=candidate.release_digest,
                    import_run_id=candidate.import_run_id,
                    posts=tuple(
                        BusinessObjectRef("Post", post_id)
                        for post_id in candidate.release_post_ids
                    ),
                )
            )
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

    def readback(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> ReadbackResult:
        if isinstance(provisioned.value, ImmutableReleaseHandle):
            return ReadbackResult(
                passed=bool(provisioned.value.posts),
                details={"postCount": len(provisioned.value.posts)},
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
