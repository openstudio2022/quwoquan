from __future__ import annotations

from ..api import (
    AssertionStatus,
    BusinessCaseRunner,
    CaseAssertion,
    CaseExecution,
    CaseExecutionContext,
    CaseRef,
)
from ..capabilities.chat_service import (
    DIRECT_CONVERSATION_WITH_MESSAGES,
    GROUP_CONVERSATION,
    DirectConversationResult,
    DirectConversationWithMessagesParams,
    GroupConversationParams,
    GroupConversationResult,
    MessageStatus,
)
from ..capabilities.common import ActorRole
from ..capabilities.user_service import (
    AUTHENTICATED_ACTORS,
    PERSONA_RELATIONSHIP,
    AuthenticatedActorsParams,
    MutualActorRelationship,
    RelationshipParams,
)
from .ids import AcceptanceCaseId


class ChatRecallCase(BusinessCaseRunner[DirectConversationResult]):
    result_type = DirectConversationResult

    @classmethod
    def execute(
        cls,
        value: DirectConversationResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        sender = context.actor(ActorRole.SENDER)
        executor = context.public_operations(DIRECT_CONVERSATION_WITH_MESSAGES.key.value)
        response = executor.call(
            "chat.message.ListMessages",
            actor=sender,
            step_id="business-list-messages",
            bindings={"conversationId": value.conversation.object_id},
            query={"limit": max(20, len(value.messages))},
        )
        rows = _items(response)
        by_id = {
            str(row.get("messageId") or row.get("id") or "").strip(): row
            for row in rows
        }
        recalled = tuple(
            item.message.object_id
            for item in value.messages
            if item.status is MessageStatus.RECALLED
        )
        expected_ids = {item.message.object_id for item in value.messages}
        recalled_visible = all(
            str(
                by_id.get(message_id, {}).get("status")
                or by_id.get(message_id, {}).get("messageStatus")
                or ""
            ).lower()
            == MessageStatus.RECALLED.value
            for message_id in recalled
        )
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "chat-message-reentry",
                    (
                        AssertionStatus.PASSED
                        if expected_ids.issubset(by_id)
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "chat-recalled-message-readback",
                    (
                        AssertionStatus.PASSED
                        if recalled and recalled_visible
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def chat_recall_case() -> CaseRef[DirectConversationResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER),
            mutual_relationships=(
                MutualActorRelationship(
                    source_role=ActorRole.SENDER,
                    target_role=ActorRole.RECEIVER,
                ),
            ),
        )
    )
    conversation = DIRECT_CONVERSATION_WITH_MESSAGES.bind(
        DirectConversationWithMessagesParams(
            actors=actors.output.whole(),
            sender_role=ActorRole.SENDER,
            receiver_role=ActorRole.RECEIVER,
            message_count=3,
            recalled_message_index=1,
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.CHAT_RECALL,
        request=conversation,
        runner_type=ChatRecallCase,
    )


class ChatGroupGovernanceCase(BusinessCaseRunner[GroupConversationResult]):
    result_type = GroupConversationResult

    @classmethod
    def execute(
        cls,
        value: GroupConversationResult,
        context: CaseExecutionContext,
    ) -> CaseExecution:
        owner = context.actor(value.owner_role)
        executor = context.public_operations(GROUP_CONVERSATION.key.value)
        home = executor.call(
            "chat.conversation.GetGroupHome",
            actor=owner,
            step_id="business-get-group-home",
            bindings={"conversationId": value.conversation.object_id},
        )
        observed_conversation_id = str(
            home.get("conversationId") or home.get("id") or ""
        ).strip()
        announcement_visible = (
            observed_conversation_id == value.conversation.object_id
            and str(home.get("announcement") or "") == value.announcement
        )
        members = executor.call(
            "chat.conversation_membership.ListMembers",
            actor=owner,
            step_id="business-list-group-members",
            bindings={"conversationId": value.conversation.object_id},
            query={"limit": 50},
        )
        role_by_user = {
            str(row.get("userId") or "").strip(): str(row.get("role") or "").strip()
            for row in _items(members)
        }
        expected_member_ids = {member.object_id for member in value.members}
        members_visible = expected_member_ids.issubset(role_by_user)
        # TransferOwnership 会让原 owner 失去 DissolveConversation cleanup 权限，
        # 故按契约事实退化为只读断言 owner/admin 治理角色可见。
        governance_visible = (
            role_by_user.get(value.admin.object_id) == "admin"
            and role_by_user.get(owner.account.object_id) == "owner"
        )
        return CaseExecution(
            assertions=(
                CaseAssertion(
                    "chat-group-home-announcement",
                    (
                        AssertionStatus.PASSED
                        if announcement_visible
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "chat-group-members-visible",
                    (
                        AssertionStatus.PASSED
                        if members_visible
                        else AssertionStatus.FAILED
                    ),
                ),
                CaseAssertion(
                    "chat-group-admin-governance-visible",
                    (
                        AssertionStatus.PASSED
                        if governance_visible
                        else AssertionStatus.FAILED
                    ),
                ),
            )
        )


def chat_group_governance_case() -> CaseRef[GroupConversationResult]:
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER, ActorRole.MEMBER),
        )
    )
    owner_and_admin_mutual = PERSONA_RELATIONSHIP.bind(
        RelationshipParams(
            actors=actors.output.whole(),
            source_role=ActorRole.SENDER,
            target_role=ActorRole.RECEIVER,
            mutual=True,
        )
    )
    owner_and_member_mutual = PERSONA_RELATIONSHIP.bind(
        RelationshipParams(
            actors=actors.output.whole(),
            source_role=ActorRole.SENDER,
            target_role=ActorRole.MEMBER,
            mutual=True,
        )
    )
    conversation = GROUP_CONVERSATION.bind(
        GroupConversationParams(
            actors=actors.output.whole(),
            mutual_follow_gates=(
                owner_and_admin_mutual.output.directions,
                owner_and_member_mutual.output.directions,
            ),
            owner_role=ActorRole.SENDER,
            member_roles=(ActorRole.RECEIVER, ActorRole.MEMBER),
            admin_role=ActorRole.RECEIVER,
            announcement="验收群公告：按用例隔离的群治理事实。",
        )
    )
    return CaseRef(
        case_id=AcceptanceCaseId.CHAT_GROUP_GOVERNANCE,
        request=conversation,
        runner_type=ChatGroupGovernanceCase,
    )


def _items(response: object) -> tuple[dict[str, object], ...]:
    if not isinstance(response, dict):
        return ()
    rows = response.get("items")
    if not isinstance(rows, list):
        return ()
    return tuple(row for row in rows if isinstance(row, dict))


__all__ = (
    "ChatGroupGovernanceCase",
    "ChatRecallCase",
    "chat_group_governance_case",
    "chat_recall_case",
)
