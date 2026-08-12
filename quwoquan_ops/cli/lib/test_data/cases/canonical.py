"""Canonical typed cases for the seven acceptance-data Providers.

Every factory constructs only the request graph needed by that business case.
There is intentionally no string-keyed registry: callers import and select
factory functions directly at the test site.
"""

from __future__ import annotations

from enum import StrEnum

from ..api import (
    AssertionStatus,
    BusinessCaseRunner,
    CaseAssertion,
    CaseExecution,
    CaseExecutionContext,
    CaseRef,
)
from ..capabilities.assistant_service import (
    ASSISTANT_PROMPT_RUN,
    AssistantRunParams,
    AssistantRunResult,
)
from ..capabilities.chat_service import (
    DIRECT_CONVERSATION_WITH_MESSAGES,
    DirectConversationResult,
    DirectConversationWithMessagesParams,
    MessageStatus,
)
from ..capabilities.circle_service import (
    CIRCLE_WITH_MEMBERS,
    CircleWithMembersParams,
    CircleWithMembersResult,
)
from ..capabilities.common import ActorRole
from ..capabilities.content_service import (
    ACTIVE_REFERENCE_RELEASE,
    POST_COMMENTS,
    ActiveReleaseParams,
    PostCommentsParams,
    PostCommentsResult,
)
from ..capabilities.notification_service import (
    NOTIFICATION_DELIVERY,
    NotificationDeliveryParams,
    NotificationDeliveryResult,
    NotificationMessageType,
)
from ..capabilities.rtc_service import (
    COMPLETED_CALL,
    CompletedCallParams,
    CompletedCallResult,
)
from ..capabilities.user_service import (
    AUTHENTICATED_ACTORS,
    PERSONA_RELATIONSHIP,
    AuthenticatedActorsParams,
    RelationshipParams,
    RelationshipResult,
)


class AcceptanceCaseId(StrEnum):
    USER_RELATIONSHIP = "user-relationship"
    CONTENT_COMMENTS = "content-comments"
    CIRCLE_MEMBERSHIP = "circle-membership"
    CHAT_RECALL = "chat-recall"
    ASSISTANT_PROMPT = "assistant-prompt"
    NOTIFICATION_DELIVERY = "notification-delivery"
    RTC_COMPLETED_CALL = "rtc-completed-call"


def _assert(assertion_id: str, passed: bool) -> CaseAssertion:
    return CaseAssertion(
        assertion_id=assertion_id,
        status=AssertionStatus.PASSED if passed else AssertionStatus.FAILED,
    )


