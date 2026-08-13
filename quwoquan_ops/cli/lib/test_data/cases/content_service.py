from __future__ import annotations

from ..api import (
    AssertionStatus,
    BusinessCaseRunner,
    CaseAssertion,
    CaseExecution,
    CaseExecutionContext,
    CaseRef,
)
from ..capabilities.common import ActorRole
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
from ..capabilities.user_service import AUTHENTICATED_ACTORS, AuthenticatedActorsParams
from .ids import AcceptanceCaseId


class ContentCommentsCase(BusinessCaseRunner[PostCommentsResult]):
    result_type = PostCommentsResult

    @classmethod
    def execute(
        cls,
        value: PostCommentsResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        actor = context.actor(ActorRole.PRIMARY)
        executor = context.public_operations(POST_COMMENTS.key.value)
        response = executor.call(
            "content.comment.ListComments",
            actor=actor,
            step_id="business-list-comments",
            bindings={"postId": value.post.object_id},
            query={"limit": 100, "sort": "latest"},
        )
        observed = {
            str(item.get("commentId") or item.get("id") or "").strip()
            for item in _items(response)
        }
        expected = {comment.object_id for comment in value.comments}
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "content-comment-identities",
                    (
                        AssertionStatus.PASSED
                        if expected.issubset(observed)
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "content-comment-count",
                    (
                        AssertionStatus.PASSED
                        if len(expected) == 2
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def content_comments_case() -> CaseRef[PostCommentsResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(roles=(ActorRole.PRIMARY,))
    )
    release = ACTIVE_REFERENCE_RELEASE.bind(ActiveReleaseParams(minimum_posts=1))
    comments = POST_COMMENTS.bind(
        PostCommentsParams(
            release=release.output.whole(),
            actors=actors.output.whole(),
            author_role=ActorRole.PRIMARY,
            comment_count=2,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.CONTENT_COMMENTS,
        request=comments,
        runner_type=ContentCommentsCase,
    )


class ContentReactionCase(BusinessCaseRunner[PostReactionResult]):
    result_type = PostReactionResult

    @classmethod
    def execute(
        cls,
        value: PostReactionResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        reactor = context.actor(value.reactor_role)
        executor = context.public_operations(POST_REACTIONS.key.value)
        state = executor.call(
            "content.content_reaction.GetContentReactionState",
            actor=reactor,
            step_id="business-get-reaction-state",
            bindings={"postId": value.post.object_id},
        )
        observed_post = str(state.get("postId") or "").strip()
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "reaction-post-readback",
                    (
                        AssertionStatus.PASSED
                        if observed_post == value.post.object_id
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "reaction-liked-state",
                    (
                        AssertionStatus.PASSED
                        if state.get("liked") is True
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def content_reaction_case() -> CaseRef[PostReactionResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(roles=(ActorRole.PRIMARY,))
    )
    release = ACTIVE_REFERENCE_RELEASE.bind(ActiveReleaseParams(minimum_posts=1))
    reaction = POST_REACTIONS.bind(
        PostReactionParams(
            release=release.output.whole(),
            actors=actors.output.whole(),
            reactor_role=ActorRole.PRIMARY,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.CONTENT_REACTION,
        request=reaction,
        runner_type=ContentReactionCase,
    )


class ContentFootprintCase(BusinessCaseRunner[PostFootprintResult]):
    result_type = PostFootprintResult

    @classmethod
    def execute(
        cls,
        value: PostFootprintResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        viewer = context.actor(value.viewer_role)
        executor = context.public_operations(POST_FOOTPRINT.key.value)
        page = executor.call(
            "content.post.GetMyFootprint",
            actor=viewer,
            step_id="business-get-my-footprint",
            query={"type": "viewed", "limit": 50},
        )
        rows = _items(page)
        observed_posts = {
            str(row.get("postId") or "").strip() for row in rows
        }
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "footprint-not-empty",
                    (
                        AssertionStatus.PASSED
                        if rows
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "footprint-contains-viewed-post",
                    (
                        AssertionStatus.PASSED
                        if value.post.object_id in observed_posts
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def content_footprint_case() -> CaseRef[PostFootprintResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(roles=(ActorRole.PRIMARY,))
    )
    release = ACTIVE_REFERENCE_RELEASE.bind(ActiveReleaseParams(minimum_posts=1))
    footprint = POST_FOOTPRINT.bind(
        PostFootprintParams(
            release=release.output.whole(),
            actors=actors.output.whole(),
            viewer_role=ActorRole.PRIMARY,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.CONTENT_FOOTPRINT,
        request=footprint,
        runner_type=ContentFootprintCase,
    )


__all__ = (
    "ContentCommentsCase",
    "ContentFootprintCase",
    "ContentReactionCase",
    "content_comments_case",
    "content_footprint_case",
    "content_reaction_case",
)


def _items(response: object) -> tuple[dict[str, object], ...]:
    if not isinstance(response, dict):
        return ()
    rows = response.get("items")
    if not isinstance(rows, list):
        return ()
    return tuple(row for row in rows if isinstance(row, dict))