class UserRelationshipCase(BusinessCaseRunner[RelationshipResult]):
    result_type = RelationshipResult

    @classmethod
    def execute(
        cls,
        value: RelationshipResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        del context
        return CaseExecution(
            assertions=(
                _assert("relationship-directions", value.directions == 2),
                _assert(
                    "relationship-roles",
                    value.source_role is ActorRole.SENDER
                    and value.target_role is ActorRole.RECEIVER,
                ),
            )
        )


class ContentCommentsCase(BusinessCaseRunner[PostCommentsResult]):
    result_type = PostCommentsResult

    @classmethod
    def execute(
        cls,
        value: PostCommentsResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        del context
        return CaseExecution(
            assertions=(
                _assert("content-post-reference", value.post.object_type == "Post"),
                _assert("content-comment-count", len(value.comments) == 2),
                _assert(
                    "content-comment-identities",
                    len({item.object_id for item in value.comments}) == 2,
                ),
            )
        )


class CircleMembershipCase(BusinessCaseRunner[CircleWithMembersResult]):
    result_type = CircleWithMembersResult

    @classmethod
    def execute(
        cls,
        value: CircleWithMembersResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        del context
        return CaseExecution(
            assertions=(
                _assert("circle-reference", value.circle.object_type == "Circle"),
                _assert("circle-membership-count", len(value.memberships) == 1),
            )
        )


class ChatRecallCase(BusinessCaseRunner[DirectConversationResult]):
    result_type = DirectConversationResult

    @classmethod
    def execute(
        cls,
        value: DirectConversationResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        del context
        return CaseExecution(
            assertions=(
                _assert(
                    "chat-conversation-reference",
                    value.conversation.object_type == "Conversation",
                ),
                _assert("chat-message-count", len(value.messages) == 3),
                _assert(
                    "chat-recalled-message",
                    value.messages[1].status is MessageStatus.RECALLED,
                ),
            )
        )


class AssistantPromptCase(BusinessCaseRunner[AssistantRunResult]):
    result_type = AssistantRunResult

    @classmethod
    def execute(
        cls,
        value: AssistantRunResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        del context
        return CaseExecution(
            assertions=(
                _assert("assistant-session", value.session.object_type == "AssistantSession"),
                _assert("assistant-run", value.run.object_type == "AssistantRun"),
            )
        )


class NotificationDeliveryCase(BusinessCaseRunner[NotificationDeliveryResult]):
    result_type = NotificationDeliveryResult

    @classmethod
    def execute(
        cls,
        value: NotificationDeliveryResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        del context
        return CaseExecution(
            assertions=(
                _assert(
                    "notification-reference",
                    value.notification.object_type == "Notification",
                ),
                _assert("notification-delivered", value.delivered),
            )
        )


class RtcCompletedCallCase(BusinessCaseRunner[CompletedCallResult]):
    result_type = CompletedCallResult

    @classmethod
    def execute(
        cls,
        value: CompletedCallResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        del context
        return CaseExecution(
            assertions=(
                _assert("rtc-call-reference", value.call.object_type == "CallSession"),
                _assert("rtc-final-state", value.final_state == "ended"),
            )
        )


def _two_actors():
    return AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER),
        )
    )


def _conversation(*, message_count: int = 3, recalled_index: int | None = 1):
    actors = _two_actors()
    conversation = DIRECT_CONVERSATION_WITH_MESSAGES.bind(
        DirectConversationWithMessagesParams(
            actors=actors.output.whole(),
            sender_role=ActorRole.SENDER,
            receiver_role=ActorRole.RECEIVER,
            message_count=message_count,
            recalled_message_index=recalled_index,
        )
    )
    return actors, conversation


def user_relationship_case() -> CaseRef[RelationshipResult]:
    actors = _two_actors()
    relationship = PERSONA_RELATIONSHIP.bind(
        RelationshipParams(
            actors=actors.output.whole(),
            source_role=ActorRole.SENDER,
            target_role=ActorRole.RECEIVER,
            mutual=True,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.USER_RELATIONSHIP,
        request=relationship,
        runner_type=UserRelationshipCase,
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


def circle_membership_case() -> CaseRef[CircleWithMembersResult]:
    actors = _two_actors()
    circle = CIRCLE_WITH_MEMBERS.bind(
        CircleWithMembersParams(
            actors=actors.output.whole(),
            owner_role=ActorRole.SENDER,
            member_roles=(ActorRole.RECEIVER,),
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.CIRCLE_MEMBERSHIP,
        request=circle,
        runner_type=CircleMembershipCase,
    )


def chat_recall_case() -> CaseRef[DirectConversationResult]:
    _actors, conversation = _conversation()
    return CaseRef(
        case_id=AcceptanceCaseId.CHAT_RECALL,
        request=conversation,
        runner_type=ChatRecallCase,
    )


def assistant_prompt_case() -> CaseRef[AssistantRunResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(roles=(ActorRole.SENDER,))
    )
    run = ASSISTANT_PROMPT_RUN.bind(
        AssistantRunParams(
            actors=actors.output.whole(),
            sender_role=ActorRole.SENDER,
            prompt="请返回用于验收的简短确认。",
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.ASSISTANT_PROMPT,
        request=run,
        runner_type=AssistantPromptCase,
    )


def notification_delivery_case() -> CaseRef[NotificationDeliveryResult]:
    actors, conversation = _conversation(message_count=1, recalled_index=None)
    delivery = NOTIFICATION_DELIVERY.bind(
        NotificationDeliveryParams(
            actors=actors.output.whole(),
            source=conversation.output.delivery_source,
            recipient_role=ActorRole.RECEIVER,
            message_type=NotificationMessageType.CHAT,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.NOTIFICATION_DELIVERY,
        request=delivery,
        runner_type=NotificationDeliveryCase,
    )


def rtc_completed_call_case() -> CaseRef[CompletedCallResult]:
    actors, conversation = _conversation(message_count=1, recalled_index=None)
    call = COMPLETED_CALL.bind(
        CompletedCallParams(
            actors=actors.output.whole(),
            conversation=conversation.output.conversation,
            caller_role=ActorRole.SENDER,
            callee_role=ActorRole.RECEIVER,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.RTC_COMPLETED_CALL,
        request=call,
        runner_type=RtcCompletedCallCase,
    )


def canonical_acceptance_suite() -> tuple[CaseRef[object], ...]:
    """Return the governed cross-domain release Journey set.

    This is one typed composition root, not a string-keyed case or capability
    registry.  Focused test runners continue to import only the concrete case
    factories they select.
    """

    return (
        user_relationship_case(),
        content_comments_case(),
        circle_membership_case(),
        chat_recall_case(),
        assistant_prompt_case(),
        notification_delivery_case(),
        rtc_completed_call_case(),
    )


__all__ = (
    "AcceptanceCaseId",
    "AssistantPromptCase",
    "ChatRecallCase",
    "CircleMembershipCase",
    "ContentCommentsCase",
    "NotificationDeliveryCase",
    "RtcCompletedCallCase",
    "UserRelationshipCase",
    "assistant_prompt_case",
    "canonical_acceptance_suite",
    "chat_recall_case",
    "circle_membership_case",
    "content_comments_case",
    "notification_delivery_case",
    "rtc_completed_call_case",
    "user_relationship_case",
)
